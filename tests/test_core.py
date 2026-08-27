"""
Fast tests for deterministic application components.

These tests do not call Gemini and therefore do not
consume API quota.
"""

from datetime import timedelta

import pytest

from app.data_repository import (
    AccountNotFoundError,
    get_repository,
)
from app.retrieval import (
    KnowledgeBaseRetriever,
    has_confident_match,
)
from app.schemas import TicketTriageRequest
from app.utils.pii import redact_ticket


def test_dataset_contains_expected_records() -> None:
    """
    Confirm that the complete provided dataset loads.
    """

    repository = get_repository()

    assert len(repository.tickets) == 500
    assert len(repository.accounts) == 50


def test_account_tickets_use_company_fallback() -> None:
    """
    Confirm that inconsistent account IDs are handled
    using the documented company-name fallback.
    """

    repository = get_repository()

    result = repository.get_recent_account_tickets(
        "ACC-3336"
    )

    assert result.account.company == (
        "Omni Consumer Products"
    )

    assert result.match_method == (
        "exact_company_fallback"
    )

    assert len(result.tickets) > 0

    assert all(
        ticket.company == result.account.company
        for ticket in result.tickets
    )

    assert len(result.warnings) > 0


def test_recent_ticket_window_is_ninety_days() -> None:
    """
    Confirm that the static dataset uses an exact
    deterministic 90-day window.
    """

    repository = get_repository()

    result = repository.get_recent_account_tickets(
        "ACC-3336"
    )

    assert (
        result.as_of_date
        - result.cutoff_date
    ) == timedelta(days=90)

    assert all(
        result.cutoff_date
        <= ticket.created_at
        <= result.as_of_date
        for ticket in result.tickets
    )


def test_recent_tickets_have_stable_ordering() -> None:
    """
    Confirm that recent tickets are sorted newest first.
    """

    repository = get_repository()

    result = repository.get_recent_account_tickets(
        "ACC-3336"
    )

    ticket_dates = [
        ticket.created_at
        for ticket in result.tickets
    ]

    assert ticket_dates == sorted(
        ticket_dates,
        reverse=True,
    )


def test_missing_account_raises_controlled_error() -> None:
    """
    Confirm that an invalid account does not cause an
    uncontrolled crash.
    """

    repository = get_repository()

    with pytest.raises(
        AccountNotFoundError,
        match="INVALID-ACCOUNT",
    ):
        repository.get_recent_account_tickets(
            "INVALID-ACCOUNT"
        )


def test_exact_error_code_creates_confident_match() -> None:
    """
    Confirm that known KB error codes produce a
    confident retrieval result.
    """

    retriever = KnowledgeBaseRetriever()

    results = retriever.retrieve(
        "SecureVault authentication failure",
        (
            "Production requests fail with "
            "AUTH_TOKEN_EXPIRED."
        ),
    )

    assert has_confident_match(results)

    assert any(
        "AUTH_TOKEN_EXPIRED"
        in result.matched_error_codes
        for result in results
    )


def test_unrelated_text_has_no_confident_match() -> None:
    """
    Confirm that unrelated text does not create a false
    known-issue claim.
    """

    retriever = KnowledgeBaseRetriever()

    results = retriever.retrieve(
        "Zebra violin",
        "Please arrange lunar gardening lessons.",
    )

    assert not has_confident_match(results)


def test_pii_is_redacted_without_changing_original() -> None:
    """
    Confirm that sensitive values are removed before
    sending ticket text to an external API.
    """

    original = TicketTriageRequest(
        subject=(
            "Login issue for alex@example.com"
        ),
        body=(
            "Call +91 98765 43210. "
            "Source IP is 192.168.1.20. "
            "api_key=abc123secret. "
            "Card 4111 1111 1111 1111. "
            "Error AUTH_TOKEN_EXPIRED."
        ),
    )

    safe_ticket, counts = redact_ticket(
        original
    )

    assert "[EMAIL_ADDRESS]" in safe_ticket.subject
    assert "[PHONE_NUMBER]" in safe_ticket.body
    assert "[IP_ADDRESS]" in safe_ticket.body
    assert "[REDACTED_SECRET]" in safe_ticket.body
    assert "[PAYMENT_CARD]" in safe_ticket.body

    assert counts == {
        "emails": 1,
        "ip_addresses": 1,
        "payment_cards": 1,
        "phone_numbers": 1,
        "secrets": 1,
    }

    # Important technical evidence such as error codes
    # should remain available to the retriever and LLM.
    assert (
        "AUTH_TOKEN_EXPIRED"
        in safe_ticket.body
    )

    # Pydantic models are not modified in place.
    assert "alex@example.com" in original.subject