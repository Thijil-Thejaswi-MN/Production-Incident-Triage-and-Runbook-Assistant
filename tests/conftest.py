from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from triage.config import Settings, get_settings

REPO_ROOT = Path(__file__).resolve().parents[1]

VALID_ENV: dict[str, str] = {
    "LLM_BASE_URL": "http://llm-stub:8080/v1",
    "LLM_API_KEY": "test-placeholder-key",
    "LLM_MODEL": "stub",
}


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[pytest.MonkeyPatch]:
    """Remove every Settings variable from the environment so tests start from nothing."""
    for name in Settings.model_fields:
        monkeypatch.delenv(name.upper(), raising=False)
    get_settings.cache_clear()
    yield monkeypatch
    get_settings.cache_clear()


@pytest.fixture
def valid_env(clean_env: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    for key, value in VALID_ENV.items():
        clean_env.setenv(key, value)
    return clean_env
