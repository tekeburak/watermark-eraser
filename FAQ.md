# FAQ

Questions this project actually gets, answered honestly. Deeper detail lives
in [`skills/remove-ai-marks/references/`](skills/remove-ai-marks/references/) —
especially [`vendor-notes.md`](skills/remove-ai-marks/references/vendor-notes.md),
[`scheme-taxonomy.md`](skills/remove-ai-marks/references/scheme-taxonomy.md) and
[`research.md`](skills/remove-ai-marks/references/research.md).

## Can this tool tell me whether text was written by AI?

No — and it never claims to. This is a *removal/hygiene* toolkit for content
you own. Detection is a different problem with different tools: watermark
detectors (need the vendor's key), or watermark-agnostic classifiers
(DetectGPT/Binoculars-class, commercial services). Our optional scorers only
score watermarks **you** created with **your** keys.

## Can you remove Claude's watermark?

Claude output has carried an embedded statistical text watermark since
2026-08-02, plus signed C2PA metadata on files.

- The **C2PA/metadata** part: yes, verifiably — that's Layer C
  (`clean_file.py` / `clean_image.py`), and the output is re-inspected.
- The **text watermark**: Layer B (`rewrite_text.py`) attacks this class the
  way the research literature does — heavy rewording. It is **best-effort**.
  Anthropic has published no detector, so nobody (including us) can verify
  removal against their mark. Anyone promising otherwise is guessing.

## If I strip everything, is the content "undetectable"?

No. Watermarks are one signal; statistical classifiers are another and they
don't need a watermark. Stripping marks addresses *provenance hygiene*, not
"classifier evasion" — see the honesty section in the
[README](README.md#the-honest-part) and the impossibility literature it cites.

## Does the tool phone home?

No. Core tools are pure stdlib, no network. The only network paths are
opt-in: pointing Layer B at **your** local model endpoint (loopback-only by
default, resolved-IP-validated, connection-pinned), or the sitemap auditor
you explicitly run. Files never leave your machine otherwise.

## Why did cleaning keep my `` character?

Probably a Private Use Area codepoint (U+E000–F8FF or planes 15/16). Icon
fonts (Font Awesome & friends) legitimately live there, so Layer A *reports*
PUA always but strips it only with `--aggressive-homoglyphs`. Re-run with
that flag if you know you don't use icon fonts.

## Why did emoji keep their invisible characters?

ZWJ and VS16 inside an emoji sequence (`👨‍👩‍👧`, `⚖️`) are load-bearing:
removing them visibly breaks the text. The engine preserves emoji glue,
script joiners (Persian/Devanagari), flag tag sequences and orthographic
Arabic marks by default. `--strip-emoji-glue` opts into paranoid mode.

## Which formats are supported?

16: PNG, JPEG, WebP, TIFF, GIF, SVG, PDF, DOCX, PPTX, XLSX, ODT, ODP, ODS,
HTML, Markdown, plain text/code. Routing is extension-first, then magic
bytes — including OOXML/ODF archives by zip contents. AVIF/HEIC/JPEG XL and
EPUB are on the [roadmap](README.md#roadmap).

## Do I need Python packages, Docker, or a GPU?

None. Core is Python 3.10+ stdlib — `git clone` and run. Optional backends
(`c2patool`, `exiftool`, SynthID-Text scorer, CtrlRegen) are bootstrapped on
demand; only CtrlRegen realistically wants a GPU.

## How do I verify a Layer B rewrite actually did anything?

`make bootstrap-synthid-text` once, then:

```bash
.../synthid-text/.venv/bin/python skills/remove-ai-marks/scripts/rewrite_text.py \
  draft.md --backend ollama --model MODEL --score-synthid-text --json-stats
```

You get `synthid_text_before` / `synthid_text_after` in the stats JSON.
Scores ≈0.5 mean "no watermark with these keys"; watch the delta on your own
keyed watermarks. That is self-verification, not a vendor guarantee.

## Is it legal / ethical to use?

For **your own** content: it's a privacy/hygiene tool and the EU AI Act
transparency wave is exactly why it exists. For fraud, plagiarism,
copyright evasion, or passing AI work off as human-written: no — see
[`references/ethics.md`](skills/remove-ai-marks/references/ethics.md).
A detected Claude mark also doesn't prove sole AI authorship (proofreading
gets stamped too), and no mark doesn't prove human origin.

## How is the project tested?

260 hermetic tests (no network, no torch in CI), CLI smoke tests on
fixtures, CI on Ubuntu + Windows, pip-audit, CodeQL, Dependabot. Run it
yourself: `uv sync && uv run python -m pytest` or `make smoke`.

## Can I use the code?

MIT — see [LICENSE](LICENSE). If it helped your research or product, a star
and a citation ([CITATION.cff](CITATION.cff)) are appreciated.
