"""Unit tests for the relative lookback helper in market_data_overrides."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from alpaca_mcp_server.market_data_overrides import _relative_start


def test_lookback_is_anchored_to_end_when_given():
    assert _relative_start(days=5, end="2024-03-15T00:00:00Z") == "2024-03-10T00:00:00Z"


def test_lookback_honours_end_offset_and_hours_minutes():
    start = _relative_start(hours=1, minutes=30, end="2024-03-15T10:00:00-04:00")
    assert start == "2024-03-15T12:30:00Z"


def test_naive_end_is_treated_as_utc():
    assert _relative_start(days=1, end="2024-03-15T09:00:00") == "2024-03-14T09:00:00Z"


def test_lookback_defaults_to_now_without_end():
    before = datetime.now(timezone.utc) - timedelta(days=2, seconds=1)
    start = datetime.strptime(_relative_start(days=2), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    assert before <= start <= datetime.now(timezone.utc) - timedelta(days=2) + timedelta(seconds=1)


def test_unparseable_end_falls_back_to_now():
    assert _relative_start(days=1, end="not-a-date") is not None


def test_zero_offset_returns_none():
    assert _relative_start(end="2024-03-15T00:00:00Z") is None
