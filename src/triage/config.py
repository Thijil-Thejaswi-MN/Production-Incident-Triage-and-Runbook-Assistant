"""Runtime configuration, read only from environment variables (requirement D4).

No endpoint, credential or model identifier has a default here: they must be
injected at runtime. Variable names are the upper-case field names; see
`.env.example` for documentation of every variable.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import AnyHttpUrl, Field, PositiveFloat, PositiveInt, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=None,  # values come from the process environment only
        case_sensitive=False,
        extra="ignore",
        frozen=True,
    )

    # --- Application -----------------------------------------------------------------
    app_env: Literal["development", "test", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_json: bool = True

    # --- Corpus ----------------------------------------------------------------------
    # The project indexes exactly one PostgreSQL major version (decision D-1).
    # (`Literal[17]` would reject the string "17" that environment variables provide.)
    pg_docs_major_version: int = Field(default=17, ge=17, le=17)

    # --- LLM provider (required; no defaults by design) -----------------------------
    llm_base_url: AnyHttpUrl
    llm_api_key: SecretStr = Field(min_length=1)
    llm_model: str = Field(min_length=1)
    llm_timeout_s: PositiveFloat = 20.0
    llm_max_retries: int = Field(default=3, ge=0, le=5)

    # --- Agent loop bounds (requirement A1) -----------------------------------------
    agent_max_steps: PositiveInt = 12
    agent_max_tool_calls: PositiveInt = 10
    agent_wall_clock_s: PositiveFloat = 90.0
    verifier_wall_clock_s: PositiveFloat = 45.0

    @model_validator(mode="after")
    def _check_bounds(self) -> Settings:
        if self.agent_max_tool_calls > self.agent_max_steps:
            raise ValueError("AGENT_MAX_TOOL_CALLS must not exceed AGENT_MAX_STEPS")
        if self.llm_timeout_s >= self.agent_wall_clock_s:
            raise ValueError("LLM_TIMEOUT_S must be shorter than AGENT_WALL_CLOCK_S")
        if self.llm_timeout_s >= self.verifier_wall_clock_s:
            raise ValueError("LLM_TIMEOUT_S must be shorter than VERIFIER_WALL_CLOCK_S")
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Process-wide settings; raises `pydantic.ValidationError` if the environment is invalid."""
    return Settings()  # required fields come from the environment
