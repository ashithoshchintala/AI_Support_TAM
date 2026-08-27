# Design Note

## System architecture

The solution is organized as a modular Python application with separate components for data access, retrieval, prompt construction, structured model interaction, validation, evaluation, and presentation. This separation allows each component to be tested independently and prevents business rules from becoming tightly coupled to the user interface. The Streamlit application calls the same `triage_ticket()` and `summarize_account()` functions used by the evaluation harness, ensuring that the demonstrated interface and evaluated pipelines behave consistently.

The data repository loads and validates the supplied dataset of 500 tickets and 50 accounts. Account lookup first uses the account ID. Because the source data contains inconsistent account identifiers, the repository can use an exact normalized company-name fallback when necessary and returns a warning describing that match method. Task 2 uses a deterministic 90-day ticket window and stable newest-first ordering, making repeated account summaries reproducible.

## Task 1: Support-ticket triage

Task 1 accepts either raw ticket text or structured input containing a subject and body. Input is validated through Pydantic before processing. Sensitive information—including email addresses, phone numbers, IP addresses, payment-card numbers, and secrets—is redacted before ticket content is sent to the external model. Technical evidence such as application error codes remains available because it is important for classification and knowledge-base retrieval.

The retrieval component searches the local knowledge base using transparent, deterministic signals such as matching error codes and relevant terms. An issue is labelled as known only when the retrieval confidence satisfies the defined threshold. If no confident match exists, the system returns no knowledge-base document rather than inventing a reference.

Gemini receives the redacted ticket, grounded retrieval context, taxonomy, and versioned instructions. Its response is validated against the `TicketTriageResult` schema, which requires product area, issue category, urgency, reasoning, known-issue status, recommended team, and a customer-facing draft response. Ticket text is treated as untrusted data, so instructions embedded inside a ticket cannot override the system’s routing rules or reveal internal prompts.

## Task 2: TAM account brief

Task 2 combines validated account information with tickets from the previous 90 days. The summarizer produces exactly three sections: an executive summary, open risks and flagged issues, and three to five recommended talking points. Context is normalized and ordered before generation to improve repeatability.

Churn and escalation risks require direct evidence from a recent source ticket. Every supplied quote is validated as an exact substring of its referenced ticket. Account-level health and notes may inform the executive summary or other supported risks, but they cannot independently create a ticket-backed churn or escalation flag. This intentionally conservative design reduces hallucination and makes important risk claims auditable. Risks are also returned in a fixed priority order so the most important issues appear first.

Missing accounts raise a controlled `AccountNotFoundError` instead of producing fabricated data or an unpredictable crash. Internal fallback metadata and repository diagnostics are used for validation but are not exposed in the customer-facing brief or Streamlit interface.

## Reliability, evaluation, and trade-offs

The evaluation harness contains five cases for each task, including an adversarial case for both. Each result receives named deterministic checks, strict pass/fail status, and a quality score between zero and one. All ten end-to-end evaluation cases passed with an average quality score of 1.0. Eight additional automated tests verify dataset loading, account matching, date filtering, stable ordering, retrieval confidence, controlled errors, and PII redaction without making Gemini requests. Prompt versions are recorded in the generated reports to make later changes traceable.

Rule-based evaluation is fast, reproducible, and inexpensive, but it cannot measure every aspect of writing quality. Similarly, deterministic keyword and error-code retrieval is more explainable than fully semantic retrieval but may miss conceptually similar issues that use unfamiliar language. The strict quote policy can omit a genuine risk when no qualifying ticket quote exists, but this is preferable to presenting unsupported claims.

For production deployment, I would add role-based access control, encrypted storage, centralized secret management, audit logging, rate limits, monitoring, and human approval for high-impact customer communications. These controls would complement the existing grounding, redaction, structured validation, and controlled-error mechanisms.
