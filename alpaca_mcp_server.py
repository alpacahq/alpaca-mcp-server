import os
import re
import sys
import time
import argparse
from datetime import datetime, timedelta, date
from typing import Dict, Any, List, Optional, Union

from dotenv import load_dotenv

from alpaca.common.enums import SupportedCurrencies
from alpaca.common.exceptions import APIError
from alpaca.data.enums import DataFeed, OptionsFeed, CorporateActionsType
from alpaca.data.historical.option import OptionHistoricalDataClient
from alpaca.data.historical.stock import StockHistoricalDataClient, StockLatestTradeRequest
from alpaca.data.historical.corporate_actions import CorporateActionsClient
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
    CorporateActionsRequest
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

# Initialize FastMCP server with intelligent log level detection
is_pycharm = detect_pycharm_environment()
log_level = "ERROR" if is_pycharm else "INFO"

# Optional: Print detection result for debugging (only in non-PyCharm environments)
# Only print when running as main script to avoid noise when imported
if not is_pycharm and __name__ == "__main__":
    print(f"MCP Server starting with transport={args.transport}, log_level={log_level} (PyCharm detected: {is_pycharm})")

mcp = FastMCP("alpaca-trading", log_level=log_level)

# Initialize Alpaca clients using environment variables
# Import our .env file within the same directory
load_dotenv()

TRADE_API_KEY = os.getenv("ALPACA_API_KEY")
TRADE_API_SECRET = os.getenv("ALPACA_SECRET_KEY")
ALPACA_PAPER_TRADE = os.getenv("ALPACA_PAPER_TRADE", "True")
TRADE_API_URL = os.getenv("TRADE_API_URL")
TRDE_API_WSS = os.getenv("TRDE_API_WSS")
DATA_API_URL = os.getenv("DATA_API_URL")
STREAM_DATA_WSS = os.getenv("STREAM_DATA_WSS")

# Check if keys are available
if not TRADE_API_KEY or not TRADE_API_SECRET:
    raise ValueError("Alpaca API credentials not found in environment variables.")

# Initialize clients
# For trading
trade_client = TradingClientSigned(TRADE_API_KEY, TRADE_API_SECRET, paper=ALPACA_PAPER_TRADE)
# For historical market data
stock_historical_data_client = StockHistoricalDataClientSigned(TRADE_API_KEY, TRADE_API_SECRET)
# For streaming market data
stock_data_stream_client = StockDataStream(TRADE_API_KEY, TRADE_API_SECRET, url_override=STREAM_DATA_WSS)
# For option historical data
option_historical_data_client = OptionHistoricalDataClientSigned(api_key=TRADE_API_KEY, secret_key=TRADE_API_SECRET)
# For corporate actions data
corporate_actions_client = CorporateActionsClientSigned(api_key=TRADE_API_KEY, secret_key=TRADE_API_SECRET)

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

# ============================================================================
# Market Data Tools
# ============================================================================

@mcp.tool()
async def get_stock_quote(symbol: str) -> str:
    """
    Retrieves and formats the latest quote for a stock.
    
    Args:
        symbol (str): Stock ticker symbol (e.g., AAPL, MSFT)
    
    Returns:
        str: Formatted string containing:
            - Ask Price
            - Bid Price
            - Ask Size
            - Bid Size
            - Timestamp
    """
    try:
        request_params = StockLatestQuoteRequest(symbol_or_symbols=symbol)
        quotes = stock_historical_data_client.get_stock_latest_quote(request_params)

        if symbol in quotes:
            quote = quotes[symbol]
            return f"""
                    Latest Quote for {symbol}:
                    ------------------------
                    Ask Price: ${quote.ask_price:.2f}
                    Bid Price: ${quote.bid_price:.2f}
                    Ask Size: {quote.ask_size}
                    Bid Size: {quote.bid_size}
                    Timestamp: {quote.timestamp}
                    """
        else:
            return f"No quote data found for {symbol}."
    except Exception as e:
        return f"Error fetching quote for {symbol}: {str(e)}"

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
                start_time = datetime.fromisoformat(start.replace('Z', '+00:00'))
            except ValueError:
                return f"Error: Invalid start time format '{start}'. Use ISO format like '2023-01-01T09:30:00' or '2023-01-01'"

        if end:
            try:
                end_time = datetime.fromisoformat(end.replace('Z', '+00:00'))
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
# Market Data Tools - Stock Snapshot Data with Helper Functions
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
# Order Management Tools
# ============================================================================

@mcp.tool()
async def get_orders(status: str = "all", limit: int = 10) -> str:
    """
    Retrieves and formats orders with the specified status.
    
    Args:
        status (str): Order status to filter by (open, closed, all)
        limit (int): Maximum number of orders to return (default: 10)
    
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

        request_params = GetOrdersRequest(
            status=query_status,
            limit=limit
        )

        orders = trade_client.get_orders(request_params)

        if not orders:
            return f"No {status} orders found."

        result = f"{status.capitalize()} Orders (Last {len(orders)}):\n"
        result += "-----------------------------------\n"

        for order in orders:
            result += f"""
                        Symbol: {order.symbol}
                        ID: {order.id}
                        Type: {order.type}
                        Side: {order.side}
                        Quantity: {order.qty}
                        Status: {order.status}
                        Submitted At: {order.submitted_at}
                        """
            if hasattr(order, 'filled_at') and order.filled_at:
                result += f"Filled At: {order.filled_at}\n"

            if hasattr(order, 'filled_avg_price') and order.filled_avg_price:
                result += f"Filled Price: ${float(order.filled_avg_price):.2f}\n"

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
                Order Placed Successfully:
                -------------------------
                Order ID: {order.id}
                Symbol: {order.symbol}
                Side: {order.side}
                Quantity: {order.qty}
                Type: {order.type}
                Time In Force: {order.time_in_force}
                Status: {order.status}
                Client Order ID: {order.client_order_id}
                """
    except Exception as e:
        return f"Error placing order: {str(e)}"

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

# ============================================================================
# Position Management Tools
# ============================================================================

@mcp.tool()
async def close_position(symbol: str, qty: Optional[str] = None, percentage: Optional[str] = None) -> str:
    """
    Closes a specific position for a single symbol.
    
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
        start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
        end_dt = datetime.strptime(end_date, "%Y-%m-%d").date()

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
# Options Trading Tools
# ============================================================================

@mcp.tool()
async def get_option_contracts(
    underlying_symbol: str,
    expiration_date: Optional[date] = None,
    expiration_month: Optional[int] = None,
    expiration_year: Optional[int] = None,
    expiration_week_start: Optional[date] = None,
    strike_price_gte: Optional[str] = None,
    strike_price_lte: Optional[str] = None,
    type: Optional[ContractType] = None,
    status: Optional[AssetStatus] = None,
    root_symbol: Optional[str] = None,
    limit: Optional[int] = None
) -> str:
    """
    Retrieves metadata for option contracts based on specified criteria. This endpoint returns contract specifications
    and static data, not real-time pricing information.
    
    Args:
        underlying_symbol (str): The symbol of the underlying asset (e.g., 'AAPL')
        expiration_date (Optional[date]): Optional specific expiration date for the options
        expiration_month (Optional[int]): Optional expiration month (1-12) to get all contracts for that month
        expiration_year (Optional[int]): Optional expiration year (required if expiration_month is provided)
        expiration_week_start (Optional[date]): Optional start date of week to find all contracts expiring in that week (Monday-Sunday)
        strike_price_gte (Optional[str]): Optional minimum strike price
        strike_price_lte (Optional[str]): Optional maximum strike price
        type (Optional[ContractType]): Optional contract type (CALL or PUT)
        status (Optional[AssetStatus]): Optional asset status filter (e.g., ACTIVE)
        root_symbol (Optional[str]): Optional root symbol for the option
        limit (Optional[int]): Optional maximum number of contracts to return
    
    Returns:
        str: Formatted string containing option contract metadata including:
            - Contract ID and Symbol
            - Name and Type (Call/Put)
            - Strike Price and Expiration Date
            - Exercise Style (American/European)
            - Contract Size and Status
            - Open Interest and Close Price
            - Underlying Asset Information ('underlying_asset_id', 'underlying_symbol', 'underlying_name', 'underlying_exchange')
            - Trading Status (Tradable/Non-tradable)
    
    Note:
        This endpoint returns contract specifications and static data. For real-time pricing
        information (bid/ask prices, sizes, etc.), use get_option_latest_quote instead.
        
        For month-based queries, use expiration_month and expiration_year instead of expiration_date.
        For week-based queries, use expiration_week_start to find all contracts expiring in that week.
        The function will check all dates from Monday through Sunday of that week.
        
        When more than 500 contracts are found, a guidance message is displayed instead of 
        overwhelming output to help users narrow their search criteria.
    """
    try:
        # Determine the appropriate expiration filtering strategy
        use_specific_date = expiration_date is not None
        use_month_filter = expiration_month is not None and expiration_year is not None
        use_week_filter = expiration_week_start is not None

        # Create the request object - if filtering by month or week, don't use expiration_date
        request_expiration_date = expiration_date if use_specific_date and not use_month_filter and not use_week_filter else None

        # Create the request object with all available parameters
        # Set a higher limit to get more contracts (default is 100, we use 1000 for comprehensive results)
        request = GetOptionContractsRequest(
            underlying_symbols=[underlying_symbol],
            expiration_date=request_expiration_date,
            strike_price_gte=strike_price_gte,
            strike_price_lte=strike_price_lte,
            type=type,
            status=status,
            root_symbol=root_symbol,
            limit=limit if limit else 1000  # Default to 1000 to get more comprehensive results
        )

        # Get the option contracts
        response = trade_client.get_option_contracts(request)

        if not response or not response.option_contracts:
            return f"No option contracts found for {underlying_symbol} matching the criteria."

        # Filter by month or week if specified
        contracts_to_display = response.option_contracts
        if use_month_filter:
            contracts_to_display = [
                contract for contract in response.option_contracts
                if contract.expiration_date.month == expiration_month and contract.expiration_date.year == expiration_year
            ]

            if not contracts_to_display:
                month_name = date(expiration_year, expiration_month, 1).strftime("%B")
                return f"No option contracts found for {underlying_symbol} expiring in {month_name} {expiration_year}."

        elif use_week_filter:
            # Calculate the week range (Monday to Sunday)
            from datetime import timedelta

            # Find the Monday of the week containing expiration_week_start
            days_since_monday = expiration_week_start.weekday()
            week_start = expiration_week_start - timedelta(days=days_since_monday)
            week_end = week_start + timedelta(days=6)  # Sunday

            contracts_to_display = [
                contract for contract in response.option_contracts
                if week_start <= contract.expiration_date <= week_end
            ]

            if not contracts_to_display:
                return f"No option contracts found for {underlying_symbol} expiring during the week of {week_start.strftime('%B %d, %Y')}."

        # Format the response
        if use_month_filter:
            month_name = date(expiration_year, expiration_month, 1).strftime("%B")
            result = f"Option Contracts for {underlying_symbol} expiring in {month_name} {expiration_year}:\n"
        elif use_week_filter:
            from datetime import timedelta
            days_since_monday = expiration_week_start.weekday()
            week_start = expiration_week_start - timedelta(days=days_since_monday)
            week_end = week_start + timedelta(days=6)
            result = f"Option Contracts for {underlying_symbol} expiring during the week of {week_start.strftime('%B %d')} - {week_end.strftime('%B %d, %Y')}:\n"
        else:
            result = f"Option Contracts for {underlying_symbol}:\n"
        result += "----------------------------------------\n"

        # Check if there are too many results and provide guidance instead of overwhelming output
        total_contracts = len(contracts_to_display)
        max_display_contracts = 500  # Threshold to limit display and show guidance message instead

        # Sort contracts by expiration date and strike price
        contracts_to_display.sort(key=lambda x: (x.expiration_date, float(x.strike_price)))

        if total_contracts > max_display_contracts:
            # Too many results - provide simple guidance
            result += f"Found {total_contracts} contracts. For easier viewing, please specify a particular expiration date or strike price range."

        else:
            # Normal display for manageable number of results
            for contract in contracts_to_display:
                result += f"""
                Symbol: {contract.symbol}
                Name: {contract.name}
                Type: {contract.type}
                Strike Price: ${float(contract.strike_price):.2f}
                Expiration Date: {contract.expiration_date}
                Status: {contract.status}
                Root Symbol: {contract.root_symbol}
                Underlying Symbol: {contract.underlying_symbol}
                Exercise Style: {contract.style}
                Contract Size: {contract.size}
                Tradable: {'Yes' if contract.tradable else 'No'}
                Open Interest: {contract.open_interest}
                Close Price: ${float(contract.close_price) if contract.close_price else 'N/A'}
                Close Price Date: {contract.close_price_date}
                -------------------------
                """

        # Add summary information
        if use_month_filter:
            month_name = date(expiration_year, expiration_month, 1).strftime("%B")
            result += f"\nTotal contracts found for {underlying_symbol} in {month_name} {expiration_year}: {total_contracts}"
        elif use_week_filter:
            from datetime import timedelta
            days_since_monday = expiration_week_start.weekday()
            week_start = expiration_week_start - timedelta(days=days_since_monday)
            result += f"\nTotal contracts found for {underlying_symbol} during the week of {week_start.strftime('%B %d, %Y')}: {total_contracts}"
        else:
            result += f"\nTotal contracts found for {underlying_symbol}: {total_contracts}"

        return result

    except Exception as e:
        return f"Error fetching option contracts: {str(e)}"

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

def _validate_option_order_inputs(legs: List[Dict[str, Any]], quantity: int, time_in_force: TimeInForce) -> Optional[str]:
    """Validate inputs for option order placement."""
    if not legs:
        return "Error: No option legs provided"
    if len(legs) > 4:
        return "Error: Maximum of 4 legs allowed for option orders"
    if quantity <= 0:
        return "Error: Quantity must be positive"
    if time_in_force != TimeInForce.DAY:
        return "Error: Only DAY time_in_force is supported for options trading"
    return None

def _convert_order_class_string(order_class: Optional[Union[str, OrderClass]]) -> Union[OrderClass, str]:
    """Convert order class string to enum if needed."""
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
    return order_class

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
    time_in_force: TimeInForce = TimeInForce.DAY,
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
        time_in_force (TimeInForce): Time in force for the order. For options trading, 
            only DAY is supported (default: TimeInForce.DAY)
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
            order_legs, order_class, quantity, time_in_force, extended_hours
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

def parse_timeframe_with_enums(timeframe_str: str) -> Optional[TimeFrame]:
    """
    Parse timeframe string to Alpaca TimeFrame object using proper enumerations.
    Supports flexible parsing of any valid timeframe format.
    
    Args:
        timeframe_str (str): Timeframe string (e.g., "1Min", "4Min", "2Hour", "1Day")
        
    Returns:
        Optional[TimeFrame]: Parsed TimeFrame object using TimeFrameUnit enums or None if invalid
        
    Reference:
        https://alpaca.markets/sdks/python/api_reference/data/timeframe.html#timeframeunit
    """

    try:
        timeframe_str = timeframe_str.strip()

        # Use predefined TimeFrame objects for common cases (more efficient)
        predefined_timeframes = {
            "1Min": TimeFrame.Minute,
            "1Hour": TimeFrame.Hour,
            "1Day": TimeFrame.Day,
            "1Week": TimeFrame.Week,
            "1Month": TimeFrame.Month
        }

        if timeframe_str in predefined_timeframes:
            return predefined_timeframes[timeframe_str]

        # Flexible regex pattern to parse any valid timeframe format
        # Matches: <number><unit> where unit can be Min, Hour, Day, Week, Month
        pattern = r'^(\d+)(Min|Hour|Day|Week|Month)$'
        match = re.match(pattern, timeframe_str, re.IGNORECASE)

        if not match:
            return None

        amount = int(match.group(1))
        unit_str = match.group(2).lower()

        # Map unit strings to TimeFrameUnit enums
        unit_mapping = {
            'min': TimeFrameUnit.Minute,
            'hour': TimeFrameUnit.Hour,
            'day': TimeFrameUnit.Day,
            'week': TimeFrameUnit.Week,
            'month': TimeFrameUnit.Month
        }

        unit = unit_mapping.get(unit_str)
        if unit is None:
            return None

        # Validate amount based on unit type
        if unit == TimeFrameUnit.Minute and amount > 59:
            # Minutes should be reasonable (1-59)
            return None
        elif unit == TimeFrameUnit.Hour and amount > 23:
            # Hours should be reasonable (1-23) 
            return None
        elif unit in [TimeFrameUnit.Day, TimeFrameUnit.Week, TimeFrameUnit.Month] and amount > 365:
            # Days/weeks/months should be reasonable
            return None

        return TimeFrame(amount, unit)

    except (ValueError, AttributeError, TypeError):
        return None

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