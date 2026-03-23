"""Shared fixtures for the Alpaca MCP Server test suite."""

from __future__ import annotations

import os

import pytest
from fastmcp.client import Client

from alpaca_mcp_server.server import build_server


@pytest.fixture(autouse=True, scope="session")
async def _cleanup_paper_account():
    """Cancel stale orders and close orphan positions before the suite runs.

    Ensures a clean slate even if a previous CI run crashed mid-test.
    Silently skips when paper API credentials are absent.
    """
    if not (os.environ.get("ALPACA_API_KEY") and os.environ.get("ALPACA_SECRET_KEY")):
        yield
        return

    os.environ.setdefault("ALPACA_PAPER_TRADE", "true")
    server = build_server()
    async with Client(transport=server) as mcp:
        await mcp.call_tool("cancel_all_orders", {})
        await mcp.call_tool("close_all_positions", {})
        # close_all_positions may queue sell orders when market is closed;
        # cancel them so they don't trigger wash-trade rejections in tests.
        await mcp.call_tool("cancel_all_orders", {})
    yield
