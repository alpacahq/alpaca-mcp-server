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

from mcp.server.fastmcp import FastMCP

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
    """Initialize Alpaca clients on first use."""
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
async def get_stock_bars(
    symbol: str, 
    days: int = 5, 
    timeframe: str = "1Day",
    limit: Optional[int] = None,
    start: Optional[str] = None,
    end: Optional[str] = None
) -> str:
    """
    Retrieves and formats historical price bars for a stock with configurable timeframe and time range.
    
    Args:
        symbol (str): Stock ticker symbol (e.g., AAPL, MSFT)
        days (int): Number of days to look back (default: 5, ignored if start/end provided)
        timeframe (str): Bar timeframe - supports flexible Alpaca formats:
            - Minutes: "1Min", "2Min", "3Min", "4Min", "5Min", "15Min", "30Min", etc.
            - Hours: "1Hour", "2Hour", "3Hour", "4Hour", "6Hour", etc.
            - Days: "1Day", "2Day", "3Day", etc.
            - Weeks: "1Week", "2Week", etc.
            - Months: "1Month", "2Month", etc.
            (default: "1Day")
        limit (Optional[int]): Maximum number of bars to return (optional)
        start (Optional[str]): Start time in ISO format (e.g., "2023-01-01T09:30:00" or "2023-01-01")
        end (Optional[str]): End time in ISO format (e.g., "2023-01-01T16:00:00" or "2023-01-01")
    
    Returns:
        str: Formatted string containing historical price data with timestamps, OHLCV data
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
        
        # If no start/end provided, calculate from days parameter OR limit+timeframe
        if not start_time:
            if limit and timeframe_obj.unit_value in [TimeFrameUnit.Minute, TimeFrameUnit.Hour]:
                # Calculate based on limit and timeframe for intraday data
                if timeframe_obj.unit_value == TimeFrameUnit.Minute:
                    minutes_back = limit * timeframe_obj.amount
                    start_time = datetime.now() - timedelta(minutes=minutes_back)
                elif timeframe_obj.unit_value == TimeFrameUnit.Hour:
                    hours_back = limit * timeframe_obj.amount
                    start_time = datetime.now() - timedelta(hours=hours_back)
            else:
                # Fall back to days parameter for daily+ timeframes
                start_time = datetime.now() - timedelta(days=days)
        if not end_time:
            end_time = datetime.now()
        
        request_params = StockBarsRequest(
            symbol_or_symbols=symbol,
            timeframe=timeframe_obj,
            start=start_time,
            end=end_time,
            limit=limit
        )
        
        bars = stock_historical_data_client.get_stock_bars(request_params)
        
        if bars[symbol]:
            time_range = f"{start_time.strftime('%Y-%m-%d %H:%M')} to {end_time.strftime('%Y-%m-%d %H:%M')}"
            result = f"Historical Data for {symbol} ({timeframe} bars, {time_range}):\n"
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
            return f"No historical data found for {symbol} with {timeframe} timeframe in the specified time range."
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
        return f"API Error fetching historical data for {symbol}: {error_message}"
    except Exception as e:
        return f"Error fetching historical data for {symbol}: {str(e)}"

@mcp.tool()
async def get_stock_trades(
    symbol: str,
    days: int = 5,
    limit: Optional[int] = None,
    sort: Optional[Sort] = Sort.ASC,
    feed: Optional[DataFeed] = None,
    currency: Optional[SupportedCurrencies] = None,
    asof: Optional[str] = None
) -> str:
    """
    Retrieves and formats historical trades for a stock.
    
    Args:
        symbol (str): Stock ticker symbol (e.g., 'AAPL', 'MSFT')
        days (int): Number of days to look back (default: 5)
        limit (Optional[int]): Upper limit of number of data points to return
        sort (Optional[Sort]): Chronological order of response (ASC or DESC)
        feed (Optional[DataFeed]): The stock data feed to retrieve from
        currency (Optional[SupportedCurrencies]): Currency for prices (default: USD)
        asof (Optional[str]): The asof date in YYYY-MM-DD format
    
    Returns:
        str: Formatted string containing trade history or an error message
    """
    _ensure_clients()
    try:
        # Calculate start time based on days
        start_time = datetime.now() - timedelta(days=days)
        
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
            result = f"Historical Trades for {symbol} (Last {days} days):\n"
            result += "---------------------------------------------------\n"
            
            for trade in trades[symbol]:
                result += f"""
                    Time: {trade.timestamp}
                    Price: ${float(trade.price):.6f}
                    Size: {trade.size}
                    Exchange: {trade.exchange}
                    ID: {trade.id}
                    Conditions: {trade.conditions}
                    -------------------
                    """
            return result
        else:
            return f"No trade data found for {symbol} in the last {days} days."
    except Exception as e:
        return f"Error fetching trades: {str(e)}"

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
# Compatibility wrapper for CLI
# ============================================================================

def parse_arguments() -> argparse.Namespace:
    p = argparse.ArgumentParser("Alpaca MCP Server")
    p.add_argument("--transport", choices=["stdio","streamable-http"], default="stdio")
    # p.add_argument("--host", default=os.environ.get("HOST","127.0.0.1"))
    p.add_argument("--host", default=os.environ.get("HOST", "0.0.0.0"))
    p.add_argument("--port", type=int, default=int(os.environ.get("PORT", 8000)))
    return p.parse_args()

class AlpacaMCPServer:
    def __init__(self, config_file: Optional[Path] = None) -> None:
        pass

    def run(self, transport: str = "stdio", host: str = "0.0.0.0", port: int = 8000) -> None:
    # def run(self, transport: str = "stdio", host: str = "127.0.0.1", port: int = 8000) -> None:
        if transport == "streamable-http":
            # Configure FastMCP settings for host/port with current MCP versions
            mcp.settings.host = host
            mcp.settings.port = port
            mcp.run(transport="streamable-http")
        else:
            mcp.run(transport="stdio")

if __name__ == "__main__":
    args = parse_arguments()
    try:
        AlpacaMCPServer().run(args.transport, args.host, args.port)
    except Exception as e:
        print(f"Error starting server: {e}", file=sys.stderr); sys.exit(1)
