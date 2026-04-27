"""
Test that vendor extension keys (x-*) are stripped from OpenAPI specs.

This validates the fix for preventing Gemini 400 errors caused by
unknown vendor extension fields in generated tool schemas.
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest
from fastmcp.client import Client

from alpaca_mcp_server.server import build_server, _strip_vendor_extensions


class TestStripVendorExtensions:
    """Unit tests for the _strip_vendor_extensions function."""

    def test_strips_dict_keys_starting_with_x(self):
        """Keys starting with 'x-' should be removed from dicts."""
        input_obj = {"name": "test", "x-internal": True, "description": "value"}
        result = _strip_vendor_extensions(input_obj)
        assert "name" in result
        assert "description" in result
        assert "x-internal" not in result

    def test_strips_nested_x_keys(self):
        """x- keys should be stripped recursively."""
        input_obj = {
            "properties": {
                "symbol": {"type": "string", "x-stoplight": True},
                "qty": {"type": "number"},
            }
        }
        result = _strip_vendor_extensions(input_obj)
        assert "x-stoplight" not in str(result)

    def test_strips_x_keys_in_lists(self):
        """x- keys should be stripped from items in lists."""
        input_obj = [
            {"name": "item1", "x-go-type": "string"},
            {"name": "item2", "x-internal": True},
        ]
        result = _strip_vendor_extensions(input_obj)
        for item in result:
            assert "x-" not in str(item)

    def test_preserves_non_x_keys(self):
        """Non-x- keys should be preserved."""
        input_obj = {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "description": {"type": "string"},
            }
        }
        result = _strip_vendor_extensions(input_obj)
        assert result == input_obj

    def test_handles_deeply_nested_structures(self):
        """Deeply nested x- keys should be stripped."""
        input_obj = {
            "a": {
                "b": {
                    "c": {
                        "x-go-type": "int",
                        "x-internal": True,
                        "value": 42,
                    }
                }
            }
        }
        result = _strip_vendor_extensions(input_obj)
        # Navigate to the innermost dict
        assert result["a"]["b"]["c"]["value"] == 42
        assert "x-go-type" not in str(result)
        assert "x-internal" not in str(result)

    def test_handles_null_and_primitive_types(self):
        """Null and primitive values should pass through unchanged."""
        assert _strip_vendor_extensions(None) is None
        assert _strip_vendor_extensions("string") == "string"
        assert _strip_vendor_extensions(123) == 123
        assert _strip_vendor_extensions(True) is True


DUMMY_ENV = {
    "ALPACA_API_KEY": "test-key",
    "ALPACA_SECRET_KEY": "test-secret",
    "ALPACA_PAPER_TRADE": "true",
}


async def _get_tool_schemas() -> list[dict]:
    """Build server and return tool schemas with their input schemas."""
    with patch.dict(os.environ, DUMMY_ENV, clear=False):
        server = build_server()
    async with Client(transport=server) as c:
        tools = await c.list_tools()
        # Return the raw tool definitions including inputSchemas
        return [
            {
                "name": t.name,
                "description": t.description,
                "inputSchema": t.inputSchema,
            }
            for t in tools
        ]


@pytest.mark.asyncio
async def test_no_x_keys_in_tool_schemas():
    """Generated tool schemas must not contain x- keys anywhere."""
    tools = await _get_tool_schemas()
    
    def contains_x_key(obj) -> bool:
        """Recursively check if object contains any x- key."""
        if isinstance(obj, dict):
            for k in obj:
                if k.startswith("x-"):
                    return True
                if contains_x_key(obj[k]):
                    return True
        elif isinstance(obj, list):
            for item in obj:
                if contains_x_key(item):
                    return True
        return False

    tools_with_x_keys = []
    for tool in tools:
        schema = tool.get("inputSchema", {})
        if contains_x_key(schema):
            tools_with_x_keys.append(tool["name"])

    assert not tools_with_x_keys, (
        f"The following tools still contain x- vendor extension keys: {tools_with_x_keys}"
    )


@pytest.mark.asyncio
async def test_no_x_go_type_in_tool_schemas():
    """Tool schemas must not contain x-go-type vendor extension."""
    tools = await _get_tool_schemas()
    
    tools_with_go_type = []
    for tool in tools:
        schema_str = str(tool.get("inputSchema", {}))
        if "x-go-type" in schema_str:
            tools_with_go_type.append(tool["name"])

    assert not tools_with_go_type, (
        f"Tools still contain x-go-type: {tools_with_go_type}"
    )
