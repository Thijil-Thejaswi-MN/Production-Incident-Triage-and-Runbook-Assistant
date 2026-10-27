from __future__ import annotations

import io
import json
from datetime import datetime
from typing import Any

import pytest

from triage.observability.logging import (
    REDACTED,
    configure_logging,
    correlation_scope,
    get_logger,
)


def _lines(stream: io.StringIO) -> list[dict[str, Any]]:
    return [json.loads(line) for line in stream.getvalue().splitlines() if line.strip()]


@pytest.fixture
def stream() -> io.StringIO:
    buf = io.StringIO()
    configure_logging(level="DEBUG", json=True, stream=buf)
    return buf


def test_each_line_is_json_with_timestamp_level_and_event(stream: io.StringIO) -> None:
    get_logger("t").info("run_submitted", alert_id="a-1")
    (record,) = _lines(stream)
    assert record["event"] == "run_submitted"
    assert record["level"] == "info"
    assert record["alert_id"] == "a-1"
    ts = datetime.fromisoformat(record["timestamp"].replace("Z", "+00:00"))
    assert ts.utcoffset() is not None and ts.utcoffset().total_seconds() == 0  # type: ignore[union-attr]


def test_correlation_id_is_bound_inside_scope_and_removed_after(stream: io.StringIO) -> None:
    log = get_logger("t")
    with correlation_scope("run-123") as cid:
        log.info("inside")
        log.warning("inside_again")
    log.info("outside")
    inside, inside_again, outside = _lines(stream)
    assert cid == "run-123"
    assert inside["correlation_id"] == inside_again["correlation_id"] == "run-123"
    assert "correlation_id" not in outside


def test_generated_correlation_ids_are_unique(stream: io.StringIO) -> None:
    with correlation_scope() as first:
        get_logger().info("a")
    with correlation_scope() as second:
        get_logger().info("b")
    a, b = _lines(stream)
    assert first != second
    assert (a["correlation_id"], b["correlation_id"]) == (first, second)
    assert len(first) == 32


def test_nested_scope_restores_outer_correlation_id(stream: io.StringIO) -> None:
    with correlation_scope("outer"):
        with correlation_scope("inner"):
            get_logger().info("inner_event")
        get_logger().info("outer_event")
    inner, outer = _lines(stream)
    assert inner["correlation_id"] == "inner"
    assert outer["correlation_id"] == "outer"


def test_sensitive_values_are_redacted_but_token_counts_are_not(stream: io.StringIO) -> None:
    fake_key = "abc123" + "secretvalue"  # built at runtime so the secret scanner stays clean
    get_logger().info(
        "llm_call",
        llm_api_key=fake_key,
        authorization="Bearer xyz",
        password="hunter2",
        prompt_tokens=120,
        completion_tokens=30,
    )
    (record,) = _lines(stream)
    assert record["llm_api_key"] == REDACTED
    assert record["authorization"] == REDACTED
    assert record["password"] == REDACTED
    assert record["prompt_tokens"] == 120
    assert record["completion_tokens"] == 30
    assert fake_key not in stream.getvalue()


def test_level_filtering(stream: io.StringIO) -> None:
    configure_logging(level="WARNING", json=True, stream=stream)
    get_logger().info("dropped")
    get_logger().warning("kept")
    assert [r["event"] for r in _lines(stream)] == ["kept"]


def test_exceptions_are_rendered_into_the_json_line(stream: io.StringIO) -> None:
    try:
        raise ValueError("boom")
    except ValueError:
        get_logger().exception("failed")
    (record,) = _lines(stream)
    assert record["level"] == "error"
    assert "ValueError: boom" in record["exception"]
