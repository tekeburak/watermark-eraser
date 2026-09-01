# Research map — watermarking & provenance literature

Annotated reading list for anyone who wants to understand *why* this toolkit
is built the way it is. Organized by question, not by venue. Last reviewed:
2026-08. See also [`glossary.md`](glossary.md) for terminology and
[`scheme-taxonomy.md`](scheme-taxonomy.md) for a scheme-by-scheme comparison.

## 1. Text watermarking schemes (what we attack with Layer B)

| Work | One-line contribution |
| --- | --- |
| [Kirchenbauer et al., *A Watermark for Large Language Models*](https://arxiv.org/abs/2301.10226) (2023) | The foundational "green list" scheme: hash the previous token, bias sampling toward a green subset; detect with a z-test using the key + tokenizer (no model needed at detect time). |
| [Dathathri et al., *Scalable watermarking for identifying LLM outputs*](https://www.nature.com/articles/s41586-024-08025-4) (Nature 2024) — **SynthID-Text** | Production-scale tournament sampling; detection via accumulated g-values and the key. Deployed in Gemini. Reference code: [google-deepmind/synthid-text](https://github.com/google-deepmind/synthid-text) — this repo's optional scorer uses its hashing-based scorer. |
| [Zhao et al., *Provable Robust Watermarking for LMs*](https://arxiv.org/abs/2306.09133) (2023) — Unigram | A fixed global green list; survives editing/copying better than per-context hashing, at some quality cost. |
| [Hu et al., *Unbiased Watermark for Large Language Models*](https://arxiv.org/abs/2310.10669) (2024) | Γ/Δ-reweighting that leaves the *distribution* unchanged (distortion-free); weaker signal, harder to spot statistically. |
| [Su & Wu, *SemStamp*](https://arxiv.org/abs/2312.03710) (ACL 2024) | Paragraph-level semantic clustering watermark — robust to paraphrase, which token-level schemes are not. Not deployed at frontier scale (yet). |
| [Thilak et al., *PostMark*](https://arxiv.org/abs/2406.14573) (2024) | Entropy-aware design for *low-entropy* text (code, lists) — the regime where token watermarks usually fail. |

**Multi-scheme toolkit:** [THU-BPM/MarkLLM](https://github.com/THU-BPM/MarkLLM)
(EMNLP 2024 demo) implements several of the above with robustness
evaluation — the natural next backend if you want broader Layer B verification.
The original KGW code lives at [jwkirchenbauer/lm-watermarking](https://github.com/jwkirchenbauer/lm-watermarking).

## 2. Fundamental limits (why "remover" claims deserve skepticism)

- [Zhang et al., *Watermarks in the Sand: Impossibility of Strong Watermarking for Generative Models*](https://arxiv.org/abs/2311.04378) (ICML 2024) — under realistic assumptions no watermark is both high-quality and undetectable-removal-proof. **Read this before promising anything.**
- [Kirchenbauer & Sadasivan-style paraphrase studies](https://arxiv.org/abs/2303.13407) — even a *different* LLM asked to paraphrase measurably degrades token watermarks: the empirical basis of Layer B.

## 3. Attacks & removal (the methods this repo wraps)

| Work | Attack class | Our integration |
| --- | --- | --- |
| [Krishna et al., *Paraphrasing evades detectors…*](https://arxiv.org/abs/2303.13407) (2023) | DIPPER paraphrase | Conceptual basis of `rewrite_text.py` (paraphrase / humanize / backtranslate / structural strengths) |
| [Kassis & Hengartner, *UnMarker*](https://arxiv.org/abs/2405.08363) (IEEE S&P 2025) | Universal degradation attack on defensive image watermarks | Documented context; not bundled |
| [Liu et al., *CtrlRegen*](https://arxiv.org/abs/2410.05470) (ICLR 2025) | Image regeneration from controlled noise | Optional backend (`clean_image.py --remove-pixel ctrlregen`) |
| [Goonatilake & Atenesi, *…Forensic Stealth in Watermark Removal*](https://arxiv.org/abs/2605.09203) (2026) | Removal leaves forensic traces | Why our CtrlRegen default strength is conservative (0.25) |
| [aloshdenny/reverse-SynthID](https://github.com/aloshdenny/reverse-SynthID) | Community pixel-domain SynthID scorer | Optional scorer (`score_synthid.py`); non-commercial license, never bundled |

## 4. Detection without watermarks (the part stripping cannot fix)

Stripping a watermark does **not** make content unclassifiable. Independent
detectors exist and are converging on statistical pattern recognition:

- [Mitchell et al., *DetectGPT*](https://arxiv.org/abs/2301.11305) (2023) — curvature-based zero-shot detection (classic).
- [Hans et al., *Binoculars*](https://arxiv.org/abs/2401.12070) (2024) — perplexity-ratio detection, strong and cheap.
- Google [AI Content Detection API](https://www.infoq.com/news/2026/05/google-synthid-content-detection/) (I/O 2026) — cross-provider detection as a Cloud service.
- [SynthID Detector portal](https://deepmind.google/models/synthid/) — official upload-and-verify for image/video/audio.

**Implication for this repo:** Layer A/C removals are *verifiable*; Layer B
is explicitly best-effort; and *no* layer claims to fool a classifier. That
boundary is stated in `ethics.md` and repeated everywhere on purpose.

## 5. Standards, policy & vendor posture

- [C2PA specification](https://c2pa.org/) · [Content Credentials verify](https://contentcredentials.org/verify) — signed provenance manifests (Layer C's target).
- EU AI Act Article 50 + [Code of Practice on Transparency](https://support.claude.com/en/articles/16266773-how-claude-marks-ai-generated-content) — the regulatory driver of the 2026 marking wave.
- [Anthropic — How Claude marks AI-generated content](https://support.claude.com/en/articles/16266773-how-claude-marks-ai-generated-content) — live since 2026-08-02 (see [`how-claude-marks.md`](how-claude-marks.md)).
- [OpenAI — Advancing content provenance](https://openai.com/index/advancing-content-provenance/) (2026-07-31) — OpenAI audio now carries SynthID.
- [Institute of AI PM — C2PA and SynthID guide](https://www.institutepm.com/knowledge-hub/ai-content-provenance-watermarking) — the two-layer industry model (hard-bound metadata + soft-bound watermark).
- California SB 942 — the US counterpart transparency law.

## 6. Steganography & invisible carriers (Layer A's target)

- Unicode invisible/format characters (Cf category, zero-width family, tag
  characters, variation selectors, PUA) as covert channels — long documented
  in steganography literature ([UTR #36 security considerations](https://www.unicode.org/reports/tr36/) and
  [UTS #39 security mechanisms](https://www.unicode.org/reports/tr39/) are the entry points).
- Homoglyph/confusable data: [Unicode confusables.txt](https://www.unicode.org/Public/security/latest/confusables.txt).

## How we use this literature

| Claim in this repo | Backing |
| --- | --- |
| Layer A removals are verifiable | Deterministic codepoint accounting; re-inspection |
| Layer B is best-effort, never certified | Impossibility results (§2); no public Claude detector; vendor caveats |
| Rewrite with a *non-origin* model | Re-stamping risk documented by all sampling-scheme papers |
| Pixel removal is conservative by default | Forensic-stealth results (§3) |
| Stripping ≠ undetectable | Classifier literature (§4) |
