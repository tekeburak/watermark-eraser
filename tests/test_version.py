"""Tests: --version wiring across every CLI, synced with pyproject.toml."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "remove-ai-marks" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from common import __version__  # noqa: E402

# Every user-facing CLI. Libraries (common, routing, net_guard, *_meta,
# text_unicode, audit_lib) are intentionally not listed.
CLIS = [
    "inspect_text.py",
    "clean_text.py",
    "inspect_image.py",
    "clean_image.py",
    "inspect_file.py",
    "clean_file.py",
    "rewrite_text.py",
    "audit_dir.py",
    "audit_website.py",
    "clean_ctrlregen.py",
    "score_synthid.py",
    "score_synthid_text.py",
]


def test_version_matches_pyproject():
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.M)
    assert m, "pyproject.toml has no version"
    assert m.group(1) == __version__, (
        f"common.__version__ ({__version__}) != pyproject version ({m.group(1)})"
    )


def test_every_cli_script_has_version_flag():
    for name in CLIS:
        source = (SCRIPTS / name).read_text(encoding="utf-8")
        assert "add_version_flag(p)" in source, f"{name} missing --version wiring"


def test_cli_version_runs():
    for name in CLIS:
        r = subprocess.run(
            [sys.executable, str(SCRIPTS / name), "--version"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert r.returncode == 0, f"{name} --version rc={r.returncode}: {r.stderr}"
        assert __version__ in (r.stdout + r.stderr), f"{name} --version output lacks {__version__}"
