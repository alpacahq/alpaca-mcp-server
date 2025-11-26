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
    StockQuotesRequest,
    StockTradesRequest,
    StockLatestBarRequest,
    StockLatestQuoteRequest,
    StockLatestTradeRequest,
    StockSnapshotRequest,
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

# Market data disclaimer
MARKET_DATA_DISCLAIMER = """
---
DISCLAIMER: The Mini version of Alpaca's MCP Server for the OpenAI ChatGPT Connector provides market data solely for reference and informational purposes. The market data made available through this mini version is delayed and may be incomplete, inaccurate, or subject to change without notice. The information provided should not be relied upon for trading or investment decisions, and Alpaca makes no representations or warranties regarding the accuracy, timeliness, or suitability of the data for any purpose. Use of this server is at your own risk.
"""

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
        
        results: List[str] = []
        
        # The response.data contains action types as keys (e.g., 'cash_dividends', 'forward_splits')
        # Each value is a list of corporate actions
        for action_type, actions_list in announcements.data.items():
            if not actions_list:
                continue
            
            for action in actions_list:
                symbol = getattr(action, 'symbol', 'Unknown')
                results.append(f"Symbol: {symbol}")
                
                # Display action details based on available attributes
                if hasattr(action, 'corporate_action_type'):
                    results.append(f"Type: {action.corporate_action_type}")
                if hasattr(action, 'ex_date') and action.ex_date:
                    results.append(f"Ex Date: {action.ex_date}")
                if hasattr(action, 'record_date') and action.record_date:
                    results.append(f"Record Date: {action.record_date}")
                if hasattr(action, 'payable_date') and action.payable_date:
                    results.append(f"Payable Date: {action.payable_date}")
                if hasattr(action, 'process_date') and action.process_date:
                    results.append(f"Process Date: {action.process_date}")
                # Cash dividend specific fields
                if hasattr(action, 'rate') and action.rate:
                    results.append(f"Rate: ${action.rate:.6f}")
                if hasattr(action, 'foreign') and hasattr(action, 'special'):
                    results.append(f"Foreign: {action.foreign}, Special: {action.special}")
                # Split specific fields
                if hasattr(action, 'old_rate') and action.old_rate:
                    results.append(f"Old Rate: {action.old_rate}")
                if hasattr(action, 'new_rate') and action.new_rate:
                    results.append(f"New Rate: {action.new_rate}")
                # Due bill dates
                if hasattr(action, 'due_bill_on_date') and action.due_bill_on_date:
                    results.append(f"Due Bill On Date: {action.due_bill_on_date}")
                if hasattr(action, 'due_bill_off_date') and action.due_bill_off_date:
                    results.append(f"Due Bill Off Date: {action.due_bill_off_date}")
                
                results.append("")
        
        return "\n".join(results)
    except Exception as e:
        return f"Error fetching corporate announcements: {str(e)}"

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
) -> str:
    """
    Retrieves and formats historical price bars for a stock with configurable timeframe and time range.
    
    Args:
        symbol (Union[str, List[str]]): Stock ticker symbol(s) (e.g., 'AAPL', 'MSFT' or ['AAPL', 'MSFT'])
        days (int): Number of days to look back (default: 5, ignored if start is provided)
        hours (int): Number of hours to look back (default: 0, ignored if start is provided)
        minutes (int): Number of minutes to look back (default: 30, ignored if start is provided)
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
        feed (Optional[DataFeed]): The stock data feed to retrieve from (default: IEX)
        currency (Optional[SupportedCurrencies]): Currency for prices (default: USD)
        asof (Optional[str]): The asof date in YYYY-MM-DD format
        tz (str): Timezone for naive datetime strings (default: "America/New_York")
            Supported: "UTC", "ET", "EST", "EDT", "America/New_York"
    
    Returns:
        str: Formatted string containing historical price data with timestamps, OHLCV data
    """
    _ensure_clients()
    try:
        # Parse timeframe string to TimeFrame object
        timeframe_obj = parse_timeframe_with_enums(timeframe)
        if timeframe_obj is None:
            return f"Error: Invalid timeframe '{timeframe}'. Supported formats: 1Min, 2Min, 5Min, 15Min, 30Min, 1Hour, 2Hour, 4Hour, 1Day, 1Week, 1Month, etc."
        
        # Parse start/end times or calculate from days/hours/minutes
        start_time = None
        end_time = None
        now_utc = datetime.now(timezone.utc)  # Capture once for consistency

        if start:
            try:
                start_time = _parse_iso_datetime(start, default_timezone=tz)
            except ValueError as e:
                return f"Error: {str(e)}"
        
        if end:
            try:
                end_time = _parse_iso_datetime(end, default_timezone=tz)
            except ValueError as e:
                return f"Error: {str(e)}"
        else:
            end_time = now_utc - timedelta(minutes=15)
        
        # Compute start_time fallback: use explicit days/hours/minutes parameters
        if not start_time:
            
            if days > 0:
                start_time = now_utc - timedelta(days=days)
            elif hours > 0:
                start_time = now_utc - timedelta(hours=hours)
            elif minutes > 0:
                start_time = now_utc - timedelta(minutes=minutes)
        
        # Create the request object
        request_params = StockBarsRequest(
            symbol_or_symbols=[symbol] if isinstance(symbol, str) else symbol,
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
        
        symbols_list = symbol if isinstance(symbol, list) else [symbol]
        results: List[str] = []
        
        for sym in symbols_list:
            if bars[sym]:
                results.extend([
                    f"Historical Bars for {sym} ({timeframe} timeframe):",
                    f"Total Records: {len(bars[sym])}",
                    ""
                ])
                
                for bar in bars[sym]:
                    # Format timestamp based on timeframe unit
                    if timeframe_obj.unit_value in [TimeFrameUnit.Minute, TimeFrameUnit.Hour]:
                        time_str = bar.timestamp.strftime('%Y-%m-%d %H:%M:%S') + " UTC"
                    else:
                        time_str = str(bar.timestamp.date())
                    
                    results.append(f"Time: {time_str}, Open: ${bar.open:.2f}, High: ${bar.high:.2f}, Low: ${bar.low:.2f}, Close: ${bar.close:.2f}, Volume: {bar.volume}")
                
                results.append("")
                if len(symbols_list) > 1:
                    results.append("")  # Separator between symbols
            else:
                results.append(f"No bar data found for {sym} with {timeframe} timeframe in the specified time range.")
        
        if results:
            results.append(MARKET_DATA_DISCLAIMER)
            return "\n".join(results)
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
) -> str:
    """
    Retrieves and formats historical quote data (level 1 bid/ask) for a stock.
    
    Args:
        symbol (Union[str, List[str]]): Stock ticker symbol(s) (e.g., 'AAPL', 'MSFT' or ['AAPL', 'MSFT'])
        days (int): Number of days to look back (default: 0, ignored if start is provided)
        hours (int): Number of hours to look back (default: 0, ignored if start is provided)
        minutes (int): Number of minutes to look back (default: 20, ignored if start is provided)
        limit (Optional[int]): Upper limit of number of data points to return (default: 1000)
        start (Optional[str]): Start time in ISO format (e.g., "2023-01-01T09:30:00" or "2023-01-01")
        end (Optional[str]): End time in ISO format (e.g., "2023-01-01T16:00:00" or "2023-01-01")
        sort (Optional[Sort]): Chronological order of response (ASC or DESC)
        feed (Optional[DataFeed]): The stock data feed to retrieve from (default: IEX)
        currency (Optional[SupportedCurrencies]): Currency for prices (default: USD)
        asof (Optional[str]): The asof date in YYYY-MM-DD format
        tz (str): Timezone for naive datetime strings (default: "America/New_York")
            Supported: "UTC", "ET", "EST", "EDT", "America/New_York"
        
    Returns:
        str: Formatted string containing quote summary or an error message
    """
    _ensure_clients()
    try:
        # Set default limit if not provided
        if limit is None:
            limit = 1000
        
        # Capture current time once for consistency
        now_utc = datetime.now(timezone.utc)
        
        # Handle start time: use provided start or calculate from days/hours/minutes
        if start:
            try:
                start_time = _parse_iso_datetime(start, default_timezone=tz)
            except ValueError as e:
                return f"Error: {str(e)}"
        else:
            # Calculate start time based on days, hours, or minutes (priority order)
            if days > 0:
                start_time = now_utc - timedelta(days=days)
            elif hours > 0:
                start_time = now_utc - timedelta(hours=hours)
            elif minutes > 0:
                start_time = now_utc - timedelta(minutes=minutes)
            else:
                # Default fallback: let SDK handle defaults
                start_time = None
        
        # Handle end time: use provided end or default to 15 minutes ago
        if end:
            try:
                end_time = _parse_iso_datetime(end, default_timezone=tz)
            except ValueError as e:
                return f"Error: {str(e)}"
        else:
            end_time = now_utc - timedelta(minutes=15)
        
        # Create the request object
        request_params = StockQuotesRequest(
            symbol_or_symbols=[symbol] if isinstance(symbol, str) else symbol,
            start=start_time,
            end=end_time,
            limit=limit,
            sort=sort,
            feed=feed,
            currency=currency,
            asof=asof
        )
        
        quotes = stock_historical_data_client.get_stock_quotes(request_params)
        
        symbols_list = symbol if isinstance(symbol, list) else [symbol]
        results: List[str] = []

        for sym in symbols_list:
            if quotes[sym]:
                data = quotes[sym]
                results.extend([
                    f"Historical Quotes for {sym}",
                    f"Total Records: {len(data)}",
                    ""
                ])
                
                for quote in data:
                    results.extend([
                        f"Timestamp: {quote.timestamp} UTC",
                        f"  Bid Price: {quote.bid_price}",
                        f"  Bid Size: {quote.bid_size}",
                        f"  Bid Exchange: {quote.bid_exchange}",
                        f"  Ask Price: {quote.ask_price}",
                        f"  Ask Size: {quote.ask_size}",
                        f"  Ask Exchange: {quote.ask_exchange}",
                        f"  Conditions: {quote.conditions}",
                        f"  Tape: {quote.tape}",
                        ""
                    ])
                
                results.append("")
                if len(symbols_list) > 1:
                    results.append("")  # Separator
            else:
                results.append(f"No quotes for {sym}")

        if results:
            results.append(MARKET_DATA_DISCLAIMER)
            return "\n".join(results)
        else:
            return f"No quotes found"
            
    except APIError as api_error:
        error_message = str(api_error)
        lower = error_message.lower()
        if "subscription" in lower and "sip" in lower and ("recent" in lower or "15" in lower):
            fifteen_ago = datetime.now(timezone.utc) - timedelta(minutes=15)
            hint_end = fifteen_ago.strftime('%Y-%m-%dT%H:%M:%S')
            return f"Error: Free-plan limitation: Alpaca REST SIP data is delayed by 15 minutes. Retry with `end` <= {hint_end} or use IEX feed. Original error: {error_message}"
        return f"API Error fetching quotes for {symbol}: {error_message}"
    except Exception as e:
        return f"Error fetching quotes for {symbol}: {str(e)}"

@mcp.tool()
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
) -> str:
    """
    Retrieves and formats historical trades for a stock.
    
    Args:
        symbol (Union[str, List[str]]): Stock ticker symbol(s) (e.g., 'AAPL', 'MSFT' or ['AAPL', 'MSFT'])
        days (int): Number of days to look back (default: 0, ignored if start is provided)
        hours (int): Number of hours to look back (default: 0, ignored if start is provided)
        minutes (int): Number of minutes to look back (default: 30, ignored if start is provided)
        limit (Optional[int]): Upper limit of number of data points to return
        start (Optional[str]): Start time in ISO format (e.g., "2023-01-01T09:30:00" or "2023-01-01")
        end (Optional[str]): End time in ISO format (e.g., "2023-01-01T16:00:00" or "2023-01-01")
        sort (Optional[Sort]): Chronological order of response (ASC or DESC)
        feed (Optional[DataFeed]): The stock data feed to retrieve from (default: IEX)
        currency (Optional[SupportedCurrencies]): Currency for prices (default: USD)
        asof (Optional[str]): The asof date in YYYY-MM-DD format
        tz (str): Timezone for naive datetime strings (default: "America/New_York")
            Supported: "UTC", "ET", "EST", "EDT", "America/New_York"
    
    Returns:
        str: Formatted string containing trade history or an error message
    """
    _ensure_clients()
    try:
        # Capture current time once for consistency
        now_utc = datetime.now(timezone.utc)
        
        # Handle start time: use provided start or calculate from days/hours/minutes
        if start:
            try:
                start_time = _parse_iso_datetime(start, default_timezone=tz)
            except ValueError as e:
                return f"Error: {str(e)}"
        else:
            # Calculate start time based on days, hours, or minutes (priority order)
            if days > 0:
                start_time = now_utc - timedelta(days=days)
            elif hours > 0:
                start_time = now_utc - timedelta(hours=hours)
            elif minutes > 0:
                start_time = now_utc - timedelta(minutes=minutes)
            else:
                # Default fallback: let SDK handle defaults
                start_time = None

        if end:
            try:
                end_time = _parse_iso_datetime(end, default_timezone=tz)
            except ValueError as e:
                return f"Error: {str(e)}"
        else:
            end_time = now_utc - timedelta(minutes=15)
        
        # Create the request object with all available parameters
        request_params = StockTradesRequest(
            symbol_or_symbols=[symbol] if isinstance(symbol, str) else symbol,
            start=start_time,
            end=end_time,
            limit=limit,
            sort=sort,
            feed=feed,
            currency=currency,
            asof=asof
        )
        
        # Get the trades
        trades = stock_historical_data_client.get_stock_trades(request_params)
        
        symbols_list = symbol if isinstance(symbol, list) else [symbol]
        results: List[str] = []

        for sym in symbols_list:
            if sym in trades:
                results.extend([
                    f"Historical Trades for {sym}:",
                    f"Total Records: {len(trades[sym])}",
                    ""
                ])
                
                for trade in trades[sym]:
                    results.append(f"Time: {trade.timestamp} UTC, Price: ${float(trade.price):.6f}, Size: {trade.size}, Exchange: {trade.exchange}, ID: {trade.id}, Conditions: {trade.conditions}, Tape: {trade.tape}")
                    results.append("")
                
                results.append("")
                if len(symbols_list) > 1:
                    results.append("")  # Separator
            else:
                results.append(f"No trade data found for {sym} in the specified time range.")

        if results:
            results.append(MARKET_DATA_DISCLAIMER)
            return "\n".join(results)
        else:
            return f"No trade data found"
    except Exception as e:
        return f"Error fetching trades: {str(e)}"

@mcp.tool()
async def get_stock_latest_bar(
    symbol_or_symbols: Union[str, List[str]],
    feed: Optional[DataFeed] = DataFeed.IEX,
    currency: Optional[SupportedCurrencies] = None
) -> str:
    """Get the latest minute bar for one or more stocks.
    
    Args:
        symbol_or_symbols: Stock ticker symbol(s) (e.g., 'AAPL' or ['AAPL', 'MSFT'])
        feed: The stock data feed to retrieve from (optional)
        currency: The currency for prices (optional, defaults to USD)
    
    Returns:
        A formatted string containing the latest bar details or an error message
    """
    _ensure_clients()
    try:
        symbols_list = [symbol_or_symbols] if isinstance(symbol_or_symbols, str) else list(symbol_or_symbols)
        if not symbols_list:
            return "No symbols provided."
        
        # Create the request object with all available parameters
        request_params = StockLatestBarRequest(
            symbol_or_symbols=symbol_or_symbols,
            feed=feed,
            currency=currency
        )
        
        # Get the latest bar
        latest_bars = stock_historical_data_client.get_stock_latest_bar(request_params)
        
        results: List[str] = []
        for symbol in symbols_list:
            bar = latest_bars.get(symbol)
            if not bar:
                results.append(f"No latest bar data found for {symbol}.")
                continue
            
            results.extend([
                f"Symbol: {symbol}",
                f"Time: {bar.timestamp}",
                f"Open: ${float(bar.open):.2f}",
                f"High: ${float(bar.high):.2f}",
                f"Low: ${float(bar.low):.2f}",
                f"Close: ${float(bar.close):.2f}",
                f"Volume: {bar.volume}",
                ""
            ])
        
        results.append(MARKET_DATA_DISCLAIMER)
        return "\n".join(results).strip()
    except Exception as e:
        symbols_list = [symbol_or_symbols] if isinstance(symbol_or_symbols, str) else list(symbol_or_symbols)
        requested = ", ".join(symbols_list) if symbols_list else ""
        return f"Error fetching latest bar for {requested}: {str(e)}"

@mcp.tool()
async def get_stock_latest_quote(
    symbol_or_symbols: Union[str, List[str]],
    feed: Optional[DataFeed] = DataFeed.IEX,    
    currency: Optional[SupportedCurrencies] = None
    ) -> str:
    """
    Retrieves and formats the latest quote for one or more stocks.
    
    Args:
        symbol_or_symbols (Union[str, List[str]]): Single stock ticker symbol (e.g., "AAPL")
            or a list of symbols (e.g., ["AAPL", "MSFT"]).
        feed: The stock data feed to retrieve from (default: IEX )
        currency: The currency for prices (optional, defaults to USD)
    
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
        
        request_params = StockLatestQuoteRequest(
            symbol_or_symbols=symbol_or_symbols,
            feed=feed,
            currency=currency
        )

        quotes = stock_historical_data_client.get_stock_latest_quote(request_params)

        results: List[str] = []
        for symbol in symbols:
            quote = quotes.get(symbol)
            if not quote:
                results.append(f"No quote data found for {symbol}.")
                continue

            timestamp_value = getattr(quote, "timestamp", None)
            timestamp = timestamp_value.isoformat() if hasattr(timestamp_value, "isoformat") else timestamp_value or "N/A"

            results.extend([
                f"Symbol: {symbol}",
                f"Ask Price: ${quote.ask_price:.2f}",
                f"Bid Price: ${quote.bid_price:.2f}",
                f"Ask Size: {quote.ask_size}",
                f"Bid Size: {quote.bid_size}",
                f"Timestamp: {timestamp}",
                "",
            ])

        results.append(MARKET_DATA_DISCLAIMER)
        return "\n".join(results).strip()
    except Exception as e:
        symbols = [symbol_or_symbols] if isinstance(symbol_or_symbols, str) else list(symbol_or_symbols)
        requested = ", ".join(symbols) if symbols else ""
        return f"Error fetching quote for {requested}: {str(e)}"

@mcp.tool()
async def get_stock_latest_trade(
    symbol_or_symbols: Union[str, List[str]],
    feed: Optional[DataFeed] = DataFeed.IEX,
    currency: Optional[SupportedCurrencies] = None
) -> str:
    """Get the latest trade for one or more stocks.
    
    Args:
        symbol_or_symbols: Stock ticker symbol(s) (e.g., 'AAPL' or ['AAPL', 'MSFT'])
        feed: The stock data feed to retrieve from (optional)
        currency: The currency for prices (optional, defaults to USD)
    
    Returns:
        A formatted string containing the latest trade details or an error message
    """
    _ensure_clients()
    try:
        symbols_list = [symbol_or_symbols] if isinstance(symbol_or_symbols, str) else list(symbol_or_symbols)
        if not symbols_list:
            return "No symbols provided."
        
        # Create the request object with all available parameters
        request_params = StockLatestTradeRequest(
            symbol_or_symbols=symbol_or_symbols,
            feed=feed,
            currency=currency
        )
        
        # Get the latest trade
        latest_trades = stock_historical_data_client.get_stock_latest_trade(request_params)
        
        results: List[str] = []
        for symbol in symbols_list:
            trade = latest_trades.get(symbol)
            if not trade:
                results.append(f"No latest trade data found for {symbol}.")
                continue
            
            results.extend([
                f"Symbol: {symbol}",
                f"Time: {trade.timestamp}",
                f"Price: ${float(trade.price):.6f}",
                f"Size: {trade.size}",
                f"Exchange: {trade.exchange}",
                f"ID: {trade.id}",
                f"Conditions: {trade.conditions}",
                ""
            ])
        
        results.append(MARKET_DATA_DISCLAIMER)
        return "\n".join(results).strip()
    except Exception as e:
        symbols_list = [symbol_or_symbols] if isinstance(symbol_or_symbols, str) else list(symbol_or_symbols)
        requested = ", ".join(symbols_list) if symbols_list else ""
        return f"Error fetching latest trade for {requested}: {str(e)}"

@mcp.tool()
async def get_stock_snapshot(
    symbol_or_symbols: Union[str, List[str]], 
    feed: Optional[DataFeed] = DataFeed.IEX,
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
        
        results.append(MARKET_DATA_DISCLAIMER)
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
    hours: int = 0,
    minutes: int = 30,
    timeframe: str = "1Hour",
    limit: Optional[int] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    feed: CryptoFeed = CryptoFeed.US,
    tz: str = "America/New_York"
) -> str:
    """
    Retrieves and formats historical price bars for a cryptocurrency with configurable timeframe and time range.
    
    Args:
        symbol (Union[str, List[str]]): Crypto symbol(s) (e.g., 'BTC/USD', 'ETH/USD' or ['BTC/USD', 'ETH/USD'])
        days (int): Number of days to look back (default: 1, ignored if start is provided)
        hours (int): Number of hours to look back (default: 0, ignored if start is provided)
        minutes (int): Number of minutes to look back (default: 30, ignored if start is provided)
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
        tz (str): Timezone for naive datetime strings (default: "America/New_York")
            Supported: "UTC", "ET", "EST", "EDT", "America/New_York"
    
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
        now_utc = datetime.now(timezone.utc)  # Capture once for consistency
        
        if start:
            try:
                start_time = _parse_iso_datetime(start, default_timezone=tz)
            except ValueError as e:
                return f"Error: {str(e)}"
   
        if end:
            try:
                end_time = _parse_iso_datetime(end, default_timezone=tz)
            except ValueError as e:
                return f"Error: {str(e)}"
        else:
            end_time = None
        
        # Compute start_time fallback: use explicit days/hours/minutes parameters
        if not start_time:
            
            if days > 0:
                start_time = now_utc - timedelta(days=days)
            elif hours > 0:
                start_time = now_utc - timedelta(hours=hours)
            elif minutes > 0:
                start_time = now_utc - timedelta(minutes=minutes)
        
        request_params = CryptoBarsRequest(
            symbol_or_symbols=[symbol] if isinstance(symbol, str) else symbol,
            timeframe=timeframe_obj,
            start=start_time,
            end=end_time,
            limit=limit
        )
        
        bars = crypto_historical_data_client.get_crypto_bars(request_params, feed=feed)
        
        symbols_list = symbol if isinstance(symbol, list) else [symbol]
        results: List[str] = []
        
        for sym in symbols_list:
            if bars[sym]:
                results.extend([
                    f"Historical Crypto Bars for {sym} ({timeframe} timeframe):",
                    f"Total Records: {len(bars[sym])}",
                    ""
                ])
                
                for bar in bars[sym]:
                    if timeframe_obj.unit_value in [TimeFrameUnit.Minute, TimeFrameUnit.Hour]:
                        time_str = bar.timestamp.strftime('%Y-%m-%d %H:%M:%S') + " UTC"
                    else:
                        time_str = bar.timestamp.date()
                    results.append(f"Time: {time_str}, Open: ${bar.open:.6f}, High: ${bar.high:.6f}, Low: ${bar.low:.6f}, Close: ${bar.close:.6f}, Volume: {bar.volume}")
                
                results.append("")
                if len(symbols_list) > 1:
                    results.append("")  # Separator between symbols
            else:
                results.append(f"No bar data found for {sym} with {timeframe} timeframe in the specified time range.")
        
        if results:
            return "\n".join(results)
        else:
            return f"No bar data found for {symbol} with {timeframe} timeframe in the specified time range."
    except Exception as e:
        return f"Error fetching historical crypto data for {symbol}: {str(e)}"

@mcp.tool()
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
) -> str:
    """
    Retrieves and formats historical quote data for a cryptocurrency.
    
    Args:
        symbol (Union[str, List[str]]): Crypto symbol(s) (e.g., 'BTC/USD', 'ETH/USD' or ['BTC/USD', 'ETH/USD'])
        days (int): Number of days to look back (default: 0, ignored if start is provided)
        hours (int): Number of hours to look back (default: 0, ignored if start is provided)
        minutes (int): Number of minutes to look back (default: 15, ignored if start is provided)
        limit (Optional[int]): Maximum number of quotes to return (optional)
        start (Optional[str]): Start time in ISO format (e.g., "2023-01-01T09:30:00" or "2023-01-01")
        end (Optional[str]): End time in ISO format (e.g., "2023-01-01T16:00:00" or "2023-01-01")
        feed (CryptoFeed): The crypto data feed to retrieve from (default: US)
        tz (str): Timezone for naive datetime strings (default: "America/New_York")
            Supported: "UTC", "ET", "EST", "EDT", "America/New_York"
    
    Returns:
        str: Formatted string containing historical crypto quote data with timestamps, bid/ask prices and sizes
    """
    _ensure_clients()
    try:
        # Set default limit if not provided
        if limit is None:
            limit = 1000

        # Parse start/end times or calculate from days
        start_time = None
        end_time = None
        now_utc = datetime.now(timezone.utc)  # Capture once for consistency
        
        if start:
            try:
                start_time = _parse_iso_datetime(start, default_timezone=tz)
            except ValueError as e:
                return f"Error: {str(e)}"
        else:
            # Calculate start time based on days, hours, or minutes (priority order)
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
                return f"Error: {str(e)}"
        else:
            end_time = None 
        
        # Create the request object
        request_params = CryptoQuoteRequest(
            symbol_or_symbols=[symbol] if isinstance(symbol, str) else symbol,
            start=start_time,
            end=end_time,
            limit=limit
        )
        
        quotes = crypto_historical_data_client.get_crypto_quotes(request_params, feed=feed)

        symbols_list = symbol if isinstance(symbol, list) else [symbol]
        results: List[str] = []

        mapping_quotes = getattr(quotes, 'data', None) or quotes
        for sym in symbols_list:
            sym_quotes = mapping_quotes.get(sym) if hasattr(mapping_quotes, 'get') else None
            if not sym_quotes:
                results.append(f"No historical crypto quotes found for {sym} in the specified time range.")
                continue

            results.extend([
                f"Historical Crypto Quotes for {sym}:", f"Total Records: {len(sym_quotes)}",""])
            
            for quote in sym_quotes:
                results.extend([
                    f"Timestamp: {quote.timestamp} UTC",
                    f"  Bid Price: ${quote.bid_price:.6f}",
                    f"  Bid Size: {quote.bid_size:.6f}",
                    f"  Ask Price: ${quote.ask_price:.6f}",
                    f"  Ask Size: {quote.ask_size:.6f}",
                    ""
                ])

        return "\n".join(results)
    except Exception as e:
        return f"Error fetching historical crypto quotes for {symbol}: {str(e)}"

@mcp.tool()
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
) -> str:
    """
    Retrieves and formats historical trade prints for a cryptocurrency.

    Args:
        symbol (Union[str, List[str]]): Crypto symbol(s) (e.g., 'BTC/USD' or ['BTC/USD','ETH/USD'])
        days (int): Number of days to look back (default: 0, ignored if start is provided)
        hours (int): Number of hours to look back (default: 0, ignored if start is provided)
        minutes (int): Number of minutes to look back (default: 15, ignored if start is provided)
        limit (Optional[int]): Maximum number of trades to return
        start (Optional[str]): ISO start time (e.g., "2023-01-01T09:30:00")
        end (Optional[str]): ISO end time (e.g., "2023-01-01T16:00:00")
        sort (Optional[str]): 'asc' or 'desc' chronological order
        feed (CryptoFeed): Crypto data feed (default: US)
        tz (str): Timezone for naive datetime strings (default: "America/New_York")
            Supported: "UTC", "ET", "EST", "EDT", "America/New_York"

    Returns:
        str: Formatted trade history
    """
    _ensure_clients()
    try:
        # Set default limit if not provided
        if limit is None:
            limit = 1000
        
        # Capture current time once for consistency
        now_utc = datetime.now(timezone.utc)
        
        # Handle start time: use provided start or calculate from days/hours/minutes
        if start:
            try:
                start_time = _parse_iso_datetime(start, default_timezone=tz)
            except ValueError as e:
                return f"Error: {str(e)}"
        else:
            # Calculate start time based on days, hours, or minutes (priority order)
            if days > 0:
                start_time = now_utc - timedelta(days=days)
            elif hours > 0:
                start_time = now_utc - timedelta(hours=hours)
            elif minutes > 0:
                start_time = now_utc - timedelta(minutes=minutes)
        
        # Handle end time: use provided end or default to now
        if end:
            try:
                end_time = _parse_iso_datetime(end, default_timezone=tz)
            except ValueError as e:
                return f"Error: {str(e)}"
        else:
            end_time = None

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
            symbol_or_symbols=[symbol] if isinstance(symbol, str) else symbol,
            start=start_time,
            end=end_time,
            limit=limit,
            sort=sort_enum,
        )

        trades = crypto_historical_data_client.get_crypto_trades(request_params, feed=feed)

        symbols_list = symbol if isinstance(symbol, list) else [symbol]
        results: List[str] = []

        mapping_trades = getattr(trades, 'data', None) or trades
        for sym in symbols_list:
            sym_trades = mapping_trades.get(sym) if hasattr(mapping_trades, 'get') else None
            if not sym_trades:
                results.append(f"No historical crypto trades found for {sym} in the specified time range.")
                continue
            
            results.extend([
                f"Historical Crypto Trades for {sym}:",
                f"Total Records: {len(sym_trades)}",
                ""
            ])
            
            for t in sym_trades:
                time_str = t.timestamp.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3] + " UTC"
                line = f"Time: {time_str}, Price: ${t.price:.6f}, Size: {t.size}"
                if hasattr(t, 'exchange') and t.exchange:
                    line += f", Exchange: {t.exchange}"
                results.append(line)
            
            results.append("")
            if len(symbols_list) > 1:
                results.append("")  # Separator between symbols

        return "\n".join(results)
    except Exception as e:
        return f"Error fetching historical crypto trades for {symbol}: {str(e)}"

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
    underlying_symbols: Union[str, List[str]],
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
        underlying_symbols (Union[str, List[str]]): Underlying asset symbol(s) (e.g., 'SPY', 'AAPL' or ['SPY', 'AAPL'])
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
        get_option_contracts(["SPY", "AAPL"], expiration_date_gte=date(2025,9,1), expiration_date_lte=date(2025,9,5))
    """
    _ensure_clients()
    try:
        # Convert to list if single symbol
        symbols_list = [underlying_symbols] if isinstance(underlying_symbols, str) else list(underlying_symbols)
        if not symbols_list:
            return "No symbols provided."
        
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
            underlying_symbols=symbols_list,
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
            symbols_str = ", ".join(symbols_list)
            return f"No option contracts found for {symbols_str}."
        
        # Format results
        contracts = response.option_contracts
        result: List[str] = []
        
        for contract in contracts:
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
                ""
            ])
        
        return "\n".join(result)
        
    except Exception as e:
        return f"Error: {str(e)}"

@mcp.tool()
async def get_option_latest_quote(
    symbol_or_symbols: Union[str, List[str]],
    feed: Optional[OptionsFeed] = OptionsFeed.INDICATIVE
) -> str:
    """
    Retrieves and formats the latest quote for one or more option contracts. This endpoint returns real-time
    pricing and market data, including bid/ask prices, sizes, and exchange information.
    
    Args:
        symbol_or_symbols (Union[str, List[str]]): Option contract symbol(s) (e.g., 'AAPL230616C00150000' or ['AAPL230616C00150000', 'MSFT230616P00300000'])
        feed (Optional[OptionsFeed]): The source feed of the data (opra or indicative). (default: INDICATIVE)
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
        symbols_list = [symbol_or_symbols] if isinstance(symbol_or_symbols, str) else list(symbol_or_symbols)
        if not symbols_list:
            return "No symbols provided."
        
        # Create the request object
        request = OptionLatestQuoteRequest(
            symbol_or_symbols=symbol_or_symbols,
            feed=feed
        )
        
        # Get the latest quote
        quotes = option_historical_data_client.get_option_latest_quote(request)
        
        results: List[str] = []
        for symbol in symbols_list:
            quote = quotes.get(symbol)
            if not quote:
                results.append(f"No quote data found for {symbol}.")
                continue
            
            results.extend([
                f"Symbol: {symbol}",
                f"Ask Price: ${float(quote.ask_price):.2f}",
                f"Ask Size: {quote.ask_size}",
                f"Ask Exchange: {quote.ask_exchange}",
                f"Bid Price: ${float(quote.bid_price):.2f}",
                f"Bid Size: {quote.bid_size}",
                f"Bid Exchange: {quote.bid_exchange}",
                f"Conditions: {quote.conditions}",
                f"Tape: {quote.tape}",
                f"Timestamp: {quote.timestamp}",
                ""
            ])
        
        results.append(MARKET_DATA_DISCLAIMER)
        return "\n".join(results).strip()
    except Exception as e:
        symbols_list = [symbol_or_symbols] if isinstance(symbol_or_symbols, str) else list(symbol_or_symbols)
        requested = ", ".join(symbols_list) if symbols_list else ""
        return f"Error fetching option quote for {requested}: {str(e)}"


@mcp.tool()
async def get_option_snapshot(symbol_or_symbols: Union[str, List[str]], feed: Optional[OptionsFeed] = OptionsFeed.INDICATIVE) -> str:
    """
    Retrieves comprehensive snapshots of option contracts including latest trade, quote, implied volatility, and Greeks.
    This endpoint provides a complete view of an option's current market state and theoretical values.
    
    Args:
        symbol_or_symbols (Union[str, List[str]]): Single option symbol or list of option symbols
            (e.g., 'AAPL250613P00205000')
        feed (Optional[OptionsFeed]): The source feed of the data (opra or indicative). (default: INDICATIVE)
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
        
        result += MARKET_DATA_DISCLAIMER
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
