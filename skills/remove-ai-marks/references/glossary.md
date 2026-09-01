# Glossary — watermark & provenance terminology

Short, precise definitions for the terms used across this repo and the
literature. Cross-linked from the other reference docs.

## Marking fundamentals

| Term | Definition |
| --- | --- |
| **Provenance** | Information about where content came from and what happened to it. Watermarks and C2PA are two different provenance mechanisms. |
| **Watermark** | A signal embedded *in the content itself* (token choices, pixels, audio features) that a keyed detector can read back. Survives format conversion by design. |
| **Metadata mark** | Provenance stored *next to* the content (EXIF tag, XMP packet, C2PA manifest). Trivially removed by re-encoding; that's Layer C's job. |
| **Hard-bound vs soft-bound** | Hard-bound: the mark is embedded in the file bytes (C2PA manifest). Soft-bound: an imperceptible watermark that can *re-attach* remote metadata after the file is stripped — the reason stripping metadata is not the whole story. |
| **Edit-based watermark** | Carriers injected during/after generation as invisible Unicode or synonym rules. Our Layer A target. |
| **Statistical / token-sampling watermark** | Signal spread across *which* tokens the sampler picked. No single character is "the mark"; removal requires rewording. Layer B target. |
| **Pixel-domain watermark** | Signal in image pixels (SynthID-media, StegaStamp, Tree-Ring, StableSignature). Optional CtrlRegen backend attacks this. |

## Scheme mechanics (text)

| Term | Definition |
| --- | --- |
| **Green list / red list** | KGW's partition of the vocabulary per context: sampling is biased toward green tokens; detection counts green hits. |
| **g-value** | SynthID-Text's per-token bit derived from hashing the n-gram key; watermarked text has g-values skewed toward 1. |
| **Tournament sampling** | SynthID-Text's mechanism: candidates compete pairwise and the g-value rule decides the winner, biasing output without distorting quality much. |
| **Detection key** | The secret(s) that make the hash partition predictable. Without the key you cannot distinguish watermarked from clean text. |
| **Distortion-free / unbiased watermark** | Reweighting that preserves the output distribution in expectation (e.g. Γ/Δ reweighting). |
| **Entropy-aware watermark** | Design that adapts to low-entropy spans (code, lists) where normal watermarks are weak (PostMark). |
| **Semantic watermark** | Signal tied to meaning clusters rather than tokens (SemStamp); paragraph-level and paraphrase-robust. |

## Detection & evaluation

| Term | Definition |
| --- | --- |
| **FPR / TPR** | False-positive / true-positive rates. Detection thresholds are chosen at a target FPR *per text length* — short texts are inherently noisy. |
| **z-score (KGW detection)** | How many standard deviations the observed green-token count is above expectation under no watermark. |
| **Robustness** | How much the detection signal survives attack: paraphrase, translation, cropping, re-encoding, screenshot. |
| **Score-based detector** | Returns a continuous score (e.g. SynthID's [0,1] mean g-value ≈ 0.5 unwatermarked); thresholding is your decision. |
| **Watermark-agnostic classifier** | A detector that flags AI content *without* a watermark key (DetectGPT, Binoculars, commercial services). Stripping a watermark does not evade these. |
| **Low-reliability regime** | Fewer scored units than the threshold computation assumes (our scorer warns under 10 scored n-grams). |

## File/container terms (Layer C)

| Term | Definition |
| --- | --- |
| **C2PA manifest** | A signed JSON claim about an asset's history, stored in a JUMBF box (JPEG/PNG/WebP) or XMP packet. |
| **JUMBF** | JPEG 2000 metadata box format that C2PA rides inside (JPEG APP11, PNG `c2pa`/`caBX` chunks). |
| **XMP** | Adobe's RDF-based metadata packet, embedded in many formats. |
| **EXIF** | Camera/image metadata (maker notes, GPS, software strings). |
| **docProps / customXml** | OOXML metadata parts (DOCX/PPTX/XLSX) where generator strings and provenance injects live. |
| **Soft binding (again, practically)** | e.g. a stripped C2PA manifest that a watermark can help re-link. Out of scope for this repo and said so. |

## Unicode carriers (Layer A)

| Term | Definition |
| --- | --- |
| **Cf (format) characters** | Unicode category of invisible formatting controls (ZWSP, LRM/RLM, joiners…) — the classic covert channel. |
| **Zero-width family** | ZWSP U+200B, ZWNJ U+200C, ZWJ U+200D, word joiner U+2060, BOM/ZWNBSP U+FEFF. |
| **Tag characters** | U+E0000 block (flag emoji use them legitimately — we preserve those runs). |
| **Variation selectors** | U+FE00–FE0F and VS17–256 (U+E0100–E01EF); VS16 makes emoji colorful — preserved after an emoji base. |
| **PUA (Private Use Area)** | U+E000–F8FF + planes 15/16; icon fonts live there, so we flag always but strip only in aggressive mode. |
| **Confusable / homoglyph** | A character visually indistinguishable from another (Cyrillic `а` vs Latin `a`). |
| **Dense carrier run** | ≥4 consecutive invisible chars — the shape of bit-encoded payloads, flagged as a stronger signal than isolated marks. |
| **Bidi controls** | RLO/LRO/LRI… — invisible direction overrides; a spoofing vector, always stripped. |

## This repo's own vocabulary

| Term | Definition |
| --- | --- |
| **Layer A / B / C** | Invisible Unicode scrub / statistical rewrite / metadata strip. |
| **Verifiable vs best-effort** | Verifiable: counted and re-inspected (A, C). Best-effort: no certification possible (B). Every report says which is which. |
| **Non-origin rewrite** | Rewriting with a model from a *different* vendor than the suspected watermark origin, to avoid re-stamping. |
| **Self-verification** | Watermarking your own text with your own keys, rewriting, and scoring before/after (`--score-synthid-text`) — the honest way to measure Layer B. |
