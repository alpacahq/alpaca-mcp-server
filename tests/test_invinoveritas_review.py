"""Tests for InvinoveritasReviewMiddleware -- no network calls, real HTTP mocking
via httpx.MockTransport, real FastMCP server + tool registration (not mocked).
"""
from __future__ import annotations

import json

import httpx
import pytest
from fastmcp import Client, FastMCP
from fastmcp.exceptions import ToolError

from alpaca_mcp_server.invinoveritas_review import InvinoveritasReviewMiddleware


def _build_server(middleware: InvinoveritasReviewMiddleware) -> FastMCP:
    server = FastMCP("test-alpaca")
    server.add_middleware(middleware)

    @server.tool(annotations={"destructiveHint": True, "readOnlyHint": False})
    async def place_stock_order(symbol: str, side: str, qty: str) -> dict:
        return {"status": "filled", "symbol": symbol, "side": side, "qty": qty}

    @server.tool(annotations={"readOnlyHint": True, "destructiveHint": False})
    async def get_account() -> dict:
        return {"cash": "1000.00"}

    return server


def _patch_httpx(monkeypatch, handler):
    transport = httpx.MockTransport(handler)

    class PatchedClient(httpx.AsyncClient):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = transport
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", PatchedClient)


@pytest.mark.asyncio
async def test_reject_blocks_destructive_tool(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["artifact_type"] == "financial_transaction"
        assert json.loads(body["artifact"])["tool_name"] == "place_stock_order"
        return httpx.Response(200, json={"verdict": "reject", "confidence": 0.9, "summary": "Notional exceeds daily risk limit."})

    _patch_httpx(monkeypatch, handler)
    server = _build_server(InvinoveritasReviewMiddleware(api_key="test_key"))

    async with Client(server) as client:
        with pytest.raises(ToolError, match="BLOCKED"):
            await client.call_tool("place_stock_order", {"symbol": "AAPL", "side": "buy", "qty": "10000"})


@pytest.mark.asyncio
async def test_readonly_tool_never_reviewed(monkeypatch):
    called = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        called["n"] += 1
        return httpx.Response(200, json={"verdict": "reject"})

    _patch_httpx(monkeypatch, handler)
    server = _build_server(InvinoveritasReviewMiddleware(api_key="test_key"))

    async with Client(server) as client:
        result = await client.call_tool("get_account", {})
        assert result.data["cash"] == "1000.00"
        assert result.meta is None or "invinoveritas_review" not in result.meta
    assert called["n"] == 0


@pytest.mark.asyncio
async def test_approve_passes_through(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"verdict": "approve", "confidence": 0.98})

    _patch_httpx(monkeypatch, handler)
    server = _build_server(InvinoveritasReviewMiddleware(api_key="test_key"))

    async with Client(server) as client:
        result = await client.call_tool("place_stock_order", {"symbol": "SPY", "side": "buy", "qty": "1"})
        assert result.data["status"] == "filled"
        assert result.meta["invinoveritas_review"] == "approve"


@pytest.mark.asyncio
async def test_advisory_mode_never_blocks(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"verdict": "reject", "confidence": 0.9})

    _patch_httpx(monkeypatch, handler)
    server = _build_server(InvinoveritasReviewMiddleware(api_key="test_key", block_on_reject=False))

    async with Client(server) as client:
        result = await client.call_tool("place_stock_order", {"symbol": "TSLA", "side": "sell", "qty": "5"})
        assert result.data["status"] == "filled"
        assert result.meta["invinoveritas_review"] == "reject"


@pytest.mark.asyncio
async def test_fails_open_on_network_error(monkeypatch):
    def raise_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("simulated timeout")

    _patch_httpx(monkeypatch, raise_handler)
    server = _build_server(InvinoveritasReviewMiddleware(api_key="test_key"))

    async with Client(server) as client:
        result = await client.call_tool("place_stock_order", {"symbol": "MSFT", "side": "buy", "qty": "1"})
        assert result.data["status"] == "filled"
        assert result.meta["invinoveritas_review"] == "unavailable"


@pytest.mark.asyncio
async def test_no_api_key_skips_review_entirely(monkeypatch):
    called = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        called["n"] += 1
        return httpx.Response(200, json={"verdict": "reject"})

    _patch_httpx(monkeypatch, handler)
    monkeypatch.delenv("IVV_API_KEY", raising=False)
    server = _build_server(InvinoveritasReviewMiddleware())

    async with Client(server) as client:
        result = await client.call_tool("place_stock_order", {"symbol": "GME", "side": "buy", "qty": "1"})
        assert result.data["status"] == "filled"
        assert result.meta["invinoveritas_review"] == "unavailable"
    assert called["n"] == 0
