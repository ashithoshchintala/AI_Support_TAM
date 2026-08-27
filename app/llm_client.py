# Import lru_cache so one Gemini client can be reused.
from functools import lru_cache

# Import TypeVar to connect the requested Pydantic model
# with the returned model type.
from typing import TypeVar

# Import the official Google GenAI SDK.
from google import genai
from google.genai import types

# Import Pydantic validation tools.
from pydantic import BaseModel, ValidationError

# Import our application configuration.
from app.config import get_settings


# This represents any Pydantic response model.
ResponseModelType = TypeVar(
    "ResponseModelType",
    bound=BaseModel,
)


class LLMConfigurationError(ValueError):
    """
    Raised when Gemini configuration is missing.
    """


class LLMRequestError(RuntimeError):
    """
    Raised when the Gemini API request fails.
    """


class LLMResponseError(ValueError):
    """
    Raised when Gemini returns an invalid structured response.
    """


class GeminiStructuredClient:
    """
    Reusable Gemini client for Pydantic structured output.
    """

    def __init__(self) -> None:
        self.settings = get_settings()

        if not self.settings.llm_api_key.strip():
            raise LLMConfigurationError(
                "LLM_API_KEY is missing from the .env file."
            )

        if not self.settings.llm_model.strip():
            raise LLMConfigurationError(
                "LLM_MODEL is missing from the .env file."
            )

        self.client = genai.Client(
            api_key=self.settings.llm_api_key
        )

    def generate_structured(
        self,
        system_prompt: str,
        user_prompt: str,
        response_model: type[ResponseModelType],
        seed: int = 42,
    ) -> ResponseModelType:
        """
        Generate and validate one structured Gemini response.
        """

        if not system_prompt.strip():
            raise ValueError(
                "The system prompt cannot be empty."
            )

        if not user_prompt.strip():
            raise ValueError(
                "The user prompt cannot be empty."
            )

        try:
            response = self.client.models.generate_content(
                model=self.settings.llm_model,
                contents=user_prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    temperature=(
                        self.settings.llm_temperature
                    ),
                    seed=seed,
                    candidate_count=1,

                    # We use structured JSON,
                    # not automatic function calling.
                    automatic_function_calling=(
                        types.AutomaticFunctionCallingConfig(
                            disable=True
                        )
                    ),

                    response_mime_type="application/json",

                    # Convert the requested Pydantic model
                    # into standard JSON Schema.
                    response_json_schema=(
                        response_model.model_json_schema()
                    ),
                ),
            )

        except Exception as error:
            raise LLMRequestError(
                "The Gemini API request failed with "
                f"{type(error).__name__}."
            ) from error

        try:
            if response.parsed is not None:
                if isinstance(
                    response.parsed,
                    response_model,
                ):
                    return response.parsed

                return response_model.model_validate(
                    response.parsed
                )

            if not response.text:
                raise LLMResponseError(
                    "Gemini returned no response text."
                )

            return response_model.model_validate_json(
                response.text
            )

        except ValidationError as error:
            raise LLMResponseError(
                "Gemini returned data that did not match "
                f"{response_model.__name__}."
            ) from error


@lru_cache
def get_llm_client() -> GeminiStructuredClient:
    """
    Create and reuse one Gemini client.
    """

    return GeminiStructuredClient()