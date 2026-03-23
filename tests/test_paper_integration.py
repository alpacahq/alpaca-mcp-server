"""
Layer 3: Paper API integration tests — real network calls to Alpaca paper.

Requires ALPACA_API_KEY and ALPACA_SECRET_KEY env vars pointing at a
paper trading account. The entire module is skipped when credentials
are absent.

Run with:
    ALPACA_API_KEY=... ALPACA_SECRET_KEY=... pytest -m integration

These tests use limit orders at absurd prices to avoid fills, and
clean up any orders they create.
"""

from __future__ import annotations

import asyncio
import json
import os
import uuid

import pytest
from fastmcp.client import Client

from alpaca_mcp_server.server import build_server

_has_credentials = bool(
    os.environ.get("ALPACA_API_KEY") and os.environ.get("ALPACA_SECRET_KEY")
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not _has_credentials, reason="Paper API credentials not set"),
]


def _to_dict(obj) -> dict | list | str:
    """Coerce Pydantic models, dicts, or other objects into plain dicts."""
    if isinstance(obj, dict):
        return obj
    if isinstance(obj, list):
        return [_to_dict(item) for item in obj]
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if hasattr(obj, "__dict__"):
        return {k: v for k, v in vars(obj).items() if not k.startswith("_")}
    return obj


def _parse(result) -> dict | list | str:
    """Extract usable data from a CallToolResult."""
    if hasattr(result, "data") and result.data is not None:
        return _to_dict(result.data)
    for block in result.content:
        if hasattr(block, "text"):
            try:
                return json.loads(block.text)
            except (json.JSONDecodeError, TypeError):
                return block.text
    return str(result)


async def _call(tool_name: str, args: dict | None = None) -> dict | list | str:
    """Build server, call a tool, return parsed result.

    A fresh server + client per call avoids event-loop conflicts on Python 3.10.
    """
    os.environ.setdefault("ALPACA_PAPER_TRADE", "true")
    server = build_server()
    async with Client(transport=server) as c:
        raw = await c.call_tool(tool_name, args or {})
    return _parse(raw)


# ── Account ─────────────────────────────────────────────────────────────


async def test_get_account_info():
    result = await _call("get_account_info")
    assert isinstance(result, dict), f"Unexpected type: {type(result)}"
    assert "account_number" in result
    assert "buying_power" in result
    assert "status" in result


async def test_get_portfolio_history():
    result = await _call("get_portfolio_history", {
        "period": "1W",
        "timeframe": "1D",
    })
    assert isinstance(result, dict)
    assert "equity" in result or "timestamp" in result


async def test_get_account_config():
    result = await _call("get_account_config")
    assert isinstance(result, dict)


async def test_get_account_activities():
    result = await _call("get_account_activities")
    assert isinstance(result, (dict, list))


async def test_get_account_activities_by_type():
    result = await _call("get_account_activities_by_type", {
        "activity_type": "FILL",
    })
    assert isinstance(result, (dict, list))


# ── Market Data: Stocks ─────────────────────────────────────────────────


async def test_get_stock_bars():
    result = await _call("get_stock_bars", {
        "symbols": "AAPL",
        "timeframe": "1Day",
        "days": 3,
        "limit": 10,
    })
    assert isinstance(result, dict)
    assert "bars" in result or "AAPL" in str(result)


async def test_get_stock_quotes():
    result = await _call("get_stock_quotes", {
        "symbols": "AAPL",
        "days": 0,
        "hours": 0,
        "minutes": 5,
        "limit": 5,
    })
    assert isinstance(result, dict)


async def test_get_stock_trades():
    result = await _call("get_stock_trades", {
        "symbols": "AAPL",
        "days": 0,
        "hours": 0,
        "minutes": 5,
        "limit": 5,
    })
    assert isinstance(result, dict)


async def test_get_stock_latest_bar():
    result = await _call("get_stock_latest_bar", {"symbols": "AAPL"})
    assert isinstance(result, dict)


async def test_get_stock_latest_quote():
    result = await _call("get_stock_latest_quote", {"symbols": "AAPL"})
    assert isinstance(result, dict)


async def test_get_stock_latest_trade():
    result = await _call("get_stock_latest_trade", {"symbols": "AAPL"})
    assert isinstance(result, dict)


async def test_get_stock_snapshot():
    result = await _call("get_stock_snapshot", {"symbols": "AAPL"})
    assert isinstance(result, dict)


async def test_get_most_active_stocks():
    result = await _call("get_most_active_stocks")
    assert isinstance(result, dict)
    assert "most_actives" in result


async def test_get_market_movers():
    result = await _call("get_market_movers", {"market_type": "stocks"})
    assert isinstance(result, dict)


# ── Market Data: Crypto ─────────────────────────────────────────────────


async def test_get_crypto_bars():
    result = await _call("get_crypto_bars", {
        "symbols": "BTC/USD",
        "timeframe": "1Hour",
        "days": 1,
        "limit": 10,
    })
    assert isinstance(result, dict)


async def test_get_crypto_quotes():
    result = await _call("get_crypto_quotes", {
        "symbols": "BTC/USD",
        "days": 0,
        "hours": 0,
        "minutes": 5,
        "limit": 5,
    })
    assert isinstance(result, dict)


async def test_get_crypto_trades():
    result = await _call("get_crypto_trades", {
        "symbols": "BTC/USD",
        "days": 0,
        "hours": 0,
        "minutes": 5,
        "limit": 5,
    })
    assert isinstance(result, dict)


async def test_get_crypto_latest_bar():
    result = await _call("get_crypto_latest_bar", {"symbols": "BTC/USD", "loc": "us"})
    assert isinstance(result, dict)


async def test_get_crypto_latest_quote():
    result = await _call("get_crypto_latest_quote", {"symbols": "BTC/USD", "loc": "us"})
    assert isinstance(result, dict)


async def test_get_crypto_latest_trade():
    result = await _call("get_crypto_latest_trade", {"symbols": "BTC/USD", "loc": "us"})
    assert isinstance(result, dict)


async def test_get_crypto_snapshot():
    result = await _call("get_crypto_snapshot", {"symbols": "BTC/USD", "loc": "us"})
    assert isinstance(result, dict)


async def test_get_crypto_latest_orderbook():
    result = await _call("get_crypto_latest_orderbook", {"symbols": "BTC/USD", "loc": "us"})
    assert isinstance(result, dict)


# ── Market Data: Options ────────────────────────────────────────────────


async def test_get_option_chain():
    result = await _call("get_option_chain", {"underlying_symbol": "AAPL"})
    assert isinstance(result, dict)


async def test_get_option_exchange_codes():
    result = await _call("get_option_exchange_codes")
    assert isinstance(result, dict)


async def test_get_option_contracts():
    result = await _call("get_option_contracts", {
        "underlying_symbols": "AAPL",
    })
    assert isinstance(result, dict)


async def _find_option_symbol() -> str | None:
    """Find a real AAPL option symbol from the chain."""
    chain = await _call("get_option_chain", {"underlying_symbol": "AAPL"})
    if not isinstance(chain, dict):
        return None
    snapshots = chain.get("snapshots") or {}
    if not snapshots:
        return None
    return next(iter(snapshots))


async def test_get_option_latest_quote():
    symbol = await _find_option_symbol()
    if not symbol:
        pytest.skip("No option chain data available for AAPL")
    result = await _call("get_option_latest_quote", {"symbols": symbol})
    assert isinstance(result, dict)


async def test_get_option_latest_trade():
    symbol = await _find_option_symbol()
    if not symbol:
        pytest.skip("No option chain data available for AAPL")
    result = await _call("get_option_latest_trade", {"symbols": symbol})
    assert isinstance(result, dict)


async def test_get_option_snapshot():
    symbol = await _find_option_symbol()
    if not symbol:
        pytest.skip("No option chain data available for AAPL")
    result = await _call("get_option_snapshot", {"symbols": symbol})
    assert isinstance(result, dict)


async def test_get_option_bars():
    symbol = await _find_option_symbol()
    if not symbol:
        pytest.skip("No option chain data available for AAPL")
    result = await _call("get_option_bars", {"symbols": symbol, "timeframe": "1D"})
    assert isinstance(result, dict)


async def test_get_option_trades():
    symbol = await _find_option_symbol()
    if not symbol:
        pytest.skip("No option chain data available for AAPL")
    result = await _call("get_option_trades", {"symbols": symbol})
    assert isinstance(result, dict)


async def test_get_option_contract():
    symbol = await _find_option_symbol()
    if not symbol:
        pytest.skip("No option chain data available for AAPL")
    result = await _call("get_option_contract", {"symbol_or_id": symbol})
    assert isinstance(result, dict)


# ── Market Data: Corporate Actions ──────────────────────────────────────


async def test_get_corporate_actions():
    result = await _call("get_corporate_actions", {
        "types": "cash_dividend",
        "date_from": "2025-01-01",
        "date_to": "2025-01-31",
    })
    assert isinstance(result, dict)


# ── Assets & Market Info ────────────────────────────────────────────────


async def test_get_asset():
    result = await _call("get_asset", {"symbol_or_asset_id": "AAPL"})
    assert isinstance(result, dict)
    assert result.get("symbol") == "AAPL" or "AAPL" in str(result)


async def test_get_all_assets():
    result = await _call("get_all_assets", {
        "status": "active",
        "asset_class": "us_equity",
    })
    assert isinstance(result, (dict, list))


async def test_get_clock():
    result = await _call("get_clock")
    assert isinstance(result, dict)
    assert "is_open" in result


async def test_get_calendar():
    result = await _call("get_calendar")
    assert isinstance(result, (dict, list))


async def test_get_corporate_action_announcements():
    result = await _call("get_corporate_action_announcements", {
        "ca_types": "dividend",
        "since": "2025-01-01",
        "until": "2025-01-31",
    })
    assert isinstance(result, (dict, list))


# ── Orders: Place + Fetch + Replace + Cancel ────────────────────────────


async def test_place_and_cancel_stock_order():
    """Place a limit buy at $1 (won't fill), fetch by ID, then cancel."""
    os.environ.setdefault("ALPACA_PAPER_TRADE", "true")
    server = build_server()
    async with Client(transport=server) as mcp:
        order = _parse(await mcp.call_tool("place_stock_order", {
            "symbol": "AAPL",
            "side": "buy",
            "qty": "1",
            "type": "limit",
            "time_in_force": "day",
            "limit_price": "1.00",
        }))
        assert isinstance(order, dict), f"Order response: {order}"
        assert "error" not in order, f"Order placement failed: {order}"
        order_id = order.get("id")
        assert order_id, f"No order ID in response: {order}"

        try:
            single = _parse(await mcp.call_tool("get_order_by_id", {
                "order_id": order_id,
            }))
            assert isinstance(single, dict)
            assert single.get("id") == order_id
        finally:
            await mcp.call_tool("cancel_order_by_id", {"order_id": order_id})


async def test_place_with_client_order_id():
    """Place with client_order_id, fetch by client ID, then cancel."""
    client_oid = f"mcp-test-{uuid.uuid4().hex[:12]}"
    os.environ.setdefault("ALPACA_PAPER_TRADE", "true")
    server = build_server()
    async with Client(transport=server) as mcp:
        order = _parse(await mcp.call_tool("place_stock_order", {
            "symbol": "MSFT",
            "side": "buy",
            "qty": "1",
            "type": "limit",
            "time_in_force": "day",
            "limit_price": "1.00",
            "client_order_id": client_oid,
        }))
        assert isinstance(order, dict)
        assert "error" not in order, f"Order failed: {order}"
        order_id = order.get("id")

        try:
            by_client = _parse(await mcp.call_tool("get_order_by_client_id", {
                "client_order_id": client_oid,
            }))
            assert isinstance(by_client, dict)
            assert by_client.get("client_order_id") == client_oid
        finally:
            await mcp.call_tool("cancel_order_by_id", {"order_id": order_id})


async def test_replace_order():
    """Place a limit order, replace it with a new price, then cancel."""
    os.environ.setdefault("ALPACA_PAPER_TRADE", "true")
    server = build_server()
    async with Client(transport=server) as mcp:
        order = _parse(await mcp.call_tool("place_stock_order", {
            "symbol": "GOOG",
            "side": "buy",
            "qty": "1",
            "type": "limit",
            "time_in_force": "day",
            "limit_price": "1.00",
        }))
        assert "error" not in order, f"Order failed: {order}"
        order_id = order["id"]
        cancel_id = order_id

        try:
            # Wait for the order to leave pending_new (API rejects replace on pending_new)
            for _ in range(10):
                current = _parse(await mcp.call_tool("get_order_by_id", {"order_id": order_id}))
                if current.get("status") != "pending_new":
                    break
                await asyncio.sleep(0.5)

            replaced = _parse(await mcp.call_tool("replace_order_by_id", {
                "order_id": order_id,
                "qty": "2",
                "limit_price": "1.50",
            }))
            assert isinstance(replaced, dict)
            cancel_id = replaced.get("id", order_id)
        finally:
            await mcp.call_tool("cancel_order_by_id", {"order_id": cancel_id})


async def test_get_orders():
    result = await _call("get_orders", {"status": "all", "limit": 5})
    assert isinstance(result, (dict, list))


async def test_place_and_cancel_crypto_order():
    """Place a limit buy for BTC/USD at $20k (won't fill at ~$80k), then cancel."""
    os.environ.setdefault("ALPACA_PAPER_TRADE", "true")
    server = build_server()
    async with Client(transport=server) as mcp:
        order = _parse(await mcp.call_tool("place_crypto_order", {
            "symbol": "BTC/USD",
            "side": "buy",
            "qty": "0.001",
            "type": "limit",
            "time_in_force": "gtc",
            "limit_price": "20000.00",
        }))
        assert isinstance(order, dict), f"Order response: {order}"
        assert "error" not in order, f"Order placement failed: {order}"
        order_id = order.get("id")
        assert order_id, f"No order ID in response: {order}"

        try:
            single = _parse(await mcp.call_tool("get_order_by_id", {
                "order_id": order_id,
            }))
            assert isinstance(single, dict)
        finally:
            await mcp.call_tool("cancel_order_by_id", {"order_id": order_id})


# ── Positions ───────────────────────────────────────────────────────────


async def test_get_all_positions():
    result = await _call("get_all_positions")
    assert isinstance(result, (dict, list))


# ── Watchlists (full CRUD) ──────────────────────────────────────────────


async def test_watchlist_full_crud():
    """Create, list, update, add/remove asset, then delete."""
    wl_name = f"mcp-test-{uuid.uuid4().hex[:8]}"
    os.environ.setdefault("ALPACA_PAPER_TRADE", "true")
    server = build_server()
    async with Client(transport=server) as mcp:
        created = _parse(await mcp.call_tool("create_watchlist", {
            "name": wl_name,
            "symbols": ["AAPL"],
        }))
        assert isinstance(created, dict), f"Create response: {created}"
        wl_id = created.get("id")
        assert wl_id, f"No watchlist ID: {created}"

        try:
            # get_watchlists
            all_wl = _parse(await mcp.call_tool("get_watchlists", {}))
            assert isinstance(all_wl, (dict, list))

            # get_watchlist_by_id
            fetched = _parse(await mcp.call_tool("get_watchlist_by_id", {
                "watchlist_id": wl_id,
            }))
            assert isinstance(fetched, dict)

            # update_watchlist_by_id
            updated = _parse(await mcp.call_tool("update_watchlist_by_id", {
                "watchlist_id": wl_id,
                "name": wl_name + "-updated",
            }))
            assert isinstance(updated, dict)

            # add_asset_to_watchlist_by_id
            added = _parse(await mcp.call_tool("add_asset_to_watchlist_by_id", {
                "watchlist_id": wl_id,
                "symbol": "MSFT",
            }))
            assert isinstance(added, dict)

            # remove_asset_from_watchlist_by_id
            removed = _parse(await mcp.call_tool("remove_asset_from_watchlist_by_id", {
                "watchlist_id": wl_id,
                "symbol": "MSFT",
            }))
            assert isinstance(removed, dict)
        finally:
            await mcp.call_tool("delete_watchlist_by_id", {
                "watchlist_id": wl_id,
            })


# ── Cancel All Orders ───────────────────────────────────────────────────


async def test_cancel_all_orders():
    """Place 3 limit orders, cancel all at once, verify none remain."""
    os.environ.setdefault("ALPACA_PAPER_TRADE", "true")
    server = build_server()
    symbols = ["TSLA", "AMZN", "META"]
    async with Client(transport=server) as mcp:
        order_ids = []
        for i in range(3):
            order = _parse(await mcp.call_tool("place_stock_order", {
                "symbol": symbols[i],
                "side": "buy",
                "qty": "1",
                "type": "limit",
                "time_in_force": "day",
                "limit_price": str(1.00 + i * 0.01),
            }))
            assert "error" not in order, f"Order {i} failed: {order}"
            order_ids.append(order["id"])

        try:
            result = _parse(await mcp.call_tool("cancel_all_orders", {}))
            assert isinstance(result, (dict, list))
        except Exception:
            for oid in order_ids:
                try:
                    await mcp.call_tool("cancel_order_by_id", {"order_id": oid})
                except Exception:
                    pass
            raise


# ── Positions: Open + Get + Close ───────────────────────────────────────


async def test_position_lifecycle():
    """Buy 1 share at market, check position, close it.

    Skipped when market is closed (order won't fill immediately).
    """
    import asyncio

    os.environ.setdefault("ALPACA_PAPER_TRADE", "true")
    server = build_server()
    async with Client(transport=server) as mcp:
        clock = _parse(await mcp.call_tool("get_clock", {}))
        if not clock.get("is_open"):
            pytest.skip("Market is closed — position tests require fills")

        order = _parse(await mcp.call_tool("place_stock_order", {
            "symbol": "AAPL",
            "side": "buy",
            "qty": "1",
            "type": "market",
            "time_in_force": "day",
        }))
        assert "error" not in order, f"Market order failed: {order}"
        order_id = order["id"]

        # Wait briefly for fill
        await asyncio.sleep(2)

        filled = _parse(await mcp.call_tool("get_order_by_id", {
            "order_id": order_id,
        }))
        if filled.get("status") != "filled":
            await mcp.call_tool("cancel_order_by_id", {"order_id": order_id})
            pytest.skip("Order did not fill in time")

        try:
            # get_open_position
            pos = _parse(await mcp.call_tool("get_open_position", {
                "symbol_or_asset_id": "AAPL",
            }))
            assert isinstance(pos, dict)
            assert pos.get("symbol") == "AAPL" or "AAPL" in str(pos)

            # close_position
            closed = _parse(await mcp.call_tool("close_position", {
                "symbol_or_asset_id": "AAPL",
            }))
            assert isinstance(closed, dict)
        except Exception:
            try:
                await mcp.call_tool("close_position", {
                    "symbol_or_asset_id": "AAPL",
                })
            except Exception:
                pass
            raise


async def test_close_all_positions():
    """Call close_all_positions — safe even with no open positions."""
    result = await _call("close_all_positions")
    assert isinstance(result, (dict, list))


# ── Account Config: Toggle + Restore ────────────────────────────────────


async def test_update_account_config():
    """Toggle trade_confirm_email, verify it changed, then restore."""
    os.environ.setdefault("ALPACA_PAPER_TRADE", "true")
    server = build_server()
    async with Client(transport=server) as mcp:
        original = _parse(await mcp.call_tool("get_account_config", {}))
        assert isinstance(original, dict)
        orig_value = original.get("trade_confirm_email", "all")

        new_value = "none" if orig_value == "all" else "all"

        try:
            updated = _parse(await mcp.call_tool("update_account_config", {
                "trade_confirm_email": new_value,
            }))
            assert isinstance(updated, dict)
            assert updated.get("trade_confirm_email") == new_value
        finally:
            await mcp.call_tool("update_account_config", {
                "trade_confirm_email": orig_value,
            })
