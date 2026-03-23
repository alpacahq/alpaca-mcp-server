"""Tests for bracket/OTO/OCO order serialization.

Verifies that take_profit_price and stop_loss_price parameters are correctly
nested into the JSON structure required by the Alpaca Trading API v2:

    {
        "take_profit": { "limit_price": "..." },
        "stop_loss": { "stop_price": "...", "limit_price": "..." }
    }
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastmcp.client import Client

from alpaca_mcp_server.server import build_server


def _fake_ok_response(body: dict) -> httpx.Response:
    """Build a fake 200 response carrying the request body back as JSON."""
    resp = httpx.Response(
        200,
        json={
            "id": "fake-order-id",
            "status": "accepted",
            **body,
        },
        request=httpx.Request("POST", "https://example.com/v2/orders"),
    )
    return resp


@pytest.fixture()
def captured_bodies() -> list[dict]:
    return []


@pytest.fixture()
def _mock_post(captured_bodies: list[dict]):
    """Patch httpx.AsyncClient.post to capture the JSON body."""
    original_post = httpx.AsyncClient.post

    async def fake_post(self, url, **kwargs):
        if "/v2/orders" in str(url):
            body = kwargs.get("json", {})
            captured_bodies.append(body)
            return _fake_ok_response(body)
        return await original_post(self, url, **kwargs)

    with patch.object(httpx.AsyncClient, "post", fake_post):
        yield


@pytest.mark.asyncio
@pytest.mark.usefixtures("_mock_post")
async def test_take_profit_price_nested(captured_bodies: list[dict]):
    """take_profit_price must be serialized as take_profit.limit_price."""
    server = build_server()
    async with Client(transport=server) as mcp:
        await mcp.call_tool(
            "place_stock_order",
            {
                "symbol": "SPY",
                "side": "buy",
                "qty": "10",
                "type": "limit",
                "limit_price": "500.00",
                "time_in_force": "day",
                "order_class": "bracket",
                "take_profit_price": "510.00",
                "stop_loss_price": "495.00",
            },
        )

    assert len(captured_bodies) == 1
    body = captured_bodies[0]

    # Must be nested objects, not flat keys
    assert "take_profit_price" not in body
    assert "stop_loss_price" not in body

    assert body["take_profit"] == {"limit_price": "510.00"}
    assert body["stop_loss"] == {"stop_price": "495.00"}
    assert body["order_class"] == "bracket"


@pytest.mark.asyncio
@pytest.mark.usefixtures("_mock_post")
async def test_legacy_param_names_still_work(captured_bodies: list[dict]):
    """take_profit_limit_price / stop_loss_stop_price aliases still work."""
    server = build_server()
    async with Client(transport=server) as mcp:
        await mcp.call_tool(
            "place_stock_order",
            {
                "symbol": "AAPL",
                "side": "buy",
                "qty": "5",
                "type": "limit",
                "limit_price": "150.00",
                "time_in_force": "day",
                "take_profit_limit_price": "160.00",
                "stop_loss_stop_price": "140.00",
                "stop_loss_limit_price": "139.50",
            },
        )

    assert len(captured_bodies) == 1
    body = captured_bodies[0]

    assert body["take_profit"] == {"limit_price": "160.00"}
    assert body["stop_loss"] == {"stop_price": "140.00", "limit_price": "139.50"}
    assert body["order_class"] == "bracket"


@pytest.mark.asyncio
@pytest.mark.usefixtures("_mock_post")
async def test_preferred_name_takes_priority(captured_bodies: list[dict]):
    """When both take_profit_price and take_profit_limit_price are given,
    take_profit_price wins."""
    server = build_server()
    async with Client(transport=server) as mcp:
        await mcp.call_tool(
            "place_stock_order",
            {
                "symbol": "TSLA",
                "side": "buy",
                "qty": "1",
                "type": "market",
                "time_in_force": "day",
                "take_profit_price": "300.00",
                "take_profit_limit_price": "290.00",
                "stop_loss_price": "250.00",
                "stop_loss_stop_price": "255.00",
            },
        )

    assert len(captured_bodies) == 1
    body = captured_bodies[0]

    # Preferred names win
    assert body["take_profit"] == {"limit_price": "300.00"}
    assert body["stop_loss"] == {"stop_price": "250.00"}


@pytest.mark.asyncio
@pytest.mark.usefixtures("_mock_post")
async def test_auto_bracket_order_class(captured_bodies: list[dict]):
    """order_class is auto-set to 'bracket' when bracket params are provided."""
    server = build_server()
    async with Client(transport=server) as mcp:
        await mcp.call_tool(
            "place_stock_order",
            {
                "symbol": "FIG",
                "side": "sell",
                "qty": "324",
                "type": "stop",
                "stop_price": "22.70",
                "time_in_force": "gtc",
                "take_profit_price": "21.16",
                "stop_loss_price": "23.47",
            },
        )

    assert len(captured_bodies) == 1
    body = captured_bodies[0]
    assert body["order_class"] == "bracket"
    assert body["take_profit"] == {"limit_price": "21.16"}
    assert body["stop_loss"] == {"stop_price": "23.47"}


@pytest.mark.asyncio
@pytest.mark.usefixtures("_mock_post")
async def test_oto_order_with_take_profit_only(captured_bodies: list[dict]):
    """OTO order with only take_profit."""
    server = build_server()
    async with Client(transport=server) as mcp:
        await mcp.call_tool(
            "place_stock_order",
            {
                "symbol": "AAPL",
                "side": "buy",
                "qty": "10",
                "type": "limit",
                "limit_price": "150.00",
                "time_in_force": "day",
                "order_class": "oto",
                "take_profit_price": "160.00",
            },
        )

    assert len(captured_bodies) == 1
    body = captured_bodies[0]
    assert body["order_class"] == "oto"
    assert body["take_profit"] == {"limit_price": "160.00"}
    assert "stop_loss" not in body


@pytest.mark.asyncio
@pytest.mark.usefixtures("_mock_post")
async def test_values_are_strings(captured_bodies: list[dict]):
    """All price values in the nested objects must be strings."""
    server = build_server()
    async with Client(transport=server) as mcp:
        await mcp.call_tool(
            "place_stock_order",
            {
                "symbol": "SPY",
                "side": "buy",
                "qty": "1",
                "type": "market",
                "time_in_force": "day",
                "take_profit_price": "510",
                "stop_loss_price": "490",
                "stop_loss_limit_price": "489",
            },
        )

    body = captured_bodies[0]
    assert isinstance(body["take_profit"]["limit_price"], str)
    assert isinstance(body["stop_loss"]["stop_price"], str)
    assert isinstance(body["stop_loss"]["limit_price"], str)
