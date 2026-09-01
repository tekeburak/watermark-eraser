"""Tests for the optional SynthID-Text scorer adapter and its rewrite hook.

Hermetic: no torch/JAX in CI. The unavailable-path tests run the real CLI
(the imports fail fast in the CI environment), and the scoring paths are
exercised through monkeypatched runners.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "remove-ai-marks" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import score_synthid_text  # noqa: E402


# --- pure helpers -----------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        (None, None),
        ("", None),
        ("default", None),
        ("DEFAULT", None),
        ("  default  ", None),
        ("1,2,3", [1, 2, 3]),
        ("42", [42]),
        ("5,10,15,20", [5, 10, 15, 20]),
    ],
)
def test_parse_keys_valid(raw, expected):
    assert score_synthid_text.parse_keys(raw) == expected


@pytest.mark.parametrize("raw", ["1,x,3", "1,,2", "1,1", "3,3,5", ""])
def test_parse_keys_invalid(raw):
    if raw == "":
        return  # empty means "default" — valid
    with pytest.raises(SystemExit):
        score_synthid_text.parse_keys(raw)


def test_parse_keys_rejects_duplicates():
    with pytest.raises(SystemExit):
        score_synthid_text.parse_keys("7,7")


# --- CLI unavailable path (real subprocess, no mocks needed) -----------------


def _run_cli(*args: str, stdin: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPTS / "score_synthid_text.py"), *args],
        input=stdin,
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_cli_unavailable_when_deps_missing(tmp_path: Path):
    """In CI (no synthid_text/torch) the adapter must fail fast with rc 3."""
    sample = tmp_path / "notes.txt"
    sample.write_text("some sufficiently long prose to tokenize\n" * 4, encoding="utf-8")
    r = _run_cli(str(sample), "--json")
    if r.returncode == 0:
        pytest.skip("synthid_text installed in this environment — unavailable path n/a")
    assert r.returncode == 3, r.stderr
    assert "missing" in r.stderr.lower()


def test_cli_bad_input_empty_file(tmp_path: Path):
    empty = tmp_path / "empty.txt"
    empty.write_text("   \n", encoding="utf-8")
    r = _run_cli(str(empty))
    assert r.returncode == 2


def test_cli_bad_keys(tmp_path: Path):
    sample = tmp_path / "notes.txt"
    sample.write_text("hello world\n", encoding="utf-8")
    r = _run_cli(str(sample), "--keys", "1,x")
    assert r.returncode != 0


def test_cli_missing_file():
    r = _run_cli("/nonexistent/definitely-missing.txt")
    assert r.returncode == 2


# --- rewrite_text before/after wiring (monkeypatched scorer) -----------------


def _rewrite_kwargs(**overrides):
    kwargs = dict(
        backend="print-prompt",
        model=None,
        base_url=None,
        api_key=None,
        strength="paraphrase",
        lang="French",
        original_lang="English",
        timeout=5.0,
        layer_a_after=True,
        temperature=0.9,
        candidates=1,
    )
    kwargs.update(overrides)
    return kwargs


def test_rewrite_scores_before_only_in_print_prompt(monkeypatch):
    """print-prompt has no rewritten output, so only the input is scored."""
    import rewrite_text

    calls: list[str] = []

    def fake_scorer(text: str):
        calls.append(text[:8])
        return {"available": True, "score": 0.9}

    monkeypatch.setattr(rewrite_text, "run_synthid_text_scorer", fake_scorer)
    out, info = rewrite_text.rewrite(
        "original watermarked prose", **_rewrite_kwargs(score_synthid_text=True)
    )
    assert len(calls) == 1
    assert info["synthid_text_before"]["score"] == 0.9
    assert "synthid_text_after" not in info


def test_rewrite_scores_before_and_after(monkeypatch):
    import rewrite_text

    calls: list[str] = []

    def fake_scorer(text: str):
        calls.append(text[:8])
        return {"available": True, "score": 0.9 if "original" in text else 0.52}

    monkeypatch.setattr(rewrite_text, "run_synthid_text_scorer", fake_scorer)
    monkeypatch.setattr(rewrite_text, "_check_remote", lambda *a, **k: None)
    monkeypatch.setattr(
        rewrite_text, "call_ollama", lambda *a, **k: "rewritten output text"
    )
    out, info = rewrite_text.rewrite(
        "original watermarked prose",
        **_rewrite_kwargs(
            backend="ollama", model="m", base_url="http://127.0.0.1:1",
            score_synthid_text=True,
        ),
    )
    assert out == "rewritten output text"
    assert len(calls) == 2  # input + output
    assert info["synthid_text_before"]["score"] == 0.9
    assert info["synthid_text_after"]["score"] == 0.52


def test_rewrite_silent_when_scorer_unavailable(monkeypatch):
    import rewrite_text

    monkeypatch.setattr(rewrite_text, "run_synthid_text_scorer", lambda text: None)
    out, info = rewrite_text.rewrite(
        "plain prose", **_rewrite_kwargs(score_synthid_text=True)
    )
    assert "synthid_text_before" not in info
    assert "synthid_text_after" not in info


def test_rewrite_records_scorer_error(monkeypatch):
    import rewrite_text

    monkeypatch.setattr(
        rewrite_text, "run_synthid_text_scorer",
        lambda text: {"available": False, "error": "boom"},
    )
    out, info = rewrite_text.rewrite(
        "plain prose", **_rewrite_kwargs(score_synthid_text=True)
    )
    assert info["synthid_text_before"] == {"available": False, "error": "boom"}


def test_rewrite_no_scoring_by_default(monkeypatch):
    import rewrite_text

    def fail(text):  # pragma: no cover - must not be called
        raise AssertionError("scorer must not run without the flag")

    monkeypatch.setattr(rewrite_text, "run_synthid_text_scorer", fail)
    out, info = rewrite_text.rewrite("plain prose", **_rewrite_kwargs())
    assert "synthid_text_before" not in info


# --- subprocess runner robustness ---------------------------------------------


def test_runner_returns_none_on_exit3(monkeypatch):
    import rewrite_text

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 3, stdout="", stderr="missing")

    monkeypatch.setattr(rewrite_text.subprocess, "run", fake_run)
    assert rewrite_text.run_synthid_text_scorer("text") is None


def test_runner_returns_error_on_failure(monkeypatch):
    import rewrite_text

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="exploded")

    monkeypatch.setattr(rewrite_text.subprocess, "run", fake_run)
    result = rewrite_text.run_synthid_text_scorer("text")
    assert result == {"available": False, "error": "exploded"}


def test_runner_parses_json(monkeypatch):
    import rewrite_text

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(
            cmd, 0, stdout='{"available": true, "score": 0.7}', stderr=""
        )

    monkeypatch.setattr(rewrite_text.subprocess, "run", fake_run)
    assert rewrite_text.run_synthid_text_scorer("text") == {
        "available": True, "score": 0.7
    }
