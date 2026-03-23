"""
Hand-crafted overrides for historical market data endpoints.

The raw OpenAPI endpoints require absolute ISO-8601 timestamps for time ranges.
These overrides add relative-time convenience parameters (days, hours, minutes)
that auto-compute the start timestamp — LLMs are unreliable at computing ISO
timestamps from expressions like "last 5 days", so this removes that failure mode.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
from fastmcp import FastMCP

_TIMEFRAME_ALIASES: dict[str, str] = {
    "1min": "1Min", "5min": "5Min", "15min": "15Min", "30min": "30Min",
    "1hour": "1Hour", "4hour": "4Hour",
    "1day": "1Day", "1week": "1Week", "1month": "1Month",
}

_TIMEFRAME_PATTERN = re.compile(r"^(\d+)(min|hour|day|week|month)$")


def _relative_start(days: int = 0, hours: int = 0, minutes: int = 0) -> str | None:
    """ISO-8601 timestamp computed as now(UTC) minus the given offset.

    Returns None when offset is zero so the API can apply its own default.
    """
    if days == 0 and hours == 0 and minutes == 0:
        return None
    start = datetime.now(timezone.utc) - timedelta(days=days, hours=hours, minutes=minutes)
    return start.strftime("%Y-%m-%dT%H:%M:%SZ")


def _normalize_timeframe(tf: str) -> str:
    """Map case variants (e.g. '2hour') to API-expected format ('2Hour')."""
    lower = tf.lower().strip()
    alias = _TIMEFRAME_ALIASES.get(lower)
    if alias:
        return alias
    m = _TIMEFRAME_PATTERN.match(lower)
    if m:
        return m.group(1) + m.group(2).capitalize()
    return tf


def _error(message: str, **extra: object) -> dict:
    err: dict = {"message": message}
    err.update(extra)
    return {"error": err}


async def _get(client: httpx.AsyncClient, path: str, params: dict) -> dict:
    """GET request with error handling matching the order override pattern."""
    params = {k: v for k, v in params.items() if v is not None}
    try:
        resp = await client.get(path, params=params)
    except httpx.ReadTimeout:
        return _error(
            "Request timed out. Try narrowing the time range or reducing the limit.",
            timeout=True,
        )
    except httpx.HTTPError as exc:
        return _error(f"HTTP transport error: {exc}")

    if resp.is_error:
        try:
            detail = resp.json()
        except Exception:
            detail = {"raw": resp.text}
        return _error(
            "Market data API error",
            http_status=resp.status_code,
            detail=detail,
        )
    try:
        return resp.json()
    except Exception:
        return {"raw_response": resp.text}


def register_market_data_tools(
    server: FastMCP,
    client: httpx.AsyncClient,
) -> None:
    """Register the six historical market data tools on the given server."""

    # ── Stock Historical Data ──────────────────────────────────────────────

    @server.tool(
        annotations={
            "title": "Get Stock Bars",
            "readOnlyHint": True,
            "openWorldHint": True,
        }
    )
    async def get_stock_bars(
        symbols: str,
        timeframe: str = "1Day",
        start: Optional[str] = None,
        end: Optional[str] = None,
        days: int = 5,
        hours: int = 0,
        minutes: int = 0,
        limit: int = 1000,
        adjustment: str = "raw",
        feed: Optional[str] = None,
        currency: Optional[str] = None,
        sort: str = "asc",
        asof: Optional[str] = None,
    ) -> dict:
        """Retrieve historical price bars (OHLCV) for one or more stocks.

        When start is omitted, it is automatically computed as
        now minus the days/hours/minutes lookback.

        Args:
            symbols: Comma-separated tickers (e.g. "AAPL" or "AAPL,MSFT,GOOG").
            timeframe: Bar aggregation period — "1Min", "5Min", "15Min",
                       "30Min", "1Hour", "1Day", "1Week", or "1Month".
            start: Inclusive start time (RFC 3339). Omit to use relative lookback.
            end: Inclusive end time (RFC 3339). Omit for current time.
            days: Days to look back when start is omitted (default 5).
            hours: Additional hours in the lookback (default 0).
            minutes: Additional minutes in the lookback (default 0).
            limit: Max total data points returned across all symbols,
                   1–10000 (default 1000).
            adjustment: Price adjustment — "raw", "split", "dividend",
                        "spin-off", or "all". Comma-separated combos allowed
                        (e.g. "split,dividend"). Default "raw".
            feed: Data feed — "sip" (all US exchanges, default, paid),
                  "iex" (IEX only, free tier), "otc", or "boats".
            currency: Price currency (ISO 4217, e.g. "USD"). Default USD.
            sort: Timestamp sort order — "asc" (default) or "desc".
            asof: As-of date (YYYY-MM-DD) for point-in-time symbol mapping.
                  Useful for backtesting with historical ticker changes.
        """
        if start is None:
            start = _relative_start(days=days, hours=hours, minutes=minutes)
        return await _get(client, "/v2/stocks/bars", {
            "symbols": symbols,
            "timeframe": _normalize_timeframe(timeframe),
            "start": start,
            "end": end,
            "limit": limit,
            "adjustment": adjustment,
            "feed": feed,
            "currency": currency,
            "sort": sort,
            "asof": asof,
        })

    @server.tool(
        annotations={
            "title": "Get Stock Quotes",
            "readOnlyHint": True,
            "openWorldHint": True,
        }
    )
    async def get_stock_quotes(
        symbols: str,
        start: Optional[str] = None,
        end: Optional[str] = None,
        days: int = 0,
        hours: int = 0,
        minutes: int = 20,
        limit: int = 1000,
        feed: Optional[str] = None,
        currency: Optional[str] = None,
        sort: str = "asc",
        asof: Optional[str] = None,
    ) -> dict:
        """Retrieve historical bid/ask quotes (level 1) for one or more stocks.

        When start is omitted, it is automatically computed as
        now minus the days/hours/minutes lookback.

        Args:
            symbols: Comma-separated tickers (e.g. "AAPL" or "AAPL,MSFT").
            start: Inclusive start time (RFC 3339). Omit to use relative lookback.
            end: Inclusive end time (RFC 3339). Omit for current time.
            days: Days to look back when start is omitted (default 0).
            hours: Additional hours in the lookback (default 0).
            minutes: Additional minutes in the lookback (default 20).
            limit: Max total data points returned across all symbols,
                   1–10000 (default 1000).
            feed: Data feed — "sip" (all US exchanges, default, paid),
                  "iex" (free tier), "otc", or "boats".
                  Paper/free accounts must set feed="iex" to avoid 403 errors.
            currency: Price currency (ISO 4217). Default USD.
            sort: Timestamp sort order — "asc" (default) or "desc".
            asof: As-of date (YYYY-MM-DD) for point-in-time symbol mapping.
        """
        if start is None:
            start = _relative_start(days=days, hours=hours, minutes=minutes)
        return await _get(client, "/v2/stocks/quotes", {
            "symbols": symbols,
            "start": start,
            "end": end,
            "limit": limit,
            "feed": feed,
            "currency": currency,
            "sort": sort,
            "asof": asof,
        })

    @server.tool(
        annotations={
            "title": "Get Stock Trades",
            "readOnlyHint": True,
            "openWorldHint": True,
        }
    )
    async def get_stock_trades(
        symbols: str,
        start: Optional[str] = None,
        end: Optional[str] = None,
        days: int = 0,
        hours: int = 0,
        minutes: int = 20,
        limit: int = 1000,
        feed: Optional[str] = None,
        currency: Optional[str] = None,
        sort: str = "asc",
        asof: Optional[str] = None,
    ) -> dict:
        """Retrieve historical trade data for one or more stocks.

        When start is omitted, it is automatically computed as
        now minus the days/hours/minutes lookback.

        Args:
            symbols: Comma-separated tickers (e.g. "AAPL" or "AAPL,MSFT").
            start: Inclusive start time (RFC 3339). Omit to use relative lookback.
            end: Inclusive end time (RFC 3339). Omit for current time.
            days: Days to look back when start is omitted (default 0).
            hours: Additional hours in the lookback (default 0).
            minutes: Additional minutes in the lookback (default 20).
            limit: Max total data points returned across all symbols,
                   1–10000 (default 1000).
            feed: Data feed — "sip" (all US exchanges, default, paid),
                  "iex" (free tier), "otc", or "boats".
                  Paper/free accounts must set feed="iex" to avoid 403 errors.
            currency: Price currency (ISO 4217). Default USD.
            sort: Timestamp sort order — "asc" (default) or "desc".
            asof: As-of date (YYYY-MM-DD) for point-in-time symbol mapping.
        """
        if start is None:
            start = _relative_start(days=days, hours=hours, minutes=minutes)
        return await _get(client, "/v2/stocks/trades", {
            "symbols": symbols,
            "start": start,
            "end": end,
            "limit": limit,
            "feed": feed,
            "currency": currency,
            "sort": sort,
            "asof": asof,
        })

    # ── Crypto Historical Data ─────────────────────────────────────────────

    @server.tool(
        annotations={
            "title": "Get Crypto Bars",
            "readOnlyHint": True,
            "openWorldHint": True,
        }
    )
    async def get_crypto_bars(
        symbols: str,
        timeframe: str = "1Hour",
        start: Optional[str] = None,
        end: Optional[str] = None,
        days: int = 1,
        hours: int = 0,
        minutes: int = 0,
        limit: int = 1000,
        sort: str = "asc",
    ) -> dict:
        """Retrieve historical price bars (OHLCV) for one or more cryptocurrencies.

        When start is omitted, it is automatically computed as
        now minus the days/hours/minutes lookback.

        Args:
            symbols: Comma-separated crypto pairs (e.g. "BTC/USD" or
                     "BTC/USD,ETH/USD").
            timeframe: Bar aggregation period — "1Min", "5Min", "15Min",
                       "30Min", "1Hour", "1Day", "1Week", or "1Month".
            start: Inclusive start time (RFC 3339). Omit to use relative lookback.
            end: Inclusive end time (RFC 3339). Omit for current time.
            days: Days to look back when start is omitted (default 1).
            hours: Additional hours in the lookback (default 0).
            minutes: Additional minutes in the lookback (default 0).
            limit: Max total data points returned across all symbols,
                   1–10000 (default 1000).
            sort: Timestamp sort order — "asc" (default) or "desc".
        """
        if start is None:
            start = _relative_start(days=days, hours=hours, minutes=minutes)
        return await _get(client, "/v1beta3/crypto/us/bars", {
            "symbols": symbols,
            "timeframe": _normalize_timeframe(timeframe),
            "start": start,
            "end": end,
            "limit": limit,
            "sort": sort,
        })

    @server.tool(
        annotations={
            "title": "Get Crypto Quotes",
            "readOnlyHint": True,
            "openWorldHint": True,
        }
    )
    async def get_crypto_quotes(
        symbols: str,
        start: Optional[str] = None,
        end: Optional[str] = None,
        days: int = 0,
        hours: int = 0,
        minutes: int = 15,
        limit: int = 1000,
        sort: str = "asc",
    ) -> dict:
        """Retrieve historical bid/ask quotes for one or more cryptocurrencies.

        When start is omitted, it is automatically computed as
        now minus the days/hours/minutes lookback.

        Args:
            symbols: Comma-separated crypto pairs (e.g. "BTC/USD" or
                     "BTC/USD,ETH/USD").
            start: Inclusive start time (RFC 3339). Omit to use relative lookback.
            end: Inclusive end time (RFC 3339). Omit for current time.
            days: Days to look back when start is omitted (default 0).
            hours: Additional hours in the lookback (default 0).
            minutes: Additional minutes in the lookback (default 15).
            limit: Max total data points returned across all symbols,
                   1–10000 (default 1000).
            sort: Timestamp sort order — "asc" (default) or "desc".
        """
        if start is None:
            start = _relative_start(days=days, hours=hours, minutes=minutes)
        return await _get(client, "/v1beta3/crypto/us/quotes", {
            "symbols": symbols,
            "start": start,
            "end": end,
            "limit": limit,
            "sort": sort,
        })

    @server.tool(
        annotations={
            "title": "Get Crypto Trades",
            "readOnlyHint": True,
            "openWorldHint": True,
        }
    )
    async def get_crypto_trades(
        symbols: str,
        start: Optional[str] = None,
        end: Optional[str] = None,
        days: int = 0,
        hours: int = 0,
        minutes: int = 15,
        limit: int = 1000,
        sort: str = "asc",
    ) -> dict:
        """Retrieve historical trade data for one or more cryptocurrencies.

        When start is omitted, it is automatically computed as
        now minus the days/hours/minutes lookback.

        Args:
            symbols: Comma-separated crypto pairs (e.g. "BTC/USD" or
                     "BTC/USD,ETH/USD").
            start: Inclusive start time (RFC 3339). Omit to use relative lookback.
            end: Inclusive end time (RFC 3339). Omit for current time.
            days: Days to look back when start is omitted (default 0).
            hours: Additional hours in the lookback (default 0).
            minutes: Additional minutes in the lookback (default 15).
            limit: Max total data points returned across all symbols,
                   1–10000 (default 1000).
            sort: Timestamp sort order — "asc" (default) or "desc".
        """
        if start is None:
            start = _relative_start(days=days, hours=hours, minutes=minutes)
        return await _get(client, "/v1beta3/crypto/us/trades", {
            "symbols": symbols,
            "start": start,
            "end": end,
            "limit": limit,
            "sort": sort,
        })
