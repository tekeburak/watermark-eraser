# watermark-eraser

> Strip AI provenance signals — invisible Unicode, C2PA / EXIF / XMP metadata, and statistical text watermarks — from files **you own**. Locally, deterministically, with nothing phone-home about it.

[![CI](https://github.com/tekeburak/watermark-eraser/actions/workflows/ci.yml/badge.svg)](https://github.com/tekeburak/watermark-eraser/actions/workflows/ci.yml)
[![CodeQL](https://github.com/tekeburak/watermark-eraser/actions/workflows/codeql.yml/badge.svg)](https://github.com/tekeburak/watermark-eraser/actions/workflows/codeql.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org)
[![Release](https://img.shields.io/github/v/release/tekeburak/watermark-eraser)](https://github.com/tekeburak/watermark-eraser/releases)
[![Stars](https://img.shields.io/github/stars/tekeburak/watermark-eraser)](https://github.com/tekeburak/watermark-eraser/stargazers)

Every AI system that touches your files tends to leave fingerprints: hidden Unicode codepoints pasted into text, provenance manifests and generator tags embedded in images and documents, or sampling-pattern watermarks threaded through the wording itself. Most of the time you never asked for those fingerprints — and once they're there, almost nothing removes them.

**watermark-eraser** is a batteries-included, dependency-free toolkit that finds and erases them. Point it at a file; it figures out what the file is, reports every mark it can see, cleans it, and re-verifies the result. It also ships as an agent skill so AI assistants can run the whole workflow for you.

**For your own content.** This is a privacy and hygiene tool, not a deception tool — please read the short [ethics notes](skills/remove-ai-marks/references/ethics.md) before using it.

🌐 Landing page: **<https://tekeburak.github.io/watermark-eraser/>**

---

## Why this exists

| | |
| --- | --- |
| **No dependencies** | Pure Python 3.10+ stdlib. `git clone` and run — nothing to install. |
| **Local by default** | Files never leave your machine. Network features are loopback-only unless you explicitly opt in. |
| **Deterministic** | Every removal is counted and reported — codepoint by codepoint, chunk by chunk. |
| **Honest** | Verifiable removals are labeled verifiable; best-effort ones are labeled best-effort. No magic claims. |
| **Broad formats** | 16 file formats across images, documents, and text. |
| **Agent-native** | Ships as an installable skill with a full inspect → clean → verify workflow. |
| **234 tests** | Hermetic suite (no network), CI on Ubuntu and Windows, pip-audit + CodeQL + Dependabot. |

## Getting started

```bash
git clone https://github.com/tekeburak/watermark-eraser.git
cd watermark-eraser
```

The two commands you'll use most — they route by format automatically (extension first, then magic bytes, including OOXML/ODF archive contents):

```bash
S=skills/remove-ai-marks/scripts

python3 $S/inspect_file.py report.docx   # show every mark found (JSON: --json)
python3 $S/clean_file.py report.docx -o report.cleaned.docx
```

Both exit non-zero when marks are detected (inspect) or survive cleaning (clean), so they slot into scripts and CI pipelines. `--in-place` backs up the original to `.bak` before overwriting.

Useful single-purpose tools: `inspect_text.py` / `clean_text.py` (Unicode only), `inspect_image.py` / `clean_image.py`, `rewrite_text.py` (statistical rewrite hook), `audit_dir.py` / `audit_website.py` (bulk audits over a tree or a sitemap).

### Install as an agent skill

```bash
ln -sfn "$(pwd)/skills/remove-ai-marks" ~/.grok/skills/remove-ai-marks
```

Then just ask your agent: *"strip the AI watermarks from these files"* — or invoke `/remove-ai-marks` directly. The skill knows the full workflow, the ethics boundaries, and when rewriting is worth it.

### Optional system tools

If [`c2patool`](https://github.com/contentauth/c2pa-rs/tree/main/cli) or [`exiftool`](https://exiftool.org/) are on your `PATH`, the tools detect and use them automatically (deeper C2PA inspection; reliable PDF stripping). Everything works without them.

## The three layers

**Layer A — invisible text carriers.** Zero-width spaces, bidi overrides, tag characters, variation selectors, exotic space homoglyphs, private-use codepoints, dense carrier runs. Detected and scrubbed deterministically; every removal is counted. Legitimate load-bearing invisibles (emoji ZWJ sequences, script joiners in Persian/Devanagari, orthographic Arabic marks) are recognized and preserved.

**Layer B — statistical text watermarks.** SynthID-Text- and Kirchenbauer-class marks are encoded in *which* tokens the model picked, so the only real attack is rewording. `rewrite_text.py` drives that rewrite — paraphrase, humanize, back-translate, or structural — against a local model (Ollama or any OpenAI-compatible endpoint, loopback-only by default) or just prints the prompt for your agent to execute. Multi-candidate mode scores rewrites by lexical divergence. Section [The honest part](#the-honest-part) covers what this costs.

**Layer C — file metadata.** C2PA manifests, EXIF, XMP packets, document properties, customXml parts, generator tags — removed while image pixels and document text stay byte-compatible. The unified cleaners re-inspect their own output and report anything that survived.

## Supported formats

| Category | Formats | What gets cleaned |
| --- | --- | --- |
| Raster images | PNG, JPEG, WebP, TIFF, GIF | C2PA/JUMBF chunks, EXIF, XMP, text chunks, comment & marked app extensions |
| Vector / docs | SVG, PDF, DOCX, PPTX, XLSX, ODT, ODP, ODS | XMP/metadata blocks, docProps, customXml, generator & AI-ish meta fields |
| Text-ish | HTML, Markdown, plain text, code | generator meta, JSON-LD provenance, AI frontmatter keys + Layer A |

PDF cleaning prefers `exiftool` when available and falls back to a best-effort stdlib XMP strip (clearly flagged as degraded). Pixel-domain image watermarks are handled by an optional external [CtrlRegen](https://arxiv.org/abs/2410.05470) backend — see `skills/remove-ai-marks/SKILL.md` for setup, or run `make bootstrap-ctrlregen`.

Explicitly out of scope: C2PA *soft binding*, audio/video watermarks, and training-data backdoors. No tool honestly removes those today.

## Security design

This toolkit deliberately parses untrusted files, so it's built like a security tool:

- **Writes are atomic and symlink-safe** — outputs go through temp-file + rename; a pre-planted symlink cannot redirect a clean onto your files, and `--in-place` always backs up first.
- **Binary guard** — the text tools refuse ZIP/PDF/image input by magic number instead of mangling it (`--force-text` to override).
- **Loopback-only networking** — rewrite endpoints resolve-and-validate (full `127.0.0.0/8`, not just `127.0.0.1`), pin the connection to the validated address so DNS can't rebind mid-flight, refuse redirects (your API key never travels anywhere you didn't allow), and cap response sizes. Keys live in env vars, never argv.
- **Crawler hardening** — the sitemap auditor accepts only http(s), and won't follow remote-controlled links or redirects into private networks.
- **Resource caps** — input/stdin size caps, zip decompression budgets, and `RLIMIT_AS`/`RLIMIT_FSIZE` on every child process. All tunable via `WATERMARKS_*` env vars.
- **Supply chain** — SHA-pinned CI actions, least-privilege workflows, pinned dev deps, pip-audit, CodeQL, Dependabot.

Found something? Follow the private-disclosure policy in [SECURITY.md](SECURITY.md).

## The honest part

Layer A and Layer C removals are **verifiable**: the tool counts what it removed and re-inspects the output.

Layer B is **best-effort**, and anyone telling you otherwise is selling something. A statistical watermark lives in the wording, so removing it means rewording — a *lot* of it, sentence by sentence. Every rewrite trades some of the original's voice and precision for mark resistance. If the plan is "generate with a premium model, then rewrite with a cheap one to strip marks," ask whether generating with the cheap model directly wouldn't have been simpler. Layer B earns its keep when you want the premium model's drafting *and* have a hygiene requirement to satisfy — use a **non-origin** model for the rewrite (origin models may re-stamp), and know that no tool can certify an undetectable result.

## Roadmap

- [ ] In-browser demo (Pyodide): Layer A + metadata parsing, 100% client-side — your files never leave the tab
- [ ] EPUB, JPEG XL, AVIF/HEIC support; stdlib PDF Info-dictionary scrubber
- [ ] Hosted API for the heavy compute backends

## Contributing

Contributions are genuinely welcome — this project runs on careful parsing and paranoia about edge cases, and fresh eyes find both. **[Read the contributor guide →](CONTRIBUTING.md)**

The short version:

1. **Fork & branch** — `git checkout -b fix/my-change`
2. **Run the suite** — `uv sync && uv run python -m pytest` (preferred; uv-lockfile-exact) or `pip install -r requirements.txt` with your usual venv. All 234 tests must pass; they're hermetic, no network
3. **Add a test** for whatever you fixed or added — the suite is the project's insurance
4. **Open a PR** against `main` — CI must be green; a code-owner review merges it

Good first contributions: new format parsers (pattern: magic sniff + inspect + strip + programmatic fixtures), Layer A codepoint coverage, and docs clarity. Please keep the stdlib-first, no-network-in-tests philosophy, and keep it a tool for content people own. By participating you agree to the [Code of Conduct](CODE_OF_CONDUCT.md).

## License

MIT — see [LICENSE](LICENSE).

## Changelog

### v0.1.0

Initial public release.

- Unified `inspect_file.py` / `clean_file.py` routers over 16 formats (PNG, JPEG, WebP, TIFF, GIF, SVG, PDF, DOCX, PPTX, XLSX, ODT, ODP, ODS, HTML, Markdown, text) with magic-byte detection including OOXML/ODF archive contents
- Layer A Unicode engine: zero-width family, bidi controls, tag characters, variation selectors, Hangul fillers, line/paragraph separators, private-use detection, dense-run signal — with emoji-glue and script-joiner preservation
- Layer B rewrite hook: print-prompt / Ollama / OpenAI-compatible backends, five strengths, multi-candidate divergence scoring
- Layer C metadata cleaners with post-clean re-inspection and residual reporting
- Bulk audits: recursive directory and sitemap crawler
- Optional integrations: c2patool, exiftool, reverse-SynthID scoring, CtrlRegen pixel regeneration
- Hardened by design: atomic symlink-safe writes, binary guard, resolved-IP loopback pinning, redirect refusal, response caps, child-process rlimits
- 234 hermetic tests; CI (Ubuntu + Windows), pip-audit, CodeQL, Dependabot; agent skill with ethics guidance

## Further reading

- Dathathri et al., [*Scalable watermarking for identifying large language model outputs*](https://www.nature.com/articles/s41586-024-08025-4) — SynthID-Text (Nature, 2024)
- Kirchenbauer et al., [*A Watermark for Large Language Models*](https://arxiv.org/abs/2301.10226)
- Zhang et al., [*Watermarks in the Sand: Impossibility of Strong Watermarking for Generative Models*](https://arxiv.org/abs/2311.04378) (ICML 2024)
- Liu et al., [*Image Watermarks are Removable Using Controllable Regeneration from Clean Noise*](https://arxiv.org/abs/2410.05470) (ICLR 2025)
- Kassis & Hengartner, [*UnMarker*](https://arxiv.org/abs/2405.08363) (IEEE S&P 2025)
- Goonatilake & Atenesi, [*Removing the Watermark Is Not Enough: Forensic Stealth in Generative-AI Watermark Removal*](https://arxiv.org/abs/2605.09203)
- [C2PA specification](https://c2pa.org/) · [Content Credentials verify](https://contentcredentials.org/verify)
- [Anthropic — How Claude marks AI-generated content](https://support.claude.com/en/articles/16266773-how-claude-marks-ai-generated-content) · [Google — SynthID safeguards](https://ai.google.dev/responsible/docs/safeguards/synthid)
