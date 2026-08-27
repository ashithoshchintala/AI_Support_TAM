# Import date for values such as 2026-08-19.
# Import datetime for values containing both date and time.
from datetime import date, datetime

# Import Enum to create fields with a fixed set of allowed values.
from enum import Enum

# Import Self for validator return-type hints.
from typing import Self

# Import Pydantic tools for validation and structured models.
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)


class StrictBaseModel(BaseModel):
    """
    Base model containing validation rules shared by all schemas.
    """

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )


class Urgency(str, Enum):
    """
    Allowed ticket urgency levels.
    """

    P1 = "P1"
    P2 = "P2"
    P3 = "P3"
    P4 = "P4"


class RiskType(str, Enum):
    """
    Risk categories used in the TAM account brief.
    """

    CHURN = "churn"
    ESCALATION = "escalation"
    OPERATIONAL = "operational"
    ADOPTION = "adoption"
    RENEWAL = "renewal"


class PrimaryContact(StrictBaseModel):
    """
    Primary customer contact stored inside an account record.
    """

    name: str = Field(min_length=1)
    title: str = Field(min_length=1)


class SupportTicket(StrictBaseModel):
    """
    Validated representation of one provided support ticket.
    """

    account_id: str = Field(min_length=1)
    assigned_agent: str = Field(min_length=1)
    body: str = Field(min_length=1)
    category: str = Field(min_length=1)
    channel: str = Field(min_length=1)
    company: str = Field(min_length=1)
    created_at: datetime
    plan_tier: str = Field(min_length=1)
    product: str = Field(min_length=1)
    product_area: str = Field(min_length=1)
    satisfaction_score: int | None
    status: str = Field(min_length=1)
    subject: str = Field(min_length=1)
    tags: list[str]
    ticket_id: str = Field(min_length=1)
    updated_at: datetime
    urgency: Urgency


class AccountSummary(StrictBaseModel):
    """
    Validated representation of one provided customer account.
    """

    account_id: str = Field(min_length=1)
    arr_usd: int = Field(ge=0)
    company: str = Field(min_length=1)
    customer_since: date
    escalation_notes: list[str]
    health_status: str = Field(min_length=1)
    industry: str = Field(min_length=1)
    integrations_active: list[str]
    last_login_days_ago: int = Field(ge=0)
    last_qbr_date: date
    nps_score: int | None
    open_tickets: int = Field(ge=0)
    p1_tickets_last_30d: int = Field(ge=0)
    plan_tier: str = Field(min_length=1)
    primary_contact: PrimaryContact
    products: list[str]
    region: str = Field(min_length=1)
    renewal_date: date
    seats_active: int = Field(ge=0)
    seats_licensed: int = Field(ge=0)
    tam: str = Field(min_length=1)
    usage_trend: str = Field(min_length=1)


class TicketTriageRequest(StrictBaseModel):
    """
    Normalized JSON input for Task 1.
    """

    subject: str = Field(min_length=1)
    body: str = Field(min_length=1)


class TicketTriageResult(StrictBaseModel):
    """
    Structured result produced by the Task 1 triage pipeline.
    """

    product_area: str = Field(min_length=1)
    issue_category: str = Field(min_length=1)
    urgency: Urgency
    reasoning: str = Field(min_length=1)

    known_issue: bool
    knowledge_base_document: str | None

    recommended_team: str = Field(min_length=1)
    draft_response: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_knowledge_base_match(self) -> Self:
        """
        Ensure known-issue status agrees with the document field.
        """

        if self.known_issue and not self.knowledge_base_document:
            raise ValueError(
                "A known issue must include a knowledge-base document."
            )

        if not self.known_issue and self.knowledge_base_document:
            raise ValueError(
                "An unknown issue must not claim a knowledge-base document."
            )

        return self


class AccountBriefRequest(StrictBaseModel):
    """
    Input for Task 2.
    """

    account_id: str = Field(min_length=1)


class RiskFlag(StrictBaseModel):
    """
    One risk shown in the account brief.
    """

    risk_type: RiskType
    description: str = Field(min_length=1)

    ticket_id: str | None = None
    direct_quote: str | None = None

    @model_validator(mode="after")
    def require_evidence_for_important_risks(self) -> Self:
        """
        Require ticket evidence for churn and escalation flags.
        """

        evidence_required = self.risk_type in {
            RiskType.CHURN,
            RiskType.ESCALATION,
        }

        if evidence_required and not self.ticket_id:
            raise ValueError(
                "Churn and escalation risks require a ticket_id."
            )

        if evidence_required and not self.direct_quote:
            raise ValueError(
                "Churn and escalation risks require a direct quote."
            )

        return self


class AccountBrief(StrictBaseModel):
    """
    Task 2 output containing exactly the three required sections.
    """

    executive_summary: str = Field(
        min_length=1,
        description="A deterministic summary containing 3–5 sentences.",
    )

    open_risks_and_flagged_issues: list[RiskFlag]

    recommended_talking_points: list[str] = Field(
        min_length=1,
    )