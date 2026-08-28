# Import lru_cache so the settings object is created only once.
from functools import lru_cache

# Import Path to build file paths safely on Windows, macOS, and Linux.
from pathlib import Path

# Import BaseSettings to load values from environment variables.
from pydantic_settings import BaseSettings, SettingsConfigDict


# Find the main ai-support-tam project directory.
PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """
    Store application configuration in one central location.
    """

    # Gemini configuration.
    llm_api_key: str = ""
    llm_model: str = "gemini-3.6-flash"

    # Task 2 requires deterministic output.
    llm_temperature: float = 0.0

    # Main project directories.
    data_directory: Path = PROJECT_ROOT / "data"
    knowledge_base_directory: Path = PROJECT_ROOT / "knowledge-base"

    # Dataset file locations.
    tickets_path: Path = data_directory / "tickets.json"
    accounts_path: Path = data_directory / "accounts.json"

    # Tell Pydantic to read variables from the private .env file.
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """
    Create and return one reusable Settings object.
    """

    return Settings()