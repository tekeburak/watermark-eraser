#!/usr/bin/env python3
"""Optional SynthID-Text scorer — verify Layer B rewrites against a real watermark.

Scores whether text carries a SynthID-Text watermark for a known
watermarking configuration (keys + ngram length). The score is a pure
hashing computation over the token stream via the upstream
``compute_g_values`` teacher-forcing helper — no model weights are loaded
and it runs on CPU in seconds, using the untrained weighted-mean detector.

What this can and cannot do (important):
  - CAN score text watermarked with YOUR keys/config — self-verification:
    generate with SynthID-Text, rewrite with Layer B, compare before/after
    scores (``rewrite_text.py --score-synthid-text`` automates exactly that).
  - CANNOT detect Google's production Gemini watermarks; those keys are not
    public, and no public detector exists for them.

Upstream: https://github.com/google-deepmind/synthid-text (Apache-2.0),
installed via ``setup_synthid_text.sh`` (pinned commit, minimal deps) or
``pip install synthid-text``. Never bundled by this repository.

Exit codes:
  0  scored successfully
  1  scorer runtime error
  2  bad input (no text, bad arguments)
  3  scorer unavailable (package or dependencies missing)
"""

from __future__ import annotations

import argparse
import json
import sys

from common import add_version_flag  # noqa: E402
from pathlib import Path

# Below ~10 scored n-grams the mean is statistically meaningless (the
# upstream paper computes detection thresholds per text length).
MIN_SCORED_NGRAMS = 10

# Mirror of upstream DEFAULT_WATERMARKING_CONFIG["keys"] (30 keys) for
# reference only; the live default is read from the installed package so a
# pinned-checkout update cannot silently desync from this copy.
_DEFAULT_KEYS_REFERENCE = (
    654, 400, 836, 123, 340, 443, 597, 160, 57, 29, 590, 639, 13, 715, 468,
    990, 966, 226, 324, 585, 118, 504, 421, 521, 129, 669, 732, 225, 90, 960,
)


def parse_keys(raw: str | None) -> list[int] | None:
    """Parse a keys argument: ``None``/``''``/``default`` -> upstream defaults."""
    if raw is None or raw.strip().lower() in ("", "default"):
        return None
    try:
        keys = [int(part) for part in raw.split(",")]
    except ValueError:
        raise SystemExit("error: --keys must be comma-separated integers or 'default'")
    if not keys:
        raise SystemExit("error: --keys must not be empty")
    if len(set(keys)) != len(keys):
        raise SystemExit("error: --keys must be unique (upstream hashes each key per layer)")
    return keys


def read_text(path: str) -> str:
    if path in (None, "-"):
        data = sys.stdin.read()
    else:
        p = Path(path)
        if not p.is_file():
            print(f"not a file: {p}", file=sys.stderr)
            raise SystemExit(2)
        data = p.read_text(encoding="utf-8", errors="surrogateescape")
    if not data.strip():
        print("error: no input text to score", file=sys.stderr)
        raise SystemExit(2)
    return data


def score_text(
    text: str,
    *,
    keys: list[int] | None,
    ngram_len: int,
    context_history_size: int,
    temperature: float,
    top_k: int,
    tokenizer_name: str,
) -> dict:
    """Score text; raises ImportError when the backend is unavailable."""
    # Import order matters: synthid_text first so environments without the
    # package fail fast (exit 3) before any tokenizer/network access.
    from synthid_text.detector_mean import weighted_mean_score  # noqa: E402
    from synthid_text.logits_processing import SynthIDLogitsProcessor  # noqa: E402
    from synthid_text.synthid_mixin import DEFAULT_WATERMARKING_CONFIG  # noqa: E402
    import torch  # noqa: E402
    from transformers import AutoTokenizer  # noqa: E402

    if keys is None:
        keys = list(DEFAULT_WATERMARKING_CONFIG["keys"])
    if ngram_len <= 0:
        ngram_len = int(DEFAULT_WATERMARKING_CONFIG["ngram_len"])
    if context_history_size <= 0:
        context_history_size = int(DEFAULT_WATERMARKING_CONFIG["context_history_size"])

    tokenizer = AutoTokenizer.from_pretrained(tokenizer_name)
    input_ids = tokenizer(text, return_tensors="pt").input_ids
    eos_token_id = tokenizer.eos_token_id

    processor = SynthIDLogitsProcessor(
        ngram_len=ngram_len,
        keys=keys,
        context_history_size=context_history_size,
        temperature=temperature,
        top_k=top_k,
        device=torch.device("cpu"),
    )
    g_values = processor.compute_g_values(input_ids)
    eos_mask = processor.compute_eos_token_mask(input_ids, eos_token_id)
    repetition_mask = processor.compute_context_repetition_mask(input_ids)
    mask = torch.logical_and(eos_mask, repetition_mask)

    scores = weighted_mean_score(g_values.cpu().numpy(), mask.cpu().numpy())
    score = float(scores[0])

    return {
        "available": True,
        "score": score,
        "n_tokens": int(input_ids.shape[1]),
        "n_scored_ngrams": int(mask.sum()),
        "ngram_len": ngram_len,
        "depth": len(keys),
        "keys": "default" if keys == list(_DEFAULT_KEYS_REFERENCE) else f"custom ({len(keys)} keys)",
        "tokenizer": tokenizer_name,
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    add_version_flag(p)
    p.add_argument("path", nargs="?", default="-", help="Text file to score, or - for stdin")
    p.add_argument(
        "--keys",
        type=str,
        default="default",
        help="Comma-separated watermarking keys, or 'default' for the upstream defaults",
    )
    p.add_argument("--ngram-len", type=int, default=-1, help="N-gram length (default: upstream, 5)")
    p.add_argument(
        "--context-history-size", type=int, default=-1,
        help="Context repetition history window (default: upstream, 1024)",
    )
    p.add_argument("--temperature", type=float, default=1.0, help="Processor temperature (default 1.0)")
    p.add_argument("--top-k", type=int, default=40, help="Processor top-k (default 40)")
    p.add_argument(
        "--tokenizer", type=str, default="gpt2",
        help="Hugging Face tokenizer used to split text into tokens (default: gpt2)",
    )
    p.add_argument("--json", action="store_true", help="Emit JSON on stdout")
    args = p.parse_args()

    text = read_text(args.path)
    keys = parse_keys(args.keys)

    try:
        result = score_text(
            text,
            keys=keys,
            ngram_len=args.ngram_len,
            context_history_size=args.context_history_size,
            temperature=args.temperature,
            top_k=args.top_k,
            tokenizer_name=args.tokenizer,
        )
    except ImportError as e:
        print(f"optional scorer dependencies missing: {e}", file=sys.stderr)
        return 3
    except SystemExit:
        raise
    except Exception as e:  # tokenizer download failures, upstream API changes
        print(f"scorer error: {e}", file=sys.stderr)
        return 1

    result["note"] = (
        "score ~0.5 means unwatermarked; higher means more likely watermarked "
        "WITH THESE KEYS. Google's production Gemini keys are not public, so "
        "this verifies your own SynthID-Text watermarks only."
    )
    if result["n_scored_ngrams"] < MIN_SCORED_NGRAMS:
        result["low_reliability"] = True

    if args.json:
        json.dump(result, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        print(f"SynthID-Text score: {result['score']:.4f} ({result['n_scored_ngrams']} scored n-grams)")
        if result.get("low_reliability"):
            print(f"  warning: fewer than {MIN_SCORED_NGRAMS} scored n-grams — score is noise-level")
        print(f"  keys: {result['keys']} · ngram_len: {result['ngram_len']} · tokenizer: {result['tokenizer']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
