# Import datetime for deterministic optional as-of dates.
from datetime import datetime

# Import lru_cache for response caching.
from functools import lru_cache

# Import Any for TAM context dictionaries.
from typing import Any

# Import the local repository.
from app.data_repository import (
    DataRepository,
    get_repository,
)

# Import the reusable Gemini client.
from app.llm_client import (
    GeminiStructuredClient,
    get_llm_client,
)

# Import the versioned Task 2 prompt.
from app.prompts.tam_summary_v1 import (
    TAM_SYSTEM_PROMPT,
    build_tam_user_prompt,
)

# Import Task 2 output schemas.
from app.schemas import (
    AccountBrief,
    RiskFlag,
    RiskType,
)

# Import context and quote-validation helpers.
from app.tam_context import (
    SENTENCE_SPLIT_PATTERN,
    TAMContextBuilder,
    quote_exists_in_ticket,
)


# Deterministic risk ordering required by the prompt.
RISK_PRIORITY = {
    RiskType.ESCALATION: 1,
    RiskType.CHURN: 2,
    RiskType.RENEWAL: 3,
    RiskType.ADOPTION: 4,
    RiskType.OPERATIONAL: 5,
}


def ensure_sentence_ending(text: str) -> str:
    """
    Ensure a sentence ends with normal punctuation.
    """

    cleaned_text = text.strip()

    if not cleaned_text:
        return cleaned_text

    if cleaned_text.endswith((".", "!", "?")):
        return cleaned_text

    return cleaned_text + "."


def normalize_executive_summary(
    executive_summary: str,
    tam_context: dict[str, Any],
) -> str:
    """
    Guarantee that the executive summary has 3–5 sentences.
    """

    sentences = [
        ensure_sentence_ending(sentence)
        for sentence in SENTENCE_SPLIT_PATTERN.split(
            executive_summary
        )
        if sentence.strip()
    ]

    account = tam_context["account"]
    ticket_count = tam_context["recent_ticket_count"]

    fallback_sentences = [
        (
            f"The recorded account health status is "
            f"{account['health_status']}."
        ),
        (
            f"The account had {ticket_count} support tickets "
            f"in the supplied 90-day window."
        ),
        (
            f"The recorded usage trend is "
            f"{account['usage_trend']}."
        ),
    ]

    existing_sentences = {
        sentence.casefold()
        for sentence in sentences
    }

    for fallback_sentence in fallback_sentences:
        if len(sentences) >= 3:
            break

        if fallback_sentence.casefold() in existing_sentences:
            continue

        sentences.append(fallback_sentence)
        existing_sentences.add(
            fallback_sentence.casefold()
        )

    return " ".join(sentences[:5])


def build_allowed_quote_candidates(
    tam_context: dict[str, Any],
) -> set[tuple[str, str, str]]:
    """
    Build allowed (ticket, risk type, quote) combinations.
    """

    allowed_candidates: set[
        tuple[str, str, str]
    ] = set()

    for ticket in tam_context["recent_tickets"]:
        ticket_id = ticket["ticket_id"]

        for candidate in ticket[
            "direct_quote_candidates"
        ]:
            allowed_candidates.add(
                (
                    ticket_id,
                    candidate["risk_type"],
                    candidate["direct_quote"],
                )
            )

    return allowed_candidates


def validate_and_sort_risks(
    risks: list[RiskFlag],
    tam_context: dict[str, Any],
    repository: DataRepository,
) -> list[RiskFlag]:
    """
    Verify evidence, remove unsupported risks, and sort them.
    """

    allowed_candidates = (
        build_allowed_quote_candidates(
            tam_context
        )
    )

    recent_ticket_ids = {
        ticket["ticket_id"]
        for ticket in tam_context["recent_tickets"]
    }

    source_tickets = {
        ticket.ticket_id: ticket
        for ticket in repository.tickets
    }

    ticket_timestamps = {
        ticket["ticket_id"]: datetime.fromisoformat(
            ticket["created_at"]
        ).timestamp()
        for ticket in tam_context["recent_tickets"]
    }

    validated_risks: list[RiskFlag] = []
    seen_risks: set[tuple[str, ...]] = set()

    for risk in risks:
        risk_type_value = risk.risk_type.value
        ticket_id = risk.ticket_id
        direct_quote = risk.direct_quote

        if risk.risk_type in {
            RiskType.CHURN,
            RiskType.ESCALATION,
        }:
            candidate_key = (
                ticket_id or "",
                risk_type_value,
                direct_quote or "",
            )

            source_ticket = source_tickets.get(
                ticket_id or ""
            )

            evidence_is_valid = (
                candidate_key in allowed_candidates
                and ticket_id in recent_ticket_ids
                and source_ticket is not None
                and direct_quote is not None
                and quote_exists_in_ticket(
                    ticket=source_ticket,
                    direct_quote=direct_quote,
                )
            )

            # Drop unsupported churn or escalation claims.
            if not evidence_is_valid:
                continue

        else:
            updated_ticket_id = ticket_id
            updated_direct_quote = direct_quote

            if (
                updated_ticket_id is not None
                and updated_ticket_id
                not in recent_ticket_ids
            ):
                updated_ticket_id = None
                updated_direct_quote = None

            if updated_direct_quote is not None:
                source_ticket = source_tickets.get(
                    updated_ticket_id or ""
                )

                quote_is_valid = (
                    source_ticket is not None
                    and updated_ticket_id
                    in recent_ticket_ids
                    and quote_exists_in_ticket(
                        ticket=source_ticket,
                        direct_quote=updated_direct_quote,
                    )
                )

                if not quote_is_valid:
                    updated_ticket_id = None
                    updated_direct_quote = None

            risk_data = risk.model_dump(
                mode="python"
            )

            risk_data.update(
                {
                    "ticket_id": updated_ticket_id,
                    "direct_quote": (
                        updated_direct_quote
                    ),
                }
            )

            risk = RiskFlag.model_validate(
                risk_data
            )

        if risk.risk_type in {
            RiskType.CHURN,
            RiskType.ESCALATION,
        }:
            duplicate_key = (
                risk.risk_type.value,
                risk.ticket_id or "",
                risk.direct_quote or "",
            )

        else:
            duplicate_key = (
                risk.risk_type.value,
                risk.description.casefold(),
            )

        if duplicate_key in seen_risks:
            continue

        seen_risks.add(duplicate_key)
        validated_risks.append(risk)

    validated_risks.sort(
        key=lambda risk: (
            RISK_PRIORITY.get(
                risk.risk_type,
                99,
            ),
            -ticket_timestamps.get(
                risk.ticket_id or "",
                0.0,
            ),
            risk.description.casefold(),
        )
    )

    return validated_risks


def normalize_talking_points(
    talking_points: list[str],
    tam_context: dict[str, Any],
) -> list[str]:
    """
    Guarantee 3–5 unique TAM talking points.
    """

    normalized_points: list[str] = []
    seen_points: set[str] = set()

    for talking_point in talking_points:
        cleaned_point = talking_point.strip()

        if not cleaned_point:
            continue

        duplicate_key = cleaned_point.casefold()

        if duplicate_key in seen_points:
            continue

        normalized_points.append(cleaned_point)
        seen_points.add(duplicate_key)

        if len(normalized_points) == 5:
            break

    account = tam_context["account"]
    ticket_count = tam_context["recent_ticket_count"]

    seat_utilization = account["seat_utilization"]

    if seat_utilization is None:
        utilization_text = "unavailable"
    else:
        utilization_text = (
            f"{seat_utilization * 100:.1f}%"
        )

    fallback_points = [
        (
            f"Review ownership and next steps for the "
            f"{ticket_count} tickets in the 90-day window."
        ),
        (
            f"Discuss the {account['usage_trend']} usage "
            f"trend and {utilization_text} seat utilization."
        ),
        (
            f"Confirm priorities before the "
            f"{account['renewal_date']} renewal date."
        ),
    ]

    for fallback_point in fallback_points:
        if len(normalized_points) >= 3:
            break

        duplicate_key = fallback_point.casefold()

        if duplicate_key in seen_points:
            continue

        normalized_points.append(fallback_point)
        seen_points.add(duplicate_key)

    return normalized_points[:5]


def postprocess_account_brief(
    brief: AccountBrief,
    tam_context: dict[str, Any],
    repository: DataRepository,
) -> AccountBrief:
    """
    Apply deterministic Task 2 validation and formatting.
    """

    validated_risks = validate_and_sort_risks(
        risks=brief.open_risks_and_flagged_issues,
        tam_context=tam_context,
        repository=repository,
    )

    executive_summary = (
        normalize_executive_summary(
            executive_summary=brief.executive_summary,
            tam_context=tam_context,
        )
    )

    talking_points = normalize_talking_points(
        talking_points=(
            brief.recommended_talking_points
        ),
        tam_context=tam_context,
    )

    return AccountBrief(
        executive_summary=executive_summary,
        open_risks_and_flagged_issues=(
            validated_risks
        ),
        recommended_talking_points=(
            talking_points
        ),
    )


class TAMSummarizer:
    """
    Complete Task 2 account-health summarisation pipeline.
    """

    def __init__(
        self,
        repository: DataRepository | None = None,
        llm_client: GeminiStructuredClient | None = None,
    ) -> None:
        self.repository = (
            repository
            if repository is not None
            else get_repository()
        )

        self.llm_client = (
            llm_client
            if llm_client is not None
            else get_llm_client()
        )

        self.context_builder = TAMContextBuilder(
            repository=self.repository
        )

    @lru_cache(maxsize=128)
    def _summarize_cached(
        self,
        account_id: str,
        as_of_date_iso: str | None,
    ) -> AccountBrief:
        """
        Generate and cache one deterministic account brief.
        """

        if as_of_date_iso is None:
            as_of_date = None
        else:
            as_of_date = datetime.fromisoformat(
                as_of_date_iso
            )

        tam_context = self.context_builder.build(
            account_id=account_id,
            as_of_date=as_of_date,
        )

        user_prompt = build_tam_user_prompt(
            tam_context
        )

        generated_brief = (
            self.llm_client.generate_structured(
                system_prompt=TAM_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                response_model=AccountBrief,
                seed=42,
            )
        )

        return postprocess_account_brief(
            brief=generated_brief,
            tam_context=tam_context,
            repository=self.repository,
        )

    def summarize(
        self,
        account_id: str,
        as_of_date: datetime | None = None,
    ) -> AccountBrief:
        """
        Create a TAM brief for one account ID.
        """

        normalized_account_id = account_id.strip()

        if not normalized_account_id:
            raise ValueError(
                "account_id cannot be empty."
            )

        if as_of_date is None:
            as_of_date_iso = None
        else:
            as_of_date_iso = (
                as_of_date.isoformat()
            )

        cached_brief = self._summarize_cached(
            normalized_account_id,
            as_of_date_iso,
        )

        # Return a copy so callers cannot modify the cache.
        return cached_brief.model_copy(
            deep=True
        )


@lru_cache
def get_tam_summarizer() -> TAMSummarizer:
    """
    Create and reuse one Task 2 summariser.
    """

    return TAMSummarizer()


def summarize_account(
    account_id: str,
    as_of_date: datetime | None = None,
) -> AccountBrief:
    """
    Public Python entry point required by Task 2.
    """

    return get_tam_summarizer().summarize(
        account_id=account_id,
        as_of_date=as_of_date,
    )