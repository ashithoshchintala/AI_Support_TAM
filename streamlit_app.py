"""
Streamlit interface for the AI Support and TAM system.

The interface provides:
1. Support-ticket triage
2. TAM account-brief generation
"""

from __future__ import annotations

from enum import Enum
from typing import Any

import streamlit as st

from app.data_repository import AccountNotFoundError
from app.tam_summarizer import summarize_account
from app.triage_agent import triage_ticket


st.set_page_config(
    page_title="AI Support & TAM Copilot",
    page_icon="🤖",
    layout="wide",
)


def display_enum_value(value: Any) -> str:
    """
    Convert enum values into readable text.
    """

    if isinstance(value, Enum):
        return str(value.value)

    return str(value)


def initialize_session_state() -> None:
    """
    Create persistent result variables.

    This prevents generated results from disappearing
    during ordinary Streamlit reruns.
    """

    if "triage_result" not in st.session_state:
        st.session_state.triage_result = None

    if "account_brief" not in st.session_state:
        st.session_state.account_brief = None

    if "brief_account_id" not in st.session_state:
        st.session_state.brief_account_id = None


def display_triage_result() -> None:
    """
    Display a structured Task 1 result.
    """

    result = st.session_state.triage_result

    if result is None:
        return

    st.divider()
    st.subheader("Triage result")

    first_row = st.columns(4)

    first_row[0].metric(
        "Urgency",
        display_enum_value(result.urgency),
    )

    first_row[1].metric(
        "Product area",
        result.product_area,
    )

    first_row[2].metric(
        "Issue category",
        result.issue_category,
    )

    first_row[3].metric(
        "Recommended team",
        result.recommended_team,
    )

    known_issue_text = (
        "Yes"
        if result.known_issue
        else "No"
    )

    st.metric(
        "Known issue",
        known_issue_text,
    )

    if result.knowledge_base_document:
        st.caption(
            "Knowledge-base evidence: "
            f"{result.knowledge_base_document}"
        )
    else:
        st.caption(
            "No knowledge-base document was linked."
        )

    st.markdown("#### Classification rationale")

    with st.container(border=True):
        st.write(result.reasoning)

    st.markdown("#### Draft customer response")

    with st.container(border=True):
        st.write(result.draft_response)


def display_account_brief() -> None:
    """
    Display the exact three sections required for Task 2.
    """

    brief = st.session_state.account_brief

    if brief is None:
        return

    st.divider()

    account_id = st.session_state.brief_account_id

    st.subheader(
        f"Account brief: {account_id}"
    )

    st.markdown("### 1. Executive summary")

    with st.container(border=True):
        st.write(brief.executive_summary)

    st.markdown(
        "### 2. Open risks and flagged issues"
    )

    risks = brief.open_risks_and_flagged_issues

    if not risks:
        st.success(
            "No supported open risks or flagged issues "
            "were found in the recent ticket evidence."
        )

    for number, risk in enumerate(
        risks,
        start=1,
    ):
        risk_type = display_enum_value(
            risk.risk_type
        )

        with st.container(border=True):
            st.markdown(
                f"#### {number}. "
                f"{risk_type.replace('_', ' ').title()}"
            )

            st.write(risk.description)

            if risk.ticket_id:
                st.caption(
                    f"Source ticket: {risk.ticket_id}"
                )

            if risk.direct_quote:
                st.markdown("**Direct evidence**")
                st.code(
                    risk.direct_quote,
                    language=None,
                )

    st.markdown(
        "### 3. Recommended talking points"
    )

    for talking_point in (
        brief.recommended_talking_points
    ):
        st.markdown(f"- {talking_point}")


initialize_session_state()

st.title("AI Support & TAM Copilot")

st.write(
    "Triage incoming support tickets and create "
    "grounded account briefs from recent customer evidence."
)

with st.sidebar:
    st.header("Capabilities")

    st.markdown(
        """
- Structured ticket classification
- Urgency and team recommendation
- Knowledge-base grounding
- PII-redacted LLM processing
- Evidence-backed account risks
- Controlled missing-account handling
"""
    )

    st.info(
        "Results are generated only when you submit a form."
    )


task1_tab, task2_tab = st.tabs(
    [
        "Task 1 — Ticket Triage",
        "Task 2 — TAM Account Brief",
    ]
)


with task1_tab:
    st.header("Support-ticket triage")

    st.write(
        "Enter a ticket as separate subject and body "
        "fields or as a single raw-text message."
    )

    input_mode = st.radio(
        "Ticket input format",
        options=(
            "Subject and body",
            "Raw text",
        ),
        horizontal=True,
        key="ticket_input_mode",
    )

    with st.form("ticket_triage_form"):
        if input_mode == "Subject and body":
            subject = st.text_input(
                "Subject",
                placeholder=(
                    "Example: Production authentication outage"
                ),
            )

            body = st.text_area(
                "Body",
                height=180,
                placeholder=(
                    "Describe the affected users, symptoms, "
                    "error codes, and business impact."
                ),
            )

            raw_text = ""

        else:
            subject = ""
            body = ""

            raw_text = st.text_area(
                "Raw ticket text",
                height=220,
                placeholder=(
                    "Paste the complete support ticket here."
                ),
            )

        triage_submitted = st.form_submit_button(
            "Triage ticket",
            type="primary",
            use_container_width=True,
        )

    if triage_submitted:
        st.session_state.triage_result = None

        if input_mode == "Subject and body":
            if not subject.strip() or not body.strip():
                st.warning(
                    "Enter both a subject and a ticket body."
                )
            else:
                ticket_input: str | dict[str, str] = {
                    "subject": subject.strip(),
                    "body": body.strip(),
                }

                try:
                    with st.spinner(
                        "Classifying and grounding the ticket..."
                    ):
                        st.session_state.triage_result = (
                            triage_ticket(ticket_input)
                        )

                    st.success(
                        "Ticket triage completed."
                    )

                except Exception:
                    st.error(
                        "The ticket could not be processed. "
                        "Check the application configuration "
                        "and try again."
                    )

        else:
            if not raw_text.strip():
                st.warning(
                    "Enter the raw ticket text."
                )
            else:
                try:
                    with st.spinner(
                        "Classifying and grounding the ticket..."
                    ):
                        st.session_state.triage_result = (
                            triage_ticket(
                                raw_text.strip()
                            )
                        )

                    st.success(
                        "Ticket triage completed."
                    )

                except Exception:
                    st.error(
                        "The ticket could not be processed. "
                        "Check the application configuration "
                        "and try again."
                    )

    display_triage_result()


with task2_tab:
    st.header("TAM account brief")

    st.write(
        "Enter an account ID to generate a deterministic "
        "brief using recent account and ticket evidence."
    )

    with st.form("account_brief_form"):
        account_id = st.text_input(
            "Account ID",
            placeholder="Example: ACC-1256",
        )

        brief_submitted = st.form_submit_button(
            "Generate account brief",
            type="primary",
            use_container_width=True,
        )

    if brief_submitted:
        st.session_state.account_brief = None
        st.session_state.brief_account_id = None

        normalized_account_id = (
            account_id.strip().upper()
        )

        if not normalized_account_id:
            st.warning(
                "Enter an account ID."
            )

        else:
            try:
                with st.spinner(
                    "Collecting evidence and generating the brief..."
                ):
                    generated_brief = summarize_account(
                        normalized_account_id
                    )

                st.session_state.account_brief = (
                    generated_brief
                )

                st.session_state.brief_account_id = (
                    normalized_account_id
                )

                st.success(
                    "Account brief generated."
                )

            except AccountNotFoundError:
                st.error(
                    "No account was found for "
                    f"`{normalized_account_id}`."
                )

            except Exception:
                st.error(
                    "The account brief could not be generated. "
                    "Check the application configuration "
                    "and try again."
                )

    display_account_brief()