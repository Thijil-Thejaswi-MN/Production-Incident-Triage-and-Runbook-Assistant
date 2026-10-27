from __future__ import annotations

import pytest

from tests.conftest import REPO_ROOT
from triage.config import Settings

ENV_EXAMPLE = REPO_ROOT / ".env.example"


def _parse_env_example() -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, sep, value = line.partition("=")
        assert sep, f"malformed line in .env.example: {raw!r}"
        assert key not in values, f"duplicate key in .env.example: {key}"
        values[key] = value
    return values


def test_every_setting_is_documented_and_no_stale_keys() -> None:
    documented = set(_parse_env_example())
    expected = {name.upper() for name in Settings.model_fields}
    assert documented - expected == set(), "keys in .env.example that Settings does not read"
    assert expected - documented == set(), "Settings fields missing from .env.example"


def test_every_key_has_a_comment_above_it() -> None:
    lines = ENV_EXAMPLE.read_text(encoding="utf-8").splitlines()
    for i, line in enumerate(lines):
        if line and not line.startswith("#"):
            assert i > 0 and lines[i - 1].startswith("#"), f"undocumented variable: {line}"


def test_example_values_produce_valid_settings(clean_env: pytest.MonkeyPatch) -> None:
    for key, value in _parse_env_example().items():
        clean_env.setenv(key, value)
    Settings()


def test_example_api_key_is_an_obvious_placeholder() -> None:
    assert "not-a-real-key" in _parse_env_example()["LLM_API_KEY"]
