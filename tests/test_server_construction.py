"""
Layer 1: Server construction tests — no network, no real credentials.

Verifies that build_server() produces the expected set of MCP tools
from the bundled OpenAPI specs. Catches FastMCP API breakage, spec
parsing failures, and toolset/names misconfiguration.
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest
from fastmcp.client import Client

from alpaca_mcp_server.server import build_server

DUMMY_ENV = {
    "ALPACA_API_KEY": "test-key",
    "ALPACA_SECRET_KEY": "test-secret",
    "ALPACA_PAPER_TRADE": "true",
}

EXPECTED_TOOLS = {
    # Account
    "get_account_info",
    "get_account_config",
    "update_account_config",
    "get_portfolio_history",
    "get_account_activities",
    "get_account_activities_by_type",
    # Trading: Orders
    "get_orders",
    "get_order_by_id",
    "get_order_by_client_id",
    "replace_order_by_id",
    "cancel_order_by_id",
    "cancel_all_orders",
    # Trading: Positions
    "get_all_positions",
    "get_open_position",
    "close_position",
    "close_all_positions",
    "exercise_options_position",
    "do_not_exercise_options_position",
    # Watchlists
    "get_watchlists",
    "create_watchlist",
    "get_watchlist_by_id",
    "update_watchlist_by_id",
    "delete_watchlist_by_id",
    "add_asset_to_watchlist_by_id",
    "remove_asset_from_watchlist_by_id",
    # Assets & Market Info
    "get_all_assets",
    "get_asset",
    "get_option_contracts",
    "get_option_contract",
    "get_calendar",
    "get_clock",
    "get_corporate_action_announcements",
    "get_corporate_action_announcement",
    # Stock Data
    "get_stock_bars",
    "get_stock_quotes",
    "get_stock_trades",
    "get_stock_latest_bar",
    "get_stock_latest_quote",
    "get_stock_latest_trade",
    "get_stock_snapshot",
    "get_most_active_stocks",
    "get_market_movers",
    # Crypto Data
    "get_crypto_bars",
    "get_crypto_quotes",
    "get_crypto_trades",
    "get_crypto_latest_bar",
    "get_crypto_latest_quote",
    "get_crypto_latest_trade",
    "get_crypto_snapshot",
    "get_crypto_latest_orderbook",
    # Options Data
    "get_option_bars",
    "get_option_trades",
    "get_option_latest_trade",
    "get_option_latest_quote",
    "get_option_snapshot",
    "get_option_chain",
    "get_option_exchange_codes",
    # Corporate Actions (Market Data)
    "get_corporate_actions",
    # Order Overrides
    "place_stock_order",
    "place_crypto_order",
    "place_option_order",
}


async def _list_tools(env: dict | None = None) -> list:
    """Build server with given env and return its tool list."""
    use_env = env or DUMMY_ENV
    with patch.dict(os.environ, use_env, clear=False):
        server = build_server()
    async with Client(transport=server) as c:
        return await c.list_tools()


async def test_tool_count():
    """Server must expose exactly 61 tools."""
    tools = await _list_tools()
    assert len(tools) == 61, f"Expected 61 tools, got {len(tools)}"


async def test_tool_names_match():
    """Every expected tool name must be present, with no extras."""
    tools = await _list_tools()
    actual = {t.name for t in tools}
    missing = EXPECTED_TOOLS - actual
    extra = actual - EXPECTED_TOOLS
    assert not missing, f"Missing tools: {sorted(missing)}"
    assert not extra, f"Unexpected tools: {sorted(extra)}"


async def test_all_tools_have_descriptions():
    """Every tool must have a non-empty description."""
    tools = await _list_tools()
    empty = [t.name for t in tools if not t.description or not t.description.strip()]
    assert not empty, f"Tools with empty descriptions: {sorted(empty)}"


async def test_order_tools_have_destructive_hint():
    """Order placement tools must be annotated as destructive."""
    tools = await _list_tools()
    order_tools = [t for t in tools if t.name.startswith("place_")]
    assert len(order_tools) == 3
    for t in order_tools:
        annotations = t.annotations
        assert annotations is not None, f"{t.name} missing annotations"
        assert annotations.destructiveHint is True, (
            f"{t.name} should have destructiveHint=True"
        )


async def test_toolset_filtering():
    """ALPACA_TOOLSETS should limit which tools are exposed."""
    tools = await _list_tools({**DUMMY_ENV, "ALPACA_TOOLSETS": "account"})
    names = {t.name for t in tools}
    assert "get_account_info" in names
    assert "place_stock_order" not in names
    assert "get_stock_bars" not in names
