# Scheme taxonomy — what marks what, and what works against it

One table to answer "scheme X exists — can this repo do anything about it?"
Detection column = what the *mark owner* needs to detect it. Honest by design:
where the answer is "nothing reliable", it says so.

| Scheme (class) | Perturbs | Detect via | Key needed | Our response | Certainty |
| --- | --- | --- | --- | --- | --- |
| **KGW green-list** (Kirchenbauer 2023) | Token sampling (context-hash green list) | z-test on green hits + tokenizer | Yes | Layer B rewrite (paraphrase-class attacks measurably degrade it) | Best-effort |
| **SynthID-Text** (Google, Nature 2024) | Tournament sampling over top-k | mean g-values | Yes | Layer B rewrite; *self-verify* with own keys via `score_synthid_text.py` | Best-effort, measurable on own keys |
| **Unigram** (Zhao 2023) | Fixed global green list | green-hit count | Yes | Layer B rewrite (same class) | Best-effort |
| **Unbiased / distortion-free** (Hu 2024) | Distribution-preserving reweight | keyed statistic | Yes | Layer B rewrite — signal is weak by construction, so even light rewording helps | Best-effort |
| **SemStamp / semantic** (Su & Wu 2024) | Paragraph-level semantic clusters | cluster signature + key | Yes | Structural rewrite (Layer B `structural`) hits paragraph shape, but robustness claim is paraphrase resistance — weakest match in our toolkit | Mostly out of reach |
| **PostMark / entropy-aware** (Thilak 2024) | Low-entropy spans (code, lists) | keyed statistic | Yes | Layer B `code` strength rewording comments/identifiers; code *semantics* survive | Best-effort |
| **Claude embedded watermark** (Anthropic, live 2026-08-02) | Unpublished (public description matches sampling class) | Anthropic tooling (not yet published) | Their keys | Layer B by class analogy; **no public detector to verify against** | Best-effort, unverifiable today |
| **Edit-based / Unicode** (various) | Injected invisible characters | Layer A inspect | No | **Layer A — deterministically removed and counted** | Verifiable ✅ |
| **C2PA / EXIF / XMP / docProps** | File metadata (signed) | any parser / `c2patool` | No (signature verifies) | **Layer C — stripped, output re-inspected** | Verifiable ✅ |
| **Pixel watermark** (SynthID-media, StegaStamp, Tree-Ring, StableSignature) | Image pixels | owner's detector | Yes | Optional CtrlRegen regeneration (conservative default; forensic traces may remain) | Optional backend, no certification |
| **Soft binding** (watermark re-links remote manifest) | Combination | owner's service | Yes | **Out of scope** — survives any local strip | None (stated) |
| **Audio/video watermark** (incl. OpenAI audio SynthID, 2026-07) | Audio/video features | owner's detector | Yes | **Out of scope** | None (stated) |
| **Watermark-agnostic classifiers** (DetectGPT, Binoculars, commercial) | Nothing — they classify style/statistics | the classifier itself | No | **Nothing — and we don't pretend.** Stripping marks ≠ being unclassifiable | None (stated) |

## Reading the table

- "Key needed: Yes" is the load-bearing column. Without the vendor's key,
  nobody — including us — can *verify* removal against that vendor's mark.
  That is why Layer B reports before/after scores only for **your own keys**
  (self-verification), and why "no tool can certify undetectability" appears
  in every report we emit.
- "Verifiable ✅" rows are exactly the layers with deterministic accounting:
  every removed codepoint is counted (A), every stripped metadata part is
  listed and the output re-inspected (C).
- The two "Out of scope" rows are listed *on purpose*. A reference tool that
  quietly omits its limits is marketing, not engineering.

Cross-references: scheme papers in [`research.md`](research.md) §1–2;
terminology in [`glossary.md`](glossary.md); vendor posture in
[`vendor-notes.md`](vendor-notes.md); practical pipeline in
[`removal-matrix.md`](removal-matrix.md).
