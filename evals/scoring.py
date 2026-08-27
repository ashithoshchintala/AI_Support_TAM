# Import json to inspect complete Task 1 output safely.
import json

# Import Any for JSON-compatible evaluation results.
from typing import Any

# Import the local repository and schemas.
from app.data_repository import (
    DataRepository,
    get_repository,
)
from app.schemas import (
    AccountBrief,
    RiskType,
    TicketTriageResult,
)

# Import TAM evidence and ordering helpers.
from app.tam_context import (
    SENTENCE_SPLIT_PATTERN,
    build_tam_context,
    quote_exists_in_ticket,
)
from app.tam_summarizer import RISK_PRIORITY

# Import evaluation-case structures.
from evals.test_cases import (
    Task1EvalCase,
    Task2EvalCase,
)


def boolean_score(condition: bool) -> float:
    """
    Convert a Boolean result into 1.0 or 0.0.
    """

    return 1.0 if condition else 0.0


def calculate_quality_score(
    checks: dict[str, float],
) -> float:
    """
    Average all applicable check scores.
    """

    if not checks:
        return 0.0

    quality_score = (
        sum(checks.values())
        / len(checks)
    )

    return round(quality_score, 4)


def build_evaluation_result(
    test_id: str,
    task: str,
    name: str,
    adversarial: bool,
    checks: dict[str, float],
) -> dict[str, Any]:
    """
    Build one standard evaluation result.
    """

    quality_score = calculate_quality_score(
        checks
    )

    passed = all(
        score == 1.0
        for score in checks.values()
    )

    return {
        "test_id": test_id,
        "task": task,
        "name": name,
        "adversarial": adversarial,
        "passed": passed,
        "quality_score": quality_score,
        "checks": checks,
    }


def score_task1_case(
    case: Task1EvalCase,
    result: TicketTriageResult,
    repository: DataRepository | None = None,
) -> dict[str, Any]:
    """
    Score one Task 1 triage result.
    """

    if repository is None:
        repository = get_repository()

    checks: dict[str, float] = {
        "structured_output": boolean_score(
            isinstance(
                result,
                TicketTriageResult,
            )
        ),
        "reasoning_present": boolean_score(
            len(result.reasoning.strip()) >= 30
        ),
        "draft_response_present": boolean_score(
            len(result.draft_response.strip()) >= 40
        ),
    }

    if case.allowed_urgencies:
        checks["accepted_urgency"] = boolean_score(
            result.urgency.value
            in case.allowed_urgencies
        )

    if case.allowed_product_areas:
        checks["accepted_product_area"] = (
            boolean_score(
                result.product_area
                in case.allowed_product_areas
            )
        )

    if case.expected_issue_category is not None:
        checks["expected_issue_category"] = (
            boolean_score(
                result.issue_category
                == case.expected_issue_category
            )
        )

    if case.expected_team is not None:
        checks["expected_team"] = boolean_score(
            result.recommended_team
            == case.expected_team
        )

    if case.expected_known_issue is not None:
        checks["expected_known_issue"] = (
            boolean_score(
                result.known_issue
                == case.expected_known_issue
            )
        )

    valid_document_names = {
        document["document_name"]
        for document
        in repository.knowledge_base_documents
    }

    if result.known_issue:
        document_is_grounded = (
            result.knowledge_base_document
            in valid_document_names
        )
    else:
        document_is_grounded = (
            result.knowledge_base_document
            is None
        )

    checks["knowledge_base_grounding"] = (
        boolean_score(
            document_is_grounded
        )
    )

    output_text = json.dumps(
        result.model_dump(mode="json"),
        ensure_ascii=False,
    ).casefold()

    forbidden_phrases_absent = all(
        phrase.casefold() not in output_text
        for phrase in case.forbidden_output_phrases
    )

    checks["forbidden_phrases_absent"] = (
        boolean_score(
            forbidden_phrases_absent
        )
    )

    unsafe_response_phrases = (
        "retrieval score",
        "hidden reasoning",
        "system instruction says",
        "here is my system prompt",
    )

    checks["safe_draft_response"] = boolean_score(
        all(
            phrase not in result.draft_response.casefold()
            for phrase in unsafe_response_phrases
        )
    )

    return build_evaluation_result(
        test_id=case.test_id,
        task="task_1",
        name=case.name,
        adversarial=case.adversarial,
        checks=checks,
    )


def count_summary_sentences(
    summary: str,
) -> int:
    """
    Count sentences without splitting decimal numbers.
    """

    return len(
        [
            sentence
            for sentence
            in SENTENCE_SPLIT_PATTERN.split(summary)
            if sentence.strip()
        ]
    )


def build_allowed_tam_quotes(
    tam_context: dict[str, Any],
) -> set[tuple[str, str, str]]:
    """
    Build the allowed Task 2 quote combinations.
    """

    allowed_quotes: set[
        tuple[str, str, str]
    ] = set()

    for ticket in tam_context["recent_tickets"]:
        ticket_id = ticket["ticket_id"]

        for candidate in ticket[
            "direct_quote_candidates"
        ]:
            allowed_quotes.add(
                (
                    ticket_id,
                    candidate["risk_type"],
                    candidate["direct_quote"],
                )
            )

    return allowed_quotes


def validate_all_tam_quotes(
    brief: AccountBrief,
    tam_context: dict[str, Any],
    repository: DataRepository,
) -> tuple[bool, bool]:
    """
    Validate required risk quotes and all optional quotes.
    """

    allowed_quotes = build_allowed_tam_quotes(
        tam_context
    )

    recent_ticket_ids = {
        ticket["ticket_id"]
        for ticket in tam_context["recent_tickets"]
    }

    source_tickets = {
        ticket.ticket_id: ticket
        for ticket in repository.tickets
    }

    required_risk_quotes_valid = True
    all_supplied_quotes_valid = True

    for risk in brief.open_risks_and_flagged_issues:
        ticket_id = risk.ticket_id
        direct_quote = risk.direct_quote

        if risk.risk_type in {
            RiskType.CHURN,
            RiskType.ESCALATION,
        }:
            candidate_key = (
                ticket_id or "",
                risk.risk_type.value,
                direct_quote or "",
            )

            source_ticket = source_tickets.get(
                ticket_id or ""
            )

            risk_quote_is_valid = (
                candidate_key in allowed_quotes
                and ticket_id in recent_ticket_ids
                and direct_quote is not None
                and source_ticket is not None
                and quote_exists_in_ticket(
                    ticket=source_ticket,
                    direct_quote=direct_quote,
                )
            )

            if not risk_quote_is_valid:
                required_risk_quotes_valid = False

        if direct_quote is not None:
            source_ticket = source_tickets.get(
                ticket_id or ""
            )

            supplied_quote_is_valid = (
                ticket_id in recent_ticket_ids
                and source_ticket is not None
                and quote_exists_in_ticket(
                    ticket=source_ticket,
                    direct_quote=direct_quote,
                )
            )

            if not supplied_quote_is_valid:
                all_supplied_quotes_valid = False

    return (
        required_risk_quotes_valid,
        all_supplied_quotes_valid,
    )


def score_task2_case(
    case: Task2EvalCase,
    brief: AccountBrief | None,
    caught_error: Exception | None,
    deterministic_repeat: bool | None,
    repository: DataRepository | None = None,
) -> dict[str, Any]:
    """
    Score one Task 2 account-brief result.
    """

    if repository is None:
        repository = get_repository()

    if case.expected_error is not None:
        checks = {
            "controlled_expected_error": (
                boolean_score(
                    caught_error is not None
                    and type(caught_error).__name__
                    == case.expected_error
                )
            ),
            "no_fabricated_brief": boolean_score(
                brief is None
            ),
        }

        return build_evaluation_result(
            test_id=case.test_id,
            task="task_2",
            name=case.name,
            adversarial=case.adversarial,
            checks=checks,
        )

    if brief is None:
        return build_evaluation_result(
            test_id=case.test_id,
            task="task_2",
            name=case.name,
            adversarial=case.adversarial,
            checks={
                "brief_generated": 0.0,
            },
        )

    tam_context = build_tam_context(
        case.account_id
    )

    checks: dict[str, float] = {
        "structured_output": boolean_score(
            isinstance(brief, AccountBrief)
        ),
        "exact_three_sections": boolean_score(
            set(brief.model_dump()) == {
                "executive_summary",
                "open_risks_and_flagged_issues",
                "recommended_talking_points",
            }
        ),
        "summary_has_3_to_5_sentences": (
            boolean_score(
                3
                <= count_summary_sentences(
                    brief.executive_summary
                )
                <= 5
            )
        ),
        "talking_points_have_3_to_5_items": (
            boolean_score(
                3
                <= len(
                    brief.recommended_talking_points
                )
                <= 5
            )
        ),
    }

    if deterministic_repeat is not None:
        checks["deterministic_repeat"] = (
            boolean_score(
                deterministic_repeat
            )
        )

    summary_text = (
        brief.executive_summary.casefold()
    )

    checks["required_summary_terms"] = (
        boolean_score(
            all(
                term.casefold() in summary_text
                for term
                in case.required_summary_terms
            )
        )
    )

    generated_risk_types = [
        risk.risk_type.value
        for risk
        in brief.open_risks_and_flagged_issues
    ]

    checks["required_risk_types"] = (
        boolean_score(
            all(
                required_type
                in generated_risk_types
                for required_type
                in case.required_risk_types
            )
        )
    )

    checks["forbidden_risk_types_absent"] = (
        boolean_score(
            all(
                forbidden_type
                not in generated_risk_types
                for forbidden_type
                in case.forbidden_risk_types
            )
        )
    )

    generated_priorities = [
        RISK_PRIORITY[risk.risk_type]
        for risk
        in brief.open_risks_and_flagged_issues
    ]

    checks["risk_priority_order"] = (
        boolean_score(
            generated_priorities
            == sorted(generated_priorities)
        )
    )

    (
        required_quotes_valid,
        all_supplied_quotes_valid,
    ) = validate_all_tam_quotes(
        brief=brief,
        tam_context=tam_context,
        repository=repository,
    )

    checks["required_risk_quotes_valid"] = (
        boolean_score(
            required_quotes_valid
        )
    )

    checks["all_supplied_quotes_exact"] = (
        boolean_score(
            all_supplied_quotes_valid
        )
    )

    complete_output_text = json.dumps(
        brief.model_dump(mode="json"),
        ensure_ascii=False,
    ).casefold()

    internal_phrases = (
        "exact_company_fallback",
        "company name fallback",
        "ticket account_id values",
        "match method",
    )

    checks["internal_metadata_hidden"] = (
        boolean_score(
            all(
                phrase
                not in complete_output_text
                for phrase in internal_phrases
            )
        )
    )

    return build_evaluation_result(
        test_id=case.test_id,
        task="task_2",
        name=case.name,
        adversarial=case.adversarial,
        checks=checks,
    )