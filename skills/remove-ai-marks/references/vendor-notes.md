# Vendor notes (public / class-level)

This skill targets **mark classes**, not reverse-engineered private detectors. Details below are from public docs and the research literature. Algorithms may change. Last reviewed: **2026-08**.

## Industry two-layer model (context)

Product and regulatory guidance often frames AI disclosure as:

1. **C2PA Content Credentials** — signed, hard-bound metadata (easy to strip; what this skill removes).
2. **Imperceptible watermark** (SynthID-class) — survives strip/re-upload; includes **soft binding** that can re-attach a remote C2PA manifest.

See: [Institute of AI PM — C2PA and SynthID guide](https://www.institutepm.com/knowledge-hub/ai-content-provenance-watermarking) (SB 942 / EU AI Act Art. 50 framing). This project only implements the **hard-bound / Unicode / rewrite** side of that stack.

**2026 trend:** detection is moving beyond watermarks alone — Google's [AI Content Detection API](https://www.infoq.com/news/2026/05/google-synthid-content-detection/) (I/O 26) detects content from *other providers'* models too, and independent detectors lean on statistical pattern recognition. Assume the adversary is "watermark **or** classifier", and that stripping a watermark never fools a classifier.

## Anthropic / Claude

- **Live since 2026-08-02** (EU AI Act Art. 50 Code of Practice): **embedded text watermarks** at model level (imperceptible; survive copy-paste; may persist through some editing). Public description matches **statistical token-sampling** class, not only Unicode.
- **Signed C2PA Content Credentials** on supported files (e.g. PNG, JPEG, SVG) — provenance + tamper evidence.
- Surfaces: API, Claude apps, Claude Code, Cowork, Tag; cloud partners (AWS / Google Cloud / Microsoft Foundry) inherit watermarks. **Worldwide** rollout.
- Detection: committed for users/third parties; **tooling not yet published**.
- Caveats: mark ⇒ may have been *processed* by Claude (proofreading/translation stamps too); no mark ≠ human-only; short/heavily-edited text unreliable.

**Skill mapping:** Layer A (Unicode hygiene) + Layer B (rewrite) + container/image C2PA strip (Layer C).

Sources: [How Claude marks AI-generated content](https://support.claude.com/en/articles/16266773-how-claude-marks-ai-generated-content) · [Nature news coverage](https://www.nature.com/articles/d41586-026-02503-7) · [TechCrunch](https://techcrunch.com/2026/08/11/anthropic-says-it-will-watermark-text-generated-by-its-ai-models/).

## Google Gemini / SynthID

- Nature 2024 paper: *Scalable watermarking for identifying large language model outputs* (SynthID-Text).
- **Generative watermarking**: modifies next-token sampling (Tournament sampling); detection uses a scoring function + key; no need for the LLM at detect time.
- Paper also taxonomizes:
  - **Edit-based** (Unicode / synonym rules) → our Layer A (+ Layer B for synonyms)
  - **Data-driven / backdoor** (trigger phrases) → **out of scope**
  - **Generative** (sampling) → Layer B best-effort
- Productionized across Gemini; **production keys are not public** — no public SynthID-Text detector for others' content exists.
- **Detection ecosystem (2025–2026):** [SynthID Detector portal](https://deepmind.google/models/synthid/) (image/video/audio upload, early access), the cross-provider [AI Content Detection API](https://cloud.google.com/blog/products/ai-machine-learning/innovations-from-google-io-26-on-google-cloud) on Google Cloud (I/O 26), and SynthID checks inside Google Search / Chrome (Lens, Circle to Search) alongside C2PA.
- Current frontier production watermarks are **token-by-token** (streaming constraint); paragraph-level robust methods (SemStamp / PostMark) are not deployed yet, which keeps paraphrase-class attacks effective today.
- **Self-verification (this repo):** [`google-deepmind/synthid-text`](https://github.com/google-deepmind/synthid-text) (Apache-2.0) is wired in as an optional scorer — `score_synthid_text.py` / `rewrite_text.py --score-synthid-text`. It scores watermarks created with **your** keys/config (hashing-based, CPU-only, no model weights) so Layer B effectiveness is measurable, not folklore. It cannot detect Google's production watermarks.
- Optional external reference: [`aloshdenny/reverse-SynthID`](https://github.com/aloshdenny/reverse-SynthID) provides a reverse-engineered pixel-domain scorer. It is **not bundled** here, is best-effort, and is under a non-commercial Research License; it is not the official Google detector.
- Optional pixel-domain removal: [`mertizci/noai-watermark`](https://github.com/mertizci/noai-watermark)'s CtrlRegen profile is wired through `clean_image.py --remove-pixel ctrlregen` / `clean_ctrlregen.py`. It is **not bundled** (no LICENSE file → all-rights-reserved), and no local detector certifies the result; the official Google check is the final authority.

**Skill mapping:** Layer B rewrite attacks (paraphrase / back-translate / structural) + SynthID-Text before/after self-verification.

## OpenAI / ChatGPT

- Public provenance surfaces as **labels**, **C2PA / Content Credentials** on media exports, and product UI disclosure; no public text-sampling watermark spec comparable to SynthID-Text.
- **2026-07-31:** OpenAI announced its generated **audio** now carries SynthID watermarking in collaboration with Google ([announcement](https://openai.com/index/advancing-content-provenance/)) — watermarking is converging cross-vendor.
- Treat **file metadata / C2PA** as in-scope when present; treat any **unpublished** text watermark as the same statistical class → Layer B only, best-effort.
- Do not invent algorithm claims.

**Skill mapping:** container/image metadata strip + Layer A/B on text. Audio watermarks: out of scope.

## Open-weight / open-LLM (Kirchenbauer-style)

- Classic green-list / red-list sampling bias (Kirchenbauer et al.) and variants.
- Detectable with the **key** and tokenizer; removal still relies on heavy paraphrase or regeneration.
- Multi-scheme reference toolkits: [`jwkirchenbauer/lm-watermarking`](https://github.com/jwkirchenbauer/lm-watermarking) (the original) and [`THU-BPM/MarkLLM`](https://github.com/THU-BPM/MarkLLM) (EMNLP 2024 demo; implements KGW/SynthID-Text/Unbiased/Walter and robustness evaluation). Possible future backend for broader Layer B verification.

**Skill mapping:** Layer B multi-pass; prefer rewrite with a **different** model family when possible.

## Cross-vendor hygiene rule

| Suspected origin | Prefer rewrite backend |
| --- | --- |
| Claude | Non-Claude (local Ollama, other API) |
| Gemini | Non-Gemini |
| OpenAI | Non-OpenAI |
| Unknown | Local open-weight if available |

Prefer local open-weight backends and avoid any known-watermarked vendor, not
just the suspected origin. Then re-run Layer A on the rewritten text.
