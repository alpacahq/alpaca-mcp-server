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
from alpaca.data.enums import DataFeed, MarketType, MostActivesBy, OptionsFeed, CorporateActionsType, CryptoFeed
from alpaca.data.historical.option import OptionHistoricalDataClient
from alpaca.data.historical.screener import ScreenerClient
from alpaca.data.historical.stock import StockHistoricalDataClient
from alpaca.data.historical.corporate_actions import CorporateActionsClient
from alpaca.data.historical.crypto import CryptoHistoricalDataClient
from alpaca.data.live.stock import StockDataStream
from alpaca.data.requests import (
    MarketMoversRequest,
    MostActivesRequest,
    OptionBarsRequest,
    OptionLatestQuoteRequest,
    OptionLatestTradeRequest,
    OptionSnapshotRequest,
    OptionTradesRequest,
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
    DTBPCheck,
    OrderClass,
    OrderSide,
    OrderType,
    PDTCheck,
    QueryOrderStatus,
    TimeInForce,
    TradeConfirmationEmail,
)
from alpaca.trading.models import AccountConfiguration, Order
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
    ReplaceOrderRequest,
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
    class ScreenerClientSigned(UserAgentMixin, ScreenerClient): pass
except ImportError:
    # Fallback to unsigned clients if mixin not available
    TradingClientSigned = TradingClient
    StockHistoricalDataClientSigned = StockHistoricalDataClient
    OptionHistoricalDataClientSigned = OptionHistoricalDataClient
    CorporateActionsClientSigned = CorporateActionsClient
    CryptoHistoricalDataClientSigned = CryptoHistoricalDataClient
    ScreenerClientSigned = ScreenerClient

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
screener_client = None

def _ensure_clients():
    """
    Initialize Alpaca's Trading API clients on first use.
    Uses API key/secret pair from environment variables.
    """
    global _clients_initialized, trade_client, stock_historical_data_client, stock_data_stream_client
    global option_historical_data_client, corporate_actions_client, crypto_historical_data_client
    global screener_client

    if not _clients_initialized:
        trade_client = TradingClientSigned(TRADE_API_KEY, TRADE_API_SECRET, paper=ALPACA_PAPER_TRADE_BOOL)
        stock_historical_data_client = StockHistoricalDataClientSigned(TRADE_API_KEY, TRADE_API_SECRET)
        stock_data_stream_client = StockDataStream(TRADE_API_KEY, TRADE_API_SECRET, url_override=STREAM_DATA_WSS)
        option_historical_data_client = OptionHistoricalDataClientSigned(api_key=TRADE_API_KEY, secret_key=TRADE_API_SECRET)
        corporate_actions_client = CorporateActionsClientSigned(api_key=TRADE_API_KEY, secret_key=TRADE_API_SECRET)
        crypto_historical_data_client = CryptoHistoricalDataClientSigned(api_key=TRADE_API_KEY, secret_key=TRADE_API_SECRET)
        screener_client = ScreenerClientSigned(api_key=TRADE_API_KEY, secret_key=TRADE_API_SECRET)
        _clients_initialized = True

# ============================================================================
# Account and Positions Tools
# ============================================================================

@mcp.tool(
    annotations={
        "title": "Get Account Info",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
async def get_account_info() -> str:
    """
    Retrieves and formats the current account information including balances and status.

    Returns:
        str: Compact JSON account payload with ID, status, buying power, cash, equity, and PDT status
    """
    _ensure_clients()
    account = trade_client.get_account()
    return compact_json(account)

@mcp.tool(
    annotations={
        "title": "Get Account Configuration",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
async def get_account_config() -> CallToolResult:
    """
    Retrieves the current account configuration settings, including trading restrictions,
    margin settings, PDT checks, and options trading level.

    Returns:
        CallToolResult: Account configuration with all current settings in both
        human-readable text and structured content.
    """
    _ensure_clients()
    tool_name = "get_account_config"
    try:
        config = trade_client.get_account_configurations()
        payload = {
            "tool": tool_name,
            "config": to_serializable(config),
        }
        return build_success_result(
            tool_name,
            payload,
            summary=f"{tool_name}: ok",
            content_text=compact_json(payload),
        )
    except Exception as e:
        return build_error_result(tool_name, "internal_error", "Failed to fetch account configuration.", details={"original_error": str(e)})

@mcp.tool(
    annotations={
        "title": "Update Account Configuration",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": True
    }
)
async def update_account_config(
    fractional_trading: Optional[bool] = None,
    no_shorting: Optional[bool] = None,
    suspend_trade: Optional[bool] = None,
    max_margin_multiplier: Optional[str] = None,
    dtbp_check: Optional[str] = None,
    pdt_check: Optional[str] = None,
    trade_confirm_email: Optional[str] = None,
    ptp_no_exception_entry: Optional[bool] = None,
    max_options_trading_level: Optional[int] = None
) -> CallToolResult:
    """
    Updates one or more account configuration settings. Only the fields you provide
    will be changed; all others retain their current values.

    Args:
        fractional_trading (Optional[bool]): Enable or disable fractional share trading
        no_shorting (Optional[bool]): If True, account is set to long-only mode
        suspend_trade (Optional[bool]): If True, account cannot submit new orders
        max_margin_multiplier (Optional[str]): Margin multiplier between "1" and "4"
        dtbp_check (Optional[str]): Day Trade Buying Power check timing: "both", "entry", or "exit"
        pdt_check (Optional[str]): Pattern Day Trader check timing: "both", "entry", or "exit"
        trade_confirm_email (Optional[str]): Trade confirmation emails: "all" or "none"
        ptp_no_exception_entry (Optional[bool]): If True, accept orders for PTP symbols without exception
        max_options_trading_level (Optional[int]): Options level: 0=disabled, 1=Covered/CSP, 2=Long, 3=Spreads

    Returns:
        CallToolResult: Updated account configuration in both human-readable and structured form.
    """
    _ensure_clients()
    tool_name = "update_account_config"
    provided = [v for v in [
        fractional_trading, no_shorting, suspend_trade, max_margin_multiplier,
        dtbp_check, pdt_check, trade_confirm_email, ptp_no_exception_entry,
        max_options_trading_level
    ] if v is not None]
    if not provided:
        return build_error_result(tool_name, "no_fields", "At least one configuration field must be provided to update.")

    try:
        dtbp_check_enum = None
        if dtbp_check is not None:
            try:
                dtbp_check_enum = DTBPCheck(dtbp_check.lower())
            except ValueError:
                return build_error_result(tool_name, "invalid_dtbp_check", f"Must be one of: both, entry, exit.", field="dtbp_check", details={"provided": dtbp_check})

        pdt_check_enum = None
        if pdt_check is not None:
            try:
                pdt_check_enum = PDTCheck(pdt_check.lower())
            except ValueError:
                return build_error_result(tool_name, "invalid_pdt_check", f"Must be one of: both, entry, exit.", field="pdt_check", details={"provided": pdt_check})

        trade_confirm_enum = None
        if trade_confirm_email is not None:
            try:
                trade_confirm_enum = TradeConfirmationEmail(trade_confirm_email.lower())
            except ValueError:
                return build_error_result(tool_name, "invalid_trade_confirm_email", "Must be one of: all, none.", field="trade_confirm_email", details={"provided": trade_confirm_email})

        if max_options_trading_level is not None and max_options_trading_level not in range(4):
            return build_error_result(tool_name, "invalid_max_options_trading_level", "Must be 0, 1, 2, or 3.", field="max_options_trading_level", details={"provided": max_options_trading_level})

        if max_margin_multiplier is not None and max_margin_multiplier not in {"1", "2", "3", "4"}:
            return build_error_result(tool_name, "invalid_max_margin_multiplier", "Must be '1', '2', '3', or '4'.", field="max_margin_multiplier", details={"provided": max_margin_multiplier})

        current = trade_client.get_account_configurations()
        updated = AccountConfiguration(
            dtbp_check=dtbp_check_enum if dtbp_check_enum is not None else current.dtbp_check,
            fractional_trading=fractional_trading if fractional_trading is not None else current.fractional_trading,
            max_margin_multiplier=max_margin_multiplier if max_margin_multiplier is not None else current.max_margin_multiplier,
            no_shorting=no_shorting if no_shorting is not None else current.no_shorting,
            pdt_check=pdt_check_enum if pdt_check_enum is not None else current.pdt_check,
            suspend_trade=suspend_trade if suspend_trade is not None else current.suspend_trade,
            trade_confirm_email=trade_confirm_enum if trade_confirm_enum is not None else current.trade_confirm_email,
            ptp_no_exception_entry=ptp_no_exception_entry if ptp_no_exception_entry is not None else current.ptp_no_exception_entry,
            max_options_trading_level=max_options_trading_level if max_options_trading_level is not None else current.max_options_trading_level,
        )
        result = trade_client.set_account_configurations(updated)
        payload = {
            "tool": tool_name,
            "request": {
                "fractional_trading": fractional_trading,
                "no_shorting": no_shorting,
                "suspend_trade": suspend_trade,
                "max_margin_multiplier": max_margin_multiplier,
                "dtbp_check": dtbp_check,
                "pdt_check": pdt_check,
                "trade_confirm_email": trade_confirm_email,
                "ptp_no_exception_entry": ptp_no_exception_entry,
                "max_options_trading_level": max_options_trading_level,
            },
            "config": to_serializable(result),
        }
        return build_success_result(
            tool_name,
            payload,
            summary=f"{tool_name}: ok",
            content_text=compact_json(payload),
        )
    except Exception as e:
        return build_error_result(tool_name, "internal_error", "Failed to update account configuration.", details={"original_error": str(e)})

@mcp.tool(
    annotations={
        "title": "Get All Positions",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
async def get_all_positions() -> str:
    """
    Retrieves all current positions in the portfolio as JSON.

    Returns:
        str: JSON array of position objects with symbol, qty, side, avg_entry_price,
             current_price, market_value, cost_basis, unrealized_pl, unrealized_plpc,
             change_today fields.
    """
    _ensure_clients()
    positions = trade_client.get_all_positions()

    if not positions:
        return "No open positions found."

    result = []
    for position in positions:
        result.append({
            "symbol": position.symbol,
            "qty": str(position.qty),
            "side": position.side.value if hasattr(position.side, "value") else str(position.side),
            "avg_entry_price": str(position.avg_entry_price),
            "current_price": str(position.current_price),
            "market_value": str(position.market_value),
            "cost_basis": str(position.cost_basis),
            "unrealized_pl": str(position.unrealized_pl),
            "unrealized_plpc": str(position.unrealized_plpc),
            "change_today": str(getattr(position, "change_today", "0")),
        })
    return json.dumps(result)

@mcp.tool(
    annotations={
        "title": "Get Open Position",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
async def get_open_position(symbol: str) -> str:
    """
    Retrieves and formats details for a specific open position.
    
    Args:
        symbol (str): The symbol name of the asset to get position for (e.g., 'AAPL', 'MSFT')
    
    Returns:
        str: Compact JSON position payload with the position details or an error message
    """
    _ensure_clients()
    try:
        position = trade_client.get_open_position(symbol)
        return compact_json(to_serializable(position))
    except Exception as e:
        return compact_json({"error": {"code": "get_open_position_failed", "message": str(e), "symbol": symbol}})

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
        return compact_json({"error": {"code": "get_asset_failed", "message": str(e), "symbol": symbol}})

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
        return compact_json(
            {
                "request": {
                    "status": status,
                    "asset_class": asset_class,
                    "exchange": exchange,
                    "attributes": attributes,
                },
                "error": {"code": "get_all_assets_failed", "message": str(e)},
            }
        )

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
        return compact_json(
            {
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
                "error": {"code": "get_corporate_actions_failed", "message": str(e)},
            }
        )

# ============================================================================
# Portfolio History Tool
# ============================================================================

@mcp.tool(
    annotations={
        "title": "Get Portfolio History",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
async def get_portfolio_history(
    timeframe: Optional[str] = None,
    period: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    date_end: Optional[str] = None,
    intraday_reporting: Optional[str] = None,
    pnl_reset: Optional[str] = None,
    extended_hours: Optional[bool] = None,
    cashflow_types: Optional[List[str]] = None,
) -> str:
    """
    Retrieves account portfolio history (equity and P/L) over a requested time window.

    Args:
        timeframe (Optional[str]): Resolution of each data point.
        period (Optional[str]): Window length.
        start (Optional[str]): Start time in ISO (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS).
        end (Optional[str]): End time in ISO (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS).
        date_end (Optional[str]): End date (alternative to end) as ISO date or datetime.
        intraday_reporting (Optional[str]): "market_hours", "extended_hours", or "continuous".
        pnl_reset (Optional[str]): P/L reset behavior (e.g., "daily", "weekly", "no_reset").
        extended_hours (Optional[bool]): Include extended hours where applicable.
        cashflow_types (Optional[List[str]]): Optional cashflow categories to include.

    Returns:
        str: JSON string with keys: timestamp, equity, profit_loss, profit_loss_pct, base_value, timeframe, and optional cashflow.
    """
    _ensure_clients()

    # Parse optional datetime inputs with explicit errors (for consistency with other tools)
    try:
        start_dt = _parse_iso_datetime(start) if start else None
    except ValueError:
        return f"Invalid start timestamp: {start}. Use ISO like '2023-01-01' or '2023-01-01T09:30:00'"
    try:
        end_dt = _parse_iso_datetime(end) if end else None
    except ValueError:
        return f"Invalid end timestamp: {end}. Use ISO like '2023-01-01' or '2023-01-01T16:00:00'"
    try:
        date_end_dt = _parse_iso_datetime(date_end) if date_end else None
    except ValueError:
        return f"Invalid date_end: {date_end}. Use ISO like '2023-01-31' or '2023-01-31T00:00:00'"

    request = GetPortfolioHistoryRequest(
        period=period,
        timeframe=timeframe,
        intraday_reporting=intraday_reporting,
        start=start_dt,
        end=end_dt,
        date_end=date_end_dt,
        pnl_reset=pnl_reset,
        extended_hours=extended_hours,
        cashflow_types=cashflow_types,
    )

    try:
        resp = trade_client.get_portfolio_history(request)

        payload = {
            "timestamp": getattr(resp, "timestamp", []) or [],
            "equity": getattr(resp, "equity", []) or [],
            "profit_loss": getattr(resp, "profit_loss", []) or [],
            "profit_loss_pct": getattr(resp, "profit_loss_pct", []) or [],
            "base_value": getattr(resp, "base_value", None),
            "timeframe": getattr(resp, "timeframe", timeframe or ""),
        }

        cf = getattr(resp, "cashflow", None)
        if cf is not None:
            payload["cashflow"] = cf

        if timeframe and period in {"2M", "3M", "6M", "1Y", "all"} and timeframe != "1D":
            payload["note"] = "For period > 30 days, timeframe should be '1D'."

        return json.dumps(payload, separators=(",", ":"))
    except Exception as e:
        return f"Error fetching portfolio history: {str(e)}"

# ============================================================================
# Watchlist Management Tools
# ============================================================================

@mcp.tool(
    annotations={
        "title": "Create Watchlist",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True
    }
)
async def create_watchlist(name: str, symbols: List[str]) -> str:
    """
    Creates a new watchlist with specified symbols.
    
    Args:
        name (str): Name of the watchlist
        symbols (List[str]): List of symbols to include in the watchlist
    
    Returns:
        str: Confirmation message with watchlist creation status
    """
    _ensure_clients()
    try:
        watchlist_data = CreateWatchlistRequest(name=name, symbols=symbols)
        watchlist = trade_client.create_watchlist(watchlist_data)
        return f"Watchlist '{name}' created successfully with {len(symbols)} symbols."
    except Exception as e:
        return f"Error creating watchlist: {str(e)}"

@mcp.tool(
    annotations={
        "title": "Get Watchlists",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
async def get_watchlists() -> str:
    """
    Get all watchlists for the account.

    Returns:
        str: Compact JSON list of watchlists with name, ID, and timestamps
    """
    _ensure_clients()
    try:
        watchlists = trade_client.get_watchlists()
        return compact_json([to_serializable(wl) for wl in (watchlists or [])])
    except Exception as e:
        return compact_json({"error": {"code": "get_watchlists_failed", "message": str(e)}})

@mcp.tool(
    annotations={
        "title": "Update Watchlist",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": True
    }
)
async def update_watchlist_by_id(watchlist_id: str, name: str = None, symbols: List[str] = None) -> str:
    """
    Update an existing watchlist.

    Args:
        watchlist_id (str): The UUID of the watchlist to update
        name (str): New name for the watchlist
        symbols (List[str]): New list of symbols for the watchlist

    Returns:
        str: Confirmation message with updated watchlist name
    """
    _ensure_clients()
    try:
        update_request = UpdateWatchlistRequest(name=name, symbols=symbols)
        watchlist = trade_client.update_watchlist_by_id(watchlist_id, update_request)
        return f"Watchlist updated successfully: {watchlist.name}"
    except Exception as e:
        return f"Error updating watchlist: {str(e)}"

@mcp.tool(
    annotations={
        "title": "Get Watchlist by ID",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
async def get_watchlist_by_id(watchlist_id: str) -> str:
    """
    Get a specific watchlist by its ID.

    Args:
        watchlist_id (str): The UUID of the watchlist

    Returns:
        str: Compact JSON watchlist payload with name, ID, and timestamps, and symbols
    """
    _ensure_clients()
    try:
        wl = trade_client.get_watchlist_by_id(watchlist_id)
        return compact_json(to_serializable(wl))
    except Exception as e:
        return compact_json(
            {"error": {"code": "get_watchlist_by_id_failed", "message": str(e), "watchlist_id": watchlist_id}}
        )

@mcp.tool(
    annotations={
        "title": "Add Asset to Watchlist",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True
    }
)
async def add_asset_to_watchlist_by_id(watchlist_id: str, symbol: str) -> str:
    """
    Add an asset by symbol to a specific watchlist.

    Args:
        watchlist_id (str): The UUID of the watchlist
        symbol (str): The asset symbol to add (e.g., 'AAPL')

    Returns:
        str: Confirmation with updated watchlist symbols
    """
    _ensure_clients()
    try:
        wl = trade_client.add_asset_to_watchlist_by_id(watchlist_id, symbol)
        symbols_str = ", ".join([a.symbol for a in (getattr(wl, 'assets', []) or [])])
        return f"Added {symbol} to watchlist '{wl.name}'. Symbols: {symbols_str}"
    except Exception as e:
        return f"Error adding asset to watchlist: {str(e)}"

@mcp.tool(
    annotations={
        "title": "Remove Asset from Watchlist",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
async def remove_asset_from_watchlist_by_id(watchlist_id: str, symbol: str) -> str:
    """
    Remove an asset by symbol from a specific watchlist.

    Args:
        watchlist_id (str): The UUID of the watchlist
        symbol (str): The asset symbol to remove (e.g., 'AAPL')

    Returns:
        str: Confirmation with updated watchlist symbols
    """
    _ensure_clients()
    try:
        wl = trade_client.remove_asset_from_watchlist_by_id(watchlist_id, symbol)
        symbols_str = ", ".join([a.symbol for a in (getattr(wl, 'assets', []) or [])])
        return f"Removed {symbol} from watchlist '{wl.name}'. Symbols: {symbols_str}"
    except Exception as e:
        return f"Error removing asset from watchlist: {str(e)}"

@mcp.tool(
    annotations={
        "title": "Delete Watchlist",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
async def delete_watchlist_by_id(watchlist_id: str) -> str:
    """
    Delete a specific watchlist by its ID.

    Args:
        watchlist_id (str): The UUID of the watchlist to delete

    Returns:
        str: Confirmation message on successful deletion
    """
    _ensure_clients()
    try:
        trade_client.delete_watchlist_by_id(watchlist_id)
        return "Watchlist deleted successfully."
    except Exception as e:
        return f"Error deleting watchlist: {str(e)}"

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
        return compact_json(
            {
                "request": {"start_date": start_date, "end_date": end_date},
                "error": {"code": "get_calendar_failed", "message": str(e)},
            }
        )

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
        return compact_json({"error": {"code": "get_clock_failed", "message": str(e)}})

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
    feed: Optional[DataFeed] = None,
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
        CallToolResult: Result object containing historical price data with timestamps and OHLCV data,
        including both human-readable text output and structured content.
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
    feed: Optional[DataFeed] = None,
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
        CallToolResult: Tool result where `content` contains a human-readable
        summary (or error text) and `structuredContent` contains quote data,
        metadata, or structured error details for programmatic use.
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
            end_time = None

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
    feed: Optional[DataFeed] = None,
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
            end_time = None

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
    feed: Optional[DataFeed] = None,
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
    feed: Optional[DataFeed] = None,    
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
    feed: Optional[DataFeed] = None,
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
    feed: Optional[DataFeed] = None,
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
    if not symbols:
        return build_error_result(
            tool_name,
            "missing_symbols",
            "At least one stock symbol must be provided.",
            field="symbol_or_symbols",
            details={"symbols": symbols},
        )
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

@mcp.tool(
    annotations={
        "title": "Get Stock Screener",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
async def get_stock_screener(
    screener_type: str,
    by: Optional[str] = None,
    market_type: Optional[str] = None,
    top: Optional[int] = None
) -> CallToolResult:
    """
    Screens the market for most active stocks or biggest movers.

    Args:
        screener_type (str): Type of screen to run:
            - "most_actives": Top stocks by trading volume or number of trades
            - "market_movers": Top gaining and losing stocks or crypto
        by (Optional[str]): For most_actives only — ranking metric: "volume" (default) or "trades"
        market_type (Optional[str]): For market_movers only — market to screen: "stocks" (default) or "crypto"
        top (Optional[int]): Number of results to return (default determined by API)

    Returns:
        CallToolResult: Screener results with symbol, price, and change data in both
        human-readable text and structured content.
    """
    _ensure_clients()
    tool_name = "get_stock_screener"
    try:
        if screener_type == "most_actives":
            try:
                by_enum = MostActivesBy(by.lower()) if by else MostActivesBy.VOLUME
            except ValueError:
                return build_error_result(tool_name, "invalid_by", "Must be 'volume' or 'trades'.", field="by", details={"provided": by})
            request_kwargs: dict = {"by": by_enum}
            if top is not None:
                request_kwargs["top"] = top
            response = screener_client.get_most_actives(MostActivesRequest(**request_kwargs))
            items = [to_serializable(s) for s in response.most_actives]
            payload = {
                "tool": tool_name,
                "request": {"screener_type": screener_type, "by": by_enum.value, "top": top},
                "counts": {"records": len(items)},
                "most_actives": items,
            }
            return build_success_result(
                tool_name,
                payload,
                summary=f"{tool_name}: ok screener_type=most_actives records={len(items)}",
                content_text=compact_json(payload),
            )

        elif screener_type == "market_movers":
            try:
                mt_enum = MarketType(market_type.lower()) if market_type else MarketType.STOCKS
            except ValueError:
                return build_error_result(tool_name, "invalid_market_type", "Must be 'stocks' or 'crypto'.", field="market_type", details={"provided": market_type})
            request_kwargs = {"market_type": mt_enum}
            if top is not None:
                request_kwargs["top"] = top
            response = screener_client.get_market_movers(MarketMoversRequest(**request_kwargs))
            gainers = [to_serializable(s) for s in response.gainers]
            losers = [to_serializable(s) for s in response.losers]
            payload = {
                "tool": tool_name,
                "request": {"screener_type": screener_type, "market_type": mt_enum.value, "top": top},
                "counts": {"gainers": len(gainers), "losers": len(losers)},
                "gainers": gainers,
                "losers": losers,
            }
            return build_success_result(
                tool_name,
                payload,
                summary=f"{tool_name}: ok screener_type=market_movers gainers={len(gainers)} losers={len(losers)}",
                content_text=compact_json(payload),
            )

        else:
            return build_error_result(tool_name, "invalid_screener_type", "Must be 'most_actives' or 'market_movers'.", field="screener_type", details={"provided": screener_type})

    except Exception as e:
        return build_error_result(tool_name, "internal_error", "Failed to run stock screener.", details={"screener_type": screener_type, "original_error": str(e)})

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
    feed: Optional[OptionsFeed] = None
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
        "title": "Get Option Bars",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
async def get_option_bars(
    symbol_or_symbols: Union[str, List[str]],
    timeframe: str = "1Day",
    start: Optional[str] = None,
    end: Optional[str] = None,
    limit: Optional[int] = None,
    sort: Optional[Sort] = Sort.ASC
) -> CallToolResult:
    """
    Retrieves historical bar (OHLCV) data for one or more option contracts.

    Args:
        symbol_or_symbols (Union[str, List[str]]): Option contract symbol(s) (e.g., 'AAPL250613P00205000')
        timeframe (str): Bar timeframe. Supports flexible formats:
            - Minutes: "1Min" to "59Min", e.g., "5Min", "15Min"
            - Hours: "1Hour" to "23Hour", e.g., "1Hour", "4Hour"
            - Days: "1Day"
            - Weeks: "1Week"
            - Months: "1Month", "2Month", etc.
            (default: "1Day")
        start (Optional[str]): Start time in ISO format (e.g., "2024-01-01" or "2024-01-01T09:30:00")
        end (Optional[str]): End time in ISO format. Defaults to now.
        limit (Optional[int]): Maximum number of bars to return per symbol
        sort (Optional[Sort]): Chronological order of response (ASC or DESC, default: ASC)

    Returns:
        CallToolResult: OHLCV bar data for each symbol in both human-readable and structured form.
    """
    _ensure_clients()
    tool_name = "get_option_bars"
    symbols_list = [symbol_or_symbols] if isinstance(symbol_or_symbols, str) else list(symbol_or_symbols)
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

        start_dt = None
        end_dt = None
        if start:
            try:
                start_dt = _parse_iso_datetime(start)
            except ValueError as e:
                return build_error_result(tool_name, "invalid_start", str(e), field="start")
        if end:
            try:
                end_dt = _parse_iso_datetime(end)
            except ValueError as e:
                return build_error_result(tool_name, "invalid_end", str(e), field="end")

        request = OptionBarsRequest(
            symbol_or_symbols=symbol_or_symbols,
            timeframe=timeframe_obj,
            start=start_dt,
            end=end_dt,
            limit=limit,
            sort=sort
        )
        bars_data = option_historical_data_client.get_option_bars(request)

        bars_by_symbol: Dict[str, List[Dict[str, Any]]] = {}
        counts: Dict[str, int] = {}
        total_records = 0
        for sym in symbols_list:
            sym_bars = bars_data.get(sym) if hasattr(bars_data, "get") else []
            sym_serialized = [to_serializable(bar) for bar in (sym_bars or [])]
            bars_by_symbol[sym] = sym_serialized
            counts[sym] = len(sym_serialized)
            total_records += len(sym_serialized)

        payload = {
            "tool": tool_name,
            "request": {
                "symbols": symbols_list,
                "timeframe": timeframe,
                "start": start,
                "end": end,
                "limit": limit,
                "sort": to_serializable(sort),
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
        return build_error_result(tool_name, "internal_error", "Failed to fetch option bars.", details={"symbols": symbols_list, "original_error": str(e)})

@mcp.tool(
    annotations={
        "title": "Get Option Trades",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
async def get_option_trades(
    symbol_or_symbols: Union[str, List[str]],
    start: Optional[str] = None,
    end: Optional[str] = None,
    limit: Optional[int] = None,
    sort: Optional[Sort] = Sort.ASC
) -> CallToolResult:
    """
    Retrieves historical trade data for one or more option contracts.

    Args:
        symbol_or_symbols (Union[str, List[str]]): Option contract symbol(s) (e.g., 'AAPL250613P00205000')
        start (Optional[str]): Start time in ISO format (e.g., "2024-01-01" or "2024-01-01T09:30:00")
        end (Optional[str]): End time in ISO format. Defaults to now.
        limit (Optional[int]): Maximum number of trades to return per symbol
        sort (Optional[Sort]): Chronological order of response (ASC or DESC, default: ASC)

    Returns:
        CallToolResult: Trade data with price, size, exchange, and timestamp for each symbol
        in both human-readable and structured form.
    """
    _ensure_clients()
    tool_name = "get_option_trades"
    symbols_list = [symbol_or_symbols] if isinstance(symbol_or_symbols, str) else list(symbol_or_symbols)
    try:
        start_dt = None
        end_dt = None
        if start:
            try:
                start_dt = _parse_iso_datetime(start)
            except ValueError as e:
                return build_error_result(tool_name, "invalid_start", str(e), field="start")
        if end:
            try:
                end_dt = _parse_iso_datetime(end)
            except ValueError as e:
                return build_error_result(tool_name, "invalid_end", str(e), field="end")

        request = OptionTradesRequest(
            symbol_or_symbols=symbol_or_symbols,
            start=start_dt,
            end=end_dt,
            limit=limit,
            sort=sort
        )
        trades_data = option_historical_data_client.get_option_trades(request)

        trades_by_symbol: Dict[str, List[Dict[str, Any]]] = {}
        counts: Dict[str, int] = {}
        total_records = 0
        for sym in symbols_list:
            sym_trades = trades_data.get(sym) if hasattr(trades_data, "get") else []
            sym_serialized = [to_serializable(t) for t in (sym_trades or [])]
            trades_by_symbol[sym] = sym_serialized
            counts[sym] = len(sym_serialized)
            total_records += len(sym_serialized)

        payload = {
            "tool": tool_name,
            "request": {
                "symbols": symbols_list,
                "start": start,
                "end": end,
                "limit": limit,
                "sort": to_serializable(sort),
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
        return build_error_result(tool_name, "internal_error", "Failed to fetch option trades.", details={"symbols": symbols_list, "original_error": str(e)})

@mcp.tool(
    annotations={
        "title": "Get Option Latest Trade",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
async def get_option_latest_trade(
    symbol_or_symbols: Union[str, List[str]],
    feed: Optional[OptionsFeed] = None
) -> CallToolResult:
    """
    Retrieves the latest trade for one or more option contracts.

    Args:
        symbol_or_symbols (Union[str, List[str]]): Option contract symbol(s) (e.g., 'AAPL250613P00205000')
        feed (Optional[OptionsFeed]): Data feed source (OptionsFeed.OPRA or OptionsFeed.INDICATIVE).
            Default: OPRA if the user has the options subscription, INDICATIVE otherwise.

    Returns:
        CallToolResult: Latest trade data including price, size, exchange, and timestamp for each symbol
        in both human-readable and structured form.
    """
    _ensure_clients()
    tool_name = "get_option_latest_trade"
    symbols_list = [symbol_or_symbols] if isinstance(symbol_or_symbols, str) else list(symbol_or_symbols)
    try:
        request = OptionLatestTradeRequest(
            symbol_or_symbols=symbol_or_symbols,
            feed=feed
        )
        trades = option_historical_data_client.get_option_latest_trade(request)

        trades_by_symbol: Dict[str, Any] = {}
        found = 0
        for sym in symbols_list:
            trade = trades.get(sym) if hasattr(trades, "get") else None
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
            summary=f"{tool_name}: ok symbols={len(symbols_list)} records={found}",
            content_text=compact_json(payload),
        )
    except Exception as e:
        return build_error_result(tool_name, "internal_error", "Failed to fetch option latest trades.", details={"symbols": symbols_list, "original_error": str(e)})

@mcp.tool(
    annotations={
        "title": "Get Option Exchange Codes",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
async def get_option_exchange_codes() -> CallToolResult:
    """
    Retrieves the mapping of exchange codes to exchange names for option market data.
    Useful for interpreting exchange fields returned by other option data tools.

    Returns:
        CallToolResult: Exchange code to name mapping in both human-readable and structured form.
    """
    _ensure_clients()
    tool_name = "get_option_exchange_codes"
    try:
        exchange_codes = option_historical_data_client.get_option_exchange_codes()

        if not exchange_codes:
            return build_error_result(tool_name, "no_data", "No exchange codes found.")

        payload = {
            "tool": tool_name,
            "counts": {"exchanges": len(exchange_codes)},
            "exchange_codes": dict(sorted(exchange_codes.items())),
        }
        return build_success_result(
            tool_name,
            payload,
            summary=f"{tool_name}: ok exchanges={len(exchange_codes)}",
            content_text=compact_json(payload),
        )
    except Exception as e:
        return build_error_result(tool_name, "internal_error", "Failed to fetch option exchange codes.", details={"original_error": str(e)})


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
    feed: Optional[OptionsFeed] = None
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
    feed: Optional[OptionsFeed] = None,
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
# Order Management Tools
# ============================================================================

@mcp.tool(
    annotations={
        "title": "Get Orders",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
async def get_orders(
    status: str = "all", 
    limit: int = 10,
    after: Optional[str] = None,
    until: Optional[str] = None,
    direction: Optional[str] = None,
    nested: Optional[bool] = None,
    side: Optional[str] = None,
    symbols: Optional[List[str]] = None
) -> str:
    """
    Retrieves and formats orders with the specified filters.

    Args:
        status (str): Order status filter (open, closed, all)
        limit (int): Max orders to return (default: 10, max: 500)
        after (Optional[str]): Orders after this timestamp (ISO format)
        until (Optional[str]): Orders until this timestamp (ISO format)
        direction (Optional[str]): Sort order (asc or desc)
        nested (Optional[bool]): Roll up multi-leg orders under legs field
        side (Optional[str]): Filter by side (buy or sell)
        symbols (Optional[List[str]]): Filter by symbols

    Returns:
        str: Order details with symbol, type, side, quantity, status, and fill info
    """
    _ensure_clients()
    try:
        # Convert status string to enum
        if status.lower() == "open":
            query_status = QueryOrderStatus.OPEN
        elif status.lower() == "closed":
            query_status = QueryOrderStatus.CLOSED
        else:
            query_status = QueryOrderStatus.ALL
        
        # Convert direction string to enum if provided
        direction_enum = None
        if direction:
            if direction.lower() == "asc":
                direction_enum = Sort.ASC
            elif direction.lower() == "desc":
                direction_enum = Sort.DESC
            else:
                return f"Invalid direction: {direction}. Must be 'asc' or 'desc'."
        
        # Convert side string to enum if provided
        side_enum = None
        if side:
            if side.lower() == "buy":
                side_enum = OrderSide.BUY
            elif side.lower() == "sell":
                side_enum = OrderSide.SELL
            else:
                return f"Invalid side: {side}. Must be 'buy' or 'sell'."
        
        # Parse datetime strings if provided
        after_dt = None
        until_dt = None
        if after:
            try:
                after_dt = _parse_iso_datetime(after)
            except ValueError:
                return f"Invalid 'after' timestamp format: {after}. Use ISO format like '2023-01-01T09:30:00'"
        if until:
            try:
                until_dt = _parse_iso_datetime(until)
            except ValueError:
                return f"Invalid 'until' timestamp format: {until}. Use ISO format like '2023-01-01T16:00:00'"
            
        request_params = GetOrdersRequest(
            status=query_status,
            limit=limit,
            after=after_dt,
            until=until_dt,
            direction=direction_enum,
            nested=nested,
            side=side_enum,
            symbols=symbols
        )
        
        orders = trade_client.get_orders(request_params)
        
        payload = {
            "request": {
                "status": status,
                "limit": limit,
                "after": after,
                "until": until,
                "direction": direction,
                "nested": nested,
                "side": side,
                "symbols": symbols,
            },
            "orders": [to_serializable(order) for order in orders],
        }
        return compact_json(payload)
    except Exception as e:
        return compact_json(
            {
                "request": {
                    "status": status,
                    "limit": limit,
                    "after": after,
                    "until": until,
                    "direction": direction,
                    "nested": nested,
                    "side": side,
                    "symbols": symbols,
                },
                "error": {"code": "get_orders_failed", "message": str(e)},
            }
        )

@mcp.tool(
    annotations={
        "title": "Place Stock Order",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": True
    }
)
async def place_stock_order(
    symbol: str,
    side: str,
    quantity: float,
    type: str = "market",
    time_in_force: Union[str, TimeInForce] = "day",
    order_class: Union[str, OrderClass] = None,
    limit_price: Optional[float] = None,
    stop_price: Optional[float] = None,
    trail_price: Optional[float] = None,
    trail_percent: Optional[float] = None,
    extended_hours: bool = False,
    client_order_id: Optional[str] = None,
    take_profit_price: Optional[float] = None,
    stop_loss_price: Optional[float] = None,
) -> str:
    """
    Places a stock order using the specified order type and parameters.

    Args:
        symbol (str): Stock ticker symbol
        side (str): Order side ('buy' or 'sell')
        quantity (float): Number of shares to trade
        type (str): Order type ('market', 'limit', 'stop', 'stop_limit', 'trailing_stop')
        time_in_force (Union[str, TimeInForce]): Time in force ('day', 'gtc', 'opg', 'cls', 'ioc', 'fok' or TimeInForce enum)
        order_class (Union[str, OrderClass]): Order class ('simple', 'bracket', 'oco', 'oto' or OrderClass enum)
        limit_price (Optional[float]): Limit price (required for LIMIT, STOP_LIMIT)
        stop_price (Optional[float]): Stop price (required for STOP, STOP_LIMIT)
        trail_price (Optional[float]): Trail price (for TRAILING_STOP)
        trail_percent (Optional[float]): Trail percent (for TRAILING_STOP)
        extended_hours (bool): Allow extended hours execution
        client_order_id (Optional[str]): Custom order identifier
        take_profit_price (Optional[float]): Take-profit limit price (for bracket orders)
        stop_loss_price (Optional[float]): Stop-loss stop price (for bracket orders)

    Returns:
        str: Compact JSON order payload or a concise error string
    """
    _ensure_clients()
    try:
        # Validate side
        if side.lower() == "buy":
            order_side = OrderSide.BUY
        elif side.lower() == "sell":
            order_side = OrderSide.SELL
        else:
            return f"Invalid order side: {side}. Must be 'buy' or 'sell'."

        # Validate and convert time_in_force to enum
        if isinstance(time_in_force, TimeInForce):
            tif_enum = time_in_force
        else:
            try:
                tif_enum = TimeInForce[time_in_force.upper()]
            except (KeyError, AttributeError):
                return f"Invalid time_in_force: {time_in_force}. Valid options are: day, gtc, opg, cls, ioc, fok"

        # Convert order_class to enum (let API validate)
        if order_class is None:
            order_class_enum = None
        elif isinstance(order_class, OrderClass):
            order_class_enum = order_class
        else:
            try:
                order_class_enum = OrderClass[order_class.upper()]
            except (KeyError, AttributeError):
                order_class_enum = None

        # Convert order type string to lowercase for comparison
        order_type_lower = type.lower()

        # Build bracket legs if provided
        take_profit_req = TakeProfitRequest(limit_price=take_profit_price) if take_profit_price is not None else None
        stop_loss_req = StopLossRequest(stop_price=stop_loss_price) if stop_loss_price is not None else None

        # Create order based on type
        if order_type_lower == "market":
            order_data = MarketOrderRequest(
                symbol=symbol,
                qty=quantity,
                side=order_side,
                type=OrderType.MARKET,
                time_in_force=tif_enum,
                order_class=order_class_enum,
                extended_hours=extended_hours,
                client_order_id=client_order_id or f"order_{uuid.uuid4().hex[:16]}",
                take_profit=take_profit_req,
                stop_loss=stop_loss_req,
            )
        elif order_type_lower == "limit":
            if limit_price is None:
                return "limit_price is required for LIMIT orders."
            order_data = LimitOrderRequest(
                symbol=symbol,
                qty=quantity,
                side=order_side,
                type=OrderType.LIMIT,
                time_in_force=tif_enum,
                order_class=order_class_enum,
                limit_price=limit_price,
                extended_hours=extended_hours,
                client_order_id=client_order_id or f"order_{uuid.uuid4().hex[:16]}",
                take_profit=take_profit_req,
                stop_loss=stop_loss_req,
            )
        elif order_type_lower == "stop":
            if stop_price is None:
                return "stop_price is required for STOP orders."
            order_data = StopOrderRequest(
                symbol=symbol,
                qty=quantity,
                side=order_side,
                type=OrderType.STOP,
                time_in_force=tif_enum,
                order_class=order_class_enum,
                stop_price=stop_price,
                extended_hours=extended_hours,
                client_order_id=client_order_id or f"order_{uuid.uuid4().hex[:16]}"
            )
        elif order_type_lower == "stop_limit":
            if stop_price is None or limit_price is None:
                return "Both stop_price and limit_price are required for STOP_LIMIT orders."
            order_data = StopLimitOrderRequest(
                symbol=symbol,
                qty=quantity,
                side=order_side,
                type=OrderType.STOP_LIMIT,
                time_in_force=tif_enum,
                order_class=order_class_enum,
                stop_price=stop_price,
                limit_price=limit_price,
                extended_hours=extended_hours,
                client_order_id=client_order_id or f"order_{uuid.uuid4().hex[:16]}"
            )
        elif order_type_lower == "trailing_stop":
            if trail_price is None and trail_percent is None:
                return "Either trail_price or trail_percent is required for TRAILING_STOP orders."
            order_data = TrailingStopOrderRequest(
                symbol=symbol,
                qty=quantity,
                side=order_side,
                type=OrderType.TRAILING_STOP,
                time_in_force=tif_enum,
                order_class=order_class_enum,
                trail_price=trail_price,
                trail_percent=trail_percent,
                extended_hours=extended_hours,
                client_order_id=client_order_id or f"order_{uuid.uuid4().hex[:16]}"
            )
        else:
            return f"Invalid order type: {type}. Must be one of: MARKET, LIMIT, STOP, STOP_LIMIT, TRAILING_STOP."

        order = trade_client.submit_order(order_data)
        return compact_json(to_serializable(order))
    except Exception as e:
        return f"Error placing order: {str(e)}"

@mcp.tool(
    annotations={
        "title": "Place Crypto Order",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": True
    }
)
async def place_crypto_order(
    symbol: str,
    side: str,
    order_type: str = "market",
    time_in_force: Union[str, TimeInForce] = "gtc",
    qty: Optional[float] = None,
    notional: Optional[float] = None,
    limit_price: Optional[float] = None,
    stop_price: Optional[float] = None,
    client_order_id: Optional[str] = None
) -> str:
    """
    Place a crypto order (market, limit, stop_limit) with GTC/IOC time in force.

    Rules:
    - Market: require exactly one of qty or notional
    - Limit: require qty and limit_price (notional not supported)
    - Stop Limit: require qty, stop_price and limit_price (notional not supported)
    - time_in_force: only GTC or IOC are supported for crypto orders

    Args:
        symbol (str): Crypto symbol
        side (str): Order side ('buy' or 'sell')
        order_type (str): Order type ('market', 'limit', 'stop_limit')
        time_in_force (Union[str, TimeInForce]): Time in force ('GTC' or 'IOC')
        qty (Optional[float]): Quantity to trade
        notional (Optional[float]): Notional value (market orders only)
        limit_price (Optional[float]): Limit price (required for limit/stop_limit)
        stop_price (Optional[float]): Stop price (required for stop_limit)
        client_order_id (Optional[str]): Custom order identifier

    Returns:
        str: Order confirmation with order ID, status, and execution details
    """
    _ensure_clients()
    try:
        # Validate side
        if side.lower() == "buy":
            order_side = OrderSide.BUY
        elif side.lower() == "sell":
            order_side = OrderSide.SELL
        else:
            return f"Invalid order side: {side}. Must be 'buy' or 'sell'."

        # Validate and convert time_in_force to enum, allow only GTC/IOC
        if isinstance(time_in_force, TimeInForce):
            if time_in_force not in (TimeInForce.GTC, TimeInForce.IOC):
                return "Invalid time_in_force for crypto. Use GTC or IOC."
            tif_enum = time_in_force
        elif isinstance(time_in_force, str):
            tif_upper = time_in_force.upper()
            if tif_upper == "GTC":
                tif_enum = TimeInForce.GTC
            elif tif_upper == "IOC":
                tif_enum = TimeInForce.IOC
            else:
                return f"Invalid time_in_force: {time_in_force}. Valid options for crypto are: GTC, IOC"
        else:
            return f"Invalid time_in_force type: {type(time_in_force)}. Must be string or TimeInForce enum."

        order_type_lower = order_type.lower()

        if order_type_lower == "market":
            if (qty is None and notional is None) or (qty is not None and notional is not None):
                return "For MARKET orders, provide exactly one of qty or notional."
            order_data = MarketOrderRequest(
                symbol=symbol,
                qty=qty,
                notional=notional,
                side=order_side,
                type=OrderType.MARKET,
                time_in_force=tif_enum,
                client_order_id=client_order_id or f"crypto_{int(time.time())}"
            )
        elif order_type_lower == "limit":
            if limit_price is None:
                return "limit_price is required for LIMIT orders."
            if qty is None:
                return "qty is required for LIMIT orders."
            if notional is not None:
                return "notional is not supported for LIMIT orders. Use qty instead."
            order_data = LimitOrderRequest(
                symbol=symbol,
                qty=qty,
                side=order_side,
                type=OrderType.LIMIT,
                time_in_force=tif_enum,
                limit_price=limit_price,
                client_order_id=client_order_id or f"crypto_{int(time.time())}"
            )
        elif order_type_lower == "stop_limit":
            if stop_price is None or limit_price is None:
                return "Both stop_price and limit_price are required for STOP_LIMIT orders."
            if qty is None:
                return "qty is required for STOP_LIMIT orders."
            if notional is not None:
                return "notional is not supported for STOP_LIMIT orders. Use qty instead."
            order_data = StopLimitOrderRequest(
                symbol=symbol,
                qty=qty,
                side=order_side,
                type=OrderType.STOP_LIMIT,
                time_in_force=tif_enum,
                stop_price=stop_price,
                limit_price=limit_price,
                client_order_id=client_order_id or f"crypto_{int(time.time())}"
            )
        else:
            return "Invalid order type for crypto. Use: market, limit, stop_limit."

        order = trade_client.submit_order(order_data)
        return compact_json(to_serializable(order))
    except Exception as e:
        return f"Error placing crypto order: {str(e)}"

@mcp.tool(
    annotations={
        "title": "Place Option Order",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": True
    }
)
async def place_option_order(
    legs: List[Dict[str, Any]],
    order_type: str = "market",
    limit_price: Optional[float] = None,
    order_class: Optional[Union[str, OrderClass]] = None,
    quantity: int = 1,
    time_in_force: Union[str, TimeInForce] = "day",
    extended_hours: bool = False
) -> str:
    """
    Places an options order (market or limit) for single or multi-leg strategies.

    Supported order types for options: market, limit
    Time in force: DAY only
    Extended hours: not supported by Alpaca for options (kept for API compatibility)

    Args:
        legs (List[Dict[str, Any]]): List of option legs with symbol, side, ratio_qty
        order_type (str): "market" or "limit"
        limit_price (Optional[float]): Required for limit orders
        order_class (Optional[Union[str, OrderClass]]): simple or mleg
        quantity (int): Base quantity for the order
        time_in_force (Union[str, TimeInForce]): day only
        extended_hours (bool): Not supported for options

    Returns:
        str: Order confirmation with order ID, status, and execution details
    """
    _ensure_clients()
    order_legs: List[OptionLegRequest] = []

    try:
        # Validate inputs
        validation_error = _validate_option_order_inputs(legs, quantity, time_in_force)
        if validation_error:
            return validation_error
        if order_type.lower() not in ["market", "limit"]:
            return "Invalid order_type for options. Use: market, limit."
        if order_type.lower() == "limit" and limit_price is None:
            return "limit_price is required for LIMIT option orders."

        # Convert order class string to enum if needed
        converted_order_class = _convert_order_class_string(order_class)
        if isinstance(converted_order_class, OrderClass):
            order_class = converted_order_class
        elif isinstance(converted_order_class, str):  # Error message returned
            return converted_order_class

        # Convert time_in_force to enum if it's a string
        if isinstance(time_in_force, str):
            time_in_force = TimeInForce.DAY  # Options only support DAY

        # Determine order class if not provided
        if order_class is None:
            order_class = OrderClass.MLEG if len(legs) > 1 else OrderClass.SIMPLE

        # Process legs
        processed_legs = _process_option_legs(legs)
        if isinstance(processed_legs, str):
            return processed_legs
        order_legs = processed_legs

        # Create order request
        order_data = _create_option_order_request(
            order_legs, order_class, quantity, time_in_force, extended_hours, order_type, limit_price
        )
        if isinstance(order_data, str):
            return order_data

        # Submit order
        order = trade_client.submit_order(order_data)

        # Format and return response
        return _format_option_order_response(order, order_class, order_legs)

    except APIError as api_error:
        return _handle_option_api_error(str(api_error), order_legs, order_class)

    except Exception as e:
        return compact_json({"error": {"code": "place_option_order_failed", "message": str(e)}})

# =======================================================================================
# Position Management Tools
# =======================================================================================

@mcp.tool(
    annotations={
        "title": "Cancel All Orders",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
async def cancel_all_orders() -> str:
    """
    Cancel all open orders.
    
    Returns:
        str: Compact JSON cancellation responses
    """
    _ensure_clients()
    try:
        # Cancel all orders
        cancel_responses = trade_client.cancel_orders()
        
        return compact_json(to_serializable(cancel_responses or []))
        
    except Exception as e:
        return compact_json({"error": {"code": "cancel_all_orders_failed", "message": str(e)}})

@mcp.tool(
    annotations={
        "title": "Cancel Order",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
async def cancel_order_by_id(order_id: str) -> str:
    """
    Cancel a specific order by its ID.
    
    Args:
        order_id: The UUID of the order to cancel
        
    Returns:
        str: Compact JSON cancellation response
    """
    _ensure_clients()
    try:
        response = trade_client.cancel_order_by_id(order_id)
        return compact_json(to_serializable(response))
        
    except Exception as e:
        return compact_json({"error": {"code": "cancel_order_by_id_failed", "message": str(e), "order_id": order_id}})

@mcp.tool(
    annotations={
        "title": "Get Order by ID",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
async def get_order_by_id(order_id: str) -> CallToolResult:
    """
    Retrieves a single order by its ID.

    Args:
        order_id (str): The UUID of the order to retrieve

    Returns:
        CallToolResult: Order details including symbol, type, side, quantity, status, and fill info
        in both human-readable and structured form.
    """
    _ensure_clients()
    tool_name = "get_order_by_id"
    try:
        order = trade_client.get_order_by_id(order_id)
        payload = {
            "tool": tool_name,
            "request": {"order_id": order_id},
            "order": to_serializable(order),
        }
        return build_success_result(
            tool_name,
            payload,
            summary=f"{tool_name}: ok order_id={order_id}",
            content_text=compact_json(payload),
        )
    except Exception as e:
        return build_error_result(tool_name, "internal_error", "Failed to retrieve order.", details={"order_id": order_id, "original_error": str(e)})

@mcp.tool(
    annotations={
        "title": "Replace Order",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": True
    }
)
async def replace_order_by_id(
    order_id: str,
    qty: Optional[int] = None,
    time_in_force: Optional[str] = None,
    limit_price: Optional[float] = None,
    stop_price: Optional[float] = None,
    trail: Optional[float] = None,
    client_order_id: Optional[str] = None
) -> CallToolResult:
    """
    Replaces an existing open order with updated parameters. At least one optional
    field must be provided.

    Args:
        order_id (str): The UUID of the order to replace
        qty (Optional[int]): New number of shares
        time_in_force (Optional[str]): New expiration logic (day, gtc, opg, cls, ioc, fok)
        limit_price (Optional[float]): New limit price (required if order type is limit or stop_limit)
        stop_price (Optional[float]): New stop price (required if order type is stop or stop_limit)
        trail (Optional[float]): New trail value in price or percent (for trailing_stop orders only)
        client_order_id (Optional[str]): New client-assigned order identifier

    Returns:
        CallToolResult: Details of the replaced order in both human-readable and structured form.
    """
    _ensure_clients()
    tool_name = "replace_order_by_id"
    if all(v is None for v in [qty, time_in_force, limit_price, stop_price, trail, client_order_id]):
        return build_error_result(tool_name, "no_fields", "At least one field must be provided to replace an order.", details={"accepted_fields": ["qty", "time_in_force", "limit_price", "stop_price", "trail", "client_order_id"]})
    try:
        tif_enum = None
        if time_in_force:
            tif_map = {
                "day": TimeInForce.DAY,
                "gtc": TimeInForce.GTC,
                "opg": TimeInForce.OPG,
                "cls": TimeInForce.CLS,
                "ioc": TimeInForce.IOC,
                "fok": TimeInForce.FOK,
            }
            tif_enum = tif_map.get(time_in_force.lower())
            if tif_enum is None:
                return build_error_result(tool_name, "invalid_time_in_force", "Must be one of: day, gtc, opg, cls, ioc, fok.", field="time_in_force", details={"provided": time_in_force})

        replace_request = ReplaceOrderRequest(
            qty=qty,
            time_in_force=tif_enum,
            limit_price=limit_price,
            stop_price=stop_price,
            trail=trail,
            client_order_id=client_order_id
        )
        order = trade_client.replace_order_by_id(order_id, replace_request)
        payload = {
            "tool": tool_name,
            "request": {
                "order_id": order_id,
                "qty": qty,
                "time_in_force": time_in_force,
                "limit_price": limit_price,
                "stop_price": stop_price,
                "trail": trail,
                "client_order_id": client_order_id,
            },
            "order": to_serializable(order),
        }
        return build_success_result(
            tool_name,
            payload,
            summary=f"{tool_name}: ok order_id={order_id} new_id={order.id}",
            content_text=compact_json(payload),
        )
    except Exception as e:
        return build_error_result(tool_name, "internal_error", "Failed to replace order.", details={"order_id": order_id, "original_error": str(e)})

@mcp.tool(
    annotations={
        "title": "Close Position",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": True
    }
)
async def close_position(symbol: str, qty: Optional[str] = None, percentage: Optional[str] = None) -> str:
    """
    Closes a specific position for a single symbol. 
    This method will throw an error if the position does not exist!
    
    Args:
        symbol (str): The symbol of the position to close
        qty (Optional[str]): Optional number of shares to liquidate
        percentage (Optional[str]): Optional percentage of shares to liquidate (must result in at least 1 share)
    
    Returns:
        str: Compact JSON order payload or a concise error string
    """
    _ensure_clients()
    try:
        # Create close position request if options are provided
        close_options = None
        if qty or percentage:
            close_options = ClosePositionRequest(
                qty=qty,
                percentage=percentage
            )
        
        # Close the position
        order = trade_client.close_position(symbol, close_options)
        
        return compact_json(to_serializable(order))
                
    except APIError as api_error:
        error_message = str(api_error)
        if "42210000" in error_message and "would result in order size of zero" in error_message:
            return compact_json(
                {
                    "error": {
                        "code": "invalid_close_position_request",
                        "message": "percentage results in 0 shares; use a higher percentage, qty, or 100%.",
                        "symbol": symbol,
                        "qty": qty,
                        "percentage": percentage,
                    }
                }
            )
        else:
            return compact_json({"error": {"code": "close_position_failed", "message": error_message}})
            
    except Exception as e:
        return compact_json({"error": {"code": "close_position_failed", "message": str(e)}})
    
@mcp.tool(
    annotations={
        "title": "Close All Positions",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
async def close_all_positions(cancel_orders: bool = False) -> str:
    """
    Closes all open positions.
    
    Args:
        cancel_orders (bool): If True, cancels all open orders before liquidating positions
    
    Returns:
        str: Compact JSON position closure responses
    """
    _ensure_clients()
    try:
        close_responses = trade_client.close_all_positions(cancel_orders=cancel_orders)
        return compact_json(to_serializable(close_responses or []))
        
    except Exception as e:
        return compact_json({"error": {"code": "close_all_positions_failed", "message": str(e)}})

# Position Management Tools (Options)
@mcp.tool(
    annotations={
        "title": "Exercise Option",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
async def exercise_options_position(symbol_or_contract_id: str) -> str:
    """
    Exercises a held option contract, converting it into the underlying asset.
    
    Args:
        symbol_or_contract_id (str): Option contract symbol (e.g., 'NVDA250919C001680') or contract ID
    
    Returns:
        str: Success message or error details
    """
    _ensure_clients()
    try:
        trade_client.exercise_options_position(symbol_or_contract_id=symbol_or_contract_id)
        return f"Successfully submitted exercise request for option contract: {symbol_or_contract_id}"
    except Exception as e:
        return f"Error exercising option contract '{symbol_or_contract_id}': {str(e)}"


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
        allowed_hosts: str = "",
        no_dns_protection: bool = False
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

            if no_dns_protection:
                # Explicitly disable DNS rebinding protection
                # for trusted LAN / self-hosted deployments
                mcp.settings.transport_security = TransportSecuritySettings(
                    enable_dns_rebinding_protection=False
                )
                print("DNS rebinding protection DISABLED", file=sys.stderr)

            elif allowed_hosts:
                # Enable protection with specific allowed hosts (RECOMMENDED)
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
