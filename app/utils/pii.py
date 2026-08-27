# Import regular expressions for detecting sensitive patterns.
import re

# Import the validated Task 1 input model.
from app.schemas import TicketTriageRequest


# Detect email addresses.
EMAIL_PATTERN = re.compile(
    r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",
    flags=re.IGNORECASE,
)


# Detect IPv4 addresses such as 192.168.1.20.
IP_ADDRESS_PATTERN = re.compile(
    r"\b(?:\d{1,3}\.){3}\d{1,3}\b"
)


# Detect numbers that resemble payment-card numbers.
CARD_NUMBER_PATTERN = re.compile(
    r"\b(?:\d[ -]*?){13,19}\b"
)


# Detect possible phone-number sequences.
PHONE_NUMBER_PATTERN = re.compile(
    r"(?<![\w-])(?:\+?\d[\d\s().-]{8,}\d)(?![\w-])"
)


# Detect secrets that are explicitly labelled in text.
SECRET_PATTERN = re.compile(
    r"\b("
    r"api[_ -]?key|"
    r"access[_ -]?token|"
    r"auth[_ -]?token|"
    r"password|"
    r"secret"
    r")\s*[:=]\s*([^\s,;]+)",
    flags=re.IGNORECASE,
)


def redact_phone_numbers(
    text: str,
) -> tuple[str, int]:
    """
    Redact phone-like values containing 10 to 15 digits.
    """

    redaction_count = 0

    def replace_phone(
        match: re.Match[str],
    ) -> str:
        nonlocal redaction_count

        matched_text = match.group(0)

        digits_only = re.sub(
            pattern=r"\D",
            repl="",
            string=matched_text,
        )

        if 10 <= len(digits_only) <= 15:
            redaction_count += 1
            return "[PHONE_NUMBER]"

        return matched_text

    redacted_text = PHONE_NUMBER_PATTERN.sub(
        replace_phone,
        text,
    )

    return redacted_text, redaction_count


def redact_pii(
    text: str,
) -> tuple[str, dict[str, int]]:
    """
    Redact common structured PII and secret patterns.
    """

    if not isinstance(text, str):
        raise TypeError(
            "PII redaction expects a string."
        )

    redaction_counts: dict[str, int] = {}

    redacted_text, secret_count = SECRET_PATTERN.subn(
        lambda match: (
            f"{match.group(1)}=[REDACTED_SECRET]"
        ),
        text,
    )

    redaction_counts["secrets"] = secret_count

    redacted_text, email_count = EMAIL_PATTERN.subn(
        "[EMAIL_ADDRESS]",
        redacted_text,
    )

    redaction_counts["emails"] = email_count

    redacted_text, ip_count = IP_ADDRESS_PATTERN.subn(
        "[IP_ADDRESS]",
        redacted_text,
    )

    redaction_counts["ip_addresses"] = ip_count

    redacted_text, card_count = CARD_NUMBER_PATTERN.subn(
        "[PAYMENT_CARD]",
        redacted_text,
    )

    redaction_counts["payment_cards"] = card_count

    redacted_text, phone_count = redact_phone_numbers(
        redacted_text
    )

    redaction_counts["phone_numbers"] = phone_count

    return redacted_text, redaction_counts


def combine_redaction_counts(
    first_counts: dict[str, int],
    second_counts: dict[str, int],
) -> dict[str, int]:
    """
    Combine counts from the subject and body.
    """

    all_categories = (
        set(first_counts)
        | set(second_counts)
    )

    return {
        category: (
            first_counts.get(category, 0)
            + second_counts.get(category, 0)
        )
        for category in sorted(all_categories)
    }


def redact_ticket(
    ticket: TicketTriageRequest,
) -> tuple[TicketTriageRequest, dict[str, int]]:
    """
    Return a redacted copy of a ticket and redaction counts.
    """

    redacted_subject, subject_counts = redact_pii(
        ticket.subject
    )

    redacted_body, body_counts = redact_pii(
        ticket.body
    )

    safe_ticket = TicketTriageRequest(
        subject=redacted_subject,
        body=redacted_body,
    )

    combined_counts = combine_redaction_counts(
        first_counts=subject_counts,
        second_counts=body_counts,
    )

    return safe_ticket, combined_counts