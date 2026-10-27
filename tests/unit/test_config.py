from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from triage.config import Settings, get_settings


def _error_locs(exc: ValidationError) -> set[str]:
    return {str(err["loc"][0]) for err in exc.errors() if err["loc"]}


def test_loads_required_values_and_defaults_from_environment(valid_env: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    assert str(settings.llm_base_url) == "http://llm-stub:8080/v1"
    assert settings.llm_model == "stub"
    assert settings.llm_api_key.get_secret_value() == "test-placeholder-key"
    assert settings.pg_docs_major_version == 17
    assert settings.agent_max_steps == 12
    assert settings.agent_max_tool_calls == 10


def test_environment_overrides_defaults(valid_env: pytest.MonkeyPatch) -> None:
    valid_env.setenv("AGENT_MAX_STEPS", "20")
    valid_env.setenv("LOG_JSON", "false")
    settings = Settings()
    assert settings.agent_max_steps == 20
    assert settings.log_json is False


@pytest.mark.parametrize("missing", ["LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL"])
def test_missing_required_variable_is_named_in_error(
    valid_env: pytest.MonkeyPatch, missing: str
) -> None:
    valid_env.delenv(missing)
    with pytest.raises(ValidationError) as exc_info:
        Settings()
    assert missing.lower() in _error_locs(exc_info.value)


def test_nothing_set_reports_every_required_variable(clean_env: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValidationError) as exc_info:
        Settings()
    assert {"llm_base_url", "llm_api_key", "llm_model"} <= _error_locs(exc_info.value)


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("AGENT_MAX_STEPS", "0"),
        ("AGENT_MAX_TOOL_CALLS", "-1"),
        ("AGENT_WALL_CLOCK_S", "0"),
        ("VERIFIER_WALL_CLOCK_S", "-5"),
        ("LLM_TIMEOUT_S", "0"),
        ("LLM_MAX_RETRIES", "6"),
        ("LLM_MAX_RETRIES", "-1"),
        ("AGENT_MAX_STEPS", "many"),
    ],
)
def test_invalid_limits_are_rejected(valid_env: pytest.MonkeyPatch, name: str, value: str) -> None:
    valid_env.setenv(name, value)
    with pytest.raises(ValidationError) as exc_info:
        Settings()
    assert name.lower() in _error_locs(exc_info.value)


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("APP_ENV", "staging-ish"),
        ("LOG_LEVEL", "VERBOSE"),
        ("PG_DOCS_MAJOR_VERSION", "18"),
        ("LLM_BASE_URL", "not a url"),
        ("LLM_MODEL", ""),
        ("LLM_API_KEY", ""),
    ],
)
def test_invalid_categorical_and_format_values_are_rejected(
    valid_env: pytest.MonkeyPatch, name: str, value: str
) -> None:
    valid_env.setenv(name, value)
    with pytest.raises(ValidationError) as exc_info:
        Settings()
    assert name.lower() in _error_locs(exc_info.value)


def test_tool_calls_may_not_exceed_steps(valid_env: pytest.MonkeyPatch) -> None:
    valid_env.setenv("AGENT_MAX_STEPS", "5")
    valid_env.setenv("AGENT_MAX_TOOL_CALLS", "6")
    with pytest.raises(ValidationError, match="AGENT_MAX_TOOL_CALLS must not exceed"):
        Settings()


@pytest.mark.parametrize("limit", ["AGENT_WALL_CLOCK_S", "VERIFIER_WALL_CLOCK_S"])
def test_call_timeout_must_be_shorter_than_wall_clock(
    valid_env: pytest.MonkeyPatch, limit: str
) -> None:
    valid_env.setenv("LLM_TIMEOUT_S", "30")
    valid_env.setenv(limit, "30")
    with pytest.raises(ValidationError, match=f"shorter than {limit}"):
        Settings()


def test_api_key_is_not_exposed_in_repr_or_dump(valid_env: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    assert "test-placeholder-key" not in repr(settings)
    assert "test-placeholder-key" not in str(settings.model_dump())
    assert "test-placeholder-key" not in settings.model_dump_json()


def test_settings_are_immutable(valid_env: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    with pytest.raises(ValidationError):
        settings.agent_max_steps = 99  # type: ignore[misc]  # asserting the runtime guard


def test_dotenv_file_is_not_read_implicitly(clean_env: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # A .env in the working directory must not silently configure the process (D4).
    env_file = tmp_path / ".env"
    env_file.write_text("LLM_BASE_URL=http://llm-stub:8080/v1\nLLM_API_KEY=x\nLLM_MODEL=stub\n")
    clean_env.chdir(tmp_path)
    with pytest.raises(ValidationError):
        Settings()
