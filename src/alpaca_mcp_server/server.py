"""
Alpaca's MCP Server - Standalone Implementation

This is a standalone MCP server that provides comprehensive Alpaca's Trading API integration
for stocks, options, crypto, portfolio management, and real-time market data.

Supports 43+ tools including:
- Account management and portfolio tracking
- Order placement and management (stocks, crypto, options)
- Position tracking and closing
- Market data retrieval (quotes, bars, trades, snapshots)
- Crypto trading strategies and analytics
- Options trading strategies and analytics
- Watchlist management
- Market calendar and corporate actions
"""
import json
import os
import re
import sys
import time
import uuid
import argparse
from datetime import datetime, timedelta, date, timezone
from typing import Dict, Any, List, Optional, Union
from pathlib import Path

from dotenv import load_dotenv

from alpaca.common.enums import SupportedCurrencies
from alpaca.common.exceptions import APIError
from alpaca.data.enums import DataFeed, OptionsFeed, CorporateActionsType, CryptoFeed
from alpaca.data.historical.option import OptionHistoricalDataClient
from alpaca.data.historical.stock import StockHistoricalDataClient
from alpaca.data.historical.corporate_actions import CorporateActionsClient
from alpaca.data.historical.crypto import CryptoHistoricalDataClient
from alpaca.data.live.stock import StockDataStream
from alpaca.data.requests import (
    OptionLatestQuoteRequest,
    OptionSnapshotRequest,
    Sort,
    StockBarsRequest,
    StockLatestBarRequest,
    StockLatestQuoteRequest,
    StockLatestTradeRequest,
    StockQuotesRequest,
    StockSnapshotRequest,
    StockTradesRequest,
    OptionChainRequest,
    CorporateActionsRequest,
    CryptoBarsRequest,
    CryptoQuoteRequest,
    CryptoLatestQuoteRequest,
    CryptoTradesRequest,
    CryptoLatestBarRequest,
    CryptoLatestTradeRequest,
    CryptoSnapshotRequest,
    CryptoLatestOrderbookRequest
)

from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import (
    AssetStatus,
    ContractType,
    OrderClass,
    OrderSide,
    OrderType,
    QueryOrderStatus,
    TimeInForce,
)
from alpaca.trading.models import Order
from alpaca.trading.requests import (
    ClosePositionRequest,
    CreateWatchlistRequest,
    GetAssetsRequest,
    GetCalendarRequest,
    GetPortfolioHistoryRequest,
    GetOptionContractsRequest,
    GetOrdersRequest,
    LimitOrderRequest,
    MarketOrderRequest,
    OptionLegRequest,
    StopLimitOrderRequest,
    StopLossRequest,
    StopOrderRequest,
    TakeProfitRequest,
    TrailingStopOrderRequest,
    UpdateWatchlistRequest,
)


# Import shared helpers
# Try relative import first (works when run as a module)
# Fall back to absolute import if running as a script directly
try:
    from .helpers import (
        parse_timeframe_with_enums,
        _parse_iso_datetime,
        _parse_date_ymd,
        _parse_expiration_expression,
        _validate_option_order_inputs,
        _convert_order_class_string,
        _process_option_legs,
        _create_option_order_request,
        _format_option_order_response,
        _handle_option_api_error,
        build_success_result,
        build_error_result,
        to_serializable,
        compact_json,
    )
except ImportError:
    # Handle direct script execution where __package__ is empty
    # Add the package root to sys.path and use absolute import
    package_root = Path(__file__).parent.parent.parent
    if str(package_root) not in sys.path:
        sys.path.insert(0, str(package_root))
    from alpaca_mcp_server.helpers import (
        parse_timeframe_with_enums,
        _validate_amount,
        _parse_iso_datetime,
        _parse_date_ymd,
        _parse_expiration_expression,
        _validate_option_order_inputs,
        _convert_order_class_string,
        _process_option_legs,
        _create_option_order_request,
        _format_option_order_response,
        _handle_option_api_error,
        build_success_result,
        build_error_result,
        to_serializable,
        compact_json,
    )

from mcp.server.fastmcp import FastMCP
from mcp.types import CallToolResult

# Configure Python path for local imports (UserAgentMixin)
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = Path(current_dir).parent.parent
github_core_path = project_root / '.github' / 'core'
if github_core_path.exists() and str(github_core_path) not in sys.path:
    sys.path.insert(0, str(github_core_path))

# Import the UserAgentMixin
try:
    from user_agent_mixin import UserAgentMixin
    # Define new classes using the mixin
    class TradingClientSigned(UserAgentMixin, TradingClient): pass
    class StockHistoricalDataClientSigned(UserAgentMixin, StockHistoricalDataClient): pass
    class OptionHistoricalDataClientSigned(UserAgentMixin, OptionHistoricalDataClient): pass
    class CorporateActionsClientSigned(UserAgentMixin, CorporateActionsClient): pass
    class CryptoHistoricalDataClientSigned(UserAgentMixin, CryptoHistoricalDataClient): pass
except ImportError:
    # Fallback to unsigned clients if mixin not available
    TradingClientSigned = TradingClient
    StockHistoricalDataClientSigned = StockHistoricalDataClient
    OptionHistoricalDataClientSigned = OptionHistoricalDataClient
    CorporateActionsClientSigned = CorporateActionsClient
    CryptoHistoricalDataClientSigned = CryptoHistoricalDataClient

# Load environment variables
load_dotenv()

# Get environment variables
TRADE_API_KEY = os.getenv("ALPACA_API_KEY")
TRADE_API_SECRET = os.getenv("ALPACA_SECRET_KEY")
ALPACA_PAPER_TRADE = os.getenv("ALPACA_PAPER_TRADE", "True")
TRADE_API_URL = os.getenv("TRADE_API_URL")
TRADE_API_WSS = os.getenv("TRADE_API_WSS")
DATA_API_URL = os.getenv("DATA_API_URL")
STREAM_DATA_WSS = os.getenv("STREAM_DATA_WSS")
DEBUG = os.getenv("DEBUG", "False")

# Initialize log level
def detect_pycharm_environment():
    """Detect if we're running in PyCharm using environment variable."""
    mcp_client = os.getenv("MCP_CLIENT", "").lower()
    return mcp_client == "pycharm"

is_pycharm = detect_pycharm_environment()
log_level = "ERROR" if is_pycharm else "INFO"
log_level = "DEBUG" if DEBUG.lower() == "true" else log_level

# Initialize FastMCP server
mcp = FastMCP("alpaca-trading", log_level=log_level)

# Convert string to boolean
ALPACA_PAPER_TRADE_BOOL = ALPACA_PAPER_TRADE.lower() not in ['false', '0', 'no', 'off']

# Client initialization - lazy loading to allow server to start without credentials
_clients_initialized = False
trade_client = None
stock_historical_data_client = None
stock_data_stream_client = None
option_historical_data_client = None
corporate_actions_client = None
crypto_historical_data_client = None

def _ensure_clients():
    """
    Initialize Alpaca's Trading API clients on first use.
    Uses API key/secret pair from environment variables.
    """
    global _clients_initialized, trade_client, stock_historical_data_client, stock_data_stream_client
    global option_historical_data_client, corporate_actions_client, crypto_historical_data_client
    
    if not _clients_initialized:
        trade_client = TradingClientSigned(TRADE_API_KEY, TRADE_API_SECRET, paper=ALPACA_PAPER_TRADE_BOOL)
        stock_historical_data_client = StockHistoricalDataClientSigned(TRADE_API_KEY, TRADE_API_SECRET)
        stock_data_stream_client = StockDataStream(TRADE_API_KEY, TRADE_API_SECRET, url_override=STREAM_DATA_WSS)
        option_historical_data_client = OptionHistoricalDataClientSigned(api_key=TRADE_API_KEY, secret_key=TRADE_API_SECRET)
        corporate_actions_client = CorporateActionsClientSigned(api_key=TRADE_API_KEY, secret_key=TRADE_API_SECRET)
        crypto_historical_data_client = CryptoHistoricalDataClientSigned(api_key=TRADE_API_KEY, secret_key=TRADE_API_SECRET)
        _clients_initialized = True

# ============================================================================
# Asset Information Tools
# ============================================================================

@mcp.tool(
    annotations={
        "title": "Get Asset Info",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
async def get_asset(symbol: str) -> str:
    """
    Retrieves and formats detailed information about a specific asset.
    
    Args:
        symbol (str): The symbol of the asset to get information for
    
    Returns:
        str: Compact JSON asset payload with the asset details with name, exchange, class, status, and trading properties
    """
    _ensure_clients()
    try:
        asset = trade_client.get_asset(symbol)
        return compact_json(to_serializable(asset))
    except Exception as e:
        return f"Error fetching asset information: {str(e)}"

@mcp.tool(
    annotations={
        "title": "Get All Assets",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
async def get_all_assets(
    status: Optional[str] = None,
    asset_class: Optional[str] = None,
    exchange: Optional[str] = None,
    attributes: Optional[str] = None
) -> str:
    """
    Get all available assets with optional filtering.
    
    Args:
        status (Optional[str]): Filter by asset status (e.g., 'active', 'inactive')
        asset_class (Optional[str]): Filter by asset class (e.g., 'us_equity', 'crypto')
        exchange (Optional[str]): Filter by exchange (e.g., 'NYSE', 'NASDAQ')
        attributes (Optional[str]): Comma-separated values for multiple attributes

    Returns:
        str: Compact JSON assets payload with assets with symbol, name, exchange, class, and status
    """
    _ensure_clients()
    try:
        # Create filter if any parameters are provided
        filter_params = None
        if any([status, asset_class, exchange, attributes]):
            filter_params = GetAssetsRequest(
                status=status,
                asset_class=asset_class,
                exchange=exchange,
                attributes=attributes
            )
        
        # Get all assets
        assets = trade_client.get_all_assets(filter_params)
        
        payload = {
            "request": {
                "status": status,
                "asset_class": asset_class,
                "exchange": exchange,
                "attributes": attributes,
            },
            "assets": [to_serializable(asset) for asset in (assets or [])],
        }
        return compact_json(payload)
        
    except Exception as e:
        return f"Error fetching assets: {str(e)}"

# ============================================================================
# Corporate Actions Tools
# ============================================================================

@mcp.tool(
    annotations={
        "title": "Get Corporate Actions",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
async def get_corporate_actions(
    ca_types: Optional[List[CorporateActionsType]] = None,
    start: Optional[date] = None,
    end: Optional[date] = None,
    symbols: Optional[List[str]] = None,
    cusips: Optional[List[str]] = None,
    ids: Optional[List[str]] = None,
    limit: Optional[int] = 1000,
    sort: Optional[str] = "asc"
) -> str:
    """
    Retrieves and formats corporate action announcements.
    
    Args:
        ca_types (Optional[List[CorporateActionsType]]): List of corporate action types to filter by (default: all types)
            Available types: CorporateActionsType.REVERSE_SPLIT, CorporateActionsType.FORWARD_SPLIT, CorporateActionsType.UNIT_SPLIT, CorporateActionsType.CASH_DIVIDEND, CorporateActionsType.STOCK_DIVIDEND, CorporateActionsType.SPIN_OFF, CorporateActionsType.CASH_MERGER, CorporateActionsType.STOCK_MERGER, CorporateActionsType.STOCK_AND_CASH_MERGER, CorporateActionsType.REDEMPTION, CorporateActionsType.NAME_CHANGE, CorporateActionsType.WORTHLESS_REMOVAL, CorporateActionsType.RIGHTS_DISTRIBUTION
        start (Optional[date]): Start date for the announcements (default: current day)
        end (Optional[date]): End date for the announcements (default: current day)
        symbols (Optional[List[str]]): Optional list of stock symbols to filter by
        cusips (Optional[List[str]]): Optional list of CUSIPs to filter by
        ids (Optional[List[str]]): Optional list of corporate action IDs (mutually exclusive with other filters)
        limit (Optional[int]): Maximum number of results to return (default: 1000)
        sort (Optional[str]): Sort order (asc or desc, default: asc)
    
    Returns:
        str: Formatted string containing corporate announcement details
    """
    _ensure_clients()
    try:
        request = CorporateActionsRequest(
            symbols=symbols,
            cusips=cusips,
            types=ca_types,
            start=start,
            end=end,
            ids=ids,
            limit=limit,
            sort=sort
        )
        announcements = corporate_actions_client.get_corporate_actions(request)
        raw_data = getattr(announcements, "data", {}) if announcements else {}
        payload = {
            "request": {
                "ca_types": to_serializable(ca_types),
                "start": to_serializable(start),
                "end": to_serializable(end),
                "symbols": symbols,
                "cusips": cusips,
                "ids": ids,
                "limit": limit,
                "sort": sort,
            },
            "announcements": to_serializable(raw_data) if raw_data else {},
        }
        return compact_json(payload)
    except Exception as e:
        return f"Error fetching corporate announcements: {str(e)}"

# ============================================================================
# Market Calendar Tools
# ============================================================================

@mcp.tool(
    annotations={
        "title": "Get Market Calendar",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
async def get_calendar(start_date: str, end_date: str) -> str:
    """
    Retrieves and formats market calendar for specified date range.
    
    Args:
        start_date (str): Start date in YYYY-MM-DD format
        end_date (str): End date in YYYY-MM-DD format
    
    Returns:
        str: Compact JSON market calendar payload about market calendar information
    """
    _ensure_clients()
    try:
        # Convert string dates to date objects
        start_dt = _parse_date_ymd(start_date)
        end_dt = _parse_date_ymd(end_date)
        
        calendar_request = GetCalendarRequest(start=start_dt, end=end_dt)
        calendar = trade_client.get_calendar(calendar_request)

        payload = {
            "request": {"start_date": start_date, "end_date": end_date},
            "calendar": [to_serializable(day) for day in (calendar or [])],
        }
        return compact_json(payload)
    except Exception as e:
        return f"Error fetching market calendar: {str(e)}"

# ============================================================================
# Market Clock Tools
# ============================================================================

@mcp.tool(
    annotations={
        "title": "Get Market Clock",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
async def get_clock() -> str:
    """
    Retrieves and formats current market status and next open/close times.
    
    Returns:
        str: Compact JSON market clock payload with current time, open/closed state, and next open/close times
    """
    _ensure_clients()
    try:
        clock = trade_client.get_clock()
        return compact_json(to_serializable(clock))
    except Exception as e:
        return f"Error fetching market clock: {str(e)}"

# ============================================================================
# Stock Market Data Tools
# ============================================================================

@mcp.tool(
    annotations={
        "title": "Get Stock Bars",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
async def get_stock_bars(
    symbol: Union[str, List[str]],
    days: int = 5,
    hours: int = 0,
    minutes: int = 30,
    timeframe: str = "1Day",
    limit: Optional[int] = 1000,
    start: Optional[str] = None,
    end: Optional[str] = None,
    sort: Optional[Sort] = Sort.ASC,
    feed: Optional[DataFeed] = DataFeed.IEX,
    currency: Optional[SupportedCurrencies] = None,
    asof: Optional[str] = None,
    tz: str = "America/New_York"
) -> CallToolResult:
    """
    Retrieves and formats historical price bars for a stock with configurable timeframe and time range.
    
    Args:
        symbol (Union[str, List[str]]): Stock ticker symbol(s) (e.g., 'AAPL', 'MSFT' or ['AAPL', 'MSFT'])
        days (int): Number of days to look back
        hours (int): Number of hours to look back
        minutes (int): Number of minutes to look back
        timeframe (str): Bar timeframe - supports flexible Alpaca's formats:
            - Minutes: "1Min" to "59Min" (or "1T" to "59T")
            - Hours: "1Hour" to "23Hour" (or "1H" to "23H")
            - Days: "1Day" (or "1D")
            - Weeks: "1Week" (or "1W")
            - Months: "1Month", "2Month", "3Month", "4Month", "6Month", or "12Month" (or use "M" suffix)
            (default: "1Day")
        limit (Optional[int]): Maximum number of bars to return (default: 1000)
        start (Optional[str]): Start time in ISO format
        end (Optional[str]): End time in ISO format
        sort (Optional[Sort]): Chronological order of response (ASC or DESC)
        feed (Optional[DataFeed]): The stock data feed to retrieve from (DataFeed.IEX or DataFeed.SIP, default: None)
        currency (Optional[SupportedCurrencies]): Currency for prices (default: USD)
        asof (Optional[str]): The asof date in YYYY-MM-DD format
        tz (str): Timezone for naive datetime strings (default: "America/New_York")
    
    Returns:
        str: Historical price data with timestamps, OHLCV data
    """
    _ensure_clients()
    tool_name = "get_stock_bars"
    symbols_list = symbol if isinstance(symbol, list) else [symbol]
    try:
        timeframe_obj = parse_timeframe_with_enums(timeframe)
        if timeframe_obj is None:
            return build_error_result(
                tool_name,
                "invalid_timeframe",
                "Unsupported timeframe format.",
                field="timeframe",
                details={"provided": timeframe},
            )

        start_time = None
        end_time = None
        now_utc = datetime.now(timezone.utc)
        if start:
            try:
                start_time = _parse_iso_datetime(start, default_timezone=tz)
            except ValueError as e:
                return build_error_result(tool_name, "invalid_start", str(e), field="start")
        if end:
            try:
                end_time = _parse_iso_datetime(end, default_timezone=tz)
            except ValueError as e:
                return build_error_result(tool_name, "invalid_end", str(e), field="end")
        else:
            end_time = now_utc - timedelta(minutes=15)
        if not start_time:
            if days > 0:
                start_time = now_utc - timedelta(days=days)
            elif hours > 0:
                start_time = now_utc - timedelta(hours=hours)
            elif minutes > 0:
                start_time = now_utc - timedelta(minutes=minutes)

        request_params = StockBarsRequest(
            symbol_or_symbols=symbols_list,
            timeframe=timeframe_obj,
            start=start_time,
            end=end_time,
            limit=limit,
            sort=sort,
            feed=feed,
            currency=currency,
            asof=asof,
        )
        bars = stock_historical_data_client.get_stock_bars(request_params)
        mapping_bars = getattr(bars, "data", None) or bars

        bars_by_symbol: Dict[str, List[Dict[str, Any]]] = {}
        counts: Dict[str, int] = {}
        total_records = 0
        for sym in symbols_list:
            sym_bars = mapping_bars.get(sym) if hasattr(mapping_bars, "get") else []
            sym_serialized = [to_serializable(bar) for bar in (sym_bars or [])]
            bars_by_symbol[sym] = sym_serialized
            counts[sym] = len(sym_serialized)
            total_records += len(sym_serialized)

        payload = {
            "tool": tool_name,
            "request": {
                "symbols": symbols_list,
                "days": days,
                "hours": hours,
                "minutes": minutes,
                "timeframe": timeframe,
                "limit": limit,
                "start": start,
                "end": end,
                "sort": to_serializable(sort),
                "feed": to_serializable(feed),
                "currency": to_serializable(currency),
                "asof": asof,
                "tz": tz,
            },
            "counts": {"symbols": len(symbols_list), "records": total_records, "per_symbol": counts},
            "bars": bars_by_symbol,
        }
        return build_success_result(
            tool_name,
            payload,
            summary=f"{tool_name}: ok symbols={len(symbols_list)} records={total_records}",
            content_text=compact_json(payload),
        )
    except APIError as api_error:
        error_message = str(api_error)
        lower = error_message.lower()
        if "subscription" in lower and "sip" in lower and ("recent" in lower or "15" in lower):
            fifteen_ago = datetime.now(timezone.utc) - timedelta(minutes=15)
            hint_end = fifteen_ago.strftime("%Y-%m-%dT%H:%M:%S")
            return build_error_result(
                tool_name,
                "sip_delay_window",
                "SIP data is delayed by 15 minutes on free plan.",
                details={"hint_end": hint_end, "original_error": error_message},
            )
        return build_error_result(
            tool_name,
            "api_error",
            "Failed to fetch stock bars.",
            details={"symbols": symbols_list, "original_error": error_message},
        )
    except Exception as e:
        return build_error_result(
            tool_name,
            "internal_error",
            "Failed to fetch stock bars.",
            details={"symbols": symbols_list, "original_error": str(e)},
        )

@mcp.tool(
    annotations={
        "title": "Get Stock Quotes",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
async def get_stock_quotes(
    symbol: Union[str, List[str]],
    days: int = 0,
    hours: int = 0,
    minutes: int = 20,
    limit: Optional[int] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    sort: Optional[Sort] = Sort.ASC,
    feed: Optional[DataFeed] = DataFeed.IEX,
    currency: Optional[SupportedCurrencies] = None,
    asof: Optional[str] = None,
    tz: str = "America/New_York"
) -> CallToolResult:
    """
    Retrieves and formats historical quote data (level 1 bid/ask) for a stock.
    
    Args:
        symbol (Union[str, List[str]]): Stock ticker symbol(s) (e.g., 'AAPL', 'MSFT' or ['AAPL', 'MSFT'])
        days (int): Number of days to look back
        hours (int): Number of hours to look back
        minutes (int): Number of minutes to look back
        limit (Optional[int]): Upper limit of number of data points to return (default: 1000)
        start (Optional[str]): Start time in ISO format
        end (Optional[str]): End time in ISO format
        sort (Optional[Sort]): Chronological order of response (ASC or DESC)
        feed (Optional[DataFeed]): The stock data feed to retrieve from (DataFeed.IEX or DataFeed.SIP)
        currency (Optional[SupportedCurrencies]): Currency for prices (default: USD)
        asof (Optional[str]): The asof date in YYYY-MM-DD format
        tz (str): Timezone for naive datetime strings (default: "America/New_York")
        
    Returns:
        str: Formatted string containing quote summary or error message
    """
    _ensure_clients()
    tool_name = "get_stock_quotes"
    symbols_list = symbol if isinstance(symbol, list) else [symbol]
    try:
        if limit is None:
            limit = 1000
        now_utc = datetime.now(timezone.utc)
        if start:
            try:
                start_time = _parse_iso_datetime(start, default_timezone=tz)
            except ValueError as e:
                return build_error_result(tool_name, "invalid_start", str(e), field="start")
        else:
            if days > 0:
                start_time = now_utc - timedelta(days=days)
            elif hours > 0:
                start_time = now_utc - timedelta(hours=hours)
            elif minutes > 0:
                start_time = now_utc - timedelta(minutes=minutes)
            else:
                start_time = None
        if end:
            try:
                end_time = _parse_iso_datetime(end, default_timezone=tz)
            except ValueError as e:
                return build_error_result(tool_name, "invalid_end", str(e), field="end")
        else:
            end_time = now_utc - timedelta(minutes=15)

        request_params = StockQuotesRequest(
            symbol_or_symbols=symbols_list,
            start=start_time,
            end=end_time,
            limit=limit,
            sort=sort,
            feed=feed,
            currency=currency,
            asof=asof,
        )
        quotes = stock_historical_data_client.get_stock_quotes(request_params)
        mapping_quotes = getattr(quotes, "data", None) or quotes
        quotes_by_symbol: Dict[str, List[Dict[str, Any]]] = {}
        counts: Dict[str, int] = {}
        total_records = 0
        for sym in symbols_list:
            sym_quotes = mapping_quotes.get(sym) if hasattr(mapping_quotes, "get") else []
            sym_serialized = [to_serializable(q) for q in (sym_quotes or [])]
            quotes_by_symbol[sym] = sym_serialized
            counts[sym] = len(sym_serialized)
            total_records += len(sym_serialized)

        payload = {
            "tool": tool_name,
            "request": {
                "symbols": symbols_list,
                "days": days,
                "hours": hours,
                "minutes": minutes,
                "limit": limit,
                "start": start,
                "end": end,
                "sort": to_serializable(sort),
                "feed": to_serializable(feed),
                "currency": to_serializable(currency),
                "asof": asof,
                "tz": tz,
            },
            "counts": {"symbols": len(symbols_list), "records": total_records, "per_symbol": counts},
            "quotes": quotes_by_symbol,
        }
        return build_success_result(
            tool_name,
            payload,
            summary=f"{tool_name}: ok symbols={len(symbols_list)} records={total_records}",
            content_text=compact_json(payload),
        )
    except APIError as api_error:
        error_message = str(api_error)
        lower = error_message.lower()
        if "subscription" in lower and "sip" in lower and ("recent" in lower or "15" in lower):
            fifteen_ago = datetime.now(timezone.utc) - timedelta(minutes=15)
            hint_end = fifteen_ago.strftime("%Y-%m-%dT%H:%M:%S")
            return build_error_result(
                tool_name,
                "sip_delay_window",
                "SIP data is delayed by 15 minutes on free plan.",
                details={"hint_end": hint_end, "original_error": error_message},
            )
        return build_error_result(
            tool_name,
            "api_error",
            "Failed to fetch stock quotes.",
            details={"symbols": symbols_list, "original_error": error_message},
        )
    except Exception as e:
        return build_error_result(
            tool_name,
            "internal_error",
            "Failed to fetch stock quotes.",
            details={"symbols": symbols_list, "original_error": str(e)},
        )

@mcp.tool(
    annotations={
        "title": "Get Stock Trades",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
async def get_stock_trades(
    symbol: Union[str, List[str]],
    days: int = 0,
    hours: int = 0,
    minutes: int = 20,
    limit: Optional[int] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    sort: Optional[Sort] = Sort.ASC,
    feed: Optional[DataFeed] = DataFeed.IEX,
    currency: Optional[SupportedCurrencies] = None,
    asof: Optional[str] = None,
    tz: str = "America/New_York"
) -> CallToolResult:
    """
    Retrieves and formats historical trades for a stock.
    
    Args:
        symbol (Union[str, List[str]]): Stock ticker symbol(s)
        days (int): Number of days to look back
        hours (int): Number of hours to look back
        minutes (int): Number of minutes to look back
        limit (Optional[int]): Upper limit of number of data points to return
        start (Optional[str]): Start time in ISO format
        end (Optional[str]): End time in ISO format
        sort (Optional[Sort]): Chronological order of response (ASC or DESC)
        feed (Optional[DataFeed]): The stock data feed to retrieve from (DataFeed.IEX or DataFeed.SIP)
        currency (Optional[SupportedCurrencies]): Currency for prices
        asof (Optional[str]): The asof date in YYYY-MM-DD format
        tz (str): Timezone for naive datetime strings
            Supported: "UTC", "ET", "EST", "EDT", "America/New_York"
    
    Returns:
        str: Formatted string containing trade history or an error message
    """
    _ensure_clients()
    tool_name = "get_stock_trades"
    symbols_list = symbol if isinstance(symbol, list) else [symbol]
    try:
        now_utc = datetime.now(timezone.utc)
        if start:
            try:
                start_time = _parse_iso_datetime(start, default_timezone=tz)
            except ValueError as e:
                return build_error_result(tool_name, "invalid_start", str(e), field="start")
        else:
            if days > 0:
                start_time = now_utc - timedelta(days=days)
            elif hours > 0:
                start_time = now_utc - timedelta(hours=hours)
            elif minutes > 0:
                start_time = now_utc - timedelta(minutes=minutes)
            else:
                start_time = None

        if end:
            try:
                end_time = _parse_iso_datetime(end, default_timezone=tz)
            except ValueError as e:
                return build_error_result(tool_name, "invalid_end", str(e), field="end")
        else:
            end_time = now_utc - timedelta(minutes=15)

        request_params = StockTradesRequest(
            symbol_or_symbols=symbols_list,
            start=start_time,
            end=end_time,
            limit=limit,
            sort=sort,
            feed=feed,
            currency=currency,
            asof=asof,
        )
        trades = stock_historical_data_client.get_stock_trades(request_params)
        mapping_trades = getattr(trades, "data", None) or trades

        trades_by_symbol: Dict[str, List[Dict[str, Any]]] = {}
        counts: Dict[str, int] = {}
        total_records = 0
        for sym in symbols_list:
            sym_trades = mapping_trades.get(sym) if hasattr(mapping_trades, "get") else []
            sym_serialized = [to_serializable(t) for t in (sym_trades or [])]
            trades_by_symbol[sym] = sym_serialized
            counts[sym] = len(sym_serialized)
            total_records += len(sym_serialized)

        payload = {
            "tool": tool_name,
            "request": {
                "symbols": symbols_list,
                "days": days,
                "hours": hours,
                "minutes": minutes,
                "limit": limit,
                "start": start,
                "end": end,
                "sort": to_serializable(sort),
                "feed": to_serializable(feed),
                "currency": to_serializable(currency),
                "asof": asof,
                "tz": tz,
            },
            "counts": {"symbols": len(symbols_list), "records": total_records, "per_symbol": counts},
            "trades": trades_by_symbol,
        }
        return build_success_result(
            tool_name,
            payload,
            summary=f"{tool_name}: ok symbols={len(symbols_list)} records={total_records}",
            content_text=compact_json(payload),
        )
    except Exception as e:
        return build_error_result(
            tool_name,
            "internal_error",
            "Failed to fetch stock trades.",
            details={"symbols": symbols_list, "original_error": str(e)},
        )

@mcp.tool(
    annotations={
        "title": "Get Stock Latest Bar",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
async def get_stock_latest_bar(
    symbol_or_symbols: Union[str, List[str]],
    feed: Optional[DataFeed] = DataFeed.IEX,
    currency: Optional[SupportedCurrencies] = None
) -> CallToolResult:
    """
    Get the latest minute bar for one or more stocks.
    
    Args:
        symbol_or_symbols: Stock ticker symbol(s) (e.g., 'AAPL' or ['AAPL', 'MSFT'])
        feed: The stock data feed to retrieve from (DataFeed.IEX or DataFeed.SIP, default: None)
        currency: The currency for prices (optional, defaults to USD)
    
    Returns:
        str: Latest bar(s) for one or more stocks
    """
    _ensure_clients()
    tool_name = "get_stock_latest_bar"
    symbols_list = [symbol_or_symbols] if isinstance(symbol_or_symbols, str) else list(symbol_or_symbols)
    if not symbols_list:
        return build_error_result(tool_name, "missing_symbols", "No symbols provided.", field="symbol_or_symbols")
    try:
        request_params = StockLatestBarRequest(symbol_or_symbols=symbol_or_symbols, feed=feed, currency=currency)
        latest_bars = stock_historical_data_client.get_stock_latest_bar(request_params)
        bars_by_symbol: Dict[str, Any] = {}
        found = 0
        for sym in symbols_list:
            bar = latest_bars.get(sym) if hasattr(latest_bars, "get") else None
            bars_by_symbol[sym] = to_serializable(bar) if bar else None
            if bar:
                found += 1
        payload = {
            "tool": tool_name,
            "request": {"symbols": symbols_list, "feed": to_serializable(feed), "currency": to_serializable(currency)},
            "counts": {"symbols": len(symbols_list), "records": found},
            "bars": bars_by_symbol,
        }
        return build_success_result(
            tool_name,
            payload,
            summary=f"{tool_name}: ok symbols={len(symbols_list)} found={found}",
            content_text=compact_json(payload),
        )
    except Exception as e:
        return build_error_result(
            tool_name,
            "internal_error",
            "Failed to fetch latest stock bar.",
            details={"symbols": symbols_list, "original_error": str(e)},
        )


@mcp.tool(
    annotations={
        "title": "Get Stock Latest Quote",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
async def get_stock_latest_quote(
    symbol_or_symbols: Union[str, List[str]],
    feed: Optional[DataFeed] = DataFeed.IEX,
    currency: Optional[SupportedCurrencies] = None
    ) -> CallToolResult:
    """
    Retrieves and formats the latest quote for one or more stocks.
    
    Args:
        symbol_or_symbols (Union[str, List[str]]): Stock ticker symbol(s) (e.g., 'AAPL' or ['AAPL', 'MSFT'])
        feed (Optional[DataFeed]): Data feed source (IEX or SIP)
        currency (Optional[SupportedCurrencies]): Currency for prices (default: USD)
    
    Returns:
        str: Latest bid/ask prices, sizes, and timestamp for each symbol
    """
    _ensure_clients()
    tool_name = "get_stock_latest_quote"
    symbols = [symbol_or_symbols] if isinstance(symbol_or_symbols, str) else list(symbol_or_symbols)
    if not symbols:
        return build_error_result(tool_name, "missing_symbols", "No symbols provided.", field="symbol_or_symbols")
    try:
        request_params = StockLatestQuoteRequest(symbol_or_symbols=symbol_or_symbols, feed=feed, currency=currency)
        quotes = stock_historical_data_client.get_stock_latest_quote(request_params)
        quotes_by_symbol: Dict[str, Any] = {}
        found = 0
        for sym in symbols:
            quote = quotes.get(sym) if hasattr(quotes, "get") else None
            quotes_by_symbol[sym] = to_serializable(quote) if quote else None
            if quote:
                found += 1
        payload = {
            "tool": tool_name,
            "request": {"symbols": symbols, "feed": to_serializable(feed), "currency": to_serializable(currency)},
            "counts": {"symbols": len(symbols), "records": found},
            "quotes": quotes_by_symbol,
        }
        return build_success_result(
            tool_name,
            payload,
            summary=f"{tool_name}: ok symbols={len(symbols)} found={found}",
            content_text=compact_json(payload),
        )
    except Exception as e:
        return build_error_result(
            tool_name,
            "internal_error",
            "Failed to fetch latest stock quote.",
            details={"symbols": symbols, "original_error": str(e)},
        )

@mcp.tool(
    annotations={
        "title": "Get Stock Latest Trade",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
async def get_stock_latest_trade(
    symbol_or_symbols: Union[str, List[str]],
    feed: Optional[DataFeed] = DataFeed.IEX,
    currency: Optional[SupportedCurrencies] = None
) -> CallToolResult:
    """Get the latest trade for one or more stocks.
    
    Args:
        symbol_or_symbols: Stock ticker symbol(s) (e.g., 'AAPL' or ['AAPL', 'MSFT'])
        feed: The stock data feed to retrieve from (DataFeed.IEX or DataFeed.SIP, default: None)
        currency: The currency for prices (optional, defaults to USD)
    
    Returns:
        str: Latest trade(s) for one or more stocks
    """
    _ensure_clients()
    tool_name = "get_stock_latest_trade"
    symbols_list = [symbol_or_symbols] if isinstance(symbol_or_symbols, str) else list(symbol_or_symbols)
    if not symbols_list:
        return build_error_result(tool_name, "missing_symbols", "No symbols provided.", field="symbol_or_symbols")
    try:
        request_params = StockLatestTradeRequest(symbol_or_symbols=symbol_or_symbols, feed=feed, currency=currency)
        latest_trades = stock_historical_data_client.get_stock_latest_trade(request_params)
        trades_by_symbol: Dict[str, Any] = {}
        found = 0
        for sym in symbols_list:
            trade = latest_trades.get(sym) if hasattr(latest_trades, "get") else None
            trades_by_symbol[sym] = to_serializable(trade) if trade else None
            if trade:
                found += 1
        payload = {
            "tool": tool_name,
            "request": {"symbols": symbols_list, "feed": to_serializable(feed), "currency": to_serializable(currency)},
            "counts": {"symbols": len(symbols_list), "records": found},
            "trades": trades_by_symbol,
        }
        return build_success_result(
            tool_name,
            payload,
            summary=f"{tool_name}: ok symbols={len(symbols_list)} found={found}",
            content_text=compact_json(payload),
        )
    except Exception as e:
        return build_error_result(
            tool_name,
            "internal_error",
            "Failed to fetch latest stock trade.",
            details={"symbols": symbols_list, "original_error": str(e)},
        )


@mcp.tool(
    annotations={
        "title": "Get Stock Snapshot",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
async def get_stock_snapshot(
    symbol_or_symbols: Union[str, List[str]], 
    feed: Optional[DataFeed] = DataFeed.IEX,
    currency: Optional[SupportedCurrencies] = None
) -> CallToolResult:
    """
    Retrieves comprehensive snapshots of stock symbols including latest trade, quote, minute bar, daily bar, and previous daily bar.
    
    Args:
        symbol_or_symbols: Single stock symbol or list of stock symbols
        feed: The stock data feed to retrieve from (DataFeed.IEX or DataFeed.SIP)
        currency: The currency the data should be returned in
    
    Returns:
        str: Comprehensive snapshots including latest_quote, latest_trade, minute_bar, daily_bar, previous_daily_bar
    """
    _ensure_clients()
    tool_name = "get_stock_snapshot"
    symbols = [symbol_or_symbols] if isinstance(symbol_or_symbols, str) else list(symbol_or_symbols)
    try:
        request = StockSnapshotRequest(symbol_or_symbols=symbol_or_symbols, feed=feed, currency=currency)
        snapshots = stock_historical_data_client.get_stock_snapshot(request)
        snapshots_by_symbol: Dict[str, Any] = {}
        found = 0
        for sym in symbols:
            snapshot = snapshots.get(sym) if hasattr(snapshots, "get") else None
            snapshots_by_symbol[sym] = to_serializable(snapshot) if snapshot else None
            if snapshot:
                found += 1

        payload = {
            "tool": tool_name,
            "request": {"symbols": symbols, "feed": to_serializable(feed), "currency": to_serializable(currency)},
            "counts": {"symbols": len(symbols), "records": found},
            "snapshots": snapshots_by_symbol,
        }
        return build_success_result(
            tool_name,
            payload,
            summary=f"{tool_name}: ok symbols={len(symbols)} found={found}",
            content_text=compact_json(payload),
        )
    except APIError as api_error:
        error_message = str(api_error)
        if "subscription" in error_message.lower() and ("sip" in error_message.lower() or "premium" in error_message.lower()):
            return build_error_result(
                tool_name,
                "premium_feed_required",
                "Premium data feed subscription required.",
                details={"original_error": error_message},
            )
        return build_error_result(
            tool_name,
            "api_error",
            "Failed to retrieve stock snapshots.",
            details={"original_error": error_message},
        )
    except Exception as e:
        return build_error_result(
            tool_name,
            "internal_error",
            "Failed to retrieve stock snapshots.",
            details={"original_error": str(e)},
        )

# ============================================================================
# Crypto Market Data Tools
# ============================================================================

@mcp.tool(
    annotations={
        "title": "Get Crypto Bars",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
async def get_crypto_bars(
    symbol: Union[str, List[str]], 
    days: int = 1,
    hours: int = 0,
    minutes: int = 30,
    timeframe: str = "1Hour",
    limit: Optional[int] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    feed: CryptoFeed = CryptoFeed.US,
    tz: str = "America/New_York"
) -> CallToolResult:
    """
    Retrieves and formats historical price bars for a cryptocurrency with configurable timeframe and time range.
    
    Args:
        symbol (Union[str, List[str]]): Crypto symbol(s) (e.g., 'BTC/USD', 'ETH/USD' or ['BTC/USD', 'ETH/USD'])
        days (int): Number of days to look back
        hours (int): Number of hours to look back
        minutes (int): Number of minutes to look back
        timeframe (str): Bar timeframe - supports flexible Alpaca's formats:
            - Minutes, Hours, Days, Weeks, Months (default: "1Hour")
        limit (Optional[int]): Maximum number of bars to return (optional)
        start (Optional[str]): Start time in ISO format
        end (Optional[str]): End time in ISO format
        feed (CryptoFeed): The crypto data feed to retrieve from
        tz (str): Timezone for naive datetime strings (default: "America/New_York")
            Supported: "UTC", "ET", "EST", "EDT", "America/New_York"
    
    Returns:
        str: Formatted string containing historical crypto price data with timestamps, OHLCV data
    """
    _ensure_clients()
    tool_name = "get_crypto_bars"
    symbols_list = symbol if isinstance(symbol, list) else [symbol]
    try:
        timeframe_obj = parse_timeframe_with_enums(timeframe)
        if timeframe_obj is None:
            return build_error_result(
                tool_name,
                "invalid_timeframe",
                "Unsupported timeframe format.",
                field="timeframe",
                details={"provided": timeframe},
            )

        start_time = None
        end_time = None
        now_utc = datetime.now(timezone.utc)
        if start:
            try:
                start_time = _parse_iso_datetime(start, default_timezone=tz)
            except ValueError as e:
                return build_error_result(tool_name, "invalid_start", str(e), field="start")
        if end:
            try:
                end_time = _parse_iso_datetime(end, default_timezone=tz)
            except ValueError as e:
                return build_error_result(tool_name, "invalid_end", str(e), field="end")
        if not start_time:
            if days > 0:
                start_time = now_utc - timedelta(days=days)
            elif hours > 0:
                start_time = now_utc - timedelta(hours=hours)
            elif minutes > 0:
                start_time = now_utc - timedelta(minutes=minutes)

        request_params = CryptoBarsRequest(
            symbol_or_symbols=symbols_list,
            timeframe=timeframe_obj,
            start=start_time,
            end=end_time,
            limit=limit,
        )
        bars = crypto_historical_data_client.get_crypto_bars(request_params, feed=feed)
        mapping_bars = getattr(bars, "data", None) or bars

        bars_by_symbol: Dict[str, List[Dict[str, Any]]] = {}
        counts: Dict[str, int] = {}
        total_records = 0
        for sym in symbols_list:
            sym_bars = mapping_bars.get(sym) if hasattr(mapping_bars, "get") else []
            sym_serialized = [to_serializable(b) for b in (sym_bars or [])]
            bars_by_symbol[sym] = sym_serialized
            counts[sym] = len(sym_serialized)
            total_records += len(sym_serialized)

        payload = {
            "tool": tool_name,
            "request": {
                "symbols": symbols_list,
                "days": days,
                "hours": hours,
                "minutes": minutes,
                "timeframe": timeframe,
                "limit": limit,
                "start": start,
                "end": end,
                "feed": to_serializable(feed),
                "tz": tz,
            },
            "counts": {"symbols": len(symbols_list), "records": total_records, "per_symbol": counts},
            "bars": bars_by_symbol,
        }
        return build_success_result(
            tool_name,
            payload,
            summary=f"{tool_name}: ok symbols={len(symbols_list)} records={total_records}",
            content_text=compact_json(payload),
        )
    except Exception as e:
        return build_error_result(
            tool_name,
            "internal_error",
            "Failed to fetch historical crypto bars.",
            details={"symbols": symbols_list, "original_error": str(e)},
        )

@mcp.tool(
    annotations={
        "title": "Get Crypto Quotes",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
async def get_crypto_quotes(
    symbol: Union[str, List[str]],
    days: int = 0,
    hours: int = 0,
    minutes: int = 15,
    limit: Optional[int] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    feed: CryptoFeed = CryptoFeed.US,
    tz: str = "America/New_York"
) -> CallToolResult:
    """
    Returns historical quote data for one or more crypto symbols.
    
    Args:
        symbol (Union[str, List[str]]): Crypto symbol(s) (e.g., 'BTC/USD' or ['BTC/USD','ETH/USD'])
        days (int): Number of days to look back
        hours (int): Number of hours to look back
        minutes (int): Number of minutes to look back
        limit (Optional[int]): Maximum number of quotes to return (optional)
        start (Optional[str]): Start time in ISO format
        end (Optional[str]): End time in ISO format
        feed (CryptoFeed): The crypto data feed to retrieve from
        tz (str): Timezone for naive datetime strings
            Supported: "UTC", "ET", "EST", "EDT", "America/New_York"
    
    Returns:
        str: Formatted string containing historical crypto quote data with timestamps, bid/ask prices and sizes
    """
    _ensure_clients()
    tool_name = "get_crypto_quotes"
    symbols_list = symbol if isinstance(symbol, list) else [symbol]
    try:
        if limit is None:
            limit = 1000
        start_time = None
        end_time = None
        now_utc = datetime.now(timezone.utc)
        if start:
            try:
                start_time = _parse_iso_datetime(start, default_timezone=tz)
            except ValueError as e:
                return build_error_result(tool_name, "invalid_start", str(e), field="start")
        else:
            if days > 0:
                start_time = now_utc - timedelta(days=days)
            elif hours > 0:
                start_time = now_utc - timedelta(hours=hours)
            elif minutes > 0:
                start_time = now_utc - timedelta(minutes=minutes)
        if end:
            try:
                end_time = _parse_iso_datetime(end, default_timezone=tz)
            except ValueError as e:
                return build_error_result(tool_name, "invalid_end", str(e), field="end")

        request_params = CryptoQuoteRequest(
            symbol_or_symbols=symbols_list,
            start=start_time,
            end=end_time,
            limit=limit,
        )
        quotes = crypto_historical_data_client.get_crypto_quotes(request_params, feed=feed)
        mapping_quotes = getattr(quotes, "data", None) or quotes

        quotes_by_symbol: Dict[str, List[Dict[str, Any]]] = {}
        counts: Dict[str, int] = {}
        total_records = 0
        for sym in symbols_list:
            sym_quotes = mapping_quotes.get(sym) if hasattr(mapping_quotes, "get") else []
            sym_serialized = [to_serializable(q) for q in (sym_quotes or [])]
            quotes_by_symbol[sym] = sym_serialized
            counts[sym] = len(sym_serialized)
            total_records += len(sym_serialized)

        payload = {
            "tool": tool_name,
            "request": {
                "symbols": symbols_list,
                "days": days,
                "hours": hours,
                "minutes": minutes,
                "limit": limit,
                "start": start,
                "end": end,
                "feed": to_serializable(feed),
                "tz": tz,
            },
            "counts": {"symbols": len(symbols_list), "records": total_records, "per_symbol": counts},
            "quotes": quotes_by_symbol,
        }
        return build_success_result(
            tool_name,
            payload,
            summary=f"{tool_name}: ok symbols={len(symbols_list)} records={total_records}",
            content_text=compact_json(payload),
        )
    except Exception as e:
        return build_error_result(
            tool_name,
            "internal_error",
            "Failed to fetch historical crypto quotes.",
            details={"symbols": symbols_list, "original_error": str(e)},
        )

@mcp.tool(
    annotations={
        "title": "Get Crypto Trades",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
async def get_crypto_trades(
    symbol: Union[str, List[str]],
    days: int = 0,
    hours: int = 0,
    minutes: int = 15,
    limit: Optional[int] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    sort: Optional[str] = None,
    feed: CryptoFeed = CryptoFeed.US,
    tz: str = "America/New_York"
) -> CallToolResult:
    """
    Returns historical trade data for one or more crypto symbols.

    Args:
        symbol (Union[str, List[str]]): Crypto symbol(s) (e.g., 'BTC/USD' or ['BTC/USD','ETH/USD'])
        days (int): Number of days to look back
        hours (int): Number of hours to look back
        minutes (int): Number of minutes to look back
        limit (Optional[int]): Maximum number of trades to return
        start (Optional[str]): ISO start time
        end (Optional[str]): ISO end time
        sort (Optional[str]): 'asc' or 'desc'
        feed (CryptoFeed): Crypto data feed
        tz (str): Timezone for naive datetime strings
            Supported: "UTC", "ET", "EST", "EDT", "America/New_York"

    Returns:
        str: Formatted string containing trade history or error message
    """
    _ensure_clients()
    tool_name = "get_crypto_trades"
    symbols_list = symbol if isinstance(symbol, list) else [symbol]
    try:
        if limit is None:
            limit = 1000
        now_utc = datetime.now(timezone.utc)
        if start:
            try:
                start_time = _parse_iso_datetime(start, default_timezone=tz)
            except ValueError as e:
                return build_error_result(tool_name, "invalid_start", str(e), field="start")
        else:
            if days > 0:
                start_time = now_utc - timedelta(days=days)
            elif hours > 0:
                start_time = now_utc - timedelta(hours=hours)
            elif minutes > 0:
                start_time = now_utc - timedelta(minutes=minutes)
            else:
                start_time = None
        if end:
            try:
                end_time = _parse_iso_datetime(end, default_timezone=tz)
            except ValueError as e:
                return build_error_result(tool_name, "invalid_end", str(e), field="end")
        else:
            end_time = None

        sort_enum = Sort.ASC
        if sort:
            if sort.lower() == "asc":
                sort_enum = Sort.ASC
            elif sort.lower() == "desc":
                sort_enum = Sort.DESC
            else:
                return build_error_result(
                    tool_name,
                    "invalid_sort",
                    "Sort must be 'asc' or 'desc'.",
                    field="sort",
                    details={"provided": sort},
                )

        request_params = CryptoTradesRequest(
            symbol_or_symbols=symbols_list,
            start=start_time,
            end=end_time,
            limit=limit,
            sort=sort_enum,
        )
        trades = crypto_historical_data_client.get_crypto_trades(request_params, feed=feed)
        mapping_trades = getattr(trades, "data", None) or trades

        trades_by_symbol: Dict[str, List[Dict[str, Any]]] = {}
        counts: Dict[str, int] = {}
        total_records = 0
        for sym in symbols_list:
            sym_trades = mapping_trades.get(sym) if hasattr(mapping_trades, "get") else []
            sym_serialized = [to_serializable(t) for t in (sym_trades or [])]
            trades_by_symbol[sym] = sym_serialized
            counts[sym] = len(sym_serialized)
            total_records += len(sym_serialized)

        payload = {
            "tool": tool_name,
            "request": {
                "symbols": symbols_list,
                "days": days,
                "hours": hours,
                "minutes": minutes,
                "limit": limit,
                "start": start,
                "end": end,
                "sort": sort,
                "feed": to_serializable(feed),
                "tz": tz,
            },
            "counts": {"symbols": len(symbols_list), "records": total_records, "per_symbol": counts},
            "trades": trades_by_symbol,
        }
        return build_success_result(
            tool_name,
            payload,
            summary=f"{tool_name}: ok symbols={len(symbols_list)} records={total_records}",
            content_text=compact_json(payload),
        )
    except Exception as e:
        return build_error_result(
            tool_name,
            "internal_error",
            "Failed to fetch historical crypto trades.",
            details={"symbols": symbols_list, "original_error": str(e)},
        )

@mcp.tool(
    annotations={
        "title": "Get Crypto Latest Bar",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
async def get_crypto_latest_bar(
    symbol: Union[str, List[str]],
    feed: CryptoFeed = CryptoFeed.US
) -> CallToolResult:
    """
    Returns the latest minute bar for one or more crypto symbols.

    Args:
        symbol (Union[str, List[str]]): Crypto symbol(s) (e.g., 'BTC/USD' or ['BTC/USD','ETH/USD'])
        feed (CryptoFeed): The crypto data feed (default: US)

    Returns:
        str: Formatted string containing latest bar(s) or error message
    """
    _ensure_clients()
    tool_name = "get_crypto_latest_bar"
    symbols_list = symbol if isinstance(symbol, list) else [symbol]
    try:
        request_params = CryptoLatestBarRequest(symbol_or_symbols=symbol)
        latest = crypto_historical_data_client.get_crypto_latest_bar(request_params, feed=feed)
        mapping_latest_bars = getattr(latest, "data", None) or latest
        bars_by_symbol: Dict[str, Any] = {}
        found = 0
        for sym in symbols_list:
            bar = mapping_latest_bars.get(sym) if hasattr(mapping_latest_bars, "get") else None
            bars_by_symbol[sym] = to_serializable(bar) if bar else None
            if bar:
                found += 1
        payload = {
            "tool": tool_name,
            "request": {"symbols": symbols_list, "feed": to_serializable(feed)},
            "counts": {"symbols": len(symbols_list), "records": found},
            "bars": bars_by_symbol,
        }
        return build_success_result(
            tool_name,
            payload,
            summary=f"{tool_name}: ok symbols={len(symbols_list)} found={found}",
            content_text=compact_json(payload),
        )
    except Exception as e:
        return build_error_result(
            tool_name,
            "internal_error",
            "Failed to retrieve latest crypto bar.",
            details={"symbols": symbols_list, "original_error": str(e)},
        )

@mcp.tool(
    annotations={
        "title": "Get Crypto Latest Quote",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
async def get_crypto_latest_quote(
    symbol: Union[str, List[str]],
    feed: CryptoFeed = CryptoFeed.US
) -> CallToolResult:
    """
    Returns the latest quote for one or more crypto symbols.

    Args:
        symbol (Union[str, List[str]]): Crypto symbol(s) (e.g., 'BTC/USD' or ['BTC/USD','ETH/USD'])
        feed (CryptoFeed): The crypto data feed (default: US)

    Returns:
        str: Formatted string containing latest quote(s) or error message
    """
    _ensure_clients()
    tool_name = "get_crypto_latest_quote"
    symbols_list = symbol if isinstance(symbol, list) else [symbol]
    try:
        request_params = CryptoLatestQuoteRequest(symbol_or_symbols=symbol)
        latest = crypto_historical_data_client.get_crypto_latest_quote(request_params, feed=feed)
        mapping_latest_quotes = getattr(latest, "data", None) or latest
        quotes_by_symbol: Dict[str, Any] = {}
        found = 0
        for sym in symbols_list:
            quote = mapping_latest_quotes.get(sym) if hasattr(mapping_latest_quotes, "get") else None
            quotes_by_symbol[sym] = to_serializable(quote) if quote else None
            if quote:
                found += 1
        payload = {
            "tool": tool_name,
            "request": {"symbols": symbols_list, "feed": to_serializable(feed)},
            "counts": {"symbols": len(symbols_list), "records": found},
            "quotes": quotes_by_symbol,
        }
        return build_success_result(
            tool_name,
            payload,
            summary=f"{tool_name}: ok symbols={len(symbols_list)} found={found}",
            content_text=compact_json(payload),
        )
    except Exception as e:
        return build_error_result(
            tool_name,
            "internal_error",
            "Failed to retrieve latest crypto quote.",
            details={"symbols": symbols_list, "original_error": str(e)},
        )

@mcp.tool(
    annotations={
        "title": "Get Crypto Latest Trade",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
async def get_crypto_latest_trade(
    symbol: Union[str, List[str]],
    feed: CryptoFeed = CryptoFeed.US
) -> CallToolResult:
    """
    Returns the latest trade for one or more crypto symbols.

    Args:
        symbol (Union[str, List[str]]): Crypto symbol(s) (e.g., 'BTC/USD' or ['BTC/USD','ETH/USD'])
        feed (CryptoFeed): The crypto data feed (default: US)

    Returns:
        str: Formatted string containing latest trade(s) or error message
    """
    _ensure_clients()
    tool_name = "get_crypto_latest_trade"
    symbols_list = symbol if isinstance(symbol, list) else [symbol]
    try:
        request_params = CryptoLatestTradeRequest(symbol_or_symbols=symbol)
        latest = crypto_historical_data_client.get_crypto_latest_trade(request_params, feed=feed)
        mapping_latest_trades = getattr(latest, "data", None) or latest
        trades_by_symbol: Dict[str, Any] = {}
        found = 0
        for sym in symbols_list:
            trade = mapping_latest_trades.get(sym) if hasattr(mapping_latest_trades, "get") else None
            trades_by_symbol[sym] = to_serializable(trade) if trade else None
            if trade:
                found += 1
        payload = {
            "tool": tool_name,
            "request": {"symbols": symbols_list, "feed": to_serializable(feed)},
            "counts": {"symbols": len(symbols_list), "records": found},
            "trades": trades_by_symbol,
        }
        return build_success_result(
            tool_name,
            payload,
            summary=f"{tool_name}: ok symbols={len(symbols_list)} found={found}",
            content_text=compact_json(payload),
        )
    except Exception as e:
        return build_error_result(
            tool_name,
            "internal_error",
            "Failed to retrieve latest crypto trade.",
            details={"symbols": symbols_list, "original_error": str(e)},
        )


@mcp.tool(
    annotations={
        "title": "Get Crypto Snapshot",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
async def get_crypto_snapshot(
    symbol: Union[str, List[str]],
    feed: CryptoFeed = CryptoFeed.US
) -> CallToolResult:
    """
    Returns a snapshot for one or more crypto symbols including latest trade, quote,
    minute bar, daily bar, and previous daily bar.

    Args:
        symbol (Union[str, List[str]]): Crypto symbol(s) (e.g., 'BTC/USD' or ['BTC/USD', 'ETH/USD'])
        feed (CryptoFeed): Data feed source (default: US)

    Returns:
        str: Snapshot with latest quote, trade, and OHLCV bars for each symbol
    """
    _ensure_clients()
    tool_name = "get_crypto_snapshot"
    symbols_list = symbol if isinstance(symbol, list) else [symbol]
    try:
        request_params = CryptoSnapshotRequest(symbol_or_symbols=symbol)
        snapshots = crypto_historical_data_client.get_crypto_snapshot(request_params, feed=feed)
        mapping_snapshots = getattr(snapshots, "data", None) or snapshots
        snapshots_by_symbol: Dict[str, Any] = {}
        found = 0
        for sym in symbols_list:
            snap = mapping_snapshots.get(sym) if hasattr(mapping_snapshots, "get") else None
            snapshots_by_symbol[sym] = to_serializable(snap) if snap else None
            if snap:
                found += 1
        payload = {
            "tool": tool_name,
            "request": {"symbols": symbols_list, "feed": to_serializable(feed)},
            "counts": {"symbols": len(symbols_list), "records": found},
            "snapshots": snapshots_by_symbol,
        }
        return build_success_result(
            tool_name,
            payload,
            summary=f"{tool_name}: ok symbols={len(symbols_list)} found={found}",
            content_text=compact_json(payload),
        )
    except APIError as api_error:
        return build_error_result(
            tool_name,
            "api_error",
            "Failed to retrieve crypto snapshots.",
            details={"original_error": str(api_error)},
        )
    except Exception as e:
        return build_error_result(
            tool_name,
            "internal_error",
            "Failed to retrieve crypto snapshots.",
            details={"original_error": str(e)},
        )


@mcp.tool(
    annotations={
        "title": "Get Crypto Orderbook",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
async def get_crypto_latest_orderbook(
    symbol: Union[str, List[str]],
    feed: CryptoFeed = CryptoFeed.US
) -> CallToolResult:
    """
    Returns the latest orderbook for one or more crypto symbols.

    Args:
        symbol (Union[str, List[str]]): Crypto symbol(s) (e.g., 'BTC/USD' or ['BTC/USD','ETH/USD'])
        feed (CryptoFeed): The crypto data feed (default: US)

    Returns:
        str: Formatted string containing latest orderbook(s) or error message
    """
    _ensure_clients()
    tool_name = "get_crypto_latest_orderbook"
    symbols_list = symbol if isinstance(symbol, list) else [symbol]
    try:
        request_params = CryptoLatestOrderbookRequest(symbol_or_symbols=symbol)
        books = crypto_historical_data_client.get_crypto_latest_orderbook(request_params, feed=feed)
        mapping_books = getattr(books, "data", None) or books
        orderbooks_by_symbol: Dict[str, Any] = {}
        found = 0
        for sym in symbols_list:
            orderbook = mapping_books.get(sym) if hasattr(mapping_books, "get") else None
            orderbooks_by_symbol[sym] = to_serializable(orderbook) if orderbook else None
            if orderbook:
                found += 1
        payload = {
            "tool": tool_name,
            "request": {"symbols": symbols_list, "feed": to_serializable(feed)},
            "counts": {"symbols": len(symbols_list), "records": found},
            "orderbooks": orderbooks_by_symbol,
        }
        return build_success_result(
            tool_name,
            payload,
            summary=f"{tool_name}: ok symbols={len(symbols_list)} found={found}",
            content_text=compact_json(payload),
        )
    except Exception as e:
        return build_error_result(
            tool_name,
            "internal_error",
            "Failed to retrieve latest crypto orderbook.",
            details={"symbols": symbols_list, "original_error": str(e)},
        )

# ============================================================================
# Options Market Data Tools
# ============================================================================

@mcp.tool(
    annotations={
        "title": "Get Option Contracts",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
async def get_option_contracts(
    underlying_symbols: Union[str, List[str]],
    expiration_date: Optional[date] = None,
    expiration_date_gte: Optional[date] = None,
    expiration_date_lte: Optional[date] = None,
    expiration_expression: Optional[str] = None,
    strike_price_gte: Optional[str] = None,
    strike_price_lte: Optional[str] = None,
    contract_type: Optional[str] = None,
    status: Optional[AssetStatus] = None,
    root_symbol: Optional[str] = None,
    limit: Optional[int] = None
) -> CallToolResult:
    """
    Retrieves option contracts for underlying symbol(s).

    Args:
        underlying_symbols (Union[str, List[str]]): Underlying asset symbol(s)
        expiration_date (Optional[date]): Specific expiration date
        expiration_date_gte (Optional[date]): Minimum expiration date
        expiration_date_lte (Optional[date]): Maximum expiration date
        expiration_expression (Optional[str]): Natural language
        strike_price_gte (Optional[str]): Minimum strike price
        strike_price_lte (Optional[str]): Maximum strike price
        contract_type (Optional[str]): Filter by 'call' or 'put'
        status (Optional[AssetStatus]): Filter by status
        root_symbol (Optional[str]): Filter by root symbol
        limit (Optional[int]): Maximum number of contracts to return

    Returns:
        str: List of option contracts with symbol, strike, expiration, type, and status
    """

    _ensure_clients()
    tool_name = "get_option_contracts"
    try:
        symbols_list = [underlying_symbols] if isinstance(underlying_symbols, str) else list(underlying_symbols)
        if not symbols_list:
            return build_error_result(tool_name, "missing_symbols", "No symbols provided.", field="underlying_symbols")

        contract_type_enum = None
        if contract_type and isinstance(contract_type, str):
            type_lower = contract_type.lower()
            if type_lower == "call":
                contract_type_enum = ContractType.CALL
            elif type_lower == "put":
                contract_type_enum = ContractType.PUT

        if expiration_expression:
            parsed = _parse_expiration_expression(expiration_expression)
            if parsed.get("error"):
                return build_error_result(
                    tool_name,
                    "invalid_expiration_expression",
                    parsed["error"],
                    field="expiration_expression",
                )
            if "expiration_date" in parsed:
                expiration_date = parsed["expiration_date"]
            elif "expiration_date_gte" in parsed:
                expiration_date_gte = parsed["expiration_date_gte"]
                expiration_date_lte = parsed["expiration_date_lte"]

        request = GetOptionContractsRequest(
            underlying_symbols=symbols_list,
            expiration_date=expiration_date,
            expiration_date_gte=expiration_date_gte,
            expiration_date_lte=expiration_date_lte,
            strike_price_gte=strike_price_gte,
            strike_price_lte=strike_price_lte,
            type=contract_type_enum,
            status=status,
            root_symbol=root_symbol,
            limit=limit,
        )
        response = trade_client.get_option_contracts(request)
        contracts = (response.option_contracts if response and response.option_contracts else [])
        payload = {
            "tool": tool_name,
            "request": {
                "underlying_symbols": symbols_list,
                "expiration_date": to_serializable(expiration_date),
                "expiration_date_gte": to_serializable(expiration_date_gte),
                "expiration_date_lte": to_serializable(expiration_date_lte),
                "expiration_expression": expiration_expression,
                "strike_price_gte": strike_price_gte,
                "strike_price_lte": strike_price_lte,
                "contract_type": contract_type,
                "status": to_serializable(status),
                "root_symbol": root_symbol,
                "limit": limit,
            },
            "counts": {"symbols": len(symbols_list), "records": len(contracts)},
            "contracts": [to_serializable(c) for c in contracts],
        }
        return build_success_result(
            tool_name,
            payload,
            summary=f"{tool_name}: ok symbols={len(symbols_list)} records={len(contracts)}",
            content_text=compact_json(payload),
        )
    except Exception as e:
        return build_error_result(
            tool_name,
            "internal_error",
            "Failed to retrieve option contracts.",
            details={"original_error": str(e)},
        )

@mcp.tool(
    annotations={
        "title": "Get Option Latest Quote",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
async def get_option_latest_quote(
    symbol_or_symbols: Union[str, List[str]],
    feed: Optional[OptionsFeed] = OptionsFeed.INDICATIVE
) -> CallToolResult:
    """
    Retrieves and formats the latest quote for one or more option contracts. This endpoint returns real-time
    pricing and market data, including bid/ask prices, sizes, and exchange information.
    
    Args:
        symbol_or_symbols (Union[str, List[str]]): Option contract symbol(s) (e.g., 'AAPL230616C00150000' or ['AAPL230616C00150000', 'MSFT230616P00300000'])
        feed (Optional[OptionsFeed]): Data feed source (OptionsFeed.OPRA or OptionsFeed.INDICATIVE)
            Default: OptionsFeed.OPRA if the user has the options subscription, OptionsFeed.INDICATIVE otherwise
    
    Returns:
        str: Formatted string containing the latest quote information including:
            - Ask Price, Ask Size, Bid Price, Bid Size, Ask Exchange, Bid Exchange, Trade Conditions, Tape Information, Timestamp (in UTC)
    
    Note:
        This endpoint returns real-time market data. For contract specifications and static data,
        use get_option_contracts instead.
    """
    _ensure_clients()
    tool_name = "get_option_latest_quote"
    symbols_list = [symbol_or_symbols] if isinstance(symbol_or_symbols, str) else list(symbol_or_symbols)
    if not symbols_list:
        return build_error_result(tool_name, "missing_symbols", "No symbols provided.", field="symbol_or_symbols")
    try:
        request = OptionLatestQuoteRequest(symbol_or_symbols=symbol_or_symbols, feed=feed)
        quotes = option_historical_data_client.get_option_latest_quote(request)
        quotes_by_symbol: Dict[str, Any] = {}
        found = 0
        for sym in symbols_list:
            quote = quotes.get(sym) if hasattr(quotes, "get") else None
            quotes_by_symbol[sym] = to_serializable(quote) if quote else None
            if quote:
                found += 1
        payload = {
            "tool": tool_name,
            "request": {"symbols": symbols_list, "feed": to_serializable(feed)},
            "counts": {"symbols": len(symbols_list), "records": found},
            "quotes": quotes_by_symbol,
        }
        return build_success_result(
            tool_name,
            payload,
            summary=f"{tool_name}: ok symbols={len(symbols_list)} found={found}",
            content_text=compact_json(payload),
        )
    except Exception as e:
        return build_error_result(
            tool_name,
            "internal_error",
            "Failed to fetch option latest quote.",
            details={"symbols": symbols_list, "original_error": str(e)},
        )


@mcp.tool(
    annotations={
        "title": "Get Option Snapshot",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
async def get_option_snapshot(
    symbol_or_symbols: Union[str, List[str]], 
    feed: Optional[OptionsFeed] = OptionsFeed.INDICATIVE
) -> CallToolResult:
    """
    Retrieves comprehensive snapshots of option contracts including latest trade, quote,
    implied volatility, and Greeks.

    Args:
        symbol_or_symbols (Union[str, List[str]]): Option symbol(s)
        feed (Optional[OptionsFeed]): Data feed source (OPRA or INDICATIVE)

    Returns:
        str: Snapshot with quote, trade, implied volatility, and Greeks for each contract
    """
    _ensure_clients()
    tool_name = "get_option_snapshot"
    symbols = [symbol_or_symbols] if isinstance(symbol_or_symbols, str) else list(symbol_or_symbols)
    try:
        request = OptionSnapshotRequest(symbol_or_symbols=symbol_or_symbols, feed=feed)
        snapshots = option_historical_data_client.get_option_snapshot(request)
        snapshots_by_symbol: Dict[str, Any] = {}
        found = 0
        for sym in symbols:
            snapshot = snapshots.get(sym) if hasattr(snapshots, "get") else None
            snapshots_by_symbol[sym] = to_serializable(snapshot) if snapshot else None
            if snapshot:
                found += 1

        payload = {
            "tool": tool_name,
            "request": {"symbols": symbols, "feed": to_serializable(feed)},
            "counts": {"symbols": len(symbols), "records": found},
            "snapshots": snapshots_by_symbol,
        }
        return build_success_result(
            tool_name,
            payload,
            summary=f"{tool_name}: ok symbols={len(symbols)} found={found}",
            content_text=compact_json(payload),
        )
    except Exception as e:
        return build_error_result(
            tool_name,
            "internal_error",
            "Failed to retrieve option snapshots.",
            details={"symbols": symbols, "original_error": str(e)},
        )


@mcp.tool(
    annotations={
        "title": "Get Option Chain",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
async def get_option_chain(
    underlying_symbol: str,
    feed: Optional[OptionsFeed] = OptionsFeed.INDICATIVE,
    contract_type: Optional[str] = None,
    strike_price_gte: Optional[float] = None,
    strike_price_lte: Optional[float] = None,
    expiration_date: Optional[Union[date, str]] = None,
    expiration_date_gte: Optional[Union[date, str]] = None,
    expiration_date_lte: Optional[Union[date, str]] = None,
    root_symbol: Optional[str] = None,
    limit: Optional[int] = None
) -> CallToolResult:
    """
    Retrieves option chain data for an underlying symbol, including latest trade, quote,
    implied volatility, and greeks for each contract.

    Args:
        underlying_symbol (str): The underlying symbol
        feed (Optional[OptionsFeed]): Data feed source (OPRA or INDICATIVE)
        contract_type (Optional[str]): Filter by contract type ('call', 'put', or None for both)
        strike_price_gte (Optional[float]): Minimum strike price filter
        strike_price_lte (Optional[float]): Maximum strike price filter
        expiration_date (Optional[Union[date, str]]): Exact expiration date (YYYY-MM-DD)
        expiration_date_gte (Optional[Union[date, str]]): Minimum expiration date
        expiration_date_lte (Optional[Union[date, str]]): Maximum expiration date
        root_symbol (Optional[str]): Filter by root symbol
        limit (Optional[int]): Max snapshots to return (1-1000)

    Returns:
        str: Option chain with quote, trade, IV, and greeks for each contract
    """
    _ensure_clients()
    tool_name = "get_option_chain"
    try:
        contract_type_enum = None
        if contract_type and isinstance(contract_type, str):
            type_lower = contract_type.lower()
            if type_lower == "call":
                contract_type_enum = ContractType.CALL
            elif type_lower == "put":
                contract_type_enum = ContractType.PUT

        request = OptionChainRequest(
            underlying_symbol=underlying_symbol,
            feed=feed,
            type=contract_type_enum,
            strike_price_gte=strike_price_gte,
            strike_price_lte=strike_price_lte,
            expiration_date=expiration_date,
            expiration_date_gte=expiration_date_gte,
            expiration_date_lte=expiration_date_lte,
            root_symbol=root_symbol,
            limit=limit,
        )
        chain = option_historical_data_client.get_option_chain(request)
        mapping_chain = getattr(chain, "data", None) or chain or {}
        chain_payload = {sym: to_serializable(snapshot) for sym, snapshot in mapping_chain.items()}
        payload = {
            "tool": tool_name,
            "request": {
                "underlying_symbol": underlying_symbol,
                "feed": to_serializable(feed),
                "contract_type": contract_type,
                "strike_price_gte": strike_price_gte,
                "strike_price_lte": strike_price_lte,
                "expiration_date": to_serializable(expiration_date),
                "expiration_date_gte": to_serializable(expiration_date_gte),
                "expiration_date_lte": to_serializable(expiration_date_lte),
                "root_symbol": root_symbol,
                "limit": limit,
            },
            "counts": {"records": len(chain_payload)},
            "chain": chain_payload,
        }
        return build_success_result(
            tool_name,
            payload,
            summary=f"{tool_name}: ok contracts={len(chain_payload)}",
            content_text=compact_json(payload),
        )
    except Exception as e:
        return build_error_result(
            tool_name,
            "internal_error",
            "Failed to retrieve option chain.",
            details={"underlying_symbol": underlying_symbol, "original_error": str(e)},
        )

# ============================================================================
# Server Entry Point and CLI
# ============================================================================

def parse_arguments() -> argparse.Namespace:
    """Parse command-line arguments for the Alpaca's MCP Server."""
    p = argparse.ArgumentParser(
        "Alpaca's MCP Server",
        description="MCP server for Alpaca's Trading API integration"
    )
    p.add_argument(
        "--transport",
        choices=["stdio", "streamable-http"],
        default="stdio",
        help="Transport protocol to use (default: stdio)"
    )
    p.add_argument(
        "--host",
        default=os.environ.get("HOST", "127.0.0.1"),
        help="Host to bind to for HTTP transport (default: 127.0.0.1 for security)"
    )
    p.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("PORT", 8000)),
        help="Port to bind to for HTTP transport (default: 8000)"
    )
    p.add_argument(
        "--allowed-hosts",
        default=os.environ.get("ALLOWED_HOSTS", ""),
        help="Comma-separated list of allowed Host header values for DNS rebinding protection. "
             "Required for cloud deployments (e.g., 'example.onrender.com,api.example.com')"
    )
    return p.parse_args()


class AlpacaMCPServer:
    """
    Alpaca's MCP Server implementation.
    
    This server exposes Alpaca's Trading API functionality through the Model Context Protocol,
    allowing AI assistants to interact with trading accounts, market data, and order management.
    
    Authentication is handled via environment variables (ALPACA_API_KEY, ALPACA_SECRET_KEY).
    """
    
    def __init__(self, config_file: Optional[Path] = None) -> None:
        """
        Initialize the Alpaca's MCP Server.
        
        Args:
            config_file: Optional path to a custom .env configuration file.
                        Note: Config file support is maintained for compatibility but
                        generally not needed as environment variables are loaded at startup.
        """
        # Note: Environment variables are already loaded at module initialization.
        # This __init__ is kept simple to avoid global state mutation antipatterns.
        pass

    def run(
        self,
        transport: str = "stdio",
        host: str = "127.0.0.1",
        port: int = 8000,
        allowed_hosts: str = ""
    ) -> None:
        """Run the Alpaca's MCP Server.
        
        Use stdio (default) for local, or streamable-http with --allowed-hosts for cloud.
        """
        if transport == "streamable-http":
            # Configure FastMCP settings for HTTP transport
            mcp.settings.host = host
            mcp.settings.port = port
            
            # Configure transport security for DNS rebinding protection
            from mcp.server.transport_security import TransportSecuritySettings
            
            if allowed_hosts:
                # Option 2: Enable protection with specific allowed hosts (RECOMMENDED)
                # Parse comma-separated host list
                hosts_list = [h.strip() for h in allowed_hosts.split(",") if h.strip()]
                
                # For each host, add both the bare hostname and wildcard port version
                # This handles both "Host: example.com" and "Host: example.com:8000"
                all_allowed_hosts = []
                for h in hosts_list:
                    if ":" not in h:
                        # Add both bare hostname and wildcard pattern
                        all_allowed_hosts.append(h)        # Matches "example.com"
                        all_allowed_hosts.append(f"{h}:*") # Matches "example.com:8000"
                    else:
                        # Already has port or is a pattern, add as-is
                        all_allowed_hosts.append(h)
                
                # Always include localhost variants for local testing
                all_allowed_hosts.extend([
                    "127.0.0.1", "127.0.0.1:*",
                    "localhost", "localhost:*",
                    "[::1]", "[::1]:*"
                ])
                
                # Generate allowed origins for CORS (both http and https)
                allowed_origins = (
                    [f"https://{h}" for h in hosts_list] +
                    [f"http://{h}" for h in hosts_list] +
                    ["http://127.0.0.1:*", "http://localhost:*"]
                )
                
                mcp.settings.transport_security = TransportSecuritySettings(
                    enable_dns_rebinding_protection=True,
                    allowed_hosts=all_allowed_hosts,
                    allowed_origins=allowed_origins
                )
                
                print(f"DNS protection enabled: {', '.join(hosts_list)}", file=sys.stderr)
                
            else:
                print("DNS protection: localhost only", file=sys.stderr)
            
            # Start the server with streamable HTTP transport
            mcp.run(transport="streamable-http")
            
        else:
            # Use stdio transport (default)
            mcp.run(transport="stdio")


if __name__ == "__main__":
    args = parse_arguments()
    try:
        AlpacaMCPServer().run(
            transport=args.transport,
            host=args.host,
            port=args.port,
            allowed_hosts=args.allowed_hosts
        )
    except Exception as e:
        print(f"Error starting server: {e}", file=sys.stderr)
        sys.exit(1)
