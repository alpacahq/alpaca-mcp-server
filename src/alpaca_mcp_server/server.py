"""
Alpaca MCP Server - Standalone Implementation

This is a standalone MCP server that provides comprehensive Alpaca Trading API integration
for stocks, options, crypto, portfolio management, and real-time market data.

Supports 38+ tools including:
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
import argparse
from datetime import datetime, timedelta, date
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
    StopOrderRequest,
    TrailingStopOrderRequest,
    UpdateWatchlistRequest,
)


# Import shared helpers
# Try relative import first (works when run as a module)
# Fall back to absolute import if running as a script directly
try:
    from .helpers import (
        parse_timeframe_with_enums,
        _validate_amount,
        _parse_iso_datetime,
        _parse_date_ymd,
        _format_ohlcv_bar,
        _format_quote_data,
        _format_trade_data,
        _parse_expiration_expression,
        _validate_option_order_inputs,
        _convert_order_class_string,
        _process_option_legs,
        _create_option_market_order_request,
        _format_option_order_response,
        _handle_option_api_error,
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
        _format_ohlcv_bar,
        _format_quote_data,
        _format_trade_data,
        _parse_expiration_expression,
        _validate_option_order_inputs,
        _convert_order_class_string,
        _process_option_legs,
        _create_option_market_order_request,
        _format_option_order_response,
        _handle_option_api_error,
    )

from mcp.server.fastmcp import FastMCP
import contextvars

# Context variable to store Authorization header from incoming HTTP requests
# This will be passed along to Alpaca Trading API calls
auth_header_context = contextvars.ContextVar('authorization_header', default=None)

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

def _inject_auth_header(client):
    """
    Inject Authorization header from request context into Alpaca SDK HTTP requests.
    
    Sets the Authorization header on the session's default headers.
    """
    # Check if there's an Authorization header in the request context
    auth_header = auth_header_context.get()
    
    if auth_header and hasattr(client, '_api') and hasattr(client._api, '_session'):
        # Get the underlying requests session and set the Authorization header
        session = client._api._session
        session.headers['Authorization'] = auth_header


def _ensure_clients():
    """
    Initialize Alpaca clients on first use.
    
    Supports two authentication modes:
    1. Authorization header from incoming HTTP request (takes precedence)
    2. API key/secret pair from environment variables (fallback)
    
    When an Authorization header is present in the request context, it will be
    passed along to all Alpaca Trading API calls.
    """
    global _clients_initialized, trade_client, stock_historical_data_client, stock_data_stream_client
    global option_historical_data_client, corporate_actions_client, crypto_historical_data_client
    
    # Check if Authorization header is provided in the request context
    auth_header = auth_header_context.get()
    
    if auth_header:
        # Initialize clients (will use env vars initially, but we'll override with auth header)
        # We need to initialize clients even with dummy credentials because we'll inject the auth header
        if not _clients_initialized or not trade_client:
            trade_client = TradingClientSigned(TRADE_API_KEY or "dummy", TRADE_API_SECRET or "dummy", paper=ALPACA_PAPER_TRADE_BOOL)
            stock_historical_data_client = StockHistoricalDataClientSigned(TRADE_API_KEY or "dummy", TRADE_API_SECRET or "dummy")
            stock_data_stream_client = StockDataStream(TRADE_API_KEY or "dummy", TRADE_API_SECRET or "dummy", url_override=STREAM_DATA_WSS)
            option_historical_data_client = OptionHistoricalDataClientSigned(api_key=TRADE_API_KEY or "dummy", secret_key=TRADE_API_SECRET or "dummy")
            corporate_actions_client = CorporateActionsClientSigned(api_key=TRADE_API_KEY or "dummy", secret_key=TRADE_API_SECRET or "dummy")
            crypto_historical_data_client = CryptoHistoricalDataClientSigned(api_key=TRADE_API_KEY or "dummy", secret_key=TRADE_API_SECRET or "dummy")
        
        # Inject the Authorization header from the incoming request into each client
        _inject_auth_header(trade_client)
        _inject_auth_header(stock_historical_data_client)
        _inject_auth_header(option_historical_data_client)
        _inject_auth_header(corporate_actions_client)
        _inject_auth_header(crypto_historical_data_client)
        
        # For auth header mode, we don't set _clients_initialized to True
        # This ensures we reinject the header on each request
        _clients_initialized = False
    elif not _clients_initialized:
        # Use API key/secret authentication (traditional method)
        trade_client = TradingClientSigned(TRADE_API_KEY, TRADE_API_SECRET, paper=ALPACA_PAPER_TRADE_BOOL)
        stock_historical_data_client = StockHistoricalDataClientSigned(TRADE_API_KEY, TRADE_API_SECRET)
        stock_data_stream_client = StockDataStream(TRADE_API_KEY, TRADE_API_SECRET, url_override=STREAM_DATA_WSS)
        option_historical_data_client = OptionHistoricalDataClientSigned(api_key=TRADE_API_KEY, secret_key=TRADE_API_SECRET)
        corporate_actions_client = CorporateActionsClientSigned(api_key=TRADE_API_KEY, secret_key=TRADE_API_SECRET)
        crypto_historical_data_client = CryptoHistoricalDataClientSigned(api_key=TRADE_API_KEY, secret_key=TRADE_API_SECRET)
        _clients_initialized = True

# ============================================================================
# Account and Positions Tools
# ============================================================================

@mcp.tool()
async def get_account_info() -> str:
    """
    Retrieves and formats the current account information including balances and status.
    
    Returns:
        str: Formatted string containing account details including:
            - Account ID
            - Status
            - Currency
            - Buying Power
            - Cash Balance
            - Portfolio Value
            - Equity
            - Market Values
            - Pattern Day Trader Status
            - Day Trades Remaining
    """
    _ensure_clients()
    account = trade_client.get_account()
    
    info = f"""
            Account Information:
            -------------------
            Account ID: {account.id}
            Status: {account.status}
            Currency: {account.currency}
            Buying Power: ${float(account.buying_power):.2f}
            Cash: ${float(account.cash):.2f}
            Portfolio Value: ${float(account.portfolio_value):.2f}
            Equity: ${float(account.equity):.2f}
            Long Market Value: ${float(account.long_market_value):.2f}
            Short Market Value: ${float(account.short_market_value):.2f}
            Pattern Day Trader: {'Yes' if account.pattern_day_trader else 'No'}
            Day Trades Remaining: {account.daytrade_count if hasattr(account, 'daytrade_count') else 'Unknown'}
            """
    return info

@mcp.tool()
async def get_all_positions() -> str:
    """
    Retrieves and formats all current positions in the portfolio.
    
    Returns:
        str: Formatted string containing details of all open positions including:
            - Symbol
            - Quantity
            - Market Value
            - Average Entry Price
            - Current Price
            - Unrealized P/L
    """
    _ensure_clients()
    positions = trade_client.get_all_positions()
    
    if not positions:
        return "No open positions found."
    
    result = "Current Positions:\n-------------------\n"
    for position in positions:
        result += f"""
                    Symbol: {position.symbol}
                    Quantity: {position.qty} shares
                    Market Value: ${float(position.market_value):.2f}
                    Average Entry Price: ${float(position.avg_entry_price):.2f}
                    Current Price: ${float(position.current_price):.2f}
                    Unrealized P/L: ${float(position.unrealized_pl):.2f} ({float(position.unrealized_plpc) * 100:.2f}%)
                    -------------------
                    """
    return result

@mcp.tool()
async def get_open_position(symbol: str) -> str:
    """
    Retrieves and formats details for a specific open position.
    
    Args:
        symbol (str): The symbol name of the asset to get position for (e.g., 'AAPL', 'MSFT')
    
    Returns:
        str: Formatted string containing the position details or an error message
    """
    _ensure_clients()
    try:
        position = trade_client.get_open_position(symbol)
        
        # Check if it's an options position by looking for the options symbol pattern
        is_option = len(symbol) > 6 and any(c in symbol for c in ['C', 'P'])
        
        # Format quantity based on asset type
        quantity_text = f"{position.qty} contracts" if is_option else f"{position.qty}"

        return f"""
                Position Details for {symbol}:
                ---------------------------
                Quantity: {quantity_text}
                Market Value: ${float(position.market_value):.2f}
                Average Entry Price: ${float(position.avg_entry_price):.2f}
                Current Price: ${float(position.current_price):.2f}
                Unrealized P/L: ${float(position.unrealized_pl):.2f}
                """ 
    except Exception as e:
        return f"Error fetching position: {str(e)}"

# ============================================================================
# Asset Information Tools
# ============================================================================

@mcp.tool()
async def get_asset(symbol: str) -> str:
    """
    Retrieves and formats detailed information about a specific asset.
    
    Args:
        symbol (str): The symbol of the asset to get information for
    
    Returns:
        str: Formatted string containing asset details including:
            - Name
            - Exchange
            - Class
            - Status
            - Trading Properties
    """
    _ensure_clients()
    try:
        asset = trade_client.get_asset(symbol)
        return f"""
                Asset Information for {symbol}:
                ----------------------------
                Name: {asset.name}
                Exchange: {asset.exchange}
                Class: {asset.asset_class}
                Status: {asset.status}
                Tradable: {'Yes' if asset.tradable else 'No'}
                Marginable: {'Yes' if asset.marginable else 'No'}
                Shortable: {'Yes' if asset.shortable else 'No'}
                Easy to Borrow: {'Yes' if asset.easy_to_borrow else 'No'}
                Fractionable: {'Yes' if asset.fractionable else 'No'}
                """
    except Exception as e:
        return f"Error fetching asset information: {str(e)}"

@mcp.tool()
async def get_all_assets(
    status: Optional[str] = None,
    asset_class: Optional[str] = None,
    exchange: Optional[str] = None,
    attributes: Optional[str] = None
) -> str:
    """
    Get all available assets with optional filtering.
    
    Args:
        status: Filter by asset status (e.g., 'active', 'inactive')
        asset_class: Filter by asset class (e.g., 'us_equity', 'crypto')
        exchange: Filter by exchange (e.g., 'NYSE', 'NASDAQ')
        attributes: Comma-separated values to query for multiple attributes
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
        
        if not assets:
            return "No assets found matching the criteria."
        
        # Format the response
        response_parts = ["Available Assets:"]
        response_parts.append("-" * 30)
        
        for asset in assets:
            response_parts.append(f"Symbol: {asset.symbol}")
            response_parts.append(f"Name: {asset.name}")
            response_parts.append(f"Exchange: {asset.exchange}")
            response_parts.append(f"Class: {asset.asset_class}")
            response_parts.append(f"Status: {asset.status}")
            response_parts.append(f"Tradable: {'Yes' if asset.tradable else 'No'}")
            response_parts.append("-" * 30)
        
        return "\n".join(response_parts)
        
    except Exception as e:
        return f"Error fetching assets: {str(e)}"

# ============================================================================
# Corporate Actions Tools
# ============================================================================

@mcp.tool()
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
            Available types from https://alpaca.markets/sdks/python/api_reference/data/enums.html#corporateactionstype:
            - CorporateActionsType.REVERSE_SPLIT: Reverse split
            - CorporateActionsType.FORWARD_SPLIT: Forward split  
            - CorporateActionsType.UNIT_SPLIT: Unit split
            - CorporateActionsType.CASH_DIVIDEND: Cash dividend
            - CorporateActionsType.STOCK_DIVIDEND: Stock dividend
            - CorporateActionsType.SPIN_OFF: Spin off
            - CorporateActionsType.CASH_MERGER: Cash merger
            - CorporateActionsType.STOCK_MERGER: Stock merger
            - CorporateActionsType.STOCK_AND_CASH_MERGER: Stock and cash merger
            - CorporateActionsType.REDEMPTION: Redemption
            - CorporateActionsType.NAME_CHANGE: Name change
            - CorporateActionsType.WORTHLESS_REMOVAL: Worthless removal
            - CorporateActionsType.RIGHTS_DISTRIBUTION: Rights distribution
        start (Optional[date]): Start date for the announcements (default: current day)
        end (Optional[date]): End date for the announcements (default: current day)
        symbols (Optional[List[str]]): Optional list of stock symbols to filter by
        cusips (Optional[List[str]]): Optional list of CUSIPs to filter by
        ids (Optional[List[str]]): Optional list of corporate action IDs (mutually exclusive with other filters)
        limit (Optional[int]): Maximum number of results to return (default: 1000)
        sort (Optional[str]): Sort order (asc or desc, default: asc)
    
    Returns:
        str: Formatted string containing corporate announcement details
        
    References:
        - API Documentation: https://docs.alpaca.markets/reference/corporateactions-1
        - CorporateActionsType Enum: https://alpaca.markets/sdks/python/api_reference/data/enums.html#corporateactionstype
        - CorporateActionsRequest: https://alpaca.markets/sdks/python/api_reference/data/corporate_actions/requests.html#corporateactionsrequest
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
        
        if not announcements or not announcements.data:
            return "No corporate announcements found for the specified criteria."
        
        result = "Corporate Announcements:\n----------------------\n"
        
        # The response.data contains action types as keys (e.g., 'cash_dividends', 'forward_splits')
        # Each value is a list of corporate actions
        for action_type, actions_list in announcements.data.items():
            if not actions_list:
                continue
                
            result += f"\n{action_type.replace('_', ' ').title()}:\n"
            result += "=" * 30 + "\n"
            
            for action in actions_list:
                # Group by symbol for better organization
                symbol = getattr(action, 'symbol', 'Unknown')
                result += f"\nSymbol: {symbol}\n"
                result += "-" * 15 + "\n"
                
                # Display action details based on available attributes
                if hasattr(action, 'corporate_action_type'):
                    result += f"Type: {action.corporate_action_type}\n"
                
                if hasattr(action, 'ex_date') and action.ex_date:
                    result += f"Ex Date: {action.ex_date}\n"
                    
                if hasattr(action, 'record_date') and action.record_date:
                    result += f"Record Date: {action.record_date}\n"
                    
                if hasattr(action, 'payable_date') and action.payable_date:
                    result += f"Payable Date: {action.payable_date}\n"
                    
                if hasattr(action, 'process_date') and action.process_date:
                    result += f"Process Date: {action.process_date}\n"
                
                # Cash dividend specific fields
                if hasattr(action, 'rate') and action.rate:
                    result += f"Rate: ${action.rate:.6f}\n"
                    
                if hasattr(action, 'foreign') and hasattr(action, 'special'):
                    result += f"Foreign: {action.foreign}, Special: {action.special}\n"
                
                # Split specific fields
                if hasattr(action, 'old_rate') and action.old_rate:
                    result += f"Old Rate: {action.old_rate}\n"
                    
                if hasattr(action, 'new_rate') and action.new_rate:
                    result += f"New Rate: {action.new_rate}\n"
                
                # Due bill dates
                if hasattr(action, 'due_bill_on_date') and action.due_bill_on_date:
                    result += f"Due Bill On Date: {action.due_bill_on_date}\n"
                    
                if hasattr(action, 'due_bill_off_date') and action.due_bill_off_date:
                    result += f"Due Bill Off Date: {action.due_bill_off_date}\n"
                
                result += "\n"
        return result
    except Exception as e:
        return f"Error fetching corporate announcements: {str(e)}"

# ============================================================================
# Portfolio History Tool
# ============================================================================

@mcp.tool()
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
        timeframe (Optional[str]): Resolution of each data point (e.g., "1Min", "5Min", "15Min", "1H", "1D").
        period (Optional[str]): Window length (e.g., "1W", "1M", "3M", "6M", "1Y", "all").
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

@mcp.tool()
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

@mcp.tool()
async def get_watchlists() -> str:
    """Get all watchlists for the account."""
    _ensure_clients()
    try:
        watchlists = trade_client.get_watchlists()
        result = "Watchlists:\n------------\n"
        for wl in watchlists:
            result += f"Name: {wl.name}\n"
            result += f"ID: {wl.id}\n"
            result += f"Created: {wl.created_at}\n"
            result += f"Updated: {wl.updated_at}\n\n"
        return result
    except Exception as e:
        return f"Error fetching watchlists: {str(e)}"

@mcp.tool()
async def update_watchlist_by_id(watchlist_id: str, name: str = None, symbols: List[str] = None) -> str:
    """Update an existing watchlist."""
    _ensure_clients()
    try:
        update_request = UpdateWatchlistRequest(name=name, symbols=symbols)
        watchlist = trade_client.update_watchlist_by_id(watchlist_id, update_request)
        return f"Watchlist updated successfully: {watchlist.name}"
    except Exception as e:
        return f"Error updating watchlist: {str(e)}"

@mcp.tool()
async def get_watchlist_by_id(watchlist_id: str) -> str:
    """Get a specific watchlist by its ID."""
    _ensure_clients()
    try:
        wl = trade_client.get_watchlist_by_id(watchlist_id)
        result = "Watchlist:\n----------\n"
        result += f"Name: {wl.name}\n"
        result += f"ID: {wl.id}\n"
        result += f"Created: {wl.created_at}\n"
        result += f"Updated: {wl.updated_at}\n"
        symbols_list = [a.symbol for a in (getattr(wl, 'assets', []) or [])]
        result += f"Symbols: {', '.join(symbols_list)}\n"
        return result
    except Exception as e:
        return f"Error fetching watchlist by id: {str(e)}"

@mcp.tool()
async def add_asset_to_watchlist_by_id(watchlist_id: str, symbol: str) -> str:
    """Add an asset by symbol to a specific watchlist by ID."""
    _ensure_clients()
    try:
        wl = trade_client.add_asset_to_watchlist_by_id(watchlist_id, symbol)
        symbols_str = ", ".join([a.symbol for a in (getattr(wl, 'assets', []) or [])])
        return f"Added {symbol} to watchlist '{wl.name}'. Symbols: {symbols_str}"
    except Exception as e:
        return f"Error adding asset to watchlist: {str(e)}"

@mcp.tool()
async def remove_asset_from_watchlist_by_id(watchlist_id: str, symbol: str) -> str:
    """Remove an asset by symbol from a specific watchlist by ID."""
    _ensure_clients()
    try:
        wl = trade_client.remove_asset_from_watchlist_by_id(watchlist_id, symbol)
        symbols_str = ", ".join([a.symbol for a in (getattr(wl, 'assets', []) or [])])
        return f"Removed {symbol} from watchlist '{wl.name}'. Symbols: {symbols_str}"
    except Exception as e:
        return f"Error removing asset from watchlist: {str(e)}"

@mcp.tool()
async def delete_watchlist_by_id(watchlist_id: str) -> str:
    """Delete a specific watchlist by its ID."""
    _ensure_clients()
    try:
        trade_client.delete_watchlist_by_id(watchlist_id)
        return "Watchlist deleted successfully."
    except Exception as e:
        return f"Error deleting watchlist: {str(e)}"

# ============================================================================
# Market Calendar Tools
# ============================================================================

@mcp.tool()
async def get_calendar(start_date: str, end_date: str) -> str:
    """
    Retrieves and formats market calendar for specified date range.
    
    Args:
        start_date (str): Start date in YYYY-MM-DD format
        end_date (str): End date in YYYY-MM-DD format
    
    Returns:
        str: Formatted string containing market calendar information
    """
    _ensure_clients()
    try:
        # Convert string dates to date objects
        start_dt = _parse_date_ymd(start_date)
        end_dt = _parse_date_ymd(end_date)
        
        # Create the request object with the correct parameters
        calendar_request = GetCalendarRequest(start=start_dt, end=end_dt)
        calendar = trade_client.get_calendar(calendar_request)
        
        result = f"Market Calendar ({start_date} to {end_date}):\n----------------------------\n"
        for day in calendar:
            result += f"Date: {day.date}, Open: {day.open}, Close: {day.close}\n"
        return result
    except Exception as e:
        return f"Error fetching market calendar: {str(e)}"

# ============================================================================
# Market Clock Tools
# ============================================================================

@mcp.tool()
async def get_clock() -> str:
    """
    Retrieves and formats current market status and next open/close times.
    
    Returns:
        str: Formatted string containing:
            - Current Time
            - Market Open Status
            - Next Open Time
            - Next Close Time
    """
    _ensure_clients()
    try:
        clock = trade_client.get_clock()
        return f"""
                Market Status:
                -------------
                Current Time: {clock.timestamp}
                Is Open: {'Yes' if clock.is_open else 'No'}
                Next Open: {clock.next_open}
                Next Close: {clock.next_close}
                """
    except Exception as e:
        return f"Error fetching market clock: {str(e)}"

# ============================================================================
# Stock Market Data Tools
# ============================================================================

@mcp.tool()
async def get_stock_bars(
    symbol: str,
    days: int = 5,
    hours: int = 0,
    minutes: int = 15,
    timeframe: str = "1Day",
    limit: Optional[int] = 1000,
    start: Optional[str] = None,
    end: Optional[str] = None,
    sort: Optional[Sort] = Sort.ASC,
    feed: Optional[DataFeed] = None,
    currency: Optional[SupportedCurrencies] = None,
    asof: Optional[str] = None
) -> str:
    """
    Retrieves and formats historical price bars for a stock with configurable timeframe and time range.
    
    Args:
        symbol (str): Stock ticker symbol (e.g., AAPL, MSFT)
        days (int): Number of days to look back (default: 5, ignored if start is provided)
        hours (int): Number of hours to look back (default: 0, ignored if start is provided)
        minutes (int): Number of minutes to look back (default: 15, ignored if start is provided)
        timeframe (str): Bar timeframe - supports flexible Alpaca formats:
            - Minutes: "1Min" to "59Min" (or "1T" to "59T"), e.g., "5Min", "15Min", "30Min"
            - Hours: "1Hour" to "23Hour" (or "1H" to "23H"), e.g., "1Hour", "4Hour", "6Hour"
            - Days: "1Day" (or "1D")
            - Weeks: "1Week" (or "1W")
            - Months: "1Month", "2Month", "3Month", "4Month", "6Month", or "12Month" (or use "M" suffix)
            (default: "1Day")
        limit (Optional[int]): Maximum number of bars to return (default: 1000)
        start (Optional[str]): Start time in ISO format (e.g., "2023-01-01T09:30:00" or "2023-01-01")
        end (Optional[str]): End time in ISO format (e.g., "2023-01-01T16:00:00" or "2023-01-01")
        sort (Optional[Sort]): Chronological order of response (ASC or DESC)
        feed (Optional[DataFeed]): The stock data feed to retrieve from
        currency (Optional[SupportedCurrencies]): Currency for prices (default: USD)
        asof (Optional[str]): The asof date in YYYY-MM-DD format
    
    Returns:
        str: Formatted string containing historical price data with timestamps, OHLCV data
    """
    _ensure_clients()
    try:
        # Parse timeframe string to TimeFrame object
        timeframe_obj = parse_timeframe_with_enums(timeframe)
        if timeframe_obj is None:
            return f"Error: Invalid timeframe '{timeframe}'. Supported formats: 1Min, 2Min, 5Min, 15Min, 30Min, 1Hour, 2Hour, 4Hour, 1Day, 1Week, 1Month, etc."
        
        # Handle start time: use provided start or calculate from days/hours/minutes
        if start:
            try:
                start_time = _parse_iso_datetime(start)
            except ValueError:
                return f"Error: Invalid start time format '{start}'. Use ISO format like '2023-01-01T09:30:00' or '2023-01-01'"
        else:
            # Calculate start time based on days, hours, or minutes (priority order)
            if days > 0:
                start_time = datetime.now() - timedelta(days=days)
            elif hours > 0:
                start_time = datetime.now() - timedelta(hours=hours)
            else:
                start_time = datetime.now() - timedelta(minutes=minutes)
        
        # Handle end time: use provided end or default to now
        if end:
            try:
                end_time = _parse_iso_datetime(end)
            except ValueError:
                return f"Error: Invalid end time format '{end}'. Use ISO format like '2023-01-01T16:00:00' or '2023-01-01'"
        else:
            end_time = datetime.now()
        
        # Create the request object
        request_params = StockBarsRequest(
            symbol_or_symbols=symbol,
            timeframe=timeframe_obj,
            start=start_time,
            end=end_time,
            limit=limit,
            sort=sort,
            feed=feed,
            currency=currency,
            asof=asof
        )
        
        bars = stock_historical_data_client.get_stock_bars(request_params)
        
        if bars[symbol]:
            time_range = f"{start_time.strftime('%Y-%m-%d %H:%M')} to {end_time.strftime('%Y-%m-%d %H:%M')}"
            result = f"Historical Bars for {symbol} ({timeframe} timeframe, {time_range}):\n"
            result += "---------------------------------------------------\n"
            
            for bar in bars[symbol]:
                # Format timestamp based on timeframe unit
                if timeframe_obj.unit_value in [TimeFrameUnit.Minute, TimeFrameUnit.Hour]:
                    time_str = bar.timestamp.strftime('%Y-%m-%d %H:%M:%S')
                else:
                    time_str = bar.timestamp.date()
                
                result += f"Time: {time_str}, Open: ${bar.open:.2f}, High: ${bar.high:.2f}, Low: ${bar.low:.2f}, Close: ${bar.close:.2f}, Volume: {bar.volume}\n"
            
            return result
        else:
            return f"No bar data found for {symbol} with {timeframe} timeframe in the specified time range."
            
    except APIError as api_error:
        error_message = str(api_error)
        lower = error_message.lower()
        if "subscription" in lower and "sip" in lower and ("recent" in lower or "15" in lower):
            fifteen_ago = datetime.now() - timedelta(minutes=15)
            hint_end = fifteen_ago.strftime('%Y-%m-%dT%H:%M:%S')
            return (
                f"Free-plan limitation: Alpaca REST SIP data is delayed by 15 minutes. "
                f"Your request likely included the most recent 15 minutes. "
                f"Retry with `end` <= {hint_end} (exclude the last 15 minutes), "
                f"use the IEX feed where supported, or upgrade for real-time SIP.\n"
                f"Original error: {error_message}"
            )
        return f"API Error fetching bars for {symbol}: {error_message}"
    except Exception as e:
        return f"Error fetching bars for {symbol}: {str(e)}"

@mcp.tool()
async def get_stock_quotes(
    symbol: str,
    days: int = 1,
    hours: int = 0,
    minutes: int = 15,
    limit: Optional[int] = 1000,
    sort: Optional[Sort] = Sort.ASC,
    feed: Optional[DataFeed] = None,
    currency: Optional[SupportedCurrencies] = None,
    asof: Optional[str] = None
) -> str:
    """
    Retrieves and formats historical quote data (level 1 bid/ask) for a stock.
    
    Args:
        symbol (str): Stock ticker symbol (e.g., 'AAPL', 'MSFT')
        days (int): Number of days to look back (default: 1)
        hours (int): Number of hours to look back (default: 0)
        minutes (int): Number of minutes to look back (default: 15)
        limit (Optional[int]): Upper limit of number of data points to return (default: 1000)
        sort (Optional[Sort]): Chronological order of response (ASC or DESC)
        feed (Optional[DataFeed]): The stock data feed to retrieve from
        currency (Optional[SupportedCurrencies]): Currency for prices (default: USD)
        asof (Optional[str]): The asof date in YYYY-MM-DD format
        
    Returns:
        str: Formatted string containing quote history or an error message
    """
    _ensure_clients()
    try:
        # Calculate start time based on days, hours, or minutes (priority order)
        if days > 0:
            start_time = datetime.now() - timedelta(days=days)
            time_desc = f"Last {days} day{'s' if days > 1 else ''}"
        elif hours > 0:
            start_time = datetime.now() - timedelta(hours=hours)
            time_desc = f"Last {hours} hour{'s' if hours > 1 else ''}"
        else:
            start_time = datetime.now() - timedelta(minutes=minutes)
            time_desc = f"Last {minutes} minute{'s' if minutes > 1 else ''}"
        
        # Create the request object with all available parameters
        request_params = StockQuotesRequest(
            symbol_or_symbols=symbol,
            start=start_time,
            end=datetime.now(),
            limit=limit,
            sort=sort,
            feed=feed,
            currency=currency,
            asof=asof
        )
        
        # Get the quotes
        quotes = stock_historical_data_client.get_stock_quotes(request_params)
        
        if symbol in quotes:
            result = f"Historical Quotes for {symbol} ({time_desc}):\n"
            result += "---------------------------------------------------\n"
            for quote in quotes[symbol]:
                result += f"""
                    Timestamp: {quote.timestamp}
                    Ask Price: ${float(quote.ask_price):.6f}
                    Bid Price: ${float(quote.bid_price):.6f}
                    Ask Size: {quote.ask_size}
                    Bid Size: {quote.bid_size}
                    Ask Exchange: {quote.ask_exchange}
                    Bid Exchange: {quote.bid_exchange}
                    Conditions: {quote.conditions}
                    Tape: {quote.tape}
                    -------------------
                    """
            return result
        else:
            return f"No quote data found for {symbol} in the specified time range."
            
    except APIError as api_error:
        error_message = str(api_error)
        lower = error_message.lower()
        if "subscription" in lower and "sip" in lower and ("recent" in lower or "15" in lower):
            fifteen_ago = datetime.now() - timedelta(minutes=15)
            hint_end = fifteen_ago.strftime('%Y-%m-%dT%H:%M:%S')
            return (
                f"Free-plan limitation: Alpaca REST SIP data is delayed by 15 minutes. "
                f"Your request likely included the most recent 15 minutes. "
                f"Retry with `end` <= {hint_end} (exclude the last 15 minutes), "
                f"use the IEX feed where supported, or upgrade for real-time SIP.\n"
                f"Original error: {error_message}"
            )
        return f"API Error fetching quotes for {symbol}: {error_message}"
    except Exception as e:
        return f"Error fetching quotes for {symbol}: {str(e)}"

@mcp.tool()
async def get_stock_trades(
    symbol: str,
    days: int = 1,
    minutes: int = 15,
    hours: int = 0,
    limit: Optional[int] = 1000,
    sort: Optional[Sort] = Sort.ASC,
    feed: Optional[DataFeed] = None,
    currency: Optional[SupportedCurrencies] = None,
    asof: Optional[str] = None
) -> str:
    """
    Retrieves and formats historical trades for a stock.
    Args:
        symbol (str): Stock ticker symbol (e.g., 'AAPL', 'MSFT')
        days (int): Number of days to look back (default: 1)
        minutes (int): Number of minutes to look back (default: 15)
        limit (Optional[int]): Upper limit of number of data points to return (default: 1000)
        sort (Optional[Sort]): Chronological order of response (ASC or DESC)
        feed (Optional[DataFeed]): The stock data feed to retrieve from
        currency (Optional[SupportedCurrencies]): Currency for prices (default: USD)
        asof (Optional[str]): The asof date in YYYY-MM-DD format
    Returns:
        str: Formatted string containing trade history or an error message
    """
    _ensure_clients()
    try:
        # Calculate start time based on days, hours, or minutes (priority order)
        if days > 0:
            start_time = datetime.now() - timedelta(days=days)
            time_desc = f"Last {days} day{'s' if days > 1 else ''}"
        elif hours > 0:
            start_time = datetime.now() - timedelta(hours=hours)
            time_desc = f"Last {hours} hour{'s' if hours > 1 else ''}"
        else:
            start_time = datetime.now() - timedelta(minutes=minutes)
            time_desc = f"Last {minutes} minute{'s' if minutes > 1 else ''}"
        
        # Create the request object with all available parameters
        request_params = StockTradesRequest(
            symbol_or_symbols=symbol,
            start=start_time,
            end=datetime.now(),
            limit=limit,
            sort=sort,
            feed=feed,
            currency=currency,
            asof=asof
        )
        # Get the trades
        trades = stock_historical_data_client.get_stock_trades(request_params)
        if symbol in trades:
            result = f"Historical Trades for {symbol} ({time_desc}):\n"
            result += "---------------------------------------------------\n"
            for trade in trades[symbol]:
                result += f"""
                    Timestamp: {trade.timestamp}
                    Price: ${float(trade.price):.6f}
                    Size: {trade.size}
                    Exchange: {trade.exchange}
                    ID: {trade.id}
                    Conditions: {trade.conditions}
                    Tape: {trade.tape}
                    -------------------
                    """
            return result
        else:
            return f"No trade data found for {symbol} in the specified time range."
    except APIError as api_error:
        error_message = str(api_error)
        lower = error_message.lower()
        if "subscription" in lower and "sip" in lower and ("recent" in lower or "15" in lower):
            fifteen_ago = datetime.now() - timedelta(minutes=15)
            hint_end = fifteen_ago.strftime('%Y-%m-%dT%H:%M:%S')
            return (
                f"Free-plan limitation: Alpaca REST SIP data is delayed by 15 minutes. "
                f"Your request likely included the most recent 15 minutes. "
                f"Retry with `end` <= {hint_end} (exclude the last 15 minutes), "
                f"use the IEX feed where supported, or upgrade for real-time SIP.\n"
                f"Original error: {error_message}"
            )
        return f"API Error fetching trades for {symbol}: {error_message}"
    except Exception as e:
        return f"Error fetching trades for {symbol}: {str(e)}"

@mcp.tool()
async def get_stock_latest_bar(
    symbol: str,
    feed: Optional[DataFeed] = None,
    currency: Optional[SupportedCurrencies] = None
) -> str:
    """Get the latest minute bar for a stock.
    
    Args:
        symbol: Stock ticker symbol (e.g., 'AAPL', 'MSFT')
        feed: The stock data feed to retrieve from (optional)
        currency: The currency for prices (optional, defaults to USD)
    
    Returns:
        A formatted string containing the latest bar details or an error message
    """
    _ensure_clients()
    try:
        # Create the request object with all available parameters
        request_params = StockLatestBarRequest(
            symbol_or_symbols=symbol,
            feed=feed,
            currency=currency
        )
        
        # Get the latest bar
        latest_bars = stock_historical_data_client.get_stock_latest_bar(request_params)
        
        if symbol in latest_bars:
            bar = latest_bars[symbol]
            return f"""
                Latest Minute Bar for {symbol}:
                ---------------------------
                Time: {bar.timestamp}
                Open: ${float(bar.open):.2f}
                High: ${float(bar.high):.2f}
                Low: ${float(bar.low):.2f}
                Close: ${float(bar.close):.2f}
                Volume: {bar.volume}
                """
        else:
            return f"No latest bar data found for {symbol}."
    except Exception as e:
        return f"Error fetching latest bar: {str(e)}"

@mcp.tool()
async def get_stock_latest_quote(symbol_or_symbols: Union[str, List[str]]) -> str:
    """
    Retrieves and formats the latest quote for one or more stocks.
    
    Args:
        symbol_or_symbols (Union[str, List[str]]): Single stock ticker symbol (e.g., "AAPL")
            or a list of symbols (e.g., ["AAPL", "MSFT"]).
    
    Returns:
        str: Formatted string containing for each requested symbol:
            - Ask Price
            - Bid Price
            - Ask Size
            - Bid Size
            - Timestamp
    """
    _ensure_clients()
    try:
        # Validate input before making API call
        symbols = [symbol_or_symbols] if isinstance(symbol_or_symbols, str) else list(symbol_or_symbols)
        if not symbols:
            return "No symbols provided."
        
        request_params = StockLatestQuoteRequest(symbol_or_symbols=symbol_or_symbols)
        quotes = stock_historical_data_client.get_stock_latest_quote(request_params)

        results: List[str] = ["Latest Stock Quotes:", "====================", ""]
        for symbol in symbols:
            quote = quotes.get(symbol)
            if not quote:
                results.extend([f"Symbol: {symbol}", "------------------", f"No quote data found for {symbol}.", ""])
                continue

            timestamp_value = getattr(quote, "timestamp", None)
            timestamp = timestamp_value.isoformat() if hasattr(timestamp_value, "isoformat") else timestamp_value or "N/A"

            results.extend([
                f"Symbol: {symbol}",
                "------------------",
                f"Ask Price: ${quote.ask_price:.2f}",
                f"Bid Price: ${quote.bid_price:.2f}",
                f"Ask Size: {quote.ask_size}",
                f"Bid Size: {quote.bid_size}",
                f"Timestamp: {timestamp}",
                "",
            ])

        return "\n".join(results).strip()
    except Exception as e:
        symbols = [symbol_or_symbols] if isinstance(symbol_or_symbols, str) else list(symbol_or_symbols)
        requested = ", ".join(symbols) if symbols else ""
        return f"Error fetching quote for {requested}: {str(e)}"

@mcp.tool()
async def get_stock_latest_trade(
    symbol: str,
    feed: Optional[DataFeed] = None,
    currency: Optional[SupportedCurrencies] = None
) -> str:
    """Get the latest trade for a stock.
    
    Args:
        symbol: Stock ticker symbol (e.g., 'AAPL', 'MSFT')
        feed: The stock data feed to retrieve from (optional)
        currency: The currency for prices (optional, defaults to USD)
    
    Returns:
        A formatted string containing the latest trade details or an error message
    """
    _ensure_clients()
    try:
        # Create the request object with all available parameters
        request_params = StockLatestTradeRequest(
            symbol_or_symbols=symbol,
            feed=feed,
            currency=currency
        )
        
        # Get the latest trade
        latest_trades = stock_historical_data_client.get_stock_latest_trade(request_params)
        
        if symbol in latest_trades:
            trade = latest_trades[symbol]
            return f"""
                Latest Trade for {symbol}:
                ---------------------------
                Time: {trade.timestamp}
                Price: ${float(trade.price):.6f}
                Size: {trade.size}
                Exchange: {trade.exchange}
                ID: {trade.id}
                Conditions: {trade.conditions}
                """
        else:
            return f"No latest trade data found for {symbol}."
    except Exception as e:
        return f"Error fetching latest trade: {str(e)}"


@mcp.tool()
async def get_stock_snapshot(
    symbol_or_symbols: Union[str, List[str]], 
    feed: Optional[DataFeed] = None,
    currency: Optional[SupportedCurrencies] = None
) -> str:
    """
    Retrieves comprehensive snapshots of stock symbols including latest trade, quote, minute bar, daily bar, and previous daily bar.
    
    Args:
        symbol_or_symbols: Single stock symbol or list of stock symbols (e.g., 'AAPL' or ['AAPL', 'MSFT'])
        feed: The stock data feed to retrieve from (optional)
        currency: The currency the data should be returned in (default: USD)
    
    Returns:
        Formatted string with comprehensive snapshots including:
        - latest_quote: Current bid/ask prices and sizes
        - latest_trade: Most recent trade price, size, and exchange
        - minute_bar: Latest minute OHLCV bar
        - daily_bar: Current day's OHLCV bar  
        - previous_daily_bar: Previous trading day's OHLCV bar
    """
    _ensure_clients()
    try:
        # Create and execute request
        request = StockSnapshotRequest(symbol_or_symbols=symbol_or_symbols, feed=feed, currency=currency)
        snapshots = stock_historical_data_client.get_stock_snapshot(request)
        
        # Format response
        symbols = [symbol_or_symbols] if isinstance(symbol_or_symbols, str) else symbol_or_symbols
        results = ["Stock Snapshots:", "=" * 15, ""]
        
        for symbol in symbols:
            snapshot = snapshots.get(symbol)
            if not snapshot:
                results.append(f"No data available for {symbol}\n")
                continue
            
            # Build snapshot data using helper functions
            snapshot_data = [
                f"Symbol: {symbol}",
                "-" * 15,
                _format_quote_data(snapshot.latest_quote),
                _format_trade_data(snapshot.latest_trade),
                _format_ohlcv_bar(snapshot.minute_bar, "Latest Minute Bar", True),
                _format_ohlcv_bar(snapshot.daily_bar, "Latest Daily Bar", False),
                _format_ohlcv_bar(snapshot.previous_daily_bar, "Previous Daily Bar", False),
            ]
            
            results.extend(filter(None, snapshot_data))  # Filter out empty strings
        
        return "\n".join(results)
        
    except APIError as api_error:
        error_message = str(api_error)
        # Handle specific data feed subscription errors
        if "subscription" in error_message.lower() and ("sip" in error_message.lower() or "premium" in error_message.lower()):
            return f"""
                    Error: Premium data feed subscription required.

                    The requested data feed requires a premium subscription. Available data feeds:

                    • IEX (Default): Investor's Exchange data feed - Free with basic account
                    • SIP: Securities Information Processor feed - Requires premium subscription
                    • DELAYED_SIP: SIP data with 15-minute delay - Requires premium subscription  
                    • OTC: Over the counter feed - Requires premium subscription

                    Most users can access comprehensive market data using the default IEX feed.
                    To use premium feeds (SIP, DELAYED_SIP, OTC), please upgrade your subscription.

                    Original error: {error_message}
                    """
        else:
            return f"API Error retrieving stock snapshots: {error_message}"
            
    except Exception as e:
        return f"Error retrieving stock snapshots: {str(e)}"

# ============================================================================
# Crypto Market Data Tools
# ============================================================================

@mcp.tool()
async def get_crypto_bars(
    symbol: Union[str, List[str]], 
    days: int = 1, 
    timeframe: str = "1Hour",
    limit: Optional[int] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    feed: CryptoFeed = CryptoFeed.US
) -> str:
    """
    Retrieves and formats historical price bars for a cryptocurrency with configurable timeframe and time range.
    
    Args:
        symbol (Union[str, List[str]]): Crypto symbol(s) (e.g., 'BTC/USD', 'ETH/USD' or ['BTC/USD', 'ETH/USD'])
        days (int): Number of days to look back (default: 1, ignored if start/end provided)
        timeframe (str): Bar timeframe - supports flexible Alpaca formats:
            - Minutes: "1Min", "2Min", "3Min", "4Min", "5Min", "15Min", "30Min", etc.
            - Hours: "1Hour", "2Hour", "3Hour", "4Hour", "6Hour", etc.
            - Days: "1Day", "2Day", "3Day", etc.
            - Weeks: "1Week", "2Week", etc.
            - Months: "1Month", "2Month", etc.
            (default: "1Hour")
        limit (Optional[int]): Maximum number of bars to return (optional)
        start (Optional[str]): Start time in ISO format (e.g., "2023-01-01T09:30:00" or "2023-01-01")
        end (Optional[str]): End time in ISO format (e.g., "2023-01-01T16:00:00" or "2023-01-01")
        feed (CryptoFeed): The crypto data feed to retrieve from (default: US)
    
    Returns:
        str: Formatted string containing historical crypto price data with timestamps, OHLCV data
    """
    _ensure_clients()
    try:
        # Parse timeframe string to TimeFrame object
        timeframe_obj = parse_timeframe_with_enums(timeframe)
        if timeframe_obj is None:
            return f"Error: Invalid timeframe '{timeframe}'. Supported formats: 1Min, 2Min, 4Min, 5Min, 15Min, 30Min, 1Hour, 2Hour, 4Hour, 1Day, 1Week, 1Month, etc."
        
        # Parse start/end times or calculate from days
        start_time = None
        end_time = None
        
        if start:
            try:
                start_time = _parse_iso_datetime(start)
            except ValueError:
                return f"Error: Invalid start time format '{start}'. Use ISO format like '2023-01-01T09:30:00' or '2023-01-01'"
                
        if end:
            try:
                end_time = _parse_iso_datetime(end)
            except ValueError:
                return f"Error: Invalid end time format '{end}'. Use ISO format like '2023-01-01T16:00:00' or '2023-01-01'"
        
        # Compute fallbacks concisely (Option A: no special 2h/24h intraday defaults)
        start_time = start_time or (
            datetime.now() - timedelta(minutes=limit * timeframe_obj.amount)
            if limit and timeframe_obj.unit_value == TimeFrameUnit.Minute else
            datetime.now() - timedelta(hours=limit * timeframe_obj.amount)
            if limit and timeframe_obj.unit_value == TimeFrameUnit.Hour else
            datetime.now() - timedelta(days=days)
        )
        end_time = end_time or datetime.now()
        
        request_params = CryptoBarsRequest(
            symbol_or_symbols=symbol,
            timeframe=timeframe_obj,
            start=start_time,
            end=end_time,
            limit=limit
        )
        
        bars = crypto_historical_data_client.get_crypto_bars(request_params, feed=feed)

        symbols_list = symbol if isinstance(symbol, list) else [symbol]
        outputs: List[str] = []
        time_range = f"{start_time.strftime('%Y-%m-%d %H:%M')} to {end_time.strftime('%Y-%m-%d %H:%M')}"

        # Prefer the underlying mapping ('.data') when present; fallback to indexed access
        mapping_bars = getattr(bars, 'data', None) or bars
        for sym in symbols_list:
            sym_bars = mapping_bars.get(sym) if hasattr(mapping_bars, 'get') else None
            if not sym_bars:
                outputs.append(f"No historical crypto data found for {sym} with {timeframe} timeframe in the specified time range.")
                continue

            result = f"Historical Crypto Data for {sym} ({timeframe} bars, {time_range}):\n"
            result += "---------------------------------------------------\n"
            for bar in sym_bars:
                if timeframe_obj.unit_value in [TimeFrameUnit.Minute, TimeFrameUnit.Hour]:
                    time_str = bar.timestamp.strftime('%Y-%m-%d %H:%M:%S')
                else:
                    time_str = bar.timestamp.date()
                result += f"Time: {time_str}, Open: ${bar.open:.6f}, High: ${bar.high:.6f}, Low: ${bar.low:.6f}, Close: ${bar.close:.6f}, Volume: {bar.volume}\n"
            outputs.append(result)

        return "\n".join(outputs)
    except Exception as e:
        return f"Error fetching historical crypto data for {symbol}: {str(e)}"

@mcp.tool()
async def get_crypto_quotes(
    symbol: Union[str, List[str]],
    days: int = 3,
    limit: Optional[int] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    feed: CryptoFeed = CryptoFeed.US
) -> str:
    """
    Retrieves and formats historical quote data for a cryptocurrency.
    
    Args:
        symbol (Union[str, List[str]]): Crypto symbol(s) (e.g., 'BTC/USD', 'ETH/USD' or ['BTC/USD', 'ETH/USD'])
        days (int): Number of days to look back (default: 3, ignored if start/end provided)
        limit (Optional[int]): Maximum number of quotes to return (optional)
        start (Optional[str]): Start time in ISO format (e.g., "2023-01-01T09:30:00" or "2023-01-01")
        end (Optional[str]): End time in ISO format (e.g., "2023-01-01T16:00:00" or "2023-01-01")
        feed (CryptoFeed): The crypto data feed to retrieve from (default: US)
    
    Returns:
        str: Formatted string containing historical crypto quote data with timestamps, bid/ask prices and sizes
    """
    _ensure_clients()
    try:
        # Parse start/end times or calculate from days
        start_time = None
        end_time = None
        
        if start:
            try:
                start_time = _parse_iso_datetime(start)
            except ValueError:
                return f"Error: Invalid start time format '{start}'. Use ISO format like '2023-01-01T09:30:00' or '2023-01-01'"
        if end:
            try:
                end_time = _parse_iso_datetime(end)
            except ValueError:
                return f"Error: Invalid end time format '{end}'. Use ISO format like '2023-01-01T16:00:00' or '2023-01-01'"
        
        # If no start/end provided, calculate from days parameter
        if not start_time:
            start_time = datetime.now() - timedelta(days=days)
        if not end_time:
            end_time = datetime.now()
        
        request_params = CryptoQuoteRequest(
            symbol_or_symbols=symbol,
            start=start_time,
            end=end_time,
            limit=limit
        )
        
        quotes = crypto_historical_data_client.get_crypto_quotes(request_params, feed=feed)

        symbols_list = symbol if isinstance(symbol, list) else [symbol]
        outputs: List[str] = []
        time_range = f"{start_time.strftime('%Y-%m-%d %H:%M')} to {end_time.strftime('%Y-%m-%d %H:%M')}"

        mapping_quotes = getattr(quotes, 'data', None) or quotes
        for sym in symbols_list:
            sym_quotes = mapping_quotes.get(sym) if hasattr(mapping_quotes, 'get') else None
            if not sym_quotes:
                outputs.append(f"No historical crypto quotes found for {sym} in the specified time range.")
                continue

            result = f"Historical Crypto Quotes for {sym} ({time_range}):\n"
            result += "---------------------------------------------------\n"
            for quote in sym_quotes:
                time_str = quote.timestamp.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
                result += f"Time: {time_str}, Bid: ${quote.bid_price:.6f} (Size: {quote.bid_size:.6f}), Ask: ${quote.ask_price:.6f} (Size: {quote.ask_size:.6f})\n"
            outputs.append(result)

        return "\n".join(outputs)
    except Exception as e:
        return f"Error fetching historical crypto quotes for {symbol}: {str(e)}"

@mcp.tool()
async def get_crypto_trades(
    symbol: Union[str, List[str]],
    days: int = 1,
    limit: Optional[int] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    sort: Optional[str] = None,
    feed: CryptoFeed = CryptoFeed.US
) -> str:
    """
    Retrieves and formats historical trade prints for a cryptocurrency.

    Args:
        symbol (Union[str, List[str]]): Crypto symbol(s) (e.g., 'BTC/USD' or ['BTC/USD','ETH/USD'])
        days (int): Number of days to look back (default: 1, ignored if start/end provided)
        limit (Optional[int]): Maximum number of trades to return
        start (Optional[str]): ISO start time (e.g., "2023-01-01T09:30:00")
        end (Optional[str]): ISO end time (e.g., "2023-01-01T16:00:00")
        sort (Optional[str]): 'asc' or 'desc' chronological order
        feed (CryptoFeed): Crypto data feed (default: US)

    Returns:
        str: Formatted trade history
    """
    _ensure_clients()
    try:
        # Parse start/end times or calculate from days
        start_time = None
        end_time = None

        if start:
            try:
                start_time = _parse_iso_datetime(start)
            except ValueError:
                return f"Error: Invalid start time format '{start}'. Use ISO format like '2023-01-01T09:30:00'"

        if end:
            try:
                end_time = _parse_iso_datetime(end)
            except ValueError:
                return f"Error: Invalid end time format '{end}'. Use ISO format like '2023-01-01T16:00:00'"

        if not start_time:
            start_time = datetime.now() - timedelta(days=days)
        if not end_time:
            end_time = datetime.now()

        # Sort mapping (default to ascending)
        sort_enum = Sort.ASC
        if sort:
            if sort.lower() == "asc":
                sort_enum = Sort.ASC
            elif sort.lower() == "desc":
                sort_enum = Sort.DESC
            else:
                return f"Invalid sort: {sort}. Must be 'asc' or 'desc'."

        request_params = CryptoTradesRequest(
            symbol_or_symbols=symbol,
            start=start_time,
            end=end_time,
            limit=limit,
            sort=sort_enum,
        )

        trades = crypto_historical_data_client.get_crypto_trades(request_params, feed=feed)

        symbols_list = symbol if isinstance(symbol, list) else [symbol]
        outputs: List[str] = []
        time_range = f"{start_time.strftime('%Y-%m-%d %H:%M')} to {end_time.strftime('%Y-%m-%d %H:%M')}"

        mapping_trades = getattr(trades, 'data', None) or trades
        for sym in symbols_list:
            sym_trades = mapping_trades.get(sym) if hasattr(mapping_trades, 'get') else None
            if not sym_trades:
                outputs.append(f"No historical crypto trades found for {sym} in the specified time range.")
                continue
            result = f"Historical Crypto Trades for {sym} ({time_range}):\n"
            result += "---------------------------------------------------\n"
            for t in sym_trades:
                time_str = t.timestamp.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
                line = f"Time: {time_str}, Price: ${t.price:.6f}, Size: {t.size}"
                if hasattr(t, 'exchange') and t.exchange:
                    line += f", Exchange: {t.exchange}"
                result += line + "\n"
            outputs.append(result)

        return "\n".join(outputs)
    except Exception as e:
        return f"Error fetching historical crypto trades for {symbol}: {str(e)}"


@mcp.tool()
async def get_crypto_latest_quote(
    symbol: Union[str, List[str]],
    feed: CryptoFeed = CryptoFeed.US
) -> str:
    """
    Returns the latest quote for one or more crypto symbols.

    Args:
        symbol (Union[str, List[str]]): Crypto symbol(s) (e.g., 'BTC/USD' or ['BTC/USD','ETH/USD'])
        feed (CryptoFeed): The crypto data feed (default: US)

    Returns:
        str: Formatted latest quote(s)
    """
    _ensure_clients()
    try:
        request_params = CryptoLatestQuoteRequest(symbol_or_symbols=symbol)
        latest = crypto_historical_data_client.get_crypto_latest_quote(request_params, feed=feed)

        symbols_list = symbol if isinstance(symbol, list) else [symbol]
        outputs: List[str] = []
        mapping_latest_quotes = getattr(latest, 'data', None) or latest
        for sym in symbols_list:
            quote = mapping_latest_quotes.get(sym) if hasattr(mapping_latest_quotes, 'get') else None
            if not quote:
                outputs.append(f"No latest crypto quote available for {sym}.")
                continue
            outputs.append(
                _format_quote_data(quote).replace("Latest Quote:", f"Latest Crypto Quote for {sym}:")
            )
        return "\n".join(outputs)
    except Exception as e:
        return f"Error retrieving latest crypto quote for {symbol}: {str(e)}"


@mcp.tool()
async def get_crypto_latest_bar(
    symbol: Union[str, List[str]],
    feed: CryptoFeed = CryptoFeed.US
) -> str:
    """
    Returns the latest minute bar for one or more crypto symbols.
    """
    _ensure_clients()
    try:
        request_params = CryptoLatestBarRequest(symbol_or_symbols=symbol)
        latest = crypto_historical_data_client.get_crypto_latest_bar(request_params, feed=feed)

        symbols_list = symbol if isinstance(symbol, list) else [symbol]
        outputs: List[str] = []
        mapping_latest_bars = getattr(latest, 'data', None) or latest
        for sym in symbols_list:
            bar = mapping_latest_bars.get(sym) if hasattr(mapping_latest_bars, 'get') else None
            if not bar:
                outputs.append(f"No latest crypto bar available for {sym}.")
                continue
            outputs.append(
                _format_ohlcv_bar(bar, f"Latest Crypto Bar for {sym}", True)
            )
        return "\n".join(outputs)
    except Exception as e:
        return f"Error retrieving latest crypto bar for {symbol}: {str(e)}"


@mcp.tool()
async def get_crypto_latest_trade(
    symbol: Union[str, List[str]],
    feed: CryptoFeed = CryptoFeed.US
) -> str:
    """
    Returns the latest trade for one or more crypto symbols.
    """
    _ensure_clients()
    try:
        request_params = CryptoLatestTradeRequest(symbol_or_symbols=symbol)
        latest = crypto_historical_data_client.get_crypto_latest_trade(request_params, feed=feed)

        symbols_list = symbol if isinstance(symbol, list) else [symbol]
        outputs: List[str] = []
        mapping_latest_trades = getattr(latest, 'data', None) or latest
        for sym in symbols_list:
            trade = mapping_latest_trades.get(sym) if hasattr(mapping_latest_trades, 'get') else None
            if not trade:
                outputs.append(f"No latest crypto trade available for {sym}.")
                continue
            formatted = _format_trade_data(trade).replace("Latest Trade:", f"Latest Crypto Trade for {sym}:")
            outputs.append(formatted)
        return "\n".join(outputs)
    except Exception as e:
        return f"Error retrieving latest crypto trade for {symbol}: {str(e)}"


@mcp.tool()
async def get_crypto_snapshot(
    symbol: Union[str, List[str]],
    feed: CryptoFeed = CryptoFeed.US
) -> str:
    """
    Returns a snapshot for one or more crypto symbols including latest trade, quote,
    latest minute bar, daily and previous daily bars.
    """
    _ensure_clients()
    try:
        request_params = CryptoSnapshotRequest(symbol_or_symbols=symbol)
        snapshots = crypto_historical_data_client.get_crypto_snapshot(request_params, feed=feed)

        symbols_list = symbol if isinstance(symbol, list) else [symbol]
        outputs: List[str] = []
        mapping_snapshots = getattr(snapshots, 'data', None) or snapshots
        for sym in symbols_list:
            snap = mapping_snapshots.get(sym) if hasattr(mapping_snapshots, 'get') else None
            if not snap:
                outputs.append(f"No crypto snapshot available for {sym}.")
                continue
            parts: List[str] = [f"Crypto Snapshot for {sym}:"]
            parts.append(_format_ohlcv_bar(getattr(snap, 'minute_bar', None), "Latest Minute Bar", True))
            parts.append(_format_ohlcv_bar(getattr(snap, 'daily_bar', None), "Latest Daily Bar", False))
            parts.append(_format_ohlcv_bar(getattr(snap, 'previous_daily_bar', None), "Previous Daily Bar", False))
            parts.append(_format_quote_data(getattr(snap, 'latest_quote', None)))
            trade = getattr(snap, 'latest_trade', None)
            if trade:
                parts.append(
                    f"Latest Trade:\n  Price: ${trade.price:.2f}, Size: {trade.size}\n  Timestamp: {trade.timestamp.strftime('%Y-%m-%d %H:%M:%S %Z')}\n\n"
                )
            outputs.append("".join(filter(None, parts)))
        return "\n".join(outputs)
    except APIError as api_error:
        error_message = str(api_error)
        return f"API Error retrieving crypto snapshots: {error_message}"
    except Exception as e:
        return f"Error retrieving crypto snapshots: {str(e)}"


@mcp.tool()
async def get_crypto_latest_orderbook(
    symbol: Union[str, List[str]],
    feed: CryptoFeed = CryptoFeed.US
) -> str:
    """
    Returns the latest orderbook for one or more crypto symbols.
    """
    _ensure_clients()
    try:
        request_params = CryptoLatestOrderbookRequest(symbol_or_symbols=symbol)
        books = crypto_historical_data_client.get_crypto_latest_orderbook(request_params, feed=feed)

        symbols_list = symbol if isinstance(symbol, list) else [symbol]
        outputs: List[str] = []
        mapping_books = getattr(books, 'data', None) or books
        for sym in symbols_list:
            ob = mapping_books.get(sym) if hasattr(mapping_books, 'get') else None
            if not ob:
                outputs.append(f"No latest crypto orderbook available for {sym}.")
                continue
            best_bid = ob.bids[0] if getattr(ob, 'bids', None) else None
            best_ask = ob.asks[0] if getattr(ob, 'asks', None) else None
            ts = getattr(ob, 'timestamp', None)
            ts_str = ts.strftime('%Y-%m-%d %H:%M:%S') if ts else ""
            line = f"Latest Crypto Orderbook for {sym}:\n"
            if best_bid:
                line += f"Bid: ${best_bid.price:.6f} x {best_bid.size} | "
            line += f"Ask: ${best_ask.price:.6f} x {best_ask.size}\n" if best_ask else "No asks available\n"
            if ts_str:
                line += f"Timestamp: {ts_str}\n"
            outputs.append(line)
        return "\n".join(outputs)
    except Exception as e:
        return f"Error retrieving latest crypto orderbook for {symbol}: {str(e)}"

# ============================================================================
# Options Market Data Tools
# ============================================================================

@mcp.tool()
async def get_option_contracts(
    underlying_symbol: str,
    expiration_date: Optional[date] = None,
    expiration_date_gte: Optional[date] = None,
    expiration_date_lte: Optional[date] = None,
    expiration_expression: Optional[str] = None,
    strike_price_gte: Optional[str] = None,
    strike_price_lte: Optional[str] = None,
    type: Optional[ContractType] = None,
    status: Optional[AssetStatus] = None,
    root_symbol: Optional[str] = None,
    limit: Optional[int] = None
) -> str:
    """
    Retrieves option contracts - direct mapping to GetOptionContractsRequest.
    
    Args:
        underlying_symbol (str): Underlying asset symbol (e.g., 'SPY', 'AAPL')
        expiration_date (Optional[date]): Specific expiration date
        expiration_date_gte (Optional[date]): Expiration date greater than or equal to
        expiration_date_lte (Optional[date]): Expiration date less than or equal to
        expiration_expression (Optional[str]): Natural language (e.g., "week of September 2, 2025")
        strike_price_gte/lte (Optional[str]): Strike price range
        type (Optional[ContractType]): "call" or "put"
        status (Optional[AssetStatus]): "active" (default)
        root_symbol (Optional[str]): Root symbol filter
        limit (Optional[int]): Maximum number of contracts to return
    
    Examples:
        get_option_contracts("NVDA", expiration_expression="week of September 2, 2025")
        get_option_contracts("SPY", expiration_date_gte=date(2025,9,1), expiration_date_lte=date(2025,9,5))
    """
    _ensure_clients()
    try:
        # Handle natural language expression
        if expiration_expression:
            parsed = _parse_expiration_expression(expiration_expression)
            if parsed.get('error'):
                return f"Error: {parsed['error']}"
            
            # Map parsed results directly to API parameters
            if 'expiration_date' in parsed:
                expiration_date = parsed['expiration_date']
            elif 'expiration_date_gte' in parsed:
                expiration_date_gte = parsed['expiration_date_gte']
                expiration_date_lte = parsed['expiration_date_lte']
        
        # Create API request - direct mapping like your baseline example
        request = GetOptionContractsRequest(
            underlying_symbols=[underlying_symbol],
            expiration_date=expiration_date,
            expiration_date_gte=expiration_date_gte,
            expiration_date_lte=expiration_date_lte,
            strike_price_gte=strike_price_gte,
            strike_price_lte=strike_price_lte,
            type=type,
            status=status,
            root_symbol=root_symbol,
            limit=limit
        )
        
        # Execute API call
        response = trade_client.get_option_contracts(request)
        
        if not response or not response.option_contracts:
            return f"No option contracts found for {underlying_symbol}."
        
        # Format results
        contracts = response.option_contracts
        result = [f"Option Contracts for {underlying_symbol}:", "=" * 50]

        for contract in contracts:  # Show ALL contracts returned by API
            contract_type = "Call" if contract.type == ContractType.CALL else "Put"
            result.extend([
                f"ID: {contract.id}",
                f"Symbol: {contract.symbol}",
                f"  Name: {contract.name}",
                f"  Type: {contract_type}",
                f"  Strike: ${contract.strike_price}",
                f"  Expiration: {contract.expiration_date}",
                f"  Style: {contract.style}",
                f"  Contract Size: {contract.size}",
                f"  Open Interest: {contract.open_interest or 'N/A'}",
                f"  Open Interest Date: {contract.open_interest_date or 'N/A'}",
                f"  Close Price: ${contract.close_price or 'N/A'}",
                f"  Close Price Date: {contract.close_price_date or 'N/A'}",
                f"  Tradable: {contract.tradable}",
                f"  Status: {contract.status}",
                f"  Root Symbol: {contract.root_symbol}",
                f"  Underlying Asset ID: {contract.underlying_asset_id}",
                f"  Underlying Symbol: {contract.underlying_symbol}",
                "-" * 40
            ])

        result.append(f"\nTotal: {len(contracts)} contracts")
        return "\n".join(result)
        
    except Exception as e:
        return f"Error: {str(e)}"

@mcp.tool()
async def get_option_latest_quote(
    symbol: str,
    feed: Optional[OptionsFeed] = None
) -> str:
    """
    Retrieves and formats the latest quote for an option contract. This endpoint returns real-time
    pricing and market data, including bid/ask prices, sizes, and exchange information.
    
    Args:
        symbol (str): The option contract symbol (e.g., 'AAPL230616C00150000')
        feed (Optional[OptionsFeed]): The source feed of the data (opra or indicative).
            Default: opra if the user has the options subscription, indicative otherwise.
    
    Returns:
        str: Formatted string containing the latest quote information including:
            - Ask Price and Ask Size
            - Bid Price and Bid Size
            - Ask Exchange and Bid Exchange
            - Trade Conditions
            - Tape Information
            - Timestamp (in UTC)
    
    Note:
        This endpoint returns real-time market data. For contract specifications and static data,
        use get_option_contracts instead.
    """
    _ensure_clients()
    try:
        # Create the request object
        request = OptionLatestQuoteRequest(
            symbol_or_symbols=symbol,
            feed=feed
        )
        
        # Get the latest quote
        quotes = option_historical_data_client.get_option_latest_quote(request)
        
        if symbol in quotes:
            quote = quotes[symbol]
            return f"""
                Latest Quote for {symbol}:
                ------------------------
                Ask Price: ${float(quote.ask_price):.2f}
                Ask Size: {quote.ask_size}
                Ask Exchange: {quote.ask_exchange}
                Bid Price: ${float(quote.bid_price):.2f}
                Bid Size: {quote.bid_size}
                Bid Exchange: {quote.bid_exchange}
                Conditions: {quote.conditions}
                Tape: {quote.tape}
                Timestamp: {quote.timestamp}
                """
        else:
            return f"No quote data found for {symbol}."
            
    except Exception as e:
        return f"Error fetching option quote: {str(e)}"


@mcp.tool()
async def get_option_snapshot(symbol_or_symbols: Union[str, List[str]], feed: Optional[OptionsFeed] = None) -> str:
    """
    Retrieves comprehensive snapshots of option contracts including latest trade, quote, implied volatility, and Greeks.
    This endpoint provides a complete view of an option's current market state and theoretical values.
    
    Args:
        symbol_or_symbols (Union[str, List[str]]): Single option symbol or list of option symbols
            (e.g., 'AAPL250613P00205000')
        feed (Optional[OptionsFeed]): The source feed of the data (opra or indicative).
            Default: opra if the user has the options subscription, indicative otherwise.
    
    Returns:
        str: Formatted string containing a comprehensive snapshot including:
            - Symbol Information
            - Latest Quote:
                * Bid/Ask Prices and Sizes
                * Exchange Information
                * Trade Conditions
                * Tape Information
                * Timestamp (UTC)
            - Latest Trade:
                * Price and Size
                * Exchange and Conditions
                * Trade ID
                * Timestamp (UTC)
            - Implied Volatility (as percentage)
            - Greeks:
                * Delta (directional risk)
                * Gamma (delta sensitivity)
                * Rho (interest rate sensitivity)
                * Theta (time decay)
                * Vega (volatility sensitivity)
    """
    _ensure_clients()
    try:
        # Create snapshot request
        request = OptionSnapshotRequest(
            symbol_or_symbols=symbol_or_symbols,
            feed=feed
        )
        
        # Get snapshots
        snapshots = option_historical_data_client.get_option_snapshot(request)
        
        # Format the response
        result = "Option Snapshots:\n"
        result += "================\n\n"
        
        # Handle both single symbol and list of symbols
        symbols = [symbol_or_symbols] if isinstance(symbol_or_symbols, str) else symbol_or_symbols
        
        for symbol in symbols:
            snapshot = snapshots.get(symbol)
            if snapshot is None:
                result += f"No data available for {symbol}\n"
                continue
                
            result += f"Symbol: {symbol}\n"
            result += "-----------------\n"
            
            # Latest Quote
            if snapshot.latest_quote:
                quote = snapshot.latest_quote
                result += f"Latest Quote:\n"
                result += f"  Bid Price: ${quote.bid_price:.6f}\n"
                result += f"  Bid Size: {quote.bid_size}\n"
                result += f"  Bid Exchange: {quote.bid_exchange}\n"
                result += f"  Ask Price: ${quote.ask_price:.6f}\n"
                result += f"  Ask Size: {quote.ask_size}\n"
                result += f"  Ask Exchange: {quote.ask_exchange}\n"
                if quote.conditions:
                    result += f"  Conditions: {quote.conditions}\n"
                if quote.tape:
                    result += f"  Tape: {quote.tape}\n"
                result += f"  Timestamp: {quote.timestamp.strftime('%Y-%m-%d %H:%M:%S.%f %Z')}\n"
            
            # Latest Trade
            if snapshot.latest_trade:
                trade = snapshot.latest_trade
                result += f"Latest Trade:\n"
                result += f"  Price: ${trade.price:.6f}\n"
                result += f"  Size: {trade.size}\n"
                if trade.exchange:
                    result += f"  Exchange: {trade.exchange}\n"
                if trade.conditions:
                    result += f"  Conditions: {trade.conditions}\n"
                if trade.tape:
                    result += f"  Tape: {trade.tape}\n"
                if trade.id:
                    result += f"  Trade ID: {trade.id}\n"
                result += f"  Timestamp: {trade.timestamp.strftime('%Y-%m-%d %H:%M:%S.%f %Z')}\n"
            
            # Implied Volatility
            if snapshot.implied_volatility is not None:
                result += f"Implied Volatility: {snapshot.implied_volatility:.2%}\n"
            
            # Greeks
            if snapshot.greeks:
                greeks = snapshot.greeks
                result += f"Greeks:\n"
                result += f"  Delta: {greeks.delta:.4f}\n"
                result += f"  Gamma: {greeks.gamma:.4f}\n"
                result += f"  Rho: {greeks.rho:.4f}\n"
                result += f"  Theta: {greeks.theta:.4f}\n"
                result += f"  Vega: {greeks.vega:.4f}\n"
            
            result += "\n"
        
        return result
        
    except Exception as e:
        return f"Error retrieving option snapshots: {str(e)}"

# ============================================================================
# Order Management Tools
# ============================================================================

@mcp.tool()
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
        status (str): Order status to filter by (open, closed, all)
        limit (int): Maximum number of orders to return (default: 10, max 500)
        after (Optional[str]): Include orders submitted after this timestamp (ISO format)
        until (Optional[str]): Include orders submitted until this timestamp (ISO format)
        direction (Optional[str]): Chronological order (asc or desc, default: desc)
        nested (Optional[bool]): Roll up multi-leg orders under legs field if True
        side (Optional[str]): Filter by order side (buy or sell)
        symbols (Optional[List[str]]): List of symbols to filter by
    
    Returns:
        str: Formatted string containing order details including:
            - Symbol
            - ID
            - Type
            - Side
            - Quantity
            - Status
            - Submission Time
            - Fill Details (if applicable)
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
        
        if not orders:
            return f"No {status} orders found."
        
        result = f"{status.capitalize()} Orders (Last {len(orders)}):\n"
        result += "-----------------------------------\n"
        
        for order in orders:
            result += f"Symbol: {order.symbol}\n"
            result += f"ID: {order.id}\n"
            result += f"Type: {order.type}\n"
            result += f"Side: {order.side}\n"
            result += f"Quantity: {order.qty}\n"
            result += f"Status: {order.status}\n"
            result += f"Asset Class: {order.asset_class}\n"
            result += f"Order Class: {order.order_class}\n"
            result += f"Time In Force: {order.time_in_force}\n"
            result += f"Extended Hours: {order.extended_hours}\n"
            result += f"Submitted At: {order.submitted_at}\n"
            result += f"Created At: {order.created_at}\n"
            result += f"Updated At: {order.updated_at}\n"
            
            # Additional core fields (these are optional)
            if hasattr(order, 'asset_id') and order.asset_id:
                result += f"Asset ID: {order.asset_id}\n"
            if hasattr(order, 'order_type') and order.order_type:
                result += f"Order Type: {order.order_type}\n"
            if hasattr(order, 'ratio_qty') and order.ratio_qty:
                result += f"Ratio Quantity: {order.ratio_qty}\n"
            
            # Optional fields that may not always be present
            if hasattr(order, 'filled_at') and order.filled_at:
                result += f"Filled At: {order.filled_at}\n"
            if hasattr(order, 'filled_avg_price') and order.filled_avg_price:
                result += f"Filled Price: ${float(order.filled_avg_price):.2f}\n"
            if hasattr(order, 'filled_qty') and order.filled_qty:
                result += f"Filled Quantity: {order.filled_qty}\n"
            if hasattr(order, 'limit_price') and order.limit_price:
                result += f"Limit Price: ${float(order.limit_price):.2f}\n"
            if hasattr(order, 'stop_price') and order.stop_price:
                result += f"Stop Price: ${float(order.stop_price):.2f}\n"
            if hasattr(order, 'trail_price') and order.trail_price:
                result += f"Trail Price: ${float(order.trail_price):.2f}\n"
            if hasattr(order, 'trail_percent') and order.trail_percent:
                result += f"Trail Percent: {order.trail_percent}%\n"
            if hasattr(order, 'notional') and order.notional:
                result += f"Notional: ${float(order.notional):.2f}\n"
            if hasattr(order, 'position_intent') and order.position_intent:
                result += f"Position Intent: {order.position_intent}\n"
            if hasattr(order, 'client_order_id') and order.client_order_id:
                result += f"Client Order ID: {order.client_order_id}\n"
            if hasattr(order, 'canceled_at') and order.canceled_at:
                result += f"Canceled At: {order.canceled_at}\n"
            if hasattr(order, 'expired_at') and order.expired_at:
                result += f"Expired At: {order.expired_at}\n"
            if hasattr(order, 'expires_at') and order.expires_at:
                result += f"Expires At: {order.expires_at}\n"
            if hasattr(order, 'failed_at') and order.failed_at:
                result += f"Failed At: {order.failed_at}\n"
            if hasattr(order, 'replaced_at') and order.replaced_at:
                result += f"Replaced At: {order.replaced_at}\n"
            if hasattr(order, 'replaced_by') and order.replaced_by:
                result += f"Replaced By: {order.replaced_by}\n"
            if hasattr(order, 'replaces') and order.replaces:
                result += f"Replaces: {order.replaces}\n"
            if hasattr(order, 'legs') and order.legs:
                result += f"Legs: {order.legs}\n"
            if hasattr(order, 'hwm') and order.hwm:
                result += f"HWM: {order.hwm}\n"
                
            result += "-----------------------------------\n"
            
        return result
    except Exception as e:
        return f"Error fetching orders: {str(e)}"

@mcp.tool()
async def place_stock_order(
    symbol: str,
    side: str,
    quantity: float,
    order_type: str = "market",
    time_in_force: str = "day",
    limit_price: float = None,
    stop_price: float = None,
    trail_price: float = None,
    trail_percent: float = None,
    extended_hours: bool = False,
    client_order_id: str = None
) -> str:
    """
    Places an order of any supported type (MARKET, LIMIT, STOP, STOP_LIMIT, TRAILING_STOP) using the correct Alpaca request class.

    Args:
        symbol (str): Stock ticker symbol (e.g., AAPL, MSFT)
        side (str): Order side (buy or sell)
        quantity (float): Number of shares to buy or sell
        order_type (str): Order type (MARKET, LIMIT, STOP, STOP_LIMIT, TRAILING_STOP). Default is MARKET.
        time_in_force (str): Time in force for the order. Valid options for equity trading: 
            DAY, GTC, OPG, CLS, IOC, FOK (default: DAY)
        limit_price (float): Limit price (required for LIMIT, STOP_LIMIT)
        stop_price (float): Stop price (required for STOP, STOP_LIMIT)
        trail_price (float): Trail price (for TRAILING_STOP)
        trail_percent (float): Trail percent (for TRAILING_STOP)
        extended_hours (bool): Allow execution during extended hours (default: False)
        client_order_id (str): Optional custom identifier for the order

    Returns:
        str: Formatted string containing order details or error message.
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
        tif_enum = None
        if isinstance(time_in_force, TimeInForce):
            tif_enum = time_in_force
        elif isinstance(time_in_force, str):
            # Convert string to TimeInForce enum
            time_in_force_upper = time_in_force.upper()
            if time_in_force_upper == "DAY":
                tif_enum = TimeInForce.DAY
            elif time_in_force_upper == "GTC":
                tif_enum = TimeInForce.GTC
            elif time_in_force_upper == "OPG":
                tif_enum = TimeInForce.OPG
            elif time_in_force_upper == "CLS":
                tif_enum = TimeInForce.CLS
            elif time_in_force_upper == "IOC":
                tif_enum = TimeInForce.IOC
            elif time_in_force_upper == "FOK":
                tif_enum = TimeInForce.FOK
            else:
                return f"Invalid time_in_force: {time_in_force}. Valid options are: DAY, GTC, OPG, CLS, IOC, FOK"
        else:
            return f"Invalid time_in_force type: {type(time_in_force)}. Must be string or TimeInForce enum."

        # Validate order_type
        order_type_upper = order_type.upper()
        if order_type_upper == "MARKET":
            order_data = MarketOrderRequest(
                symbol=symbol,
                qty=quantity,
                side=order_side,
                type=OrderType.MARKET,
                time_in_force=tif_enum,
                extended_hours=extended_hours,
                client_order_id=client_order_id or f"order_{int(time.time())}"
            )
        elif order_type_upper == "LIMIT":
            if limit_price is None:
                return "limit_price is required for LIMIT orders."
            order_data = LimitOrderRequest(
                symbol=symbol,
                qty=quantity,
                side=order_side,
                type=OrderType.LIMIT,
                time_in_force=tif_enum,
                limit_price=limit_price,
                extended_hours=extended_hours,
                client_order_id=client_order_id or f"order_{int(time.time())}"
            )
        elif order_type_upper == "STOP":
            if stop_price is None:
                return "stop_price is required for STOP orders."
            order_data = StopOrderRequest(
                symbol=symbol,
                qty=quantity,
                side=order_side,
                type=OrderType.STOP,
                time_in_force=tif_enum,
                stop_price=stop_price,
                extended_hours=extended_hours,
                client_order_id=client_order_id or f"order_{int(time.time())}"
            )
        elif order_type_upper == "STOP_LIMIT":
            if stop_price is None or limit_price is None:
                return "Both stop_price and limit_price are required for STOP_LIMIT orders."
            order_data = StopLimitOrderRequest(
                symbol=symbol,
                qty=quantity,
                side=order_side,
                type=OrderType.STOP_LIMIT,
                time_in_force=tif_enum,
                stop_price=stop_price,
                limit_price=limit_price,
                extended_hours=extended_hours,
                client_order_id=client_order_id or f"order_{int(time.time())}"
            )
        elif order_type_upper == "TRAILING_STOP":
            if trail_price is None and trail_percent is None:
                return "Either trail_price or trail_percent is required for TRAILING_STOP orders."
            order_data = TrailingStopOrderRequest(
                symbol=symbol,
                qty=quantity,
                side=order_side,
                type=OrderType.TRAILING_STOP,
                time_in_force=tif_enum,
                trail_price=trail_price,
                trail_percent=trail_percent,
                extended_hours=extended_hours,
                client_order_id=client_order_id or f"order_{int(time.time())}"
            )
        else:
            return f"Invalid order type: {order_type}. Must be one of: MARKET, LIMIT, STOP, STOP_LIMIT, TRAILING_STOP."

        # Submit order
        order = trade_client.submit_order(order_data)
        return f"""
                Stock Order Placed Successfully:
                --------------------------------
                asset_class: {order.asset_class}
                asset_id: {order.asset_id}
                canceled_at: {order.canceled_at}
                client_order_id: {order.client_order_id}
                created_at: {order.created_at}
                expired_at: {order.expired_at}
                expires_at: {order.expires_at}
                extended_hours: {order.extended_hours}
                failed_at: {order.failed_at}
                filled_at: {order.filled_at}
                filled_avg_price: {order.filled_avg_price}
                filled_qty: {order.filled_qty}
                hwm: {order.hwm}
                id: {order.id}
                legs: {order.legs}
                limit_price: {order.limit_price}
                notional: {order.notional}
                order_class: {order.order_class}
                order_type: {order.order_type}
                position_intent: {order.position_intent}
                qty: {order.qty}
                ratio_qty: {order.ratio_qty}
                replaced_at: {order.replaced_at}
                replaced_by: {order.replaced_by}
                replaces: {order.replaces}
                side: {order.side}
                status: {order.status}
                stop_price: {order.stop_price}
                submitted_at: {order.submitted_at}
                symbol: {order.symbol}
                time_in_force: {order.time_in_force}
                trail_percent: {order.trail_percent}
                trail_price: {order.trail_price}
                type: {order.type}
                updated_at: {order.updated_at}
                """
    except Exception as e:
        return f"Error placing order: {str(e)}"

@mcp.tool()
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
    Place a crypto order (market, limit, stop_limit) with GTC/IOC TIF.

    Rules:
    - Market: require exactly one of qty or notional
    - Limit: require qty and limit_price (notional not supported)
    - Stop Limit: require qty, stop_price and limit_price (notional not supported)
    - time_in_force: only GTC or IOC

    Ref: 
    - Crypto orders: https://docs.alpaca.markets/docs/crypto-orders
    - Requests: [MarketOrderRequest](https://alpaca.markets/sdks/python/api_reference/trading/requests.html#marketorderrequest), [LimitOrderRequest](https://alpaca.markets/sdks/python/api_reference/trading/requests.html#limitorderrequest), [StopLimitOrderRequest](https://alpaca.markets/sdks/python/api_reference/trading/requests.html#stoplimitorderrequest)
    - Enums: [TimeInForce](https://alpaca.markets/sdks/python/api_reference/trading/enums.html#alpaca.trading.enums.TimeInForce)
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

        return f"""
                Crypto Order Placed Successfully:
                -------------------------------
                asset_class: {order.asset_class}
                asset_id: {order.asset_id}
                canceled_at: {order.canceled_at}
                client_order_id: {order.client_order_id}
                created_at: {order.created_at}
                expired_at: {order.expired_at}
                expires_at: {order.expires_at}
                extended_hours: {order.extended_hours}
                failed_at: {order.failed_at}
                filled_at: {order.filled_at}
                filled_avg_price: {order.filled_avg_price}
                filled_qty: {order.filled_qty}
                hwm: {order.hwm}
                id: {order.id}
                legs: {order.legs}
                limit_price: {order.limit_price}
                notional: {order.notional}
                order_class: {order.order_class}
                order_type: {order.order_type}
                position_intent: {order.position_intent}
                qty: {order.qty}
                ratio_qty: {order.ratio_qty}
                replaced_at: {order.replaced_at}
                replaced_by: {order.replaced_by}
                replaces: {order.replaces}
                side: {order.side}
                status: {order.status}
                stop_price: {order.stop_price}
                submitted_at: {order.submitted_at}
                symbol: {order.symbol}
                time_in_force: {order.time_in_force}
                trail_percent: {order.trail_percent}
                trail_price: {order.trail_price}
                type: {order.type}
                updated_at: {order.updated_at}
                """
    except Exception as e:
        return f"Error placing crypto order: {str(e)}"

@mcp.tool()
async def place_option_market_order(
    legs: List[Dict[str, Any]],
    order_class: Optional[Union[str, OrderClass]] = None,
    quantity: int = 1,
    time_in_force: Union[str, TimeInForce] = "day",
    extended_hours: bool = False
) -> str:
    """
    Places a market order for options (single or multi-leg) and returns the order details.
    Supports up to 4 legs for multi-leg orders.

    Single vs Multi-Leg Orders:
    - Single-leg: One option contract (buy/sell call or put). Uses "simple" order class.
    - Multi-leg: Multiple option contracts executed together as one strategy (spreads, straddles, etc.). Uses "mleg" order class.
    
    API Processing:
    - Single-leg orders: Sent as standard MarketOrderRequest with symbol and side
    - Multi-leg orders: Sent as MarketOrderRequest with legs array for atomic execution
    
    Args:
        legs (List[Dict[str, Any]]): List of option legs, where each leg is a dictionary containing:
            - symbol (str): Option contract symbol (e.g., 'AAPL230616C00150000')
            - side (str): 'buy' or 'sell'
            - ratio_qty (int): Quantity ratio for the leg (1-4)
        order_class (Optional[Union[str, OrderClass]]): Order class ('simple', 'bracket', 'oco', 'oto', 'mleg' or OrderClass enum)
            Defaults to 'simple' for single leg, 'mleg' for multi-leg
        quantity (int): Base quantity for the order (default: 1)
        time_in_force (Union[str, TimeInForce]): Time in force for the order. For options trading, 
            only 'day' is supported (default: 'day')
        extended_hours (bool): Whether to allow execution during extended hours (default: False)
    
    Returns:
        str: Formatted string containing order details or error message

    Examples:
        # Single-leg: Buy 1 call option
        legs = [{"symbol": "AAPL230616C00150000", "side": "buy", "ratio_qty": 1}]
        
        # Multi-leg: Bull call spread (executed atomically)
        legs = [
            {"symbol": "AAPL230616C00150000", "side": "buy", "ratio_qty": 1},
            {"symbol": "AAPL230616C00160000", "side": "sell", "ratio_qty": 1}
        ]
    
    Note:
        Some option strategies may require specific account permissions:
        - Level 1: Covered calls, Covered puts, Cash-Secured put, etc.
        - Level 2: Long calls, Long puts, cash-secured puts, etc.
        - Level 3: Spreads and combinations: Butterfly Spreads, Straddles, Strangles, Calendar Spreads (except for short call calendar spread, short strangles, short straddles)
        - Level 4: Uncovered options (naked calls/puts), Short Strangles, Short Straddles, Short Call Calendar Spread, etc.
        If you receive a permission error, please check your account's option trading level.
    """
    _ensure_clients()
    # Initialize variables that might be used in exception handlers
    order_legs: List[OptionLegRequest] = []
    
    try:
        # Validate inputs
        validation_error = _validate_option_order_inputs(legs, quantity, time_in_force)
        if validation_error:
            return validation_error
        
        # Convert time_in_force to enum (handle both string and enum inputs)
        if isinstance(time_in_force, str):
            time_in_force_enum = TimeInForce.DAY  # Only DAY is supported for options
        elif isinstance(time_in_force, TimeInForce):
            time_in_force_enum = time_in_force
        else:
            return f"Error: Invalid time_in_force type: {type(time_in_force)}. Must be string or TimeInForce enum."
        
        # Convert order class string to enum if needed
        converted_order_class = _convert_order_class_string(order_class)
        if isinstance(converted_order_class, OrderClass):
            order_class = converted_order_class
        elif isinstance(converted_order_class, str):  # Error message returned
            return converted_order_class
        
        # Determine order class if not provided
        if order_class is None:
            order_class = OrderClass.MLEG if len(legs) > 1 else OrderClass.SIMPLE
        
        # Process legs
        processed_legs = _process_option_legs(legs)
        if isinstance(processed_legs, str):  # Error message returned
            return processed_legs
        order_legs = processed_legs
        
        # Create order request
        order_data = _create_option_market_order_request(
            order_legs, order_class, quantity, time_in_force_enum, extended_hours
        )
        
        # Submit order
        order = trade_client.submit_order(order_data)
        
        # Format and return response
        return _format_option_order_response(order, order_class, order_legs)
        
    except APIError as api_error:
        return _handle_option_api_error(str(api_error), order_legs, order_class)
        
    except Exception as e:
        return f"""
        Unexpected error placing option order: {str(e)}

        Please try:
        1. Verifying all input parameters
        2. Checking your account status
        3. Ensuring market is open
        4. Contacting support if the issue persists
        """

# =======================================================================================
# Position Management Tools
# =======================================================================================

@mcp.tool()
async def cancel_all_orders() -> str:
    """
    Cancel all open orders.
    
    Returns:
        A formatted string containing the status of each cancelled order.
    """
    _ensure_clients()
    try:
        # Cancel all orders
        cancel_responses = trade_client.cancel_orders()
        
        if not cancel_responses:
            return "No orders were found to cancel."
        
        # Format the response
        response_parts = ["Order Cancellation Results:"]
        response_parts.append("-" * 30)
        
        for response in cancel_responses:
            status = "Success" if response.status == 200 else "Failed"
            response_parts.append(f"Order ID: {response.id}")
            response_parts.append(f"Status: {status}")
            if response.body:
                response_parts.append(f"Details: {response.body}")
            response_parts.append("-" * 30)
        
        return "\n".join(response_parts)
        
    except Exception as e:
        return f"Error cancelling orders: {str(e)}"

@mcp.tool()
async def cancel_order_by_id(order_id: str) -> str:
    """
    Cancel a specific order by its ID.
    
    Args:
        order_id: The UUID of the order to cancel
        
    Returns:
        A formatted string containing the status of the cancelled order.
    """
    _ensure_clients()
    try:
        # Cancel the specific order
        response = trade_client.cancel_order_by_id(order_id)
        
        # Format the response
        status = "Success" if response.status == 200 else "Failed"
        result = f"""
        Order Cancellation Result:
        ------------------------
        Order ID: {response.id}
        Status: {status}
        """
        
        if response.body:
            result += f"Details: {response.body}\n"
            
        return result
        
    except Exception as e:
        return f"Error cancelling order {order_id}: {str(e)}"

@mcp.tool()
async def close_position(symbol: str, qty: Optional[str] = None, percentage: Optional[str] = None) -> str:
    """
    Closes a specific position for a single symbol. 
    This method will throw an error if the position does not exist!
    
    Args:
        symbol (str): The symbol of the position to close
        qty (Optional[str]): Optional number of shares to liquidate
        percentage (Optional[str]): Optional percentage of shares to liquidate (must result in at least 1 share)
    
    Returns:
        str: Formatted string containing position closure details or error message
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
        
        return f"""
                Position Closed Successfully:
                ----------------------------
                Symbol: {symbol}
                Order ID: {order.id}
                Status: {order.status}
                """
                
    except APIError as api_error:
        error_message = str(api_error)
        if "42210000" in error_message and "would result in order size of zero" in error_message:
            return """
            Error: Invalid position closure request.
            
            The requested percentage would result in less than 1 share.
            Please either:
            1. Use a higher percentage
            2. Close the entire position (100%)
            3. Specify an exact quantity using the qty parameter
            """
        else:
            return f"Error closing position: {error_message}"
            
    except Exception as e:
        return f"Error closing position: {str(e)}"
    
@mcp.tool()
async def close_all_positions(cancel_orders: bool = False) -> str:
    """
    Closes all open positions.
    
    Args:
        cancel_orders (bool): If True, cancels all open orders before liquidating positions
    
    Returns:
        str: Formatted string containing position closure results
    """
    _ensure_clients()
    try:
        # Close all positions
        close_responses = trade_client.close_all_positions(cancel_orders=cancel_orders)
        
        if not close_responses:
            return "No positions were found to close."
        
        # Format the response
        response_parts = ["Position Closure Results:"]
        response_parts.append("-" * 30)
        
        for response in close_responses:
            response_parts.append(f"Symbol: {response.symbol}")
            response_parts.append(f"Status: {response.status}")
            if response.order_id:
                response_parts.append(f"Order ID: {response.order_id}")
            response_parts.append("-" * 30)
        
        return "\n".join(response_parts)
        
    except Exception as e:
        return f"Error closing positions: {str(e)}"

# Position Management Tools (Options)
@mcp.tool()
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
# Compatibility wrapper for CLI
# ============================================================================

def parse_arguments() -> argparse.Namespace:
    p = argparse.ArgumentParser("Alpaca MCP Server")
    p.add_argument("--transport", choices=["stdio","streamable-http"], default="stdio")
    p.add_argument("--host", default=os.environ.get("HOST","127.0.0.1"))
    # p.add_argument("--host", default=os.environ.get("HOST", "0.0.0.0"))
    p.add_argument("--port", type=int, default=int(os.environ.get("PORT", 8000)))
    return p.parse_args()

class AuthHeaderMiddleware:
    """
    ASGI middleware to extract Authorization headers from incoming HTTP requests.
    
    This middleware intercepts HTTP requests, extracts the Authorization header,
    and stores it in a context variable. The header is then passed along to
    Alpaca Trading API calls.
    """
    def __init__(self, app):
        self.app = app
    
    async def __call__(self, scope, receive, send):
        """Process ASGI request and extract Authorization header."""
        if scope["type"] == "http":
            # Extract Authorization header
            headers = dict(scope.get("headers", []))
            auth_header = headers.get(b"authorization") or headers.get(b"Authorization")
            
            if auth_header:
                auth_value = auth_header.decode("utf-8")
                # Store the full Authorization header value (e.g., "Bearer <token>")
                auth_header_context.set(auth_value)
        
        # Call the wrapped application
        try:
            await self.app(scope, receive, send)
        finally:
            # Clear auth header from context after request
            auth_header_context.set(None)


class AlpacaMCPServer:
    def __init__(self, config_file: Optional[Path] = None) -> None:
        """
        Initialize the Alpaca MCP Server.
        
        Args:
            config_file: Optional path to a custom .env configuration file.
                        If provided, environment variables will be reloaded from this file.
        """
        # If a custom config file is specified, reload environment variables from it
        if config_file and config_file.exists():
            global TRADE_API_KEY, TRADE_API_SECRET, ALPACA_PAPER_TRADE, ALPACA_PAPER_TRADE_BOOL
            global TRADE_API_URL, TRADE_API_WSS, DATA_API_URL, STREAM_DATA_WSS, DEBUG
            
            # Reload environment variables from the custom config file
            load_dotenv(config_file, override=True)
            
            # Update module-level variables with the newly loaded values
            TRADE_API_KEY = os.getenv("ALPACA_API_KEY")
            TRADE_API_SECRET = os.getenv("ALPACA_SECRET_KEY")
            ALPACA_PAPER_TRADE = os.getenv("ALPACA_PAPER_TRADE", "True")
            TRADE_API_URL = os.getenv("TRADE_API_URL")
            TRADE_API_WSS = os.getenv("TRADE_API_WSS")
            DATA_API_URL = os.getenv("DATA_API_URL")
            STREAM_DATA_WSS = os.getenv("STREAM_DATA_WSS")
            DEBUG = os.getenv("DEBUG", "False")
            ALPACA_PAPER_TRADE_BOOL = ALPACA_PAPER_TRADE.lower() not in ['false', '0', 'no', 'off']

    def run(self, transport: str = "stdio", host: str = "0.0.0.0", port: int = 8000) -> None:
    # def run(self, transport: str = "stdio", host: str = "127.0.0.1", port: int = 8000) -> None:
        if transport == "streamable-http":
            # Configure FastMCP settings for host/port with current MCP versions
            mcp.settings.host = host
            mcp.settings.port = port
            
            # Try to wrap the MCP app with auth header middleware for HTTP transport
            # This enables extracting the Authorization header from incoming requests
            # and passing it along to Alpaca Trading API calls
            try:
                # Get the underlying ASGI application
                if hasattr(mcp, '_app'):
                    original_app = mcp._app
                    mcp._app = AuthHeaderMiddleware(original_app)
                elif hasattr(mcp, 'app'):
                    original_app = mcp.app
                    mcp.app = AuthHeaderMiddleware(original_app)
            except Exception as e:
                # If we can't wrap the app, log a warning but continue
                print(f"Note: Could not apply AuthHeaderMiddleware: {e}", file=sys.stderr)
                print("Authorization header passthrough may not work correctly", file=sys.stderr)
            
            mcp.run(transport="streamable-http")
        else:
            mcp.run(transport="stdio")

if __name__ == "__main__":
    args = parse_arguments()
    try:
        AlpacaMCPServer().run(args.transport, args.host, args.port)
    except Exception as e:
        print(f"Error starting server: {e}", file=sys.stderr); sys.exit(1)
