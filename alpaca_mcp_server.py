import os
import re
import sys
import time
import argparse
import pandas as pd
from datetime import datetime, timedelta, date
from typing import Dict, Any, List, Optional, Union

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
    CryptoLatestQuoteRequest
)

from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import (
    AssetStatus,
    ContractType,
    OrderClass,
    OrderSide,
    OrderType,
    PositionIntent,
    QueryOrderStatus,
    TimeInForce,
)
from alpaca.trading.models import Order
from alpaca.trading.requests import (
    ClosePositionRequest,
    CreateWatchlistRequest,
    GetAssetsRequest,
    GetCalendarRequest,
    GetOptionContractsRequest,
    GetOrdersRequest,
    GetPortfolioHistoryRequest,
    LimitOrderRequest,
    MarketOrderRequest,
    OptionLegRequest,
    StopLimitOrderRequest,
    StopOrderRequest,
    TrailingStopOrderRequest,
    UpdateWatchlistRequest,
)

from mcp.server.fastmcp import FastMCP

# Configure Python path for local imports
current_dir = os.path.dirname(os.path.abspath(__file__))
github_core_path = os.path.join(current_dir, '.github', 'core')
if github_core_path not in sys.path:
    sys.path.insert(0, github_core_path)
# Import the UserAgentMixin
from user_agent_mixin import UserAgentMixin
# Define new classes using the mixin
class TradingClientSigned(UserAgentMixin, TradingClient): pass
class StockHistoricalDataClientSigned(UserAgentMixin, StockHistoricalDataClient): pass
class OptionHistoricalDataClientSigned(UserAgentMixin, OptionHistoricalDataClient): pass
class CorporateActionsClientSigned(UserAgentMixin, CorporateActionsClient): pass
class CryptoHistoricalDataClientSigned(UserAgentMixin, CryptoHistoricalDataClient): pass

def detect_pycharm_environment():
    """
    Detect if we're running in PyCharm using environment variable.
    Set MCP_CLIENT=pycharm in your PyCharm MCP configuration.
    """
    mcp_client = os.getenv("MCP_CLIENT", "").lower()
    return mcp_client == "pycharm"

def parse_arguments():
    """Parse command line arguments for transport configuration."""
    parser = argparse.ArgumentParser(description="Alpaca MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "http", "sse"],
        default="stdio",
        help="Transport method to use (default: stdio). Note: WebSocket not supported, use HTTP for remote connections"
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host to bind the server to for HTTP/SSE transport (default: 127.0.0.1)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to bind the server to for HTTP/SSE transport (default: 8000)"
    )
    return parser.parse_args()

def setup_transport_config(args):
    """Setup transport configuration based on command line arguments."""
    if args.transport == "http":
        return {
            "transport": "http",
            "host": args.host,
            "port": args.port
        }
    elif args.transport == "sse":
        print(f"Warning: SSE transport is deprecated. Consider using HTTP transport instead.")
        return {
            "transport": "sse",
            "host": args.host,
            "port": args.port
        }
    else:
        return {
            "transport": "stdio"
        }

# Default args for when module is imported (not run directly)
class DefaultArgs:
    def __init__(self):
        self.transport = "stdio"
        # host and port are only set when needed (via argument parsing)

# Only parse arguments when running as main script, use defaults when imported
args = DefaultArgs()

# Initialize Alpaca clients using environment variables
# Import our .env file within the same directory
load_dotenv()

TRADE_API_KEY = os.getenv("ALPACA_API_KEY")
TRADE_API_SECRET = os.getenv("ALPACA_SECRET_KEY")
ALPACA_PAPER_TRADE = os.getenv("ALPACA_PAPER_TRADE", "True")
TRADE_API_URL = os.getenv("TRADE_API_URL")
TRADE_API_WSS = os.getenv("TRADE_API_WSS")
DATA_API_URL = os.getenv("DATA_API_URL")
STREAM_DATA_WSS = os.getenv("STREAM_DATA_WSS")
DEBUG = os.getenv("DEBUG", "False")

# Initialize FastMCP server with intelligent log level detection
is_pycharm = detect_pycharm_environment()
log_level = "ERROR" if is_pycharm else "INFO"
log_level = "DEBUG" if DEBUG.lower() == "true" else log_level

# Optional: Print detection result for debugging (only in non-PyCharm environments)
# Only print when running as main script to avoid noise when imported
if not is_pycharm and __name__ == "__main__":
    print(f"MCP Server starting with transport={args.transport}, log_level={log_level} (PyCharm detected: {is_pycharm})")

mcp = FastMCP("alpaca-trading", log_level=log_level)


# Check if keys are available
if not TRADE_API_KEY or not TRADE_API_SECRET:
    raise ValueError("Alpaca API credentials not found in environment variables.")

# Convert string to boolean
ALPACA_PAPER_TRADE_BOOL = ALPACA_PAPER_TRADE.lower() not in ['false', '0', 'no', 'off']

# Initialize clients
# For trading
trade_client = TradingClientSigned(TRADE_API_KEY, TRADE_API_SECRET, paper=ALPACA_PAPER_TRADE_BOOL)
# For historical market data
stock_historical_data_client = StockHistoricalDataClientSigned(TRADE_API_KEY, TRADE_API_SECRET)
# For streaming market data
stock_data_stream_client = StockDataStream(TRADE_API_KEY, TRADE_API_SECRET, url_override=STREAM_DATA_WSS)
# For option historical data
option_historical_data_client = OptionHistoricalDataClientSigned(api_key=TRADE_API_KEY, secret_key=TRADE_API_SECRET)
# For corporate actions data
corporate_actions_client = CorporateActionsClientSigned(api_key=TRADE_API_KEY, secret_key=TRADE_API_SECRET)
# For crypto historical data
crypto_historical_data_client = CryptoHistoricalDataClientSigned(api_key=TRADE_API_KEY, secret_key=TRADE_API_SECRET)

# ----------------------------------------------------------------------------
# Configure path for alpacaWheel option screener imports
# ----------------------------------------------------------------------------
ALPACA_WHEEL_PATH = os.getenv('ALPACA_WHEEL_PATH', '/Users/johnodwyer/PycharmProjects/alpacaWheel')
if os.path.exists(ALPACA_WHEEL_PATH):
    if ALPACA_WHEEL_PATH not in sys.path:
        sys.path.insert(0, ALPACA_WHEEL_PATH)
    try:
        from alpaca_options.option_screener_functions import (
            get_df_filtered_options,
            get_bollinger_bands,
            get_otm_options_by_expiration,
            initialize_alpaca_clients
        )
        from alpaca_options.option_execution_functions import (
            buy_longer_put_then_sell_put,
            buy_longer_call_then_sell_call,
            sell_put_option,
            buy_put_option,
            sell_call_option,
            buy_call_option
        )
        from alpaca_options.directional_integration import (
            get_df_filtered_options_with_directional
        )
        OPTION_SCREENER_AVAILABLE = True
    except ImportError as e:
        OPTION_SCREENER_AVAILABLE = False
        print(f"Warning: Could not import option screener functions: {e}")
else:
    OPTION_SCREENER_AVAILABLE = False
    print(f"Warning: ALPACA_WHEEL_PATH not found: {ALPACA_WHEEL_PATH}")

# ----------------------------------------------------------------------------
# Centralized date parsing helpers
# ----------------------------------------------------------------------------
def _parse_iso_datetime(value: Optional[str]) -> Optional[datetime]:
    """Parse an ISO-like datetime string into a datetime.

    Supports:
      - Strings ending with 'Z' by converting to '+00:00'
      - Date-only strings 'YYYY-MM-DD' by assuming midnight
    Returns:
      - datetime when a non-empty valid string is provided
      - None when value is falsy or empty
    Raises:
      - ValueError if a non-empty string is provided but cannot be parsed
    """
    if not value:
        return None
    s = value.strip()
    if not s:
        return None
    # Allow pure dates
    if re.match(r'^\d{4}-\d{2}-\d{2}$', s):
        s = s + 'T00:00:00'
    s = s.replace('Z', '+00:00')
    try:
        return datetime.fromisoformat(s)
    except Exception as e:
        raise ValueError(f"Invalid ISO datetime: {value}") from e


def _parse_date_ymd(value: str) -> date:
    """Parse 'YYYY-MM-DD' into a date object.
    Raises ValueError on invalid input."""
    return datetime.strptime(value, '%Y-%m-%d').date()


def _month_name_to_number(name: str) -> int:
    """Convert month name to month number. Accepts full and abbreviated names."""
    try:
        return datetime.strptime(name.title(), '%B').month
    except ValueError:
        return datetime.strptime(name.title(), '%b').month

# ============================================================================
# Account Information Tools
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
async def get_positions() -> str:
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

@mcp.tool()
async def get_portfolio_history(
    period: Optional[str] = None,
    timeframe: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    extended_hours: Optional[bool] = None
) -> str:
    """
    Retrieves and formats portfolio history including equity values, profit/loss, and performance metrics over time.

    Args:
        period (Optional[str]): Duration of data as number + unit (e.g., "1D", "1W", "1M", "3M", "1A").
            Units: D=day, W=week, M=month, A=year. Default: "1M"
        timeframe (Optional[str]): Resolution of time windows - "1Min", "5Min", "15Min", "1H", or "1D".
            Auto-selected if omitted: 1Min for <7 days, 15Min for <30 days, 1D otherwise
        start (Optional[str]): Start timestamp in ISO format (e.g., "2024-01-01" or "2024-01-01T09:30:00")
        end (Optional[str]): End timestamp in ISO format (e.g., "2024-12-31" or "2024-12-31T16:00:00")
        extended_hours (Optional[bool]): Include extended hours data (only effective for timeframe < 1D)

    Returns:
        str: Formatted string containing:
            - Time period and resolution
            - Equity values over time
            - Profit/loss in dollars and percentage
            - Base value for P&L calculations
            - Summary statistics (start/end equity, total P&L, return %)

    Examples:
        - Last month daily: period="1M", timeframe="1D"
        - Last week hourly: period="1W", timeframe="1H"
        - Custom range: start="2024-01-01", end="2024-12-31", timeframe="1D"
        - Intraday with pre/post market: period="1D", timeframe="5Min", extended_hours=True
    """
    try:
        # Parse datetime strings if provided
        start_dt = None
        end_dt = None

        if start:
            try:
                start_dt = datetime.fromisoformat(start.replace('Z', '+00:00'))
            except ValueError:
                return f"Error: Invalid start time format '{start}'. Use ISO format like '2024-01-01' or '2024-01-01T09:30:00'"

        if end:
            try:
                end_dt = datetime.fromisoformat(end.replace('Z', '+00:00'))
            except ValueError:
                return f"Error: Invalid end time format '{end}'. Use ISO format like '2024-12-31' or '2024-12-31T16:00:00'"

        # Create request with provided parameters
        request = GetPortfolioHistoryRequest(
            period=period,
            timeframe=timeframe,
            start=start_dt,
            end=end_dt,
            extended_hours=extended_hours
        )

        # Get portfolio history
        history = trade_client.get_portfolio_history(request)

        if not history.timestamp or len(history.timestamp) == 0:
            return "No portfolio history data available for the specified period."

        # Convert timestamps to readable format
        timestamps = [datetime.fromtimestamp(ts) for ts in history.timestamp]

        # Build formatted response
        result = f"""
Portfolio History:
==================
Period: {period or 'default (1M)'}
Timeframe: {history.timeframe}
Data Points: {len(history.timestamp)}
Time Range: {timestamps[0].strftime('%Y-%m-%d %H:%M')} to {timestamps[-1].strftime('%Y-%m-%d %H:%M')}
"""

        if history.base_value is not None:
            result += f"Base Value: ${history.base_value:.2f}\n"

        result += "\nEquity & P/L Over Time:\n"
        result += "-" * 80 + "\n"

        # Show data points (limit to reasonable number for readability)
        max_display = 50
        step = max(1, len(timestamps) // max_display)

        for i in range(0, len(timestamps), step):
            timestamp = timestamps[i]
            equity = history.equity[i]
            pl = history.profit_loss[i]
            pl_pct = history.profit_loss_pct[i]

            # Format based on timeframe
            if history.timeframe in ['1Min', '5Min', '15Min', '1H']:
                time_str = timestamp.strftime('%Y-%m-%d %H:%M')
            else:
                time_str = timestamp.strftime('%Y-%m-%d')

            pl_pct_str = f"{pl_pct:.2%}" if pl_pct is not None else "N/A"
            result += f"{time_str}: Equity=${equity:.2f}, P/L=${pl:+.2f} ({pl_pct_str})\n"

        # Add summary statistics
        start_equity = history.equity[0]
        end_equity = history.equity[-1]
        total_pl = end_equity - start_equity
        total_pl_pct = (total_pl / start_equity * 100) if start_equity != 0 else 0

        result += "\n" + "=" * 80 + "\n"
        result += f"""
Summary Statistics:
-------------------
Starting Equity: ${start_equity:.2f}
Ending Equity: ${end_equity:.2f}
Total P/L: ${total_pl:+.2f} ({total_pl_pct:+.2f}%)
Highest Equity: ${max(history.equity):.2f}
Lowest Equity: ${min(history.equity):.2f}
"""

        return result

    except APIError as api_error:
        return f"API Error fetching portfolio history: {str(api_error)}"
    except Exception as e:
        return f"Error fetching portfolio history: {str(e)}"

# ============================================================================
# Stock Market Data Tools
# ============================================================================

@mcp.tool()
async def get_stock_quote(symbol_or_symbols: Union[str, List[str]]) -> str:
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

# ============================================================================
# Stock Market Data Tools - Stock Snapshot Data with Helper Functions
# ============================================================================

def _format_ohlcv_bar(bar, bar_type: str, include_time: bool = True) -> str:
    """Helper function to format OHLCV bar data consistently."""
    if not bar:
        return ""
    
    time_format = '%Y-%m-%d %H:%M:%S %Z' if include_time else '%Y-%m-%d'
    time_label = "Timestamp" if include_time else "Date"
    
    return f"""{bar_type}:
  Open: ${bar.open:.2f}, High: ${bar.high:.2f}, Low: ${bar.low:.2f}, Close: ${bar.close:.2f}
  Volume: {bar.volume:,}, {time_label}: {bar.timestamp.strftime(time_format)}

"""

def _format_quote_data(quote) -> str:
    """Helper function to format quote data consistently."""
    if not quote:
        return ""
    
    return f"""Latest Quote:
  Bid: ${quote.bid_price:.2f} x {quote.bid_size}, Ask: ${quote.ask_price:.2f} x {quote.ask_size}
  Timestamp: {quote.timestamp.strftime('%Y-%m-%d %H:%M:%S %Z')}

"""

def _format_trade_data(trade) -> str:
    """Helper function to format trade data consistently."""
    if not trade:
        return ""
    
    optional_fields = []
    if hasattr(trade, 'exchange') and trade.exchange:
        optional_fields.append(f"Exchange: {trade.exchange}")
    if hasattr(trade, 'conditions') and trade.conditions:
        optional_fields.append(f"Conditions: {trade.conditions}")
    if hasattr(trade, 'id') and trade.id:
        optional_fields.append(f"ID: {trade.id}")
    
    optional_str = f", {', '.join(optional_fields)}" if optional_fields else ""
    
    return f"""Latest Trade:
  Price: ${trade.price:.2f}, Size: {trade.size}{optional_str}
  Timestamp: {trade.timestamp.strftime('%Y-%m-%d %H:%M:%S %Z')}

"""

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
# CryptoMarket Data Tools
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
            elif timeframe_obj.unit_value in [TimeFrameUnit.Minute, TimeFrameUnit.Hour]:
                # For intraday timeframes without limit, use a reasonable default
                if timeframe_obj.unit_value == TimeFrameUnit.Minute:
                    # Default to last 2 hours for minute timeframes
                    start_time = datetime.now() - timedelta(hours=2)
                elif timeframe_obj.unit_value == TimeFrameUnit.Hour:
                    # Default to last 24 hours for hour timeframes
                    start_time = datetime.now() - timedelta(hours=24)
            else:
                # Fall back to days parameter for daily+ timeframes
                start_time = datetime.now() - timedelta(days=days)
        if not end_time:
            end_time = datetime.now()
        
        request_params = CryptoBarsRequest(
            symbol_or_symbols=symbol,
            timeframe=timeframe_obj,
            start=start_time,
            end=end_time,
            limit=limit
        )
        
        bars = crypto_historical_data_client.get_crypto_bars(request_params, feed=feed)
        
        if bars[symbol]:
            time_range = f"{start_time.strftime('%Y-%m-%d %H:%M')} to {end_time.strftime('%Y-%m-%d %H:%M')}"
            result = f"Historical Crypto Data for {symbol} ({timeframe} bars, {time_range}):\n"
            result += "---------------------------------------------------\n"
            
            for bar in bars[symbol]:
                # Format timestamp based on timeframe unit
                if timeframe_obj.unit_value in [TimeFrameUnit.Minute, TimeFrameUnit.Hour]:
                    time_str = bar.timestamp.strftime('%Y-%m-%d %H:%M:%S')
                else:
                    time_str = bar.timestamp.date()
                
                result += f"Time: {time_str}, Open: ${bar.open:.6f}, High: ${bar.high:.6f}, Low: ${bar.low:.6f}, Close: ${bar.close:.6f}, Volume: {bar.volume}\n"
            
            return result
        else:
            return f"No historical crypto data found for {symbol} with {timeframe} timeframe in the specified time range."
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
        
        # Use the exact same simple pattern as crypto bars
        if quotes[symbol]:
            time_range = f"{start_time.strftime('%Y-%m-%d %H:%M')} to {end_time.strftime('%Y-%m-%d %H:%M')}"
            result = f"Historical Crypto Quotes for {symbol} ({time_range}):\n"
            result += "---------------------------------------------------\n"
            
            for quote in quotes[symbol]:
                time_str = quote.timestamp.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]  # Include milliseconds
                result += f"Time: {time_str}, Bid: ${quote.bid_price:.6f} (Size: {quote.bid_size:.6f}), Ask: ${quote.ask_price:.6f} (Size: {quote.ask_size:.6f})\n"
            
            return result
        else:
            return f"No historical crypto quotes found for {symbol} in the specified time range."
    except Exception as e:
        return f"Error fetching historical crypto quotes for {symbol}: {str(e)}"

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
async def cancel_all_orders() -> str:
    """
    Cancel all open orders.
    
    Returns:
        A formatted string containing the status of each cancelled order.
    """
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

# =======================================================================================
# Position Management Tools
# Ref: https://alpaca.markets/sdks/python/api_reference/trading/positions.html#positions
# =======================================================================================

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
    try:
        trade_client.exercise_options_position(symbol_or_contract_id=symbol_or_contract_id)
        return f"Successfully submitted exercise request for option contract: {symbol_or_contract_id}"
    except Exception as e:
        return f"Error exercising option contract '{symbol_or_contract_id}': {str(e)}"


# ============================================================================
# Asset Information Tools
# ============================================================================

@mcp.tool()
async def get_asset_info(symbol: str) -> str:
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
    try:
        watchlist_data = CreateWatchlistRequest(name=name, symbols=symbols)
        watchlist = trade_client.create_watchlist(watchlist_data)
        return f"Watchlist '{name}' created successfully with {len(symbols)} symbols."
    except Exception as e:
        return f"Error creating watchlist: {str(e)}"

@mcp.tool()
async def get_watchlists() -> str:
    """Get all watchlists for the account."""
    try:
        watchlists = trade_client.get_watchlists()
        result = "Watchlists:\n------------\n"
        for wl in watchlists:
            result += f"Name: {wl.name}\n"
            result += f"ID: {wl.id}\n"
            result += f"Created: {wl.created_at}\n"
            result += f"Updated: {wl.updated_at}\n"
            # Use wl.symbols, fallback to empty list if missing
            result += f"Symbols: {', '.join(getattr(wl, 'symbols', []) or [])}\n\n"
        return result
    except Exception as e:
        return f"Error fetching watchlists: {str(e)}"

@mcp.tool()
async def update_watchlist(watchlist_id: str, name: str = None, symbols: List[str] = None) -> str:
    """Update an existing watchlist."""
    try:
        update_request = UpdateWatchlistRequest(name=name, symbols=symbols)
        watchlist = trade_client.update_watchlist_by_id(watchlist_id, update_request)
        return f"Watchlist updated successfully: {watchlist.name}"
    except Exception as e:
        return f"Error updating watchlist: {str(e)}"

# ============================================================================
# Market Information Tools
# ============================================================================

@mcp.tool()
async def get_market_clock() -> str:
    """
    Retrieves and formats current market status and next open/close times.
    
    Returns:
        str: Formatted string containing:
            - Current Time
            - Market Open Status
            - Next Open Time
            - Next Close Time
    """
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

@mcp.tool()
async def get_market_calendar(start_date: str, end_date: str) -> str:
    """
    Retrieves and formats market calendar for specified date range.
    
    Args:
        start_date (str): Start date in YYYY-MM-DD format
        end_date (str): End date in YYYY-MM-DD format
    
    Returns:
        str: Formatted string containing market calendar information
    """
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
# Corporate Actions Tools
# ============================================================================

@mcp.tool()
async def get_corporate_announcements(
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
# Options Trading Helper Functions
# ============================================================================

def _parse_expiration_expression(expression: str) -> Dict[str, Any]:
    """
    Parse natural language expiration expressions into date parameters.
    
    Args:
        expression (str): Natural language expression like "week of September 7, 2025"
    
    Returns:
        Dict[str, Any]: Parsed parameters or error message
    """
    import re
    from datetime import datetime, timedelta
    
    expression = expression.strip().lower()
    
    # Pattern for "week of [date]"
    week_pattern = r'week\s+of\s+(\w+)\s+(\d{1,2}),?\s+(\d{4})'
    week_match = re.search(week_pattern, expression)
    
    if week_match:
        month_name, day_str, year_str = week_match.groups()
        try:
            # Parse the date
            month_num = _month_name_to_number(month_name)
            day = int(day_str)
            year = int(year_str)
            
            # Create the anchor date
            anchor_date = datetime(year, month_num, day).date()
            
            # Calculate the week range (Monday to Friday trading days)
            # Find the Monday of the week containing the anchor date
            days_since_monday = anchor_date.weekday()  # Monday=0, Sunday=6
            week_start = anchor_date - timedelta(days=days_since_monday)  # Go to Monday
            week_end = week_start + timedelta(days=4)  # Friday
            
            return {
                'expiration_date_gte': week_start,
                'expiration_date_lte': week_end,
                'description': f"week of {month_name.title()} {day}, {year}"
            }
            
        except (ValueError, AttributeError) as e:
            return {'error': f"Invalid date in expression: {str(e)}"}
    
    # Pattern for "month of [month] [year]"
    month_pattern = r'month\s+of\s+(\w+)\s+(\d{4})'
    month_match = re.search(month_pattern, expression)
    
    if month_match:
        month_name, year_str = month_match.groups()
        try:
            month_num = _month_name_to_number(month_name)
            year = int(year_str)
            
            start_date = datetime(year, month_num, 1).date()
            if month_num == 12:
                end_date = datetime(year + 1, 1, 1).date() - timedelta(days=1)
            else:
                end_date = datetime(year, month_num + 1, 1).date() - timedelta(days=1)

            return {
                'expiration_date_gte': start_date,
                'expiration_date_lte': end_date,
                'description': f"month of {month_name.title()} {year}"
            }
            
        except (ValueError, AttributeError) as e:
            return {'error': f"Invalid month/year in expression: {str(e)}"}
    
    # Pattern for specific date like "September 7, 2025"
    date_pattern = r'(\w+)\s+(\d{1,2}),?\s+(\d{4})'
    date_match = re.search(date_pattern, expression)
    
    if date_match:
        month_name, day_str, year_str = date_match.groups()
        try:
            month_num = _month_name_to_number(month_name)
            day = int(day_str)
            year = int(year_str)
            
            specific_date = datetime(year, month_num, day).date()
            
            return {
                'expiration_date': specific_date,
                'description': f"{month_name.title()} {day}, {year}"
            }
            
        except (ValueError, AttributeError) as e:
            return {'error': f"Invalid date in expression: {str(e)}"}
    
    return {'error': f"Unable to parse expression '{expression}'. Supported formats: 'week of September 7, 2025', 'month of December 2025', 'September 7, 2025'"}

# ============================================================================
# Options Trading Tools
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
# Options Trading Helper Functions
# ============================================================================

def _validate_option_order_inputs(legs: List[Dict[str, Any]], quantity: int, time_in_force: Union[str, TimeInForce]) -> Optional[str]:
    """Validate inputs for option order placement."""
    if not legs:
        return "Error: No option legs provided"
    if len(legs) > 4:
        return "Error: Maximum of 4 legs allowed for option orders"
    if quantity <= 0:
        return "Error: Quantity must be positive"
    
    # Handle both string and enum inputs
    if isinstance(time_in_force, str):
        if time_in_force.lower() != "day":
            return "Error: Only 'day' time_in_force is supported for options trading"
    elif isinstance(time_in_force, TimeInForce):
        if time_in_force != TimeInForce.DAY:
            return "Error: Only DAY time_in_force is supported for options trading"
    else:
        return f"Error: Invalid time_in_force type: {type(time_in_force)}. Must be string or TimeInForce enum."
    
    return None

def _convert_order_class_string(order_class: Optional[Union[str, OrderClass]]) -> Union[OrderClass, str]:
    """Convert order class string to enum if needed."""
    if order_class is None:
        return order_class
    if isinstance(order_class, OrderClass):
        return order_class
    if isinstance(order_class, str):
        order_class_upper = order_class.upper()
        class_mapping = {
            'SIMPLE': OrderClass.SIMPLE,
            'BRACKET': OrderClass.BRACKET,
            'OCO': OrderClass.OCO,
            'OTO': OrderClass.OTO,
            'MLEG': OrderClass.MLEG
        }
        if order_class_upper in class_mapping:
            return class_mapping[order_class_upper]
        else:
            return f"Invalid order class: {order_class}. Must be one of: simple, bracket, oco, oto, mleg"
    else:
        return f"Invalid order class type: {type(order_class)}. Must be string or OrderClass enum."

def _process_option_legs(legs: List[Dict[str, Any]]) -> Union[List[OptionLegRequest], str]:
    """Convert leg dictionaries to OptionLegRequest objects."""
    order_legs = []
    for leg in legs:
        # Validate ratio_qty
        if not isinstance(leg['ratio_qty'], int) or leg['ratio_qty'] <= 0:
            return f"Error: Invalid ratio_qty for leg {leg['symbol']}. Must be positive integer."
        
        # Convert side string to enum
        if leg['side'].lower() == "buy":
            order_side = OrderSide.BUY
        elif leg['side'].lower() == "sell":
            order_side = OrderSide.SELL
        else:
            return f"Invalid order side: {leg['side']}. Must be 'buy' or 'sell'."
        
        order_legs.append(OptionLegRequest(
            symbol=leg['symbol'],
            side=order_side,
            ratio_qty=leg['ratio_qty']
        ))
    return order_legs

def _create_option_market_order_request(
    order_legs: List[OptionLegRequest], 
    order_class: OrderClass, 
    quantity: int,
    time_in_force: TimeInForce,
    extended_hours: bool
) -> MarketOrderRequest:
    """Create the appropriate MarketOrderRequest based on order class."""
    if order_class == OrderClass.MLEG:
        return MarketOrderRequest(
            qty=quantity,
            order_class=order_class,
            time_in_force=time_in_force,
            extended_hours=extended_hours,
            client_order_id=f"mcp_opt_{int(time.time())}",
            type=OrderType.MARKET,
            legs=order_legs
        )
    else:
        # For single-leg orders
        return MarketOrderRequest(
            symbol=order_legs[0].symbol,
            qty=quantity,
            side=order_legs[0].side,
            order_class=order_class,
            time_in_force=time_in_force,
            extended_hours=extended_hours,
            client_order_id=f"mcp_opt_{int(time.time())}",
            type=OrderType.MARKET
        )

def _format_option_order_response(order: Order, order_class: OrderClass, order_legs: List[OptionLegRequest]) -> str:
    """Format the successful order response."""
    result = f"""
            Option Market Order Placed Successfully:
            --------------------------------------
            Order ID: {order.id}
            Client Order ID: {order.client_order_id}
            Order Class: {order.order_class}
            Order Type: {order.type}
            Time In Force: {order.time_in_force}
            Status: {order.status}
            Quantity: {order.qty}
            Created At: {order.created_at}
            Updated At: {order.updated_at}
            """
    
    if order_class == OrderClass.MLEG and order.legs:
        result += "\nLegs:\n"
        for leg in order.legs:
            result += f"""
                    Symbol: {leg.symbol}
                    Side: {leg.side}
                    Ratio Quantity: {leg.ratio_qty}
                    Status: {leg.status}
                    Asset Class: {leg.asset_class}
                    Created At: {leg.created_at}
                    Updated At: {leg.updated_at}
                    Filled Price: {leg.filled_avg_price if hasattr(leg, 'filled_avg_price') else 'Not filled'}
                    Filled Time: {leg.filled_at if hasattr(leg, 'filled_at') else 'Not filled'}
                    -------------------------
                    """
    else:
        result += f"""
                Symbol: {order.symbol}
                Side: {order_legs[0].side}
                Filled Price: {order.filled_avg_price if hasattr(order, 'filled_avg_price') else 'Not filled'}
                Filled Time: {order.filled_at if hasattr(order, 'filled_at') else 'Not filled'}
                -------------------------
                """
    
    return result

def _analyze_option_strategy_type(order_legs: List[OptionLegRequest], order_class: OrderClass) -> tuple[bool, bool, bool]:
    """Analyze the option strategy type for error handling."""
    is_short_straddle = False
    is_short_strangle = False
    is_short_calendar = False
    
    if order_class == OrderClass.MLEG and len(order_legs) == 2:
        both_short = order_legs[0].side == OrderSide.SELL and order_legs[1].side == OrderSide.SELL
        
        if both_short:
            # Check for short straddle (same strike, same expiration, both short)
            if (order_legs[0].symbol.split('C')[0] == order_legs[1].symbol.split('P')[0]):
                is_short_straddle = True
            else:
                is_short_strangle = True
                
            # Check for short calendar spread (same strike, different expirations, both short)
            leg1_type = 'C' if 'C' in order_legs[0].symbol else 'P'
            leg2_type = 'C' if 'C' in order_legs[1].symbol else 'P'
            
            if leg1_type == 'C' and leg2_type == 'C':
                leg1_exp = order_legs[0].symbol.split(leg1_type)[1][:6]
                leg2_exp = order_legs[1].symbol.split(leg2_type)[1][:6]
                if leg1_exp != leg2_exp:
                    is_short_calendar = True
                    is_short_strangle = False  # Override strangle detection
    
    return is_short_straddle, is_short_strangle, is_short_calendar

def _get_short_straddle_error_message() -> str:
    """Get error message for short straddle permission issues."""
    return """
    Error: Account not eligible to trade short straddles.
    
    This error occurs because short straddles require Level 4 options trading permission.
    A short straddle involves:
    - Selling a call option
    - Selling a put option
    - Both options have the same strike price and expiration
    
    Required Account Level:
    - Level 4 options trading permission is required
    - Please contact your broker to upgrade your account level if needed
    
    Alternative Strategies:
    - Consider using a long straddle instead
    - Use a debit spread strategy
    - Implement a covered call or cash-secured put
    """

def _get_short_strangle_error_message() -> str:
    """Get error message for short strangle permission issues."""
    return """
    Error: Account not eligible to trade short strangles.
    
    This error occurs because short strangles require Level 4 options trading permission.
    A short strangle involves:
    - Selling an out-of-the-money call option
    - Selling an out-of-the-money put option
    - Both options have the same expiration
    
    Required Account Level:
    - Level 4 options trading permission is required
    - Please contact your broker to upgrade your account level if needed
    
    Alternative Strategies:
    - Consider using a long strangle instead
    - Use a debit spread strategy
    - Implement a covered call or cash-secured put
    """

def _get_short_calendar_error_message() -> str:
    """Get error message for short calendar spread permission issues."""
    return """
    Error: Account not eligible to trade short calendar spreads.
    
    This error occurs because short calendar spreads require Level 4 options trading permission.
    A short calendar spread involves:
    - Selling a longer-term option
    - Selling a shorter-term option
    - Both options have the same strike price
    
    Required Account Level:
    - Level 4 options trading permission is required
    - Please contact your broker to upgrade your account level if needed
    
    Alternative Strategies:
    - Consider using a long calendar spread instead
    - Use a debit spread strategy
    - Implement a covered call or cash-secured put
    """

def _get_uncovered_options_error_message() -> str:
    """Get error message for uncovered options permission issues."""
    return """
    Error: Account not eligible to trade uncovered option contracts.
    
    This error occurs when attempting to place an order that could result in an uncovered position.
    Common scenarios include:
    1. Selling naked calls
    2. Calendar spreads where the short leg expires after the long leg
    3. Other strategies that could leave uncovered positions
    
    Required Account Level:
    - Level 4 options trading permission is required for uncovered options
    - Please contact your broker to upgrade your account level if needed
    
    Alternative Strategies:
    - Consider using covered calls instead of naked calls
    - Use debit spreads instead of calendar spreads
    - Ensure all positions are properly hedged
    """

def _handle_option_api_error(error_message: str, order_legs: List[OptionLegRequest], order_class: OrderClass) -> str:
    """Handle API errors with specific option strategy analysis."""
    if "40310000" in error_message and "not eligible to trade uncovered option contracts" in error_message:
        is_short_straddle, is_short_strangle, is_short_calendar = _analyze_option_strategy_type(order_legs, order_class)
        
        if is_short_straddle:
            return _get_short_straddle_error_message()
        elif is_short_strangle:
            return _get_short_strangle_error_message()
        elif is_short_calendar:
            return _get_short_calendar_error_message()
        else:
            return _get_uncovered_options_error_message()
    elif "403" in error_message:
        return f"""
        Error: Permission denied for option trading.
        
        Possible reasons:
        1. Insufficient account level for the requested strategy
        2. Account restrictions on option trading
        3. Missing required permissions
        
        Please check:
        1. Your account's option trading level
        2. Any specific restrictions on your account
        3. Required permissions for the strategy you're trying to implement
        
        Original error: {error_message}
        """
    else:
        return f"""
        Error placing option order: {error_message}
        
        Please check:
        1. All option symbols are valid
        2. Your account has sufficient buying power
        3. The market is open for trading
        4. Your account has the required permissions
        """

# ============================================================================
# Options Trading Tool
# ============================================================================

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


# ============================================================================
# Helper Functions and Utilities
# ============================================================================
# The following functions are internal helper functions used by the MCP tools
# for data parsing, validation, formatting, and other utility operations.
# ============================================================================

def parse_timeframe_with_enums(timeframe_str: str) -> Optional[TimeFrame]:
    """
    Parse timeframe string to Alpaca TimeFrame object using proper enumerations.
    Supports standard Alpaca formats and common natural language variations.
    
    Args:
        timeframe_str (str): Timeframe string (e.g., "1Min", "30 mins", "1 hour", "daily")
        
    Returns:
        Optional[TimeFrame]: Parsed TimeFrame object using TimeFrameUnit enums or None if invalid
        
    Reference:
        https://alpaca.markets/sdks/python/api_reference/data/timeframe.html#timeframeunit
    """
    
    try:
        if not timeframe_str or not isinstance(timeframe_str, str):
            return None
            
        timeframe_str = timeframe_str.strip()
        if not timeframe_str:
            return None
        
        # Use predefined TimeFrame objects for common cases (most efficient)
        predefined_timeframes = {
            "1Min": TimeFrame.Minute,
            "1Hour": TimeFrame.Hour, 
            "1Day": TimeFrame.Day,
            "1Week": TimeFrame.Week,
            "1Month": TimeFrame.Month
        }
        
        if timeframe_str in predefined_timeframes:
            return predefined_timeframes[timeframe_str]
        
        # Normalize input for flexible parsing
        normalized = re.sub(r'\s+', ' ', timeframe_str.lower().strip())
        
        # Common expressions that map directly to timeframes
        direct_mappings = {
            'half hour': (30, TimeFrameUnit.Minute),
            'quarter hour': (15, TimeFrameUnit.Minute),
            'hourly': (1, TimeFrameUnit.Hour),
            'daily': (1, TimeFrameUnit.Day),
            'weekly': (1, TimeFrameUnit.Week),
            'monthly': (1, TimeFrameUnit.Month)
        }
        
        if normalized in direct_mappings:
            amount, unit = direct_mappings[normalized]
            return TimeFrame(amount, unit)
        
        # Comprehensive pattern to handle most variations
        # Matches: number + unit (with optional spaces, hyphens, plurals)
        pattern = r'^(\d+)\s*[-\s]*\s*(min|minute|minutes|hr|hour|hours|day|days|week|weeks|month|months)s?$'
        match = re.match(pattern, normalized)
        
        if match:
            amount = int(match.group(1))
            unit_str = match.group(2)
            
            # Map unit strings to TimeFrameUnit enums
            unit_mapping = {
                'min': TimeFrameUnit.Minute, 'minute': TimeFrameUnit.Minute, 'minutes': TimeFrameUnit.Minute,
                'hr': TimeFrameUnit.Hour, 'hour': TimeFrameUnit.Hour, 'hours': TimeFrameUnit.Hour,
                'day': TimeFrameUnit.Day, 'days': TimeFrameUnit.Day,
                'week': TimeFrameUnit.Week, 'weeks': TimeFrameUnit.Week,
                'month': TimeFrameUnit.Month, 'months': TimeFrameUnit.Month
            }
            
            unit = unit_mapping.get(unit_str)
            if unit and _validate_amount(amount, unit):
                return TimeFrame(amount, unit)
        
        # Try case-insensitive standard Alpaca formats
        alpaca_pattern = r'^(\d+)(min|hour|day|week|month)s?$'
        match = re.match(alpaca_pattern, normalized)
        
        if match:
            amount = int(match.group(1))
            unit_str = match.group(2)
            
            unit_mapping = {
                'min': TimeFrameUnit.Minute,
                'hour': TimeFrameUnit.Hour,
                'day': TimeFrameUnit.Day,
                'week': TimeFrameUnit.Week,
                'month': TimeFrameUnit.Month
            }
            
            unit = unit_mapping.get(unit_str)
            if unit and _validate_amount(amount, unit):
                return TimeFrame(amount, unit)
            
        return None
        
    except (ValueError, AttributeError, TypeError):
        return None


def _validate_amount(amount: int, unit: TimeFrameUnit) -> bool:
    """
    Validate that the amount is reasonable for the given unit.
    """
    if amount <= 0:
        return False
        
    if unit == TimeFrameUnit.Minute and amount > 59:
        return False
    elif unit == TimeFrameUnit.Hour and amount > 23:
        return False
    elif unit in [TimeFrameUnit.Day, TimeFrameUnit.Week, TimeFrameUnit.Month] and amount > 365:
        return False
        
    return True


# ============================================================================
# OPTION SCREENER AND EXECUTION TOOLS
# ============================================================================

@mcp.tool()
async def screen_filtered_options(
    symbols: List[str],
    min_days: int = 15,
    max_days: int = 45,
    max_percent_otm: float = 60.0,
    min_percent_otm: float = 0.1,
    min_open_interest: int = 200,
    min_delta_put: float = -0.52,
    max_delta_put: float = -0.08,
    min_delta_call: float = 0.08,
    max_delta_call: float = 0.52,
    min_atr_multiplier: float = 0.5,
    max_atr_multiplier: float = 5.0,
    min_return_30_day: float = 2.0,
    max_spread_percent: float = 10.0,
    get_calls: bool = True,
    get_puts: bool = True
) -> str:
    """
    Screen and filter options based on comprehensive criteria including delta, ATR, open interest, and Bollinger Bands.

    Args:
        symbols: List of stock symbols to screen
        min_days: Minimum days to expiration (default: 15)
        max_days: Maximum days to expiration (default: 45)
        max_percent_otm: Maximum percent out of the money (default: 60.0)
        min_percent_otm: Minimum percent out of the money (default: 0.1)
        min_open_interest: Minimum open interest required (default: 200)
        min_delta_put: Minimum delta for puts (default: -0.52)
        max_delta_put: Maximum delta for puts (default: -0.08)
        min_delta_call: Minimum delta for calls (default: 0.08)
        max_delta_call: Maximum delta for calls (default: 0.52)
        min_atr_multiplier: Minimum ATR multiplier (default: 0.5)
        max_atr_multiplier: Maximum ATR multiplier (default: 5.0)
        min_return_30_day: Minimum 30-day annualized return percent (default: 2.0)
        max_spread_percent: Maximum bid-ask spread percent (default: 10.0)
        get_calls: Include call options (default: True)
        get_puts: Include put options (default: True)

    Returns:
        str: Formatted results with option details including:
            - Symbol and strike price
            - Days to expiration
            - Delta, implied volatility, and other Greeks
            - Bollinger Band signal (BULL/BEAR/NEUTRAL)
            - Return metrics and spreads
            - Earnings dates
    """
    if not OPTION_SCREENER_AVAILABLE:
        return "Error: Option screener functions are not available. Check ALPACA_WHEEL_PATH configuration."

    try:
        # Call the screening function from alpacaWheel
        symbol_df_results, no_result_symbols = get_df_filtered_options(
            symbols=symbols,
            trading_client=trade_client,
            stock_client=stock_historical_data_client,
            option_client=option_historical_data_client,
            min_days=min_days,
            max_days=max_days,
            max_percent_otm=max_percent_otm,
            min_percent_otm=min_percent_otm,
            min_open_interest=min_open_interest,
            min_delta_put=min_delta_put,
            max_delta_put=max_delta_put,
            min_delta_call=min_delta_call,
            max_delta_call=max_delta_call,
            min_atr_multiplier=min_atr_multiplier,
            max_atr_multiplier=max_atr_multiplier,
            min_return_30_day=min_return_30_day,
            max_spread_percent=max_spread_percent,
            get_calls=get_calls,
            get_puts=get_puts
        )

        # Format results
        result = f"Option Screening Results\n{'=' * 80}\n"
        result += f"Symbols evaluated: {', '.join(symbols)}\n"
        result += f"Symbols with no results: {', '.join(no_result_symbols) if no_result_symbols else 'None'}\n\n"

        for symbol, df in symbol_df_results:
            if not df.empty:
                earnings_date = df.iloc[0]['quarter_earnings_date']
                bb_signal = df.iloc[0]['bb_signal']
                bb_upper = df.iloc[0]['bb_upper']
                bb_middle = df.iloc[0]['bb_middle']
                bb_lower = df.iloc[0]['bb_lower']
                current_price = df.iloc[0]['underlying_price']

                result += f"\n{symbol} | Price: ${current_price:.2f} | Earnings: {earnings_date}\n"
                result += f"BB Signal: {bb_signal} | Upper: ${bb_upper:.2f} | Middle(MA): ${bb_middle:.2f} | Lower: ${bb_lower:.2f}\n"
                result += f"{'-' * 80}\n"

                # Show top 5 options for each symbol
                top_options = df.head(5)
                for _, row in top_options.iterrows():
                    result += f"  Symbol: {row['symbol']}\n"
                    result += f"  {row['type']:<4} ${row['strike_price']:<7.2f} "
                    result += f"Exp: {row['expiration_date']} "
                    result += f"DTE: {row['days_to_expiry']}d "
                    result += f"%OTM: {row['percent_otm']:<5.2f}%\n"

                    # Premium & Pricing (what you'd receive/pay)
                    result += f"    Premium: Bid=${row['bid_price']:.2f} " if pd.notna(row['bid_price']) else f"    Premium: Bid=N/A "
                    result += f"Mid=${row['mid_price']:.2f} " if pd.notna(row['mid_price']) else f"Mid=N/A "
                    result += f"Ask=${row['ask_price']:.2f} " if pd.notna(row['ask_price']) else f"Ask=N/A "
                    result += f"Spread={row['spread_percent']:.2f}%\n" if pd.notna(row['spread_percent']) else f"Spread=N/A\n"

                    # Returns & Risk
                    result += f"    Returns: 30-day={row['return_30_day']:.2f}% " if pd.notna(row['return_30_day']) else f"    Returns: 30-day=N/A "
                    result += f"Overall={row['overall_return']:.2f}%\n" if pd.notna(row['overall_return']) else f"Overall=N/A\n"

                    # Greeks (option sensitivities)
                    result += f"    Greeks: Delta={row['delta']:.3f} " if pd.notna(row['delta']) else f"    Greeks: Delta=N/A "
                    result += f"Gamma={row['gamma']:.4f} " if pd.notna(row['gamma']) else f"Gamma=N/A "
                    result += f"Theta={row['theta']:.3f} " if pd.notna(row['theta']) else f"Theta=N/A "
                    result += f"Vega={row['vega']:.3f} " if pd.notna(row['vega']) else f"Vega=N/A "
                    result += f"Rho={row['rho']:.4f}\n" if pd.notna(row['rho']) else f"Rho=N/A\n"

                    # Volatility & Liquidity
                    result += f"    Vol/Liquidity: IV={row['implied_volatility']:.1%} " if pd.notna(row['implied_volatility']) else f"    Vol/Liquidity: IV=N/A "
                    result += f"ATR(14d)=${row['atr_14d_o90d']:.2f} " if pd.notna(row['atr_14d_o90d']) else f"ATR(14d)=N/A "
                    result += f"OI={int(row['open_interest'])} " if pd.notna(row['open_interest']) else f"OI=N/A "
                    result += f"BidSize={int(row['bid_size'])} " if pd.notna(row['bid_size']) else f"BidSize=N/A "
                    result += f"AskSize={int(row['ask_size'])}\n" if pd.notna(row['ask_size']) else f"AskSize=N/A\n"
                    result += "\n"

                if len(df) > 5:
                    result += f"  ... and {len(df) - 5} more options\n"

        return result

    except Exception as e:
        return f"Error screening options: {str(e)}"


@mcp.tool()
async def screen_options_with_directional_analysis(
    symbols: List[str],
    min_days: int = 20,
    max_days: int = 45,
    max_percent_otm: float = 40.0,
    min_percent_otm: float = 0.1,
    min_open_interest: int = 200,
    min_delta_put: float = -0.42,
    max_delta_put: float = -0.18,
    min_delta_call: float = 0.18,
    max_delta_call: float = 0.42,
    min_atr_multiplier: float = 1.0,
    max_atr_multiplier: float = 3.0,
    min_return_30_day: float = 2.0,
    max_spread_percent: float = 5.0,
    get_calls: bool = True,
    get_puts: bool = True,
    include_longs: bool = False,
    enable_directional: bool = True,
    min_confidence: float = 60.0
) -> str:
    """
    Advanced options screening with multi-timeframe directional analysis and market regime detection.

    Combines traditional options filtering with sophisticated directional analysis that examines:
    - Price action across daily, hourly, and minute timeframes
    - Bollinger Bands mean reversion signals
    - Options flow and gamma exposure
    - Put/call ratios and implied volatility skew
    - Market regime (trending vs ranging)

    Returns options ranked by composite score: Expected Return (40%) + Directional Alignment (30%) + Confidence (30%)

    Args:
        symbols: Stock symbols to screen (e.g., ["AAPL", "MSFT"])
        min_days: Minimum days to expiration (default: 20)
        max_days: Maximum days to expiration (default: 45)
        max_percent_otm: Max % out-of-the-money (default: 40.0)
        min_percent_otm: Min % out-of-the-money (default: 0.1)
        min_open_interest: Minimum open interest (default: 200)
        min_delta_put: Min delta for puts (default: -0.42)
        max_delta_put: Max delta for puts (default: -0.18)
        min_delta_call: Min delta for calls (default: 0.18)
        max_delta_call: Max delta for calls (default: 0.42)
        min_atr_multiplier: Min ATR multiplier (default: 1.0)
        max_atr_multiplier: Max ATR multiplier (default: 3.0)
        min_return_30_day: Min 30-day return % (default: 2.0)
        max_spread_percent: Max bid/ask spread % (default: 5.0)
        get_calls: Include calls (default: True)
        get_puts: Include puts (default: True)
        include_longs: Include long options (default: False)
        enable_directional: Enable directional analysis (default: True)
        min_confidence: Min directional confidence % (default: 60.0)

    Returns:
        Formatted results with:
        - Directional signals (BULLISH/BEARISH/NEUTRAL)
        - Confidence scores and market regime
        - Recommendations (STRONG_BUY/BUY/HOLD/CAUTION/AVOID)
        - All option metrics (Greeks, IV, OI, spreads)
        - Composite scoring
    """
    if not OPTION_SCREENER_AVAILABLE:
        return "Error: Option screener with directional analysis not available. Check ALPACA_WHEEL_PATH configuration."

    try:
        # Call the directional integration function
        results, no_results = get_df_filtered_options_with_directional(
            symbols=symbols,
            trading_client=trade_client,
            stock_client=stock_historical_data_client,
            option_client=option_historical_data_client,
            min_days=min_days,
            max_days=max_days,
            max_percent_otm=max_percent_otm,
            min_percent_otm=min_percent_otm,
            min_open_interest=min_open_interest,
            min_delta_put=min_delta_put,
            max_delta_put=max_delta_put,
            min_delta_call=min_delta_call,
            max_delta_call=max_delta_call,
            min_atr_multiplier=min_atr_multiplier,
            max_atr_multiplier=max_atr_multiplier,
            min_return_30_day=min_return_30_day,
            max_spread_percent=max_spread_percent,
            get_calls=get_calls,
            get_puts=get_puts,
            include_longs=include_longs,
            enable_directional=enable_directional,
            min_confidence=min_confidence
        )

        # Format results
        output = []
        output.append("=" * 90)
        output.append("OPTIONS SCREENING WITH DIRECTIONAL ANALYSIS")
        output.append("=" * 90)
        output.append("")

        if no_results:
            output.append(f"No results for: {', '.join(no_results)}")
            output.append("")

        if not results:
            return "\n".join(output) + "No options found matching criteria."

        # Display results for each symbol
        for symbol, df in results:
            if df.empty:
                continue

            output.append(f"\n{'=' * 90}")
            output.append(f"SYMBOL: {symbol} - {len(df)} options found")
            output.append(f"{'=' * 90}")

            # Show top 10 by composite score
            for idx, row in df.head(10).iterrows():
                output.append(f"\n{'-' * 90}")
                output.append(f"RANK #{idx + 1}")
                output.append(f"{'-' * 90}")

                # Basic info
                output.append(f"Symbol: {row.get('symbol', 'N/A')}")
                output.append(f"Type: {row.get('type', 'N/A')} | Strike: ${row.get('strike_price', 0):.2f}")
                output.append(f"Expiry: {row.get('expiration_date', 'N/A')} ({row.get('days_to_expiry', 0):.0f} DTE)")
                output.append("")

                # Pricing
                output.append(f"Premium: ${row.get('bid', 0):.2f} / ${row.get('ask', 0):.2f} (spread: {row.get('spread_percent', 0):.2f}%)")
                output.append(f"Sizes: {row.get('bid_size', 0):,.0f} x {row.get('ask_size', 0):,.0f}")
                output.append("")

                # Greeks
                output.append(f"Greeks: Δ={row.get('delta', 0):.3f} | Γ={row.get('gamma', 0):.4f} | Θ={row.get('theta', 0):.3f} | ν={row.get('vega', 0):.3f}")
                output.append(f"IV: {row.get('implied_volatility', 0):.3f} | OI: {row.get('open_interest', 0):,.0f}")
                output.append("")

                # Directional analysis
                if enable_directional:
                    output.append("--- DIRECTIONAL ANALYSIS ---")
                    direction = row.get('dir_direction', 'N/A')
                    confidence = row.get('dir_confidence', 0)
                    output.append(f"Direction: {direction} (Confidence: {confidence:.1f}%)")
                    output.append(f"Market Regime: {row.get('market_regime', 'N/A')}")
                    output.append(f"Alignment Score: {row.get('dir_alignment_score', 0):.1f}")
                    output.append(f"Recommendation: {row.get('recommendation', 'N/A')}")
                    output.append("")

                # Returns
                output.append(f"Expected 30-Day Return: {row.get('return_30_day', 0):.2f}%")
                if enable_directional:
                    output.append(f"COMPOSITE SCORE: {row.get('composite_score', 0):.2f}")
                output.append(f"ATR Multiplier: {row.get('atr_multiplier', 0):.2f}")

        output.append(f"\n{'=' * 90}")
        return "\n".join(output)

    except Exception as e:
        return f"Error in directional screening: {str(e)}\n\nCheck that alpacaWheel is properly configured at: {ALPACA_WHEEL_PATH}"


@mcp.tool()
async def get_bollinger_band_signal(
    symbol: str,
    window: int = 20,
    multiplier: int = 2,
    lookback_days: int = 90,
    signal_threshold: float = 0.10
) -> str:
    """
    Get Bollinger Band analysis and trading signal for a symbol.

    Args:
        symbol: Stock symbol to analyze
        window: Period for moving average (default: 20)
        multiplier: Standard deviation multiplier (default: 2)
        lookback_days: Days of historical data (default: 90)
        signal_threshold: Threshold for signal generation (default: 0.10 = 10%)
                         0.05 = conservative, 0.10 = aggressive

    Returns:
        str: Bollinger Band analysis including:
            - Current price and band levels
            - BB signal (BULL/BEAR/NEUTRAL)
            - Position within bands
            - Recommended strategy
    """
    if not OPTION_SCREENER_AVAILABLE:
        return "Error: Option screener functions are not available. Check ALPACA_WHEEL_PATH configuration."

    try:
        bb_data = get_bollinger_bands(
            stock_client=stock_historical_data_client,
            underlying_symbol=symbol,
            window=window,
            multiplier=multiplier,
            lookback_days=lookback_days,
            signal_threshold=signal_threshold
        )

        result = f"""
Bollinger Band Analysis for {symbol}
{'=' * 60}
CURRENT STOCK PRICE: ${bb_data['current_price']:.2f}

Bollinger Bands:
  Upper Band:        ${bb_data['upper_band']:.2f}
  Middle Band (20MA): ${bb_data['middle_band']:.2f}
  Lower Band:        ${bb_data['lower_band']:.2f}

Band Width:       ${bb_data['bb_width']:.2f}
Price Position:   {bb_data['bb_position']:.1%} (0%=at lower band, 100%=at upper band)

Signal:           {bb_data['bb_signal']}
{'=' * 60}

Recommended Strategy:
"""

        if bb_data['bb_signal'] == 'BULL':
            result += "  → BULL PUT SPREAD (expect mean reversion up)\n"
            result += "  Price is near lower band - oversold condition"
        elif bb_data['bb_signal'] == 'BEAR':
            result += "  → BEAR CALL SPREAD (expect mean reversion down)\n"
            result += "  Price is near upper band - overbought condition"
        else:
            result += "  → NEUTRAL (no clear edge)\n"
            result += "  Price is in middle of channel"

        return result

    except Exception as e:
        return f"Error getting Bollinger Bands: {str(e)}"


@mcp.tool()
async def execute_put_spread(
    short_put_symbol: str,
    long_put_symbol: str,
    quantity: int,
    underlying_symbol: str
) -> str:
    """
    Execute a bull put spread by buying the long put first, then selling the short put.

    Args:
        short_put_symbol: Option symbol for the short put (higher strike)
        long_put_symbol: Option symbol for the long put (lower strike)
        quantity: Number of contracts
        underlying_symbol: Underlying stock symbol

    Returns:
        str: Execution confirmation with order details
    """
    if not OPTION_SCREENER_AVAILABLE:
        return "Error: Option execution functions are not available. Check ALPACA_WHEEL_PATH configuration."

    try:
        result = buy_longer_put_then_sell_put(
            trading_client=trade_client,
            short_put=short_put_symbol,
            long_put=long_put_symbol,
            qty=quantity,
            underlying_symbol=underlying_symbol
        )
        return f"Bull Put Spread Executed Successfully:\n{result}"
    except Exception as e:
        return f"Error executing put spread: {str(e)}"


@mcp.tool()
async def execute_call_spread(
    short_call_symbol: str,
    long_call_symbol: str,
    quantity: int,
    underlying_symbol: str
) -> str:
    """
    Execute a bear call spread by buying the long call first, then selling the short call.

    Args:
        short_call_symbol: Option symbol for the short call (lower strike)
        long_call_symbol: Option symbol for the long call (higher strike)
        quantity: Number of contracts
        underlying_symbol: Underlying stock symbol

    Returns:
        str: Execution confirmation with order details
    """
    if not OPTION_SCREENER_AVAILABLE:
        return "Error: Option execution functions are not available. Check ALPACA_WHEEL_PATH configuration."

    try:
        result = buy_longer_call_then_sell_call(
            trading_client=trade_client,
            short_call=short_call_symbol,
            long_call=long_call_symbol,
            qty=quantity,
            underlying_symbol=underlying_symbol
        )
        return f"Bear Call Spread Executed Successfully:\n{result}"
    except Exception as e:
        return f"Error executing call spread: {str(e)}"


# Run the server
if __name__ == "__main__":
    # Parse command line arguments when running as main script
    args = parse_arguments()
    
    # Setup transport configuration based on command line arguments
    transport_config = setup_transport_config(args)
    
    try:
        # Run server with the specified transport
        if args.transport == "http":
            mcp.settings.host = transport_config["host"]
            mcp.settings.port = transport_config["port"]
            mcp.run(transport="streamable-http")
        elif args.transport == "sse":
            mcp.settings.host = transport_config["host"]
            mcp.settings.port = transport_config["port"]
            mcp.run(transport="sse")
        else:
            mcp.run(transport="stdio")
    except Exception as e:
        if args.transport in ["http", "sse"]:
            print(f"Error starting {args.transport} server: {e}")
            print(f"Server was configured to run on {transport_config['host']}:{transport_config['port']}")
            print("Common solutions:")
            print(f"1. Ensure port {transport_config['port']} is available")
            print(f"2. Check if another service is using port {transport_config['port']}")
            print("3. Try using a different port with --port <PORT>")
            print("4. For remote access, consider using SSH tunneling or reverse proxy")
        else:
            print(f"Error starting MCP server: {e}")
        sys.exit(1)
