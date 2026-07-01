"""
ReadMe Docs MCP integration tests — real network calls to Alpaca's ReadMe MCP.

Run locally with:
    ALPACA_RUN_README_INTEGRATION=true pytest tests/test_readme_integration.py -v
"""

from __future__ import annotations

import json
import os
from typing import Any

import pytest
from fastmcp.client import Client

from alpaca_mcp_server.security import DATA_KEY
from alpaca_mcp_server.server import build_server

_run_live_readme = (
    os.environ.get("CI") == "true"
    or os.environ.get("ALPACA_RUN_README_INTEGRATION", "").lower() in {"1", "true", "yes"}
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not _run_live_readme,
        reason="Set ALPACA_RUN_README_INTEGRATION=true to run live ReadMe MCP tests",
    ),
]


def _parse(result: Any) -> dict[str, Any] | list[Any] | str:
    if getattr(result, "structured_content", None) is not None:
        parsed = result.structured_content
        if isinstance(parsed, dict) and DATA_KEY in parsed:
            return parsed[DATA_KEY]
        return parsed

    if getattr(result, "data", None) is not None:
        return result.data

    for block in getattr(result, "content", []) or []:
        text = getattr(block, "text", None)
        if text is None:
            continue
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return text
        if isinstance(parsed, dict) and DATA_KEY in parsed:
            return parsed[DATA_KEY]
        return parsed

    return str(result)


async def _call_readme_tool(tool_name: str, args: dict[str, Any]) -> dict[str, Any] | list[Any] | str:
    server = build_server()
    async with Client(transport=server) as client:
        return _parse(await client.call_tool(tool_name, args))


async def test_live_readme_endpoint_search_filters_broker_api() -> None:
    result = await _call_readme_tool("search_alpaca_api_specs", {"query": "orders"})

    assert isinstance(result, dict)
    specs = result.get("specs")
    assert isinstance(specs, list)
    assert specs

    titles = {spec.get("title") for spec in specs if isinstance(spec, dict)}
    assert titles <= {"Trading API", "Market Data API", "Authentication API"}
    assert "Broker API" not in titles
    assert "Trading API" in titles

    trading_spec = next(spec for spec in specs if spec.get("title") == "Trading API")
    endpoints = trading_spec.get("endpoints")
    assert isinstance(endpoints, list)
    assert any(endpoint.get("path") == "/v2/orders" for endpoint in endpoints)


async def test_live_readme_endpoint_docs_fetch_trading_endpoint() -> None:
    result = await _call_readme_tool(
        "get_alpaca_endpoint_docs",
        {"path": "/v2/orders", "method": "GET", "title": "Trading API"},
    )

    assert isinstance(result, dict)
    serialized = json.dumps(result)
    assert "/v2/orders" in serialized
    assert "GET" in serialized or "get" in serialized
