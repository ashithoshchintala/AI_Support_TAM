# Import Python's built-in JSON reader.
import json

# Import Path for safe file-path handling.
from pathlib import Path

# Import Any for dictionaries containing different value types.
from typing import Any

# Import the project's central configuration.
from app.config import get_settings


class DataLoadingError(Exception):
    """
    Raised when a required data file cannot be loaded or validated.
    """


def load_json_records(
    file_path: Path,
    collection_name: str,
) -> list[dict[str, Any]]:
    """
    Load a JSON file and return its records as a list of dictionaries.

    The function supports either:
    1. A top-level JSON list
    2. A dictionary containing a list under collection_name
    """

    if not file_path.exists():
        raise DataLoadingError(
            f"Required file was not found: {file_path}"
        )

    try:
        with file_path.open(
            mode="r",
            encoding="utf-8",
        ) as json_file:
            json_data = json.load(json_file)

    except json.JSONDecodeError as error:
        raise DataLoadingError(
            f"Invalid JSON inside {file_path}: {error}"
        ) from error

    except OSError as error:
        raise DataLoadingError(
            f"Could not read {file_path}: {error}"
        ) from error

    if isinstance(json_data, list):
        records = json_data

    elif (
        isinstance(json_data, dict)
        and isinstance(json_data.get(collection_name), list)
    ):
        records = json_data[collection_name]

    else:
        raise DataLoadingError(
            f"{file_path} must contain a JSON list or a "
            f"'{collection_name}' list."
        )

    for record_index, record in enumerate(records):
        if not isinstance(record, dict):
            raise DataLoadingError(
                f"Record {record_index} in {file_path} "
                "is not a JSON object."
            )

    return records


def validate_required_fields(
    records: list[dict[str, Any]],
    required_fields: set[str],
    collection_name: str,
) -> None:
    """
    Check that every record contains the required fields.
    """

    for record_index, record in enumerate(records):
        missing_fields = [
            field_name
            for field_name in required_fields
            if field_name not in record
            or record[field_name] in (None, "")
        ]

        if missing_fields:
            raise DataLoadingError(
                f"{collection_name} record {record_index} is missing: "
                f"{', '.join(sorted(missing_fields))}"
            )


def load_tickets() -> list[dict[str, Any]]:
    """
    Load and perform basic validation on support tickets.
    """

    settings = get_settings()

    tickets = load_json_records(
        file_path=settings.tickets_path,
        collection_name="tickets",
    )

    validate_required_fields(
        records=tickets,
        required_fields={"ticket_id"},
        collection_name="Ticket",
    )

    return tickets


def load_accounts() -> list[dict[str, Any]]:
    """
    Load and perform basic validation on customer accounts.
    """

    settings = get_settings()

    accounts = load_json_records(
        file_path=settings.accounts_path,
        collection_name="accounts",
    )

    validate_required_fields(
        records=accounts,
        required_fields={"account_id"},
        collection_name="Account",
    )

    return accounts


def extract_markdown_title(
    document_content: str,
    file_path: Path,
) -> str:
    """
    Use the first Markdown heading as the document title.
    """

    for line in document_content.splitlines():
        if line.startswith("# "):
            return line.removeprefix("# ").strip()

    return file_path.stem.replace("-", " ").replace("_", " ").title()


def load_knowledge_base_documents() -> list[dict[str, str]]:
    """
    Recursively load every Markdown document in the knowledge base.
    """

    settings = get_settings()
    knowledge_base_directory = settings.knowledge_base_directory

    if not knowledge_base_directory.exists():
        raise DataLoadingError(
            "Knowledge-base directory was not found: "
            f"{knowledge_base_directory}"
        )

    markdown_files = sorted(
        knowledge_base_directory.rglob("*.md")
    )

    if not markdown_files:
        raise DataLoadingError(
            "No Markdown files were found in the knowledge base."
        )

    documents = []

    for markdown_file in markdown_files:
        try:
            content = markdown_file.read_text(encoding="utf-8")
        except OSError as error:
            raise DataLoadingError(
                f"Could not read {markdown_file}: {error}"
            ) from error

        if not content.strip():
            raise DataLoadingError(
                f"Knowledge-base document is empty: {markdown_file}"
            )

        relative_path = markdown_file.relative_to(
            knowledge_base_directory
        )

        documents.append(
            {
                "document_path": relative_path.as_posix(),
                "document_name": markdown_file.name,
                "title": extract_markdown_title(
                    document_content=content,
                    file_path=markdown_file,
                ),
                "content": content,
            }
        )

    return documents


def load_all_data() -> dict[str, list[dict[str, Any]]]:
    """
    Load all locally provided assignment data.
    """

    return {
        "tickets": load_tickets(),
        "accounts": load_accounts(),
        "knowledge_base": load_knowledge_base_documents(),
    }