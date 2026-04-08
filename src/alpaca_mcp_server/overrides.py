"""
Hand-crafted tool overrides for endpoints too complex for auto-generation.

POST /v2/orders has 17+ parameters covering stocks, crypto, options, bracket
orders, trailing stops, and multi-leg orders. We split it into three focused
tools with curated parameters per asset class.
"""

from __future__ import annotations

from typing import Optional

import httpx
from fastmcp import FastMCP


def _error(message: str, **extra: object) -> dict:
    """Build a standardised error dict returned to the LLM."""
    err: dict = {"message": message}
    err.update(extra)
    return {"error": err}


async def _post_order(client: httpx.AsyncClient, body: dict) -> dict:
    """Submit an order and return the response, surfacing API error details.

    Catches read-timeouts explicitly because the request may have reached
    Alpaca even though we never received the response.  A generic retry
    would risk placing a duplicate order.
    """
    try:
        resp = await client.post("/v2/orders", json=body)
    except httpx.ReadTimeout:
        return _error(
            "Request was sent but timed out waiting for a response. "
            "The order MAY have been placed. Check open orders before "
            "retrying. If you set client_order_id, you can safely retry "
            "with the same value — the API will reject the duplicate.",
            timeout=True,
        )

    if resp.is_error:
        try:
            detail = resp.json()
        except Exception:
            detail = {"raw": resp.text}
        return _error(
            "API rejected the order",
            http_status=resp.status_code,
            detail=detail,
        )
    return resp.json()


def register_order_tools(
    server: FastMCP,
    client: httpx.AsyncClient,
) -> None:
    """Register the three order placement tools on the given server."""

    @server.tool(
        annotations={
            "title": "Place Stock Order",
            "readOnlyHint": False,
            "destructiveHint": True,
            "idempotentHint": False,
            "openWorldHint": True,
        }
    )
    async def place_stock_order(
        symbol: str,
        side: str,
        qty: Optional[str] = None,
        notional: Optional[str] = None,
        type: str = "market",
        time_in_force: str = "day",
        limit_price: Optional[str] = None,
        stop_price: Optional[str] = None,
        trail_price: Optional[str] = None,
        trail_percent: Optional[str] = None,
        extended_hours: bool = False,
        client_order_id: Optional[str] = None,
        order_class: Optional[str] = None,
        take_profit_price: Optional[str] = None,
        stop_loss_price: Optional[str] = None,
        take_profit_limit_price: Optional[str] = None,
        stop_loss_stop_price: Optional[str] = None,
        stop_loss_limit_price: Optional[str] = None,
    ) -> dict:
        """Place a stock or ETF order.

        IMPORTANT: To close or reduce an existing position (long or short),
        use the close_position tool instead. This tool does not carry
        position intent, so a "buy" on a symbol you are short will ADD
        a new long on top of the short rather than covering it — doubling
        your exposure instead of flattening it.

        Args:
            symbol: Stock ticker (e.g., "AAPL", "SPY").
            side: "buy" or "sell".
            qty: Number of shares. Mutually exclusive with notional.
            notional: Dollar amount to trade. Mutually exclusive with qty.
                      Only valid for market orders with time_in_force="day".
            type: Order type — "market", "limit", "stop", "stop_limit",
                  "trailing_stop".
            time_in_force: "day", "gtc", "opg", "cls", "ioc", or "fok".
            limit_price: Required for limit and stop_limit orders.
            stop_price: Required for stop and stop_limit orders.
            trail_price: Dollar trail amount for trailing_stop orders.
            trail_percent: Percent trail for trailing_stop orders.
            extended_hours: Allow execution in extended hours. Only works
                            with type="limit" and time_in_force="day".
            client_order_id: Unique idempotency key. If the request times out,
                             you can safely retry with the same value — the API
                             will reject duplicates. Recommended for every order.
            order_class: "simple", "bracket", "oco", or "oto". Automatically
                         set to "bracket" when take_profit or stop_loss params
                         are provided.
            take_profit_price: Limit price for the take-profit child leg.
                               Used for bracket, oto, and oco orders. The API
                               nests this as take_profit.limit_price.
            stop_loss_price: Stop trigger price for the stop-loss child leg.
                             Used for bracket, oto, and oco orders. The API
                             nests this as stop_loss.stop_price.
            take_profit_limit_price: Alias for take_profit_price. If both are
                                     provided, take_profit_price takes priority.
            stop_loss_stop_price: Alias for stop_loss_price. If both are
                                  provided, stop_loss_price takes priority.
            stop_loss_limit_price: Optional limit price for the stop-loss leg.
                                   When set alongside stop_loss_price, the child
                                   order becomes a stop_limit instead of a stop.
        """
        # Resolve aliases: take_profit_price / stop_loss_price are the
        # preferred names; fall back to the longer aliases for backwards
        # compatibility.
        _tp_limit = take_profit_price or take_profit_limit_price
        _sl_stop = stop_loss_price or stop_loss_stop_price

        if stop_loss_limit_price is not None and _sl_stop is None:
            return _error(
                "stop_loss_limit_price requires stop_loss_price "
                "(or stop_loss_stop_price)"
            )

        has_bracket_params = (
            _tp_limit is not None
            or _sl_stop is not None
        )
        if has_bracket_params and order_class is None:
            order_class = "bracket"

        body: dict = {
            "symbol": symbol,
            "side": side,
            "type": type,
            "time_in_force": time_in_force,
        }
        if qty is not None:
            body["qty"] = qty
        if notional is not None:
            body["notional"] = notional
        if limit_price is not None:
            body["limit_price"] = limit_price
        if stop_price is not None:
            body["stop_price"] = stop_price
        if trail_price is not None:
            body["trail_price"] = trail_price
        if trail_percent is not None:
            body["trail_percent"] = trail_percent
        if extended_hours:
            body["extended_hours"] = True
        if client_order_id is not None:
            body["client_order_id"] = client_order_id
        if order_class is not None:
            body["order_class"] = order_class
        if _tp_limit is not None:
            body["take_profit"] = {"limit_price": str(_tp_limit)}
        if _sl_stop is not None:
            sl: dict = {"stop_price": str(_sl_stop)}
            if stop_loss_limit_price is not None:
                sl["limit_price"] = str(stop_loss_limit_price)
            body["stop_loss"] = sl

        return await _post_order(client, body)

    @server.tool(
        annotations={
            "title": "Place Crypto Order",
            "readOnlyHint": False,
            "destructiveHint": True,
            "idempotentHint": False,
            "openWorldHint": True,
        }
    )
    async def place_crypto_order(
        symbol: str,
        side: str,
        qty: Optional[str] = None,
        notional: Optional[str] = None,
        type: str = "market",
        time_in_force: str = "gtc",
        limit_price: Optional[str] = None,
        stop_price: Optional[str] = None,
        client_order_id: Optional[str] = None,
    ) -> dict:
        """Place a cryptocurrency order.

        Args:
            symbol: Crypto pair (e.g., "BTC/USD", "ETH/USD").
            side: "buy" or "sell".
            qty: Number of coins/tokens. Mutually exclusive with notional.
            notional: Dollar amount to trade. Mutually exclusive with qty.
                      Only valid for market orders.
            type: "market", "limit", or "stop_limit".
            time_in_force: "gtc" (default) or "ioc". Crypto does not
                           support "day" or "fok".
            limit_price: Required for limit and stop_limit orders.
            stop_price: Required for stop_limit orders.
            client_order_id: Unique idempotency key. If the request times out,
                             you can safely retry with the same value — the API
                             will reject duplicates. Recommended for every order.
        """
        body: dict = {
            "symbol": symbol,
            "side": side,
            "type": type,
            "time_in_force": time_in_force,
        }
        if qty is not None:
            body["qty"] = qty
        if notional is not None:
            body["notional"] = notional
        if limit_price is not None:
            body["limit_price"] = limit_price
        if stop_price is not None:
            body["stop_price"] = stop_price
        if client_order_id is not None:
            body["client_order_id"] = client_order_id

        return await _post_order(client, body)

    @server.tool(
        annotations={
            "title": "Place Option Order",
            "readOnlyHint": False,
            "destructiveHint": True,
            "idempotentHint": False,
            "openWorldHint": True,
        }
    )
    async def place_option_order(
        qty: str,
        type: str = "market",
        time_in_force: str = "day",
        symbol: Optional[str] = None,
        side: Optional[str] = None,
        position_intent: Optional[str] = None,
        limit_price: Optional[str] = None,
        client_order_id: Optional[str] = None,
        order_class: Optional[str] = None,
        legs: Optional[list[dict]] = None,
    ) -> dict:
        """Place an options order (single-leg or multi-leg).

        For single-leg orders, provide symbol, side, and qty.
        For multi-leg orders, provide qty, legs, and optionally
        order_class="mleg" (auto-inferred). Symbol and side on the
        parent are not needed for multi-leg.

        Args:
            qty: Number of contracts. Required for both single-leg and
                 multi-leg orders. For multi-leg, this is the strategy
                 multiplier — each leg's ratio_qty is scaled by this
                 value (e.g., qty="10" with ratio_qty="2" = 20
                 contracts for that leg).
            type: "market" or "limit".
            time_in_force: "day" only. Options do not support other
                           values.
            symbol: OCC option symbol (e.g., "AAPL250321C00150000").
                    Required for single-leg.
            side: "buy" or "sell". Required for single-leg.
            position_intent: "buy_to_open", "buy_to_close", "sell_to_open",
                             or "sell_to_close". Clarifies whether the trade
                             opens or closes a position. Optional but
                             recommended.
            limit_price: Required for limit orders. For multi-leg, this is
                         the net debit/credit (positive = debit/cost,
                         negative = credit/proceeds).
            client_order_id: Unique idempotency key. If the request times out,
                             you can safely retry with the same value — the API
                             will reject duplicates. Recommended for every order.
            order_class: Set to "mleg" for multi-leg orders. Automatically
                         inferred when legs are provided.
            legs: List of leg dicts for multi-leg orders (max 4). Each leg
                  requires "symbol" and "ratio_qty" (string). Optional
                  per-leg fields: "side" ("buy" or "sell") and
                  "position_intent".
        """
        is_multi_leg = legs is not None or order_class == "mleg"

        if is_multi_leg and legs is None:
            return _error(
                "Multi-leg orders require the legs parameter"
            )

        if not is_multi_leg and (symbol is None or side is None):
            return _error(
                "Single-leg orders require symbol and side"
            )

        if legs is not None and order_class is None:
            order_class = "mleg"

        body: dict = {
            "qty": qty,
            "type": type,
            "time_in_force": time_in_force,
        }
        if symbol is not None:
            body["symbol"] = symbol
        if side is not None:
            body["side"] = side
        if position_intent is not None:
            body["position_intent"] = position_intent
        if limit_price is not None:
            body["limit_price"] = limit_price
        if client_order_id is not None:
            body["client_order_id"] = client_order_id
        if order_class is not None:
            body["order_class"] = order_class
        if legs is not None:
            body["legs"] = legs

        return await _post_order(client, body)
