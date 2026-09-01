#!/usr/bin/env python3
"""Layer B optional rewrite hook for statistical (token-sampling) watermarks.

Backends:
  print-prompt       — emit prompt only (default; CI-safe, no model)
  ollama             — POST to Ollama /api/chat
  openai-compatible  — POST to OpenAI-style /v1/chat/completions

Env (optional):
  WATERMARKS_REWRITE_BACKEND
  WATERMARKS_REWRITE_BASE_URL
  WATERMARKS_REWRITE_MODEL
  WATERMARKS_REWRITE_API_KEY      (env-only; never pass keys on argv)
  WATERMARKS_REWRITE_ALLOW_REMOTE (set to 1 to allow non-loopback endpoints)

Security notes:
  - Only http(s) endpoints are accepted; redirects are refused outright so an
    Authorization header (API key) can never be re-sent to an unvalidated host.
  - Non-loopback endpoints are denied unless WATERMARKS_REWRITE_ALLOW_REMOTE=1
    (or --allow-remote) is set explicitly. "Loopback" means the resolved
    addresses — the full 127.0.0.0/8 range, ::1, or a hostname every address
    of which is loopback — never the bare hostname string (DNS-rebinding
    defense). The connection is then pinned to the validated address, so the
    name cannot rebind between the check and the connect.
  - Responses are capped (WATERMARKS_REWRITE_MAX_RESPONSE_BYTES, 64 MiB
    default) so a hostile endpoint cannot exhaust memory.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))

import net_guard  # noqa: E402
from common import cleaned_path, eprint, read_text_input, write_text_output  # noqa: E402
from text_unicode import clean_text  # noqa: E402

MAX_RESPONSE_BYTES = int(
    os.environ.get("WATERMARKS_REWRITE_MAX_RESPONSE_BYTES", str(64 << 20))
)


def run_synthid_text_scorer(text: str) -> dict | None:
    """Score text with the optional SynthID-Text scorer (subprocess, stdin).

    Returns None when the scorer is not installed (exit 3), so the default
    "no score" behavior stays silent — same contract as the image scorer.
    """
    script = Path(__file__).resolve().parent / "score_synthid_text.py"
    try:
        r = subprocess.run(
            [sys.executable, str(script), "-", "--json"],
            input=text,
            capture_output=True,
            text=True,
            timeout=300,
        )
    except Exception as e:
        return {"available": False, "error": str(e)}
    if r.returncode == 3:
        return None
    if r.returncode != 0:
        return {"available": False, "error": (r.stderr or "").strip()[:2000]}
    try:
        return json.loads(r.stdout or "{}")
    except json.JSONDecodeError as e:
        return {"available": False, "error": f"bad scorer JSON: {e}"}

PROMPTS = {
    "paraphrase": (
        "Rewrite the following text so that it uses substantially different wording at "
        "the token level. Change clause order, connectors, and transition words; vary "
        "sentence boundaries and length; and replace both content words and function "
        "words where meaning allows. Preserve all facts, numbers, names, and technical "
        "identifiers. Do not add or remove claims. Output only the rewritten text.\n\n---\n{TEXT}"
    ),
    "humanize": (
        "Rewrite the following text so it reads as if a human wrote it from scratch. "
        "Vary sentence rhythm and length, replace formulaic AI-style transitions and "
        "filler with concrete natural phrasing, and use plain, varied wording. Preserve "
        "all facts, numbers, names, and technical identifiers. Do not add or remove "
        "claims. Output only the rewritten text.\n\n---\n{TEXT}"
    ),
    "code": (
        "Rewrite the natural-language parts of this code — comments, docstrings, and "
        "string literals — using different wording. Rename local variables, function "
        "parameters, and private helper names to semantically equivalent names. Preserve "
        "program behavior, public API names, and all values that affect output. Output "
        "only the rewritten code.\n\n---\n{TEXT}"
    ),
    "backtranslate_out": (
        "Translate the following text to {LANG}. Output only the translation.\n\n---\n{TEXT}"
    ),
    "backtranslate_back": (
        "Translate the following text to {ORIGINAL_LANG}. Preserve meaning; use natural "
        "phrasing. Output only the translation.\n\n---\n{TEXT}"
    ),
    "structural_outline": (
        "Extract a bullet outline of all claims and structure from the text "
        "(no full sentences). Output only the outline.\n\n---\n{TEXT}"
    ),
    "structural_write": (
        "Write a complete document from this outline in natural, varied human prose. "
        "Avoid formulaic transitions. Do not omit any bullet. Output only the document."
        "\n\n---\n{TEXT}"
    ),
}


def _tokens(text: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9]+", text.lower())


def _bigrams(tokens: list[str]) -> set[tuple[str, str]]:
    return set(zip(tokens, tokens[1:]))


def _lexical_divergence(original: str, candidate: str) -> float:
    """Bigram Jaccard distance: 0.0 identical, 1.0 fully different."""
    a = _tokens(original)
    b = _tokens(candidate)
    if not a and not b:
        return 0.0
    if not a or not b:
        return 1.0
    ba = _bigrams(a)
    bb = _bigrams(b)
    union = ba | bb
    if not union:
        return 0.0
    return 1.0 - len(ba & bb) / len(union)


def _select_candidate(original: str, candidates: list[str]) -> tuple[str, list[float]]:
    """Pick the most lexically diverged rewrite, gently guarding extreme length drift."""
    scores: list[float] = []
    for cand in candidates:
        score = _lexical_divergence(original, cand)
        if original:
            ratio = len(cand) / len(original)
            if ratio > 2.0 or ratio < 0.5:
                score -= 0.15
        scores.append(score)
    best_idx = max(range(len(candidates)), key=lambda i: scores[i])
    return candidates[best_idx], scores


def _env(name: str, default: str | None = None) -> str | None:
    v = os.environ.get(name)
    if v is None or v == "":
        return default
    return v


def _flag_env(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def _check_remote(base_url: str, allow_remote: bool) -> None:
    """Enforce the rewrite-endpoint allowlist against *resolved* addresses.

    Default-deny: only loopback endpoints are accepted. "Loopback" is the
    full 127.0.0.0/8 range (not just 127.0.0.1), ::1, or a hostname whose
    every resolved address is loopback — checking the hostname string alone
    left a DNS-rebinding surface. Anything else requires an explicit opt-in
    (--allow-remote / WATERMARKS_REWRITE_ALLOW_REMOTE=1), and non-http(s)
    schemes (e.g. file://) are always refused.
    """
    try:
        _, is_remote = net_guard.enforce_loopback(base_url, allow_remote=allow_remote)
    except ValueError as e:
        raise SystemExit(f"error: {e}. Set WATERMARKS_REWRITE_ALLOW_REMOTE=1 or pass --allow-remote to override.")
    except OSError as e:
        raise SystemExit(f"error: {e}; refusing to send content to an unresolvable host.")
    if is_remote:
        eprint(
            f"warning: rewrite base URL host is '{urlparse(base_url).hostname}' "
            "(not loopback); content will leave this machine"
        )


def build_prompt(strength: str, text: str, *, lang: str, original_lang: str) -> str:
    if strength == "paraphrase":
        return PROMPTS["paraphrase"].format(TEXT=text)
    if strength == "humanize":
        return PROMPTS["humanize"].format(TEXT=text)
    if strength == "code":
        return PROMPTS["code"].format(TEXT=text)
    if strength == "backtranslate":
        # single combined instruction for print-prompt / one-shot backends
        return (
            f"Translate the text to {lang}, then translate that result back to "
            f"{original_lang}. Preserve all facts, numbers, and names. "
            f"Output only the final {original_lang} text.\n\n---\n{text}"
        )
    if strength == "structural":
        return (
            "First extract a bullet outline of all claims (no full sentences). "
            "Then write a complete document from that outline in natural, varied human "
            "prose without omitting any bullet. Output only the final document.\n\n---\n"
            f"{text}"
        )
    raise ValueError(f"unknown strength: {strength}")


def _http_json(
    url: str,
    payload: dict,
    headers: dict[str, str],
    timeout: float,
    allow_remote: bool = False,
) -> dict:
    if urlparse(url).scheme not in ("http", "https"):
        raise ValueError(f"refusing non-http(s) rewrite endpoint: {url}")
    # Re-validate at connect time and pin the connection to the validated
    # address: _check_remote() already gated the policy, but resolving twice
    # (once to check, once inside urllib) would reopen the DNS-rebinding
    # window between the two resolutions.
    try:
        addrs, _ = net_guard.enforce_loopback(url, allow_remote=allow_remote)
    except OSError as e:
        raise RuntimeError(f"rewrite endpoint is not resolvable: {e}") from e
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    opener = net_guard.make_pinned_opener(addrs[0], no_redirect=True)
    with opener.open(req, timeout=timeout) as resp:
        data = resp.read(MAX_RESPONSE_BYTES + 1)
        if len(data) > MAX_RESPONSE_BYTES:
            raise RuntimeError(
                f"rewrite endpoint response exceeds cap ({MAX_RESPONSE_BYTES} bytes)"
            )
        return json.loads(data.decode("utf-8"))


def call_ollama(
    base_url: str,
    model: str,
    prompt: str,
    timeout: float,
    temperature: float,
    allow_remote: bool = False,
) -> str:
    url = base_url.rstrip("/") + "/api/chat"
    data = _http_json(
        url,
        {
            "model": model,
            "stream": False,
            "messages": [{"role": "user", "content": prompt}],
            "options": {"temperature": temperature},
        },
        {},
        timeout,
        allow_remote,
    )
    msg = data.get("message") or {}
    content = msg.get("content")
    if not content:
        raise RuntimeError(f"ollama empty response: {data!r}"[:500])
    return str(content).strip()


def call_openai_compatible(
    base_url: str,
    model: str,
    prompt: str,
    api_key: str | None,
    timeout: float,
    temperature: float,
    allow_remote: bool = False,
) -> str:
    url = base_url.rstrip("/") + "/v1/chat/completions"
    headers: dict[str, str] = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    data = _http_json(
        url,
        {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
        },
        headers,
        timeout,
        allow_remote,
    )
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError(f"openai-compatible empty choices: {data!r}"[:500])
    content = (choices[0].get("message") or {}).get("content")
    if not content:
        raise RuntimeError(f"openai-compatible empty content: {data!r}"[:500])
    return str(content).strip()


def rewrite(
    text: str,
    *,
    backend: str,
    model: str | None,
    base_url: str | None,
    api_key: str | None,
    strength: str,
    lang: str,
    original_lang: str,
    timeout: float,
    layer_a_after: bool,
    temperature: float,
    candidates: int,
    allow_remote: bool = False,
    score_synthid_text: bool = False,
) -> tuple[str, dict]:
    prompt = build_prompt(strength, text, lang=lang, original_lang=original_lang)
    info: dict = {
        "backend": backend,
        "strength": strength,
        "model": model,
        "base_url": base_url,
        "temperature": temperature,
        "prompt_chars": len(prompt),
        "input_chars": len(text),
    }

    # Self-verification: score the input before any rewriting, so the
    # before/after delta is measured on identical keys/config.
    if score_synthid_text:
        before = run_synthid_text_scorer(text)
        if before is not None:
            info["synthid_text_before"] = before

    if backend == "print-prompt":
        info["mode"] = "print-prompt"
        if candidates > 1:
            eprint("note: --candidates ignored in print-prompt mode")
        if score_synthid_text and "synthid_text_before" not in info:
            eprint("note: SynthID-Text scorer not available (see setup_synthid_text.sh)")
        return prompt, info

    if not model:
        raise SystemExit("error: --model required for ollama/openai-compatible backends")
    if not base_url:
        raise SystemExit("error: --base-url required for ollama/openai-compatible backends")
    if not 0.0 <= temperature <= 2.0:
        raise SystemExit("error: --temperature must be between 0.0 and 2.0")

    _check_remote(base_url, allow_remote)

    n = max(1, candidates)
    outs: list[str] = []
    for _ in range(n):
        if backend == "ollama":
            outs.append(
                call_ollama(base_url, model, prompt, timeout, temperature, allow_remote)
            )
        elif backend == "openai-compatible":
            outs.append(
                call_openai_compatible(
                    base_url, model, prompt, api_key, timeout, temperature, allow_remote
                )
            )
        else:
            raise SystemExit(f"unknown backend: {backend}")

    # A backend that answers with whitespace-only output is a failure, not a
    # rewrite; silently emitting it would produce an empty "cleaned" file.
    kept = [o for o in outs if o and o.strip()]
    if not kept:
        raise RuntimeError("rewrite backend returned only empty candidates")
    if len(kept) < len(outs):
        info["empty_candidates_dropped"] = len(outs) - len(kept)
    outs = kept

    if len(outs) == 1:
        out = outs[0]
    else:
        info["candidates"] = n
        out, scores = _select_candidate(text, outs)
        info["candidate_scores"] = scores

    if layer_a_after:
        out, stats = clean_text(out)
        info["layer_a_after"] = stats

    if score_synthid_text:
        after = run_synthid_text_scorer(out)
        if after is not None:
            info["synthid_text_after"] = after
        elif "synthid_text_before" in info:
            eprint("note: SynthID-Text scorer became unavailable before scoring the output")

    info["output_chars"] = len(out)
    info["mode"] = "rewritten"
    info["note"] = (
        "Layer B is best-effort against statistical token-sampling watermarks; "
        "cannot certify removal against a vendor detector."
    )
    return out, info


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("path", nargs="?", default="-", help="Input text file, or - for stdin")
    p.add_argument("-o", "--output", help="Output path (default: stdout or *.rewritten.*)")
    p.add_argument(
        "--backend",
        choices=("print-prompt", "ollama", "openai-compatible"),
        default=_env("WATERMARKS_REWRITE_BACKEND", "print-prompt"),
    )
    p.add_argument("--model", default=_env("WATERMARKS_REWRITE_MODEL"))
    p.add_argument(
        "--base-url",
        default=_env("WATERMARKS_REWRITE_BASE_URL", "http://127.0.0.1:11434"),
    )
    p.add_argument(
        "--allow-remote",
        action="store_true",
        default=None,
        help="Allow non-loopback rewrite endpoints (default: deny; "
        "WATERMARKS_REWRITE_ALLOW_REMOTE=1 has the same effect)",
    )
    # NOTE: no --api-key flag on purpose — keys on argv are visible in `ps`
    # and shell history. Set WATERMARKS_REWRITE_API_KEY instead.
    p.add_argument(
        "--strength",
        choices=("paraphrase", "backtranslate", "structural", "humanize", "code"),
        default="paraphrase",
    )
    p.add_argument("--lang", default="French", help="Pivot language for backtranslate")
    p.add_argument("--original-lang", default="English")
    p.add_argument("--timeout", type=float, default=120.0)
    p.add_argument(
        "--temperature",
        type=float,
        default=0.9,
        help="Sampling temperature for the rewrite backend",
    )
    p.add_argument(
        "--candidates",
        type=int,
        default=1,
        help="Number of rewrite candidates to generate and score",
    )
    p.add_argument(
        "--no-layer-a-after",
        action="store_true",
        help="Skip Layer A scrub on model output",
    )
    p.add_argument("--json-stats", action="store_true", help="Stats JSON on stderr")
    p.add_argument(
        "--score-synthid-text",
        action="store_true",
        default=None,
        help="Score input and output with the optional SynthID-Text scorer "
        "(before/after self-verification; WATERMARKS_SCORE_SYNTHID_TEXT=1 "
        "has the same effect)",
    )
    p.add_argument(
        "--force-text",
        action="store_true",
        help="Rewrite even when the input looks like a binary container",
    )
    args = p.parse_args()

    text = read_text_input(args.path, allow_binary=args.force_text)
    allow_remote = (
        args.allow_remote
        if args.allow_remote is not None
        else _flag_env("WATERMARKS_REWRITE_ALLOW_REMOTE")
    )
    score_synthid = (
        args.score_synthid_text
        if args.score_synthid_text is not None
        else _flag_env("WATERMARKS_SCORE_SYNTHID_TEXT")
    )
    try:
        result, info = rewrite(
            text,
            backend=args.backend,
            model=args.model,
            base_url=args.base_url,
            api_key=_env("WATERMARKS_REWRITE_API_KEY"),
            strength=args.strength,
            lang=args.lang,
            original_lang=args.original_lang,
            timeout=args.timeout,
            layer_a_after=not args.no_layer_a_after,
            temperature=args.temperature,
            candidates=args.candidates,
            allow_remote=allow_remote,
            score_synthid_text=score_synthid,
        )
    except (urllib.error.URLError, TimeoutError, RuntimeError) as e:
        eprint(f"rewrite failed: {e}")
        return 1

    out = args.output
    if out is None and args.path not in (None, "-") and args.backend != "print-prompt":
        out = str(cleaned_path(Path(args.path), suffix=".rewritten"))
    elif out is None and args.backend == "print-prompt":
        out = "-"

    write_text_output(result, out)
    if args.json_stats:
        eprint(json.dumps(info, indent=2, ensure_ascii=False))
    else:
        eprint(
            f"backend={info['backend']} strength={info['strength']} "
            f"mode={info.get('mode')} chars {info['input_chars']}->{info.get('output_chars', len(result))}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
