"""
Layer 1: Server construction tests — no network, no real credentials.

Verifies that build_server() produces the expected set of MCP tools
from the bundled OpenAPI specs. Catches FastMCP API breakage, spec
parsing failures, and toolset/names misconfiguration.
"""

from __future__ import annotations

import json
import os
from types import SimpleNamespace
from types import TracebackType
from typing import Any
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from fastmcp.client import Client

from alpaca_mcp_server.readme_docs import (
    DEFAULT_README_MCP_URL,
    README_DOC_TOOL_NAMES,
    ReadMeClientFactory,
)
from alpaca_mcp_server.security import DATA_KEY, SECURITY_KEY
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
    # News
    "get_news",
    # Fixed Income Data
    "get_fixed_income_latest_quotes",
    # Index Data
    "get_index_latest_values",
    "get_index_values",
    # Locates (Short Selling)
    "get_locates",
    "create_locate",
    "get_locate",
    "get_locate_quotes",
    # Order Overrides
    "place_stock_order",
    "place_crypto_order",
    "place_option_order",
    # ReadMe Docs
    "search_alpaca_docs",
    "fetch_alpaca_doc",
    "search_alpaca_api_specs",
    "list_alpaca_api_endpoints",
    "get_alpaca_endpoint_docs",
}

CallRecord = tuple[str, dict[str, Any] | None, dict[str, Any]]


class FakeReadMeClient:
    def __init__(self, calls: list[CallRecord]) -> None:
        self._calls = calls

    async def __aenter__(self) -> "FakeReadMeClient":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        return None

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        self._calls.append((name, arguments, kwargs))
        return SimpleNamespace(data={"upstream_tool": name, "arguments": arguments})


class FakeReadMeTextClient:
    def __init__(self, calls: list[CallRecord], payload: Any) -> None:
        self._calls = calls
        self._payload = payload

    async def __aenter__(self) -> "FakeReadMeTextClient":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        return None

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        self._calls.append((name, arguments, kwargs))
        return SimpleNamespace(content=[SimpleNamespace(text=json.dumps(self._payload))])


class FakeReadMeEndpointSearchClient:
    def __init__(
        self,
        calls: list[CallRecord],
        payload: list[dict[str, Any]],
    ) -> None:
        self._calls = calls
        self._payload = payload

    async def __aenter__(self) -> "FakeReadMeEndpointSearchClient":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        return None

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        self._calls.append((name, arguments, kwargs))
        return SimpleNamespace(data=self._payload)


class FakeReadMeErrorClient:
    async def __aenter__(self) -> "FakeReadMeErrorClient":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        return None

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        raise TimeoutError("ReadMe timed out")


async def _list_tools(
    env: dict | None = None,
    readme_client_factory: ReadMeClientFactory | None = None,
) -> list:
    """Build server with given env and return its tool list."""
    use_env = env or DUMMY_ENV
    with patch.dict(os.environ, use_env, clear=False):
        server = build_server(readme_client_factory=readme_client_factory)
    async with Client(transport=server) as c:
        return await c.list_tools()


def _parse_tool_result(result: Any) -> Any:
    if getattr(result, "structured_content", None) is not None:
        return result.structured_content
    if getattr(result, "data", None) is not None:
        return result.data
    text_blocks: list[str] = []
    for block in result.content:
        text = getattr(block, "text", None)
        if text is not None:
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                text_blocks.append(text)
    if text_blocks:
        return "\n".join(text_blocks)
    raise AssertionError(f"Unexpected tool result: {result!r}")


async def _call_tool(
    tool_name: str,
    args: dict[str, Any],
    readme_client_factory: ReadMeClientFactory | None = None,
    env: dict | None = None,
    raise_on_error: bool = True,
) -> Any:
    with patch.dict(os.environ, env or DUMMY_ENV, clear=False):
        server = build_server(readme_client_factory=readme_client_factory)
    async with Client(transport=server) as client:
        return _parse_tool_result(
            await client.call_tool(tool_name, args, raise_on_error=raise_on_error)
        )


async def test_tool_count():
    """Server must expose exactly 74 tools."""
    tools = await _list_tools()
    assert len(tools) == 74, f"Expected 74 tools, got {len(tools)}"


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


async def test_readme_tools_are_registered_by_default():
    tools = await _list_tools()
    actual = {t.name for t in tools}
    assert README_DOC_TOOL_NAMES <= actual


async def test_readme_docs_tools_have_required_openai_annotations():
    tools = await _list_tools()
    by_name = {tool.name: tool for tool in tools}

    for name in README_DOC_TOOL_NAMES:
        annotations = by_name[name].annotations
        assert annotations is not None, f"{name} missing annotations"
        assert annotations.readOnlyHint is True
        assert annotations.openWorldHint is True
        assert annotations.destructiveHint is False


async def test_readme_tool_descriptions_route_by_use_case():
    tools = await _list_tools()
    by_name = {tool.name: tool for tool in tools}

    docs_description = by_name["search_alpaca_docs"].description or ""
    assert "Search Alpaca documentation pages and guides" in docs_description
    assert "Use for conceptual or product questions" in docs_description
    assert "not for exact API method/path lookup" in docs_description
    assert "prefer search_alpaca_api_specs" in docs_description
    assert "llms.txt" not in docs_description

    fetch_description = by_name["fetch_alpaca_doc"].description or ""
    assert "Fetch one Alpaca ReadMe documentation page by page ID" in fetch_description
    assert "Use after search_alpaca_docs returns a relevant page ID" in fetch_description
    assert "not for API endpoint lookup by method and path" in fetch_description

    specs_description = by_name["search_alpaca_api_specs"].description or ""
    assert "Search Alpaca API reference endpoints" in specs_description
    assert "Use when the exact method and path are unknown" in specs_description
    assert "does not execute endpoints" in specs_description
    assert "excludes Broker API" in specs_description

    list_description = by_name["list_alpaca_api_endpoints"].description or ""
    assert "List endpoints for one allowed Alpaca OpenAPI spec" in list_description
    assert "browsing the available endpoint inventory" in list_description
    assert "excludes Broker API" in list_description
    assert "prefer search_alpaca_api_specs" in list_description

    endpoint_description = by_name["get_alpaca_endpoint_docs"].description or ""
    assert "Fetch reference docs for one exact Alpaca API endpoint" in endpoint_description
    assert "Use when the endpoint is already resolved" in endpoint_description
    assert "does not execute the endpoint" in endpoint_description
    assert "excludes Broker API" in endpoint_description


async def test_readme_tool_errors_include_public_docs_fallback():
    def factory() -> FakeReadMeErrorClient:
        return FakeReadMeErrorClient()

    result = await _call_tool(
        "search_alpaca_docs",
        {"query": "market data"},
        readme_client_factory=factory,
    )

    assert result[SECURITY_KEY]["risk"] == "external_text"
    error = result[DATA_KEY]["error"]
    assert error["message"] == "ReadMe MCP error: ReadMe timed out"
    assert error["fallback"]["message"].startswith("ReadMe MCP lookup failed")
    assert error["fallback"]["urls"] == [
        "https://docs.alpaca.markets/us/reference/api-references",
        "https://docs.alpaca.markets/llms.txt",
        "https://docs.alpaca.markets/llms-full.txt",
    ]


async def test_readme_tools_forward_to_whitelisted_upstream_tools():
    calls: list[CallRecord] = []

    def factory() -> FakeReadMeClient:
        return FakeReadMeClient(calls)

    scenarios = [
        (
            "search_alpaca_docs",
            {"query": "paper trading"},
            "search",
            {"query": "paper trading"},
        ),
        (
            "fetch_alpaca_doc",
            {"id": "doc-123"},
            "fetch",
            {"id": "doc-123"},
        ),
        (
            "search_alpaca_api_specs",
            {"query": "orders"},
            "search-endpoints",
            {"pattern": "orders"},
        ),
        (
            "list_alpaca_api_endpoints",
            {},
            "list-endpoints",
            {"title": "Trading API"},
        ),
        (
            "get_alpaca_endpoint_docs",
            {"path": "/v2/orders", "method": "post"},
            "get-endpoint",
            {"path": "/v2/orders", "method": "POST", "title": "Trading API"},
        ),
    ]

    for tool_name, args, upstream_tool, upstream_args in scenarios:
        result = await _call_tool(
            tool_name,
            args,
            readme_client_factory=factory,
        )
        assert result[DATA_KEY] == {"upstream_tool": upstream_tool, "arguments": upstream_args}
        assert result[SECURITY_KEY]["risk"] == "external_text"

    assert calls == [
        (upstream_tool, upstream_args, {"raise_on_error": False})
        for _, _, upstream_tool, upstream_args in scenarios
    ]


async def test_readme_tools_parse_json_text_results():
    calls: list[CallRecord] = []
    payload = {
        "openapi": "3.0.0",
        "paths": {"/v2/orders": {"post": {"summary": "Create an Order"}}},
    }

    def factory() -> FakeReadMeTextClient:
        return FakeReadMeTextClient(calls, payload)

    result = await _call_tool(
        "get_alpaca_endpoint_docs",
        {"path": "/v2/orders", "method": "post"},
        readme_client_factory=factory,
    )

    assert result[DATA_KEY] == payload
    assert calls == [
        (
            "get-endpoint",
            {"path": "/v2/orders", "method": "POST", "title": "Trading API"},
            {"raise_on_error": False},
        )
    ]


async def test_readme_endpoint_search_is_scoped_to_allowed_specs():
    calls: list[CallRecord] = []
    payload = [
        {
            "title": "Trading API",
            "endpoints": [
                {"path": "/v2/orders", "method": "POST", "summary": "Create an Order"},
                {"path": "/v2/assets", "method": "GET", "summary": "List Assets"},
            ],
        },
        {
            "title": "Market Data API",
            "endpoints": [
                {"path": "/v2/stocks/bars", "method": "GET", "summary": "Stock Bars"},
            ],
        },
        {
            "title": "Authentication API",
            "endpoints": [
                {"path": "/oauth/token", "method": "POST", "summary": "Create OAuth Token"},
            ],
        },
        {
            "title": "Broker API",
            "endpoints": [
                {"path": "/v1/trading/accounts/{account_id}/orders", "method": "POST"},
            ],
        },
    ]

    def factory() -> FakeReadMeEndpointSearchClient:
        return FakeReadMeEndpointSearchClient(calls, payload)

    result = await _call_tool(
        "search_alpaca_api_specs",
        {"query": "orders"},
        readme_client_factory=factory,
    )

    assert result[DATA_KEY] == {
        "query": "orders",
        "specs": [
            {
                "title": "Trading API",
                "endpoints": [
                    {
                        "path": "/v2/orders",
                        "method": "POST",
                        "summary": "Create an Order",
                    },
                    {
                        "path": "/v2/assets",
                        "method": "GET",
                        "summary": "List Assets",
                    },
                ],
            },
            {
                "title": "Market Data API",
                "endpoints": [
                    {
                        "path": "/v2/stocks/bars",
                        "method": "GET",
                        "summary": "Stock Bars",
                    },
                ],
            },
            {
                "title": "Authentication API",
                "endpoints": [
                    {
                        "path": "/oauth/token",
                        "method": "POST",
                        "summary": "Create OAuth Token",
                    },
                ],
            },
        ],
    }
    assert calls == [("search-endpoints", {"pattern": "orders"}, {"raise_on_error": False})]


async def test_readme_endpoint_tools_reject_broker_api_title():
    calls: list[CallRecord] = []

    def factory() -> FakeReadMeClient:
        return FakeReadMeClient(calls)

    list_result = await _call_tool(
        "list_alpaca_api_endpoints",
        {"title": "Broker API"},
        readme_client_factory=factory,
    )
    get_result = await _call_tool(
        "get_alpaca_endpoint_docs",
        {
            "path": "/v1/trading/accounts/{account_id}/orders",
            "method": "POST",
            "title": "Broker API",
        },
        readme_client_factory=factory,
    )

    expected = {
        "error": {
            "message": (
                "Unsupported Alpaca API spec title: Broker API. "
                "Use one of: Trading API, Market Data API, Authentication API."
            )
        }
    }
    assert list_result[DATA_KEY] == expected
    assert get_result[DATA_KEY] == expected
    assert calls == []


def test_readme_mcp_url_is_pinned_to_us_project():
    parsed = urlparse(DEFAULT_README_MCP_URL)
    assert parsed.path == "/mcp"
    assert parse_qs(parsed.query) == {"project": ["us"]}


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
    assert README_DOC_TOOL_NAMES <= names
