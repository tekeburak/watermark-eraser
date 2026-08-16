# Security Policy

## Supported versions

Security fixes target the latest code on the `main` branch and the most recent
GitHub Release (when releases exist). Older tags are not maintained.

## Reporting a vulnerability

**Do not open a public issue for security problems.**

Please report vulnerabilities privately using one of:

1. **[GitHub Security Advisories](https://github.com/tekeburak/watermark-eraser/security/advisories/new)**
   (preferred) — "Report a vulnerability" on the repository Security tab
2. A private message to the repository maintainers via GitHub

Include:

- A description of the issue and its impact
- Steps to reproduce or a proof of concept when safe to share
- Affected version or commit if known

## What to expect

- Acknowledgement when a maintainer has seen the report
- An initial assessment of severity and scope
- A coordinated fix and disclosure timeline when the report is valid

We will not take legal action against good-faith research that follows this
policy and avoids privacy harm, service disruption, or data destruction.

## Scope notes for watermark-eraser

watermark-eraser is a local agent skill and a set of Python scripts that
inspect and clean text, image and document files. Reports that matter most include:

- Path traversal or unsafe writes outside intended output paths
- Command injection when optional tools (`c2patool`, `exiftool`) are invoked
- Parser crashes or resource exhaustion on crafted images/text that affect
  the host beyond normal process failure
- Accidental leakage of user file contents in logs, error messages, or
  diagnostics that ship with the skill

Out of scope (unless they cause a concrete security impact in this project):

- Bypassing AI provenance marks for fraud, copyright evasion, or illegal
  non-disclosure (see skill `references/ethics.md`)
- Issues only in third-party tools (`c2patool`, `exiftool`, agents)
- Social engineering of individual users

## Prefer private disclosure

After a fix is released, we may credit reporters who want public credit.
Do not publish exploit details until a fixed release is available, unless we
agree otherwise.
