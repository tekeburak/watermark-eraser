#!/usr/bin/env bash
# Bootstrap the optional SynthID-Text scorer (Layer B self-verification).
#
# Clones google-deepmind/synthid-text at a pinned commit, creates a venv,
# and installs the MINIMAL dependency set from
# requirements-synthid-text-scorer.txt plus the upstream package with
# --no-deps (the PyPI metadata pulls jax[cuda]/flax/optax, which
# hashing-based scoring does not need).
#
# Usage:
#   ./setup_synthid_text.sh [--dir PATH]
#
# Afterwards, score text (or wire it into rewrite_text.py) with the venv:
#   ~/.watermark-eraser/synthid-text/.venv/bin/python \
#     skills/remove-ai-marks/scripts/score_synthid_text.py notes.txt --json
#   ~/.watermark-eraser/synthid-text/.venv/bin/python \
#     skills/remove-ai-marks/scripts/rewrite_text.py draft.md \
#       --backend ollama --model MODEL --score-synthid-text --json-stats
#
# The upstream code stays in its own checkout and is never bundled here.
# Scoring is pure CPU hashing; there is no GPU requirement.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$SCRIPT_DIR/../../.." && pwd)"

DIR="$HOME/.watermark-eraser/synthid-text"
PYTHON="${PYTHON:-python3}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dir) DIR="$2"; shift 2 ;;
    --python) PYTHON="$2"; shift 2 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
done

# Pinned upstream commit (2025-06-13, main HEAD at pin time). The scorer
# uses logits_processing.compute_g_values / detector_mean.weighted_mean_score
# from this revision; bump only after re-verifying those entry points.
SYNTHID_TEXT_REF="addb4a158143c7c6851a1308f78b89fceed59683"
UPSTREAM="https://github.com/google-deepmind/synthid-text.git"

if [[ ! -d "$DIR/.git" ]]; then
  echo "Cloning $UPSTREAM into $DIR"
  mkdir -p "$(dirname "$DIR")"
  git clone "$UPSTREAM" "$DIR"
fi
git -C "$DIR" fetch --depth 1 origin "$SYNTHID_TEXT_REF"
git -C "$DIR" checkout --detach "$SYNTHID_TEXT_REF"
HEAD_SHA="$(git -C "$DIR" rev-parse HEAD)"
if [[ "$HEAD_SHA" != "$SYNTHID_TEXT_REF" ]]; then
  echo "error: expected pinned ref $SYNTHID_TEXT_REF, got $HEAD_SHA" >&2
  exit 1
fi

VENV_PY="$DIR/.venv/bin/python"
if [[ ! -x "$VENV_PY" ]]; then
  echo "Creating venv at $DIR/.venv"
  if command -v uv >/dev/null 2>&1; then
    uv venv --python "${PYTHON}" "$DIR/.venv"
  else
    "$PYTHON" -m venv "$DIR/.venv"
  fi
fi

# uv pip when available (much faster for the torch wheel); plain pip otherwise.
if command -v uv >/dev/null 2>&1; then
  pip_install() { uv pip install --python "$VENV_PY" "$@"; }
else
  pip_install() { "$VENV_PY" -m pip install "$@"; }
  # Pin pip itself (unpinned --upgrade pip was a supply-chain drift point).
  "$VENV_PY" -m pip install --upgrade "pip==26.2.1"
fi

echo "Installing minimal scorer dependencies"
# Linux torch wheels default to CUDA; the CPU index keeps the install lean.
if [[ "$(uname -s)" == "Linux" ]]; then
  pip_install torch==2.13.0 --index-url https://download.pytorch.org/whl/cpu
  pip_install -r "$SCRIPT_DIR/requirements-synthid-text-scorer.txt"
else
  pip_install -r "$SCRIPT_DIR/requirements-synthid-text-scorer.txt"
fi

echo "Installing upstream package (no deps)"
pip_install --no-deps "$DIR"

cat <<EOF

Done. Verify the setup:

  "$VENV_PY" "$SCRIPT_DIR/score_synthid_text.py" --help

Score a text (score ~0.5 = unwatermarked, higher = watermarked with the
configured keys):

  "$VENV_PY" "$SCRIPT_DIR/score_synthid_text.py" notes.txt

Or measure a Layer B rewrite end to end:

  "$VENV_PY" "$SCRIPT_DIR/rewrite_text.py" draft.md \\
    --backend ollama --model MODEL --score-synthid-text --json-stats

NOTE: this scores watermarks created with YOUR keys/config only. Google's
production Gemini keys are not public.
EOF
