# How Claude marks AI-generated content

Primary source: [Anthropic Help Center](https://support.claude.com/en/articles/16266773-how-claude-marks-ai-generated-content) (EU AI Act Article 50(2) Code of Practice on Transparency). Status below reflects the marking rollout that went live on **2026-08-02**.

## Policy snapshot

| Topic | Anthropic position |
| --- | --- |
| Live since | **2026-08-02** — new models mark content at launch; marking is active, not planned |
| Older models | Transition-period exceptions; being retrofitted |
| Surfaces | Claude Platform (API), Claude apps, Claude Code, Claude Cowork, Claude Tag |
| Cloud partners | AWS, Google Cloud, Microsoft Foundry — watermarks apply; signed file metadata depends on platform features |
| Regions | **Worldwide**, wherever Claude is offered |
| Detection | Third-party/user detection committed under the Code; **tooling not yet published** — watch the help article |

## Mechanism 1 — embedded text watermarks

- Applied at the **model level**, woven directly into the text itself — not a header, tag, or sidecar.
- Imperceptible; does not affect meaning, quality, or readability; survives copy/paste and **may persist through some editing**.
- Weakened (per Anthropic) by heavy editing, paraphrase, translation, merging with other writing, and short passages.

**Likely technical class** (Anthropic has not published the algorithm): statistical **token-sampling** watermarks (Kirchenbauer / SynthID-style). See `vendor-notes.md` and `mark-classes.md`.

Layer A scripts only remove **Unicode / homoglyph** carriers. Layer B (rewrite) targets statistical marks. There is no public Claude detector yet, so Layer B effectiveness on Claude text cannot be verified directly — the optional SynthID-Text scorer (`score_synthid_text.py`) verifies the *method* against a production-class watermark you control.

## Mechanism 2 — signed C2PA on files

- Digitally signed **Content Credentials** attached to supported file types (examples given: `.svg`, `.png`, `.jpg`).
- Signals the file was processed by Claude and lets you check tampering (integrity + provenance).
- Tamper-evident while present; removed by re-encoding, metadata scrubbing, format conversion, or many upload pipelines.
- Inspect with `c2patool` when installed; strip via `clean_image.py` / `clean_file.py` / ExifTool (Layer C).

## Caveats (Anthropic's own)

- A detected mark ⇒ content **may have been processed** by Claude — not proof of sole authorship. Claude may only have proofread, translated, summarized, or converted text that originated elsewhere.
- **No mark ≠ human-written.** Detection can fail when: content predates marking; text was heavily edited, paraphrased, translated, or merged; passages are too short for a reliable signal; metadata was stripped via conversion, re-saving, or screenshots.
- For builders: Anthropic advises assessing your own Article 50 transparency obligations; technical guidance on marking/detection is still pending.
