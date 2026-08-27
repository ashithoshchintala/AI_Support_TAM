# Prompt Changelog

This file records changes to production prompts so evaluation results
can be traced to the exact prompt behaviour.

## triage-v1.0.0 — 2026-08-27
## tam-v1.0.0 — 2026-08-27

Initial Task 2 TAM account-health prompt.

- Required exactly three structured output sections.
- Required a 3–5 sentence executive summary.
- Added deterministic risk-priority ordering.
- Limited risk types to escalation, churn, renewal, adoption, and
  operational.
- Required churn and escalation flags to use exact ticket IDs and
  direct quote candidates.
- Prohibited account escalation notes from being presented as direct
  ticket quotes.
- Added 3–5 actionable TAM talking points.
- Added prompt-injection and data-minimization safeguards.
- Added deterministic formatting and factual-grounding rules.

Initial Task 1 prompt.

- Added the product-area and issue-category taxonomy derived from the
  provided synthetic tickets.
- Added the required P1–P4 urgency rubric.
- Added deterministic responder-team routing rules.
- Added retrieved knowledge-base evidence.
- Required exact knowledge-base filenames.
- Added safeguards against false known-issue claims.
- Added handling for ambiguous tickets using `Unknown`.
- Added prompt-injection instructions.
- Added safe first-response requirements.