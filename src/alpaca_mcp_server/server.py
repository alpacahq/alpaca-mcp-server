"""
Alpaca MCP Server v2 — FastMCP + OpenAPI

Builds MCP tools from Alpaca's OpenAPI specs at process init time.
No hand-crafted tool functions except for overrides (e.g., order placement).
"""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
from fastmcp import FastMCP
from fastmcp.server.providers.openapi.routing import MCPType

from .names import TOOL_DESCRIPTIONS, TOOL_NAMES
from .toolsets import OVERRIDE_OPERATION_IDS, TOOLSETS, get_active_operations

SPECS_DIR = Path(__file__).parent / "specs"

TRADING_API_BASE_URLS = {
    "paper": "https://paper-api.alpaca.markets",
    "live": "https://api.alpaca.markets",
}
MARKET_DATA_BASE_URL = "https://data.alpaca.markets"


def _load_spec(name: str) -> dict[str, Any]:
    path = SPECS_DIR / f"{name}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _make_filter(allowed_ops: set[str]):
    """Create a route_map_fn that includes only allowlisted operationIds."""
    def filter_fn(route, default_type):
        if route.operation_id in allowed_ops and route.operation_id not in OVERRIDE_OPERATION_IDS:
            return MCPType.TOOL
        return MCPType.EXCLUDE
    return filter_fn


def _make_customizer(descriptions: dict[str, str]):
    """Create an mcp_component_fn that overrides descriptions where provided."""
    def customizer(route, component):
        if route.operation_id in descriptions:
            component.description = descriptions[route.operation_id]
    return customizer


def _build_auth_headers() -> dict[str, str]:
    key = os.environ.get("ALPACA_API_KEY", "")
    secret = os.environ.get("ALPACA_SECRET_KEY", "")
    return {
        "APCA-API-KEY-ID": key,
        "APCA-API-SECRET-KEY": secret,
    }


def _get_trading_base_url() -> str:
    paper = os.environ.get("ALPACA_PAPER_TRADE", "true").lower() in ("true", "1", "yes")
    return TRADING_API_BASE_URLS["paper" if paper else "live"]


def _parse_toolsets() -> set[str] | None:
    raw = os.environ.get("ALPACA_TOOLSETS", "").strip()
    if not raw:
        return None
    return {t.strip() for t in raw.split(",") if t.strip()}


def build_server() -> FastMCP:
    """Construct the Alpaca MCP server from OpenAPI specs."""
    active_toolsets = _parse_toolsets()
    spec_ops = get_active_operations(active_toolsets)

    auth_headers = _build_auth_headers()
    trading_base = _get_trading_base_url()
    data_base = os.environ.get("DATA_API_URL", MARKET_DATA_BASE_URL).rstrip("/")

    clients: list[httpx.AsyncClient] = []

    trading_client: httpx.AsyncClient | None = None
    if "trading" in spec_ops:
        trading_client = httpx.AsyncClient(
            base_url=trading_base,
            headers=auth_headers,
            timeout=30.0,
        )
        clients.append(trading_client)

    data_client: httpx.AsyncClient | None = None
    if "market-data" in spec_ops:
        data_client = httpx.AsyncClient(
            base_url=data_base,
            headers=auth_headers,
            timeout=30.0,
        )
        clients.append(data_client)

    @asynccontextmanager
    async def lifespan(_server: FastMCP) -> AsyncIterator[dict]:
        try:
            yield {}
        finally:
            for c in clients:
                await c.aclose()

    main = FastMCP("Alpaca MCP Server", lifespan=lifespan)

    if trading_client is not None:
        allowed = spec_ops["trading"]
        spec = _load_spec("trading-api")
        sub = FastMCP.from_openapi(
            spec,
            client=trading_client,
            name="Alpaca Trading",
            mcp_names=TOOL_NAMES,
            route_map_fn=_make_filter(allowed),
            mcp_component_fn=_make_customizer(TOOL_DESCRIPTIONS),
            validate_output=False,
        )
        main.mount(sub)

    if data_client is not None:
        allowed = spec_ops["market-data"]
        spec = _load_spec("market-data-api")
        sub = FastMCP.from_openapi(
            spec,
            client=data_client,
            name="Alpaca Market Data",
            mcp_names=TOOL_NAMES,
            route_map_fn=_make_filter(allowed),
            mcp_component_fn=_make_customizer(TOOL_DESCRIPTIONS),
            validate_output=False,
        )
        main.mount(sub)

    active_ts = active_toolsets if active_toolsets is not None else set(TOOLSETS.keys())

    if trading_client is not None and "trading" in active_ts:
        _register_trading_overrides(main, trading_client)

    if data_client is not None and active_ts & {"stock-data", "crypto-data"}:
        _register_market_data_overrides(main, data_client)

    return main


def _register_trading_overrides(server: FastMCP, trading_client: httpx.AsyncClient) -> None:
    """Register hand-crafted override tools for complex trading endpoints."""
    from .overrides import register_order_tools
    register_order_tools(server, trading_client)


def _register_market_data_overrides(server: FastMCP, data_client: httpx.AsyncClient) -> None:
    """Register hand-crafted override tools for historical market data."""
    from .market_data_overrides import register_market_data_tools
    register_market_data_tools(server, data_client)
