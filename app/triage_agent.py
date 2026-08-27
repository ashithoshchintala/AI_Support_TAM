# Import lru_cache so one agent can be reused.
from functools import lru_cache

# Import types for flexible ticket input.
from typing import Any, TypeAlias

# Import Pydantic validation errors.
from pydantic import ValidationError

# Import the Gemini client.
from app.llm_client import (
    GeminiStructuredClient,
    get_llm_client,
)

# Import the versioned Task 1 prompt.
from app.prompts.triage_v1 import (
    ISSUE_CATEGORIES,
    PRODUCT_AREAS,
    TRIAGE_SYSTEM_PROMPT,
    build_triage_user_prompt,
)

# Import local KB retrieval.
from app.retrieval import (
    KnowledgeBaseRetriever,
    RetrievalResult,
    has_confident_match,
)

# Import Task 1 schemas.
from app.schemas import (
    TicketTriageRequest,
    TicketTriageResult,
    Urgency,
)

# Import local PII redaction.
from app.utils.pii import redact_ticket


# Task 1 accepts raw text, JSON-like dictionaries,
# or an already validated request.
TicketInput: TypeAlias = (
    str
    | dict[str, Any]
    | TicketTriageRequest
)


# Minimum similarity required for a text-only KB match.
MINIMUM_KB_SIMILARITY = 0.15


class TicketInputError(ValueError):
    """
    Raised when Task 1 receives invalid ticket input.
    """


def normalize_raw_ticket(
    raw_text: str,
) -> TicketTriageRequest:
    """
    Convert raw text into subject and body fields.
    """

    cleaned_text = raw_text.strip()

    if not cleaned_text:
        raise TicketInputError(
            "Raw ticket text cannot be empty."
        )

    non_empty_lines = [
        line.strip()
        for line in cleaned_text.splitlines()
        if line.strip()
    ]

    first_line = non_empty_lines[0]

    if first_line.casefold().startswith("subject:"):
        subject = first_line.split(
            ":",
            maxsplit=1,
        )[1].strip()

        body = "\n".join(
            non_empty_lines[1:]
        ).strip()

        if not subject:
            subject = "No subject provided"

        if not body:
            body = subject

    else:
        subject = first_line[:160]
        body = cleaned_text

    return TicketTriageRequest(
        subject=subject,
        body=body,
    )


def normalize_ticket_input(
    ticket_input: TicketInput,
) -> TicketTriageRequest:
    """
    Convert supported Task 1 inputs into one validated format.
    """

    if isinstance(
        ticket_input,
        TicketTriageRequest,
    ):
        return ticket_input

    if isinstance(ticket_input, str):
        return normalize_raw_ticket(ticket_input)

    if isinstance(ticket_input, dict):
        try:
            return TicketTriageRequest.model_validate(
                ticket_input
            )

        except ValidationError as error:
            raise TicketInputError(
                "Ticket JSON must contain non-empty "
                "'subject' and 'body' fields."
            ) from error

    raise TicketInputError(
        "Ticket input must be raw text, a dictionary, "
        "or TicketTriageRequest."
    )


def canonical_taxonomy_value(
    value: str,
    allowed_values: tuple[str, ...],
) -> str:
    """
    Return the official capitalization of an allowed value.
    """

    allowed_lookup = {
        allowed_value.casefold(): allowed_value
        for allowed_value in allowed_values
    }

    return allowed_lookup.get(
        value.casefold(),
        "Unknown",
    )


def determine_responder_team(
    urgency: Urgency,
    issue_category: str,
    product_area: str,
) -> str:
    """
    Apply deterministic responder-team routing rules.
    """

    normalized_category = issue_category.casefold()
    normalized_area = product_area.casefold()

    if (
        urgency == Urgency.P1
        or normalized_category == "data loss"
    ):
        return "Incident Response"

    if normalized_category == "billing":
        return "Billing Operations"

    if normalized_category == "feature request":
        return "Product Management"

    if normalized_category in {
        "onboarding",
        "how-to",
    }:
        return "Customer Enablement"

    if normalized_area in {
        "authentication",
        "sso",
        "permissions",
        "encryption",
        "key management",
    }:
        return "Identity & Access Support"

    if (
        normalized_category == "integration"
        or normalized_area in {
            "connectors",
            "integrations",
            "data sources",
        }
    ):
        return "Integrations Support"

    if (
        normalized_category == "performance"
        or normalized_area in {
            "api",
            "bandwidth limits",
            "error handling",
            "pipeline monitoring",
        }
    ):
        return "Platform Reliability"

    if normalized_category == "bug":
        return "Product Support"

    return "General Support"


def validate_selected_kb_document(
    selected_document_name: str | None,
    retrieval_results: list[RetrievalResult],
) -> str | None:
    """
    Confirm the selected document has sufficient retrieved evidence.
    """

    if not selected_document_name:
        return None

    results_by_document = {
        result.document_name.casefold(): result
        for result in retrieval_results
    }

    selected_result = results_by_document.get(
        selected_document_name.casefold()
    )

    if selected_result is None:
        return None

    evidence_is_sufficient = (
        selected_result.exact_error_code_match
        or selected_result.similarity_score
        >= MINIMUM_KB_SIMILARITY
    )

    if not evidence_is_sufficient:
        return None

    return selected_result.document_name


def postprocess_triage_result(
    result: TicketTriageResult,
    retrieval_results: list[RetrievalResult],
    retrieval_confident: bool,
) -> TicketTriageResult:
    """
    Deterministically enforce taxonomies, routing, and KB evidence.
    """

    product_area = canonical_taxonomy_value(
        value=result.product_area,
        allowed_values=PRODUCT_AREAS,
    )

    issue_category = canonical_taxonomy_value(
        value=result.issue_category,
        allowed_values=ISSUE_CATEGORIES,
    )

    supported_document = validate_selected_kb_document(
        selected_document_name=(
            result.knowledge_base_document
        ),
        retrieval_results=retrieval_results,
    )

    known_issue = (
        result.known_issue
        and retrieval_confident
        and supported_document is not None
    )

    if not known_issue:
        supported_document = None

    recommended_team = determine_responder_team(
        urgency=result.urgency,
        issue_category=issue_category,
        product_area=product_area,
    )

    result_data = result.model_dump(
        mode="python"
    )

    result_data.update(
        {
            "product_area": product_area,
            "issue_category": issue_category,
            "known_issue": known_issue,
            "knowledge_base_document": (
                supported_document
            ),
            "recommended_team": recommended_team,
        }
    )

    return TicketTriageResult.model_validate(
        result_data
    )


class TicketTriageAgent:
    """
    Complete Task 1 ticket-triage pipeline.
    """

    def __init__(
        self,
        retriever: KnowledgeBaseRetriever | None = None,
        llm_client: GeminiStructuredClient | None = None,
    ) -> None:
        self.retriever = (
            retriever
            if retriever is not None
            else KnowledgeBaseRetriever()
        )

        self.llm_client = (
            llm_client
            if llm_client is not None
            else get_llm_client()
        )

    def triage(
        self,
        ticket_input: TicketInput,
    ) -> TicketTriageResult:
        """
        Triage one support ticket.
        """

        ticket = normalize_ticket_input(
            ticket_input
        )

        # Retrieval is local, so it can use the original ticket.
        retrieval_results = self.retriever.retrieve(
            subject=ticket.subject,
            body=ticket.body,
            top_k=3,
        )

        retrieval_confident = has_confident_match(
            results=retrieval_results,
            minimum_similarity=MINIMUM_KB_SIMILARITY,
        )

        # Only the redacted ticket is placed in the LLM prompt.
        safe_ticket, _redaction_counts = redact_ticket(
            ticket
        )

        user_prompt = build_triage_user_prompt(
            ticket=safe_ticket,
            retrieval_results=retrieval_results,
            retrieval_confident=retrieval_confident,
        )

        generated_result = (
            self.llm_client.generate_structured(
                system_prompt=TRIAGE_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                response_model=TicketTriageResult,
                seed=42,
            )
        )

        return postprocess_triage_result(
            result=generated_result,
            retrieval_results=retrieval_results,
            retrieval_confident=retrieval_confident,
        )


@lru_cache
def get_triage_agent() -> TicketTriageAgent:
    """
    Create and reuse one Task 1 agent.
    """

    return TicketTriageAgent()


def triage_ticket(
    ticket_input: TicketInput,
) -> TicketTriageResult:
    """
    Public Python entry point required by Task 1.
    """

    return get_triage_agent().triage(
        ticket_input
    )