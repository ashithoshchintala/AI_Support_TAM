# Import regular expressions for sentence splitting.
import re

# Import datetime for the optional as-of date.
from datetime import datetime

# Import Any for JSON-compatible context dictionaries.
from typing import Any

# Import the account-ticket repository.
from app.data_repository import (
    DataRepository,
    get_repository,
)

# Import validated dataset models.
from app.schemas import (
    AccountSummary,
    SupportTicket,
)

# Import local PII redaction.
from app.utils.pii import redact_pii


# Version the deterministic context-building logic.
TAM_CONTEXT_VERSION = "tam-context-v1.0.0"


# Split text after sentence-ending punctuation or new lines.
SENTENCE_SPLIT_PATTERN = re.compile(
    r"(?<=[.!?])\s+|\n+"
)


# Strong churn-risk phrases.
CHURN_PHRASES = (
    "cancel",
    "cancellation",
    "churn",
    "competitor",
    "switch to",
    "switching",
    "not renew",
    "won't renew",
    "will not renew",
    "terminate",
    "leaving",
    "replace your",
    "vendor evaluation",
)


# Strong escalation-risk phrases.
ESCALATION_PHRASES = (
    "escalat",
    "executive",
    "legal",
    "unacceptable",
    "production outage",
    "production down",
    "all users",
    "no users",
    "data loss",
    "security breach",
    "critical impact",
    "p1",
)


def detect_risk_types(
    text: str,
) -> tuple[str, ...]:
    """
    Detect churn and escalation language in one text section.
    """

    normalized_text = text.casefold()

    detected_types: list[str] = []

    if any(
        phrase in normalized_text
        for phrase in CHURN_PHRASES
    ):
        detected_types.append("churn")

    if any(
        phrase in normalized_text
        for phrase in ESCALATION_PHRASES
    ):
        detected_types.append("escalation")

    return tuple(detected_types)


def quote_exists_in_ticket(
    ticket: SupportTicket,
    direct_quote: str,
) -> bool:
    """
    Confirm that a quote exists exactly in the source ticket.
    """

    return (
        direct_quote in ticket.subject
        or direct_quote in ticket.body
    )


def extract_safe_quote_candidates(
    ticket: SupportTicket,
    maximum_quotes: int = 4,
) -> list[dict[str, str]]:
    """
    Extract exact, PII-free churn and escalation quotes.
    """

    candidates: list[dict[str, str]] = []
    seen_candidates: set[tuple[str, str]] = set()

    # Check the body first because it usually contains
    # stronger supporting evidence than the subject.
    source_texts = (
        ticket.body,
        ticket.subject,
    )

    for source_text in source_texts:
        sentences = SENTENCE_SPLIT_PATTERN.split(
            source_text
        )

        for sentence in sentences:
            candidate_quote = sentence.strip()

            if len(candidate_quote) < 8:
                continue

            detected_types = detect_risk_types(
                candidate_quote
            )

            if not detected_types:
                continue

            redacted_quote, redaction_counts = redact_pii(
                candidate_quote
            )

            total_redactions = sum(
                redaction_counts.values()
            )

            # A redacted quote would no longer be an exact quote.
            # Therefore, exclude sentences containing detected PII.
            if (
                total_redactions > 0
                or redacted_quote != candidate_quote
            ):
                continue

            if not quote_exists_in_ticket(
                ticket=ticket,
                direct_quote=candidate_quote,
            ):
                continue

            for risk_type in detected_types:
                candidate_key = (
                    risk_type,
                    candidate_quote,
                )

                if candidate_key in seen_candidates:
                    continue

                candidates.append(
                    {
                        "risk_type": risk_type,
                        "direct_quote": candidate_quote,
                    }
                )

                seen_candidates.add(candidate_key)

                if len(candidates) >= maximum_quotes:
                    return candidates

    return candidates


def build_safe_account_payload(
    account: AccountSummary,
) -> dict[str, Any]:
    """
    Select only account fields needed for health analysis.
    """

    if account.seats_licensed > 0:
        seat_utilization = round(
            account.seats_active
            / account.seats_licensed,
            4,
        )
    else:
        seat_utilization = None

    safe_escalation_notes = [
        redact_pii(note)[0]
        for note in account.escalation_notes
    ]

    return {
        "account_id": account.account_id,
        "company": account.company,
        "industry": account.industry,
        "region": account.region,
        "plan_tier": account.plan_tier,
        "arr_usd": account.arr_usd,
        "customer_since": (
            account.customer_since.isoformat()
        ),
        "renewal_date": (
            account.renewal_date.isoformat()
        ),
        "last_qbr_date": (
            account.last_qbr_date.isoformat()
        ),
        "health_status": account.health_status,
        "usage_trend": account.usage_trend,
        "last_login_days_ago": (
            account.last_login_days_ago
        ),
        "nps_score": account.nps_score,
        "seats_active": account.seats_active,
        "seats_licensed": account.seats_licensed,
        "seat_utilization": seat_utilization,
        "open_tickets": account.open_tickets,
        "p1_tickets_last_30d": (
            account.p1_tickets_last_30d
        ),
        "products": list(account.products),
        "integrations_active": list(
            account.integrations_active
        ),
        "account_escalation_notes": (
            safe_escalation_notes
        ),
    }


def build_safe_ticket_payload(
    ticket: SupportTicket,
) -> dict[str, Any]:
    """
    Create a minimized, redacted ticket representation.
    """

    safe_subject = redact_pii(
        ticket.subject
    )[0]

    safe_body = redact_pii(
        ticket.body
    )[0]

    return {
        "ticket_id": ticket.ticket_id,
        "created_at": ticket.created_at.isoformat(),
        "updated_at": ticket.updated_at.isoformat(),
        "status": ticket.status,
        "urgency": ticket.urgency.value,
        "category": ticket.category,
        "product": ticket.product,
        "product_area": ticket.product_area,
        "subject": safe_subject,
        "body": safe_body,
        "satisfaction_score": (
            ticket.satisfaction_score
        ),
        "tags": list(ticket.tags),
        "direct_quote_candidates": (
            extract_safe_quote_candidates(ticket)
        ),
    }


class TAMContextBuilder:
    """
    Build deterministic, privacy-minimized Task 2 context.
    """

    def __init__(
        self,
        repository: DataRepository | None = None,
    ) -> None:
        self.repository = (
            repository
            if repository is not None
            else get_repository()
        )

    def build(
        self,
        account_id: str,
        as_of_date: datetime | None = None,
    ) -> dict[str, Any]:
        """
        Build account and recent-ticket context.
        """

        lookup = (
            self.repository.get_recent_account_tickets(
                account_id=account_id,
                as_of_date=as_of_date,
            )
        )

        safe_tickets = [
            build_safe_ticket_payload(ticket)
            for ticket in lookup.tickets
        ]

        return {
            "context_version": TAM_CONTEXT_VERSION,
            "snapshot_date": (
                lookup.as_of_date.isoformat()
            ),
            "window_start": (
                lookup.cutoff_date.isoformat()
            ),
            "window_days": 90,
            "match_method": lookup.match_method,
            "data_quality_warnings": list(
                lookup.warnings
            ),
            "account": build_safe_account_payload(
                lookup.account
            ),
            "recent_ticket_count": len(
                safe_tickets
            ),
            "recent_tickets": safe_tickets,
        }


def build_tam_context(
    account_id: str,
    as_of_date: datetime | None = None,
) -> dict[str, Any]:
    """
    Public helper for creating Task 2 context.
    """

    return TAMContextBuilder().build(
        account_id=account_id,
        as_of_date=as_of_date,
    )