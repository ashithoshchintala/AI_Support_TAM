# Import dataclass to create a small structured internal result.
from dataclasses import dataclass

# Import datetime tools for the deterministic 90-day window.
from datetime import datetime, timedelta, timezone

# Import lru_cache so the repository is loaded only once.
from functools import lru_cache

# Import the local data loader.
from app.data_loader import load_all_data

# Import the validated dataset schemas.
from app.schemas import AccountSummary, SupportTicket


class AccountNotFoundError(LookupError):
    """
    Raised when an account_id does not exist.
    """


class RepositoryDataError(ValueError):
    """
    Raised when repository data is empty or internally inconsistent.
    """


@dataclass(frozen=True)
class AccountTicketLookup:
    """
    Internal result of joining one account with its recent tickets.
    """

    account: AccountSummary
    tickets: tuple[SupportTicket, ...]
    as_of_date: datetime
    cutoff_date: datetime
    match_method: str
    warnings: tuple[str, ...]


def normalize_company_name(company_name: str) -> str:
    """
    Normalize a company name before comparing it.
    """

    return " ".join(
        company_name.casefold().split()
    )


class DataRepository:
    """
    Load, validate, index, and query the provided starter data.
    """

    def __init__(self) -> None:
        raw_data = load_all_data()

        self.tickets = tuple(
            SupportTicket.model_validate(ticket)
            for ticket in raw_data["tickets"]
        )

        self.accounts = tuple(
            AccountSummary.model_validate(account)
            for account in raw_data["accounts"]
        )

        self.knowledge_base_documents = tuple(
            raw_data["knowledge_base"]
        )

        if not self.tickets:
            raise RepositoryDataError(
                "The repository contains no support tickets."
            )

        if not self.accounts:
            raise RepositoryDataError(
                "The repository contains no account summaries."
            )

        self._account_by_id = {
            account.account_id: account
            for account in self.accounts
        }

        if len(self._account_by_id) != len(self.accounts):
            raise RepositoryDataError(
                "Duplicate account_id values were found."
            )

        normalized_company_names = [
            normalize_company_name(account.company)
            for account in self.accounts
        ]

        if len(set(normalized_company_names)) != len(self.accounts):
            raise RepositoryDataError(
                "Company names are not unique, so company fallback "
                "matching would be unsafe."
            )

        self.dataset_snapshot_date = max(
            ticket.created_at
            for ticket in self.tickets
        )

    def get_account(self, account_id: str) -> AccountSummary:
        """
        Return one account or raise a controlled error.
        """

        normalized_account_id = account_id.strip()

        account = self._account_by_id.get(
            normalized_account_id
        )

        if account is None:
            raise AccountNotFoundError(
                f"Account '{normalized_account_id}' was not found."
            )

        return account

    def get_recent_account_tickets(
        self,
        account_id: str,
        as_of_date: datetime | None = None,
    ) -> AccountTicketLookup:
        """
        Retrieve an account's tickets from a deterministic 90-day window.
        """

        account = self.get_account(account_id)

        account_id_matches = [
            ticket
            for ticket in self.tickets
            if ticket.account_id == account.account_id
        ]

        normalized_account_company = normalize_company_name(
            account.company
        )

        company_matches = [
            ticket
            for ticket in self.tickets
            if normalize_company_name(ticket.company)
            == normalized_account_company
        ]

        id_matches_are_complete_and_consistent = (
            bool(account_id_matches)
            and len(account_id_matches) == len(company_matches)
            and all(
                normalize_company_name(ticket.company)
                == normalized_account_company
                for ticket in account_id_matches
            )
        )

        warnings: list[str] = []

        if id_matches_are_complete_and_consistent:
            selected_tickets = account_id_matches
            match_method = "account_id"

        else:
            selected_tickets = company_matches
            match_method = "exact_company_fallback"

            warnings.append(
                "Ticket account_id values were incomplete or "
                "inconsistent. Tickets were matched using the "
                "account's exact normalized company name."
            )

        effective_as_of_date = (
            as_of_date
            if as_of_date is not None
            else self.dataset_snapshot_date
        )

        if effective_as_of_date.tzinfo is None:
            effective_as_of_date = effective_as_of_date.replace(
                tzinfo=timezone.utc
            )

        cutoff_date = effective_as_of_date - timedelta(days=90)

        recent_tickets = [
            ticket
            for ticket in selected_tickets
            if cutoff_date
            <= ticket.created_at
            <= effective_as_of_date
        ]

        recent_tickets.sort(
            key=lambda ticket: (
                ticket.created_at,
                ticket.ticket_id,
            ),
            reverse=True,
        )

        if not recent_tickets:
            warnings.append(
                "No tickets were found for this account during "
                "the selected 90-day window."
            )

        return AccountTicketLookup(
            account=account,
            tickets=tuple(recent_tickets),
            as_of_date=effective_as_of_date,
            cutoff_date=cutoff_date,
            match_method=match_method,
            warnings=tuple(warnings),
        )


@lru_cache
def get_repository() -> DataRepository:
    """
    Create and reuse one validated data repository.
    """

    return DataRepository()