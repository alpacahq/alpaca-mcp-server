"""No-network tests for hand-written order placement overrides."""

from __future__ import annotations

import json
from typing import Any, cast

import pytest
from fastmcp import FastMCP
from fastmcp.client import Client

from alpaca_mcp_server.overrides import register_order_tools


class _FakeResponse:
    is_error = False

    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def json(self) -> dict:
        return self._payload


class _FakeOrderClient:
    def __init__(self) -> None:
        self.requests: list[tuple[str, dict]] = []

    async def post(self, path: str, json: dict) -> _FakeResponse:
        self.requests.append((path, json.copy()))
        return _FakeResponse({"ok": True})


def _parse_result(result: Any) -> dict:
    if getattr(result, "data", None) is not None:
        data = result.data
        if isinstance(data, dict):
            return data
        if hasattr(data, "model_dump"):
            return data.model_dump()

    for block in getattr(result, "content", []):
        text = getattr(block, "text", None)
        if text is not None:
            return json.loads(text)

    raise AssertionError(f"Could not parse tool result: {result!r}")


async def _call_option_order(args: dict) -> tuple[_FakeOrderClient, dict]:
    server = FastMCP("Order Override Tests")
    client = _FakeOrderClient()
    register_order_tools(server, cast(Any, client))

    async with Client(transport=server) as mcp:
        result = await mcp.call_tool("place_option_order", args)

    return client, _parse_result(result)


async def test_place_option_market_order_payload():
    client, result = await _call_option_order({
        "qty": "1",
        "symbol": "AAPL250321C00150000",
        "side": "buy",
    })

    assert result == {"ok": True}
    assert client.requests == [(
        "/v2/orders",
        {
            "qty": "1",
            "type": "market",
            "time_in_force": "day",
            "symbol": "AAPL250321C00150000",
            "side": "buy",
        },
    )]


async def test_place_option_limit_order_payload():
    client, result = await _call_option_order({
        "qty": "1",
        "type": "limit",
        "symbol": "AAPL250321C00150000",
        "side": "buy",
        "limit_price": "1.25",
    })

    assert result == {"ok": True}
    assert client.requests[0][1]["type"] == "limit"
    assert client.requests[0][1]["limit_price"] == "1.25"
    assert "stop_price" not in client.requests[0][1]


async def test_place_option_stop_order_payload():
    client, result = await _call_option_order({
        "qty": "1",
        "type": "stop",
        "symbol": "AAPL250321C00150000",
        "side": "sell",
        "stop_price": "0.75",
    })

    assert result == {"ok": True}
    assert client.requests[0][1]["type"] == "stop"
    assert client.requests[0][1]["stop_price"] == "0.75"
    assert "limit_price" not in client.requests[0][1]


async def test_place_option_stop_limit_order_payload():
    client, result = await _call_option_order({
        "qty": "1",
        "type": "stop_limit",
        "symbol": "AAPL250321C00150000",
        "side": "sell",
        "stop_price": "0.75",
        "limit_price": "0.70",
    })

    assert result == {"ok": True}
    body = client.requests[0][1]
    assert body["type"] == "stop_limit"
    assert body["stop_price"] == "0.75"
    assert body["limit_price"] == "0.70"


async def test_place_option_limit_order_requires_limit_price():
    client, result = await _call_option_order({
        "qty": "1",
        "type": "limit",
        "symbol": "AAPL250321C00150000",
        "side": "buy",
    })

    assert result == {"error": {"message": "limit orders require limit_price"}}
    assert client.requests == []


async def test_place_option_stop_order_requires_stop_price():
    client, result = await _call_option_order({
        "qty": "1",
        "type": "stop",
        "symbol": "AAPL250321C00150000",
        "side": "sell",
    })

    assert result == {"error": {"message": "stop orders require stop_price"}}
    assert client.requests == []


@pytest.mark.parametrize(
    "args",
    [
        {
            "qty": "1",
            "type": "stop_limit",
            "symbol": "AAPL250321C00150000",
            "side": "sell",
            "limit_price": "0.70",
        },
        {
            "qty": "1",
            "type": "stop_limit",
            "symbol": "AAPL250321C00150000",
            "side": "sell",
            "stop_price": "0.75",
        },
    ],
)
async def test_place_option_stop_limit_order_requires_stop_and_limit_prices(args: dict):
    client, result = await _call_option_order(args)

    assert result == {
        "error": {
            "message": "stop_limit orders require stop_price and limit_price"
        }
    }
    assert client.requests == []
