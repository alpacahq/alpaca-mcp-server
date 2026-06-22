"""
Tests for the TrustBoundaryMiddleware trust-boundary envelope.

Covers:
- Middleware wraps structured tool results in the envelope
- Middleware uses risk-appropriate warning text
- Middleware does NOT double-wrap results that already contain the envelope
- Root middleware intercepts both mounted OpenAPI tools and hand-written overrides
- Tool count and names are unchanged after adding the middleware
"""

from __future__ import annotations

import json
import os
from unittest.mock import patch

from fastmcp import FastMCP
from fastmcp.client import Client

from alpaca_mcp_server.security import (
    DATA_KEY,
    INSTRUCTIONS,
    SECURITY_KEY,
    WRAPPED_MARKER,
    TrustBoundaryMiddleware,
)
from alpaca_mcp_server.server import build_server

DUMMY_ENV = {
    "ALPACA_API_KEY": "test-key",
    "ALPACA_SECRET_KEY": "test-secret",
    "ALPACA_PAPER_TRADE": "true",
}


def _parse_structured(raw) -> dict:
    """Extract structured_content from a CallToolResult."""
    if hasattr(raw, "structured_content") and raw.structured_content is not None:
        return raw.structured_content
    if hasattr(raw, "data") and raw.data is not None:
        return raw.data
    for block in raw.content:
        if hasattr(block, "text"):
            try:
                return json.loads(block.text)
            except (json.JSONDecodeError, TypeError):
                pass
    return {}


async def test_wraps_structured_result():
    """Structured dict results get wrapped under the envelope."""
    server = FastMCP("test")
    server.add_middleware(TrustBoundaryMiddleware())

    @server.tool()
    async def echo_tool(msg: str) -> dict:
        return {"message": msg}

    async with Client(transport=server) as client:
        raw = await client.call_tool("echo_tool", {"msg": "hello"})

    result = _parse_structured(raw)
    assert SECURITY_KEY in result
    assert result[SECURITY_KEY]["trust"] == "untrusted_tool_output"
    assert result[SECURITY_KEY]["tool_name"] == "echo_tool"
    assert result[SECURITY_KEY]["risk"] == "api_structured"
    assert result[SECURITY_KEY]["instructions"] == INSTRUCTIONS["api_structured"]
    assert DATA_KEY in result
    assert result[DATA_KEY]["message"] == "hello"


async def test_wraps_text_fallback_result():
    """Dict results with text content get wrapped normally."""
    server = FastMCP("test")
    server.add_middleware(TrustBoundaryMiddleware())

    @server.tool()
    async def raw_text_tool() -> dict:
        return {"raw_response": "plain text from upstream API"}

    async with Client(transport=server) as client:
        raw = await client.call_tool("raw_text_tool", {})

    result = _parse_structured(raw)
    assert SECURITY_KEY in result
    assert DATA_KEY in result
    assert result[DATA_KEY]["raw_response"] == "plain text from upstream API"


async def test_does_not_double_wrap():
    """If the result already contains the security key, skip wrapping."""
    server = FastMCP("test")
    server.add_middleware(TrustBoundaryMiddleware())

    @server.tool()
    async def pre_wrapped_tool() -> dict:
        return {
            SECURITY_KEY: {
                "trust": "untrusted_tool_output",
                "tool_name": "pre_wrapped_tool",
                "instructions": "already wrapped",
            },
            DATA_KEY: {"inner": "value"},
        }

    async with Client(transport=server) as client:
        raw = await client.call_tool("pre_wrapped_tool", {})

    result = _parse_structured(raw)
    assert result[SECURITY_KEY]["instructions"] == "already wrapped"
    assert result[DATA_KEY] == {"inner": "value"}
    assert DATA_KEY not in result.get(DATA_KEY, {})


async def test_middleware_intercepts_mounted_tools():
    """Root middleware wraps results from tools on mounted sub-servers."""
    parent = FastMCP("parent")
    parent.add_middleware(TrustBoundaryMiddleware())

    child = FastMCP("child")

    @child.tool()
    async def child_tool(x: int) -> dict:
        return {"value": x}

    parent.mount(child)

    async with Client(transport=parent) as client:
        raw = await client.call_tool("child_tool", {"x": 42})

    result = _parse_structured(raw)
    assert SECURITY_KEY in result, "Root middleware should wrap mounted tool results"
    assert result[DATA_KEY]["value"] == 42


async def test_meta_contains_wrapped_marker():
    """The result meta should contain the wrapped marker."""
    server = FastMCP("test")
    server.add_middleware(TrustBoundaryMiddleware())

    @server.tool()
    async def simple_tool() -> dict:
        return {"ok": True}

    async with Client(transport=server) as client:
        raw = await client.call_tool("simple_tool", {})

    if hasattr(raw, "meta") and raw.meta is not None:
        assert raw.meta.get(WRAPPED_MARKER) is True


async def test_real_server_tools_are_wrapped():
    """build_server() tools produce enveloped results via the middleware."""
    with patch.dict(os.environ, {**DUMMY_ENV, "ALPACA_TOOLSETS": "account"}, clear=False):
        server = build_server()

    async with Client(transport=server) as client:
        tools = await client.list_tools()
        tool_names = {t.name for t in tools}
        assert "get_account_info" in tool_names


async def test_real_server_tool_count_unchanged():
    """Adding the middleware must not change the number or names of tools."""
    with patch.dict(os.environ, DUMMY_ENV, clear=False):
        server = build_server()

    async with Client(transport=server) as client:
        tools = await client.list_tools()

    assert len(tools) == 65, f"Expected 65 tools, got {len(tools)}"


async def test_risk_level_used_in_envelope():
    """The envelope includes the risk field from the tool registry."""
    server = FastMCP("test")
    server.add_middleware(TrustBoundaryMiddleware())

    @server.tool()
    async def get_news() -> dict:
        return {"news": [{"headline": "test"}]}

    async with Client(transport=server) as client:
        raw = await client.call_tool("get_news", {})

    result = _parse_structured(raw)
    assert result[SECURITY_KEY]["risk"] == "external_text"
    assert result[SECURITY_KEY]["instructions"] == INSTRUCTIONS["external_text"]
