"""Tests for the get_stock_quote MCP tool."""

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from alpaca_mcp_server import server


def _sample_quote(ask: float, bid: float) -> SimpleNamespace:
    """Create a lightweight quote object with the required attributes."""
    return SimpleNamespace(
        ask_price=ask,
        bid_price=bid,
        ask_size=100,
        bid_size=200,
        timestamp=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
    )


@pytest.mark.asyncio
async def test_get_stock_quote_multiple_symbols_formats_each_symbol():
    quotes = {
        "AAPL": _sample_quote(ask=190.25, bid=189.95),
        "MSFT": _sample_quote(ask=420.10, bid=419.75),
    }

    with patch.object(server, "_ensure_clients"), patch.object(
        server, "stock_historical_data_client"
    ) as mock_client:
        mock_client.get_stock_latest_quote.return_value = quotes

        result = await server.get_stock_quote(["AAPL", "MSFT"])

    assert "Symbol: AAPL" in result
    assert "Ask Price: $190.25" in result
    assert "Symbol: MSFT" in result
    assert "Bid Price: $419.75" in result


@pytest.mark.asyncio
async def test_get_stock_quote_missing_symbol_reports_message():
    quotes = {"AAPL": _sample_quote(ask=190.25, bid=189.95)}

    with patch.object(server, "_ensure_clients"), patch.object(
        server, "stock_historical_data_client"
    ) as mock_client:
        mock_client.get_stock_latest_quote.return_value = quotes

        result = await server.get_stock_quote(["AAPL", "MSFT"])

    assert "Symbol: MSFT" in result
    assert "No quote data found for MSFT." in result
