import os
from dotenv import load_dotenv
from typing import Dict, Any, List, Optional, Union
from datetime import datetime, timedelta, date
from mcp.server.fastmcp import FastMCP
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import GetOrdersRequest, MarketOrderRequest, LimitOrderRequest, GetAssetsRequest, CreateWatchlistRequest, UpdateWatchlistRequest, GetCalendarRequest, GetCorporateAnnouncementsRequest, ClosePositionRequest, GetOptionContractsRequest, OptionLegRequest, StopOrderRequest, StopLimitOrderRequest, TrailingStopOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce, QueryOrderStatus, AssetStatus, CorporateActionType, CorporateActionDateType, OrderType, PositionIntent, ContractType, OrderClass
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.historical.option import OptionHistoricalDataClient
from alpaca.data.requests import Sort, StockBarsRequest, StockLatestQuoteRequest, StockTradesRequest, StockLatestTradeRequest, StockLatestBarRequest, OptionLatestQuoteRequest, OptionSnapshotRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.data.live.stock import StockDataStream
from alpaca.trading.models import Order
from alpaca.data.enums import DataFeed, OptionsFeed
from alpaca.common.enums import SupportedCurrencies

import time
import requests
import json
import threading
import asyncio
from collections import deque, defaultdict
from alpaca.common.exceptions import APIError

# Initialize FastMCP server
mcp = FastMCP("alpaca-trading")

# Initialize Alpaca clients using environment variables
# Import our .env file within the same directory
load_dotenv()

API_KEY = os.getenv("APCA_API_KEY_ID")
API_SECRET = os.getenv("APCA_API_SECRET_KEY")
PAPER = os.getenv("PAPER", "true").lower() in ["true", "1", "yes"]
trade_api_url = os.getenv("trade_api_url")
trade_api_wss = os.getenv("trade_api_wss")
data_api_url = os.getenv("data_api_url")
stream_data_wss = os.getenv("stream_data_wss")

# Check if keys are available
if not API_KEY or not API_SECRET:
    raise ValueError("Alpaca API credentials not found in environment variables.")

# Initialize clients
# For trading
trade_client = TradingClient(API_KEY, API_SECRET, paper=PAPER)
# For historical market data
stock_historical_data_client = StockHistoricalDataClient(API_KEY, API_SECRET)
# For streaming market data
stock_data_stream_client = StockDataStream(API_KEY, API_SECRET, url_override = stream_data_wss)
# For option historical data
option_historical_data_client = OptionHistoricalDataClient(api_key=API_KEY, secret_key=API_SECRET)

# ============================================================================
# Global Stock Streaming State (Alpaca allows only ONE stream connection)
# ============================================================================

_global_stock_stream = None
_stock_stream_thread = None
_stock_stream_active = False
_stock_stream_subscriptions = {
    'trades': set(),
    'quotes': set(),
    'bars': set(),
    'updated_bars': set(),
    'daily_bars': set(),
    'statuses': set()
}

# Configurable stock data buffers - no artificial limits for active stocks
_stock_data_buffers = {}
_stock_stream_stats = defaultdict(int)
_stock_stream_start_time = None
_stock_stream_end_time = None
_stock_stream_config = {
    'feed': 'sip',
    'buffer_size': None,  # Unlimited by default
    'duration_seconds': None  # No time limit by default
}

# ============================================================================
# Stock Streaming Helper Classes and Functions
# ============================================================================

class ConfigurableStockDataBuffer:
    """Thread-safe buffer with configurable size limits for stock market data"""
    
    def __init__(self, max_size: Optional[int] = None):
        """
        Initialize buffer with optional size limit.
        
        Args:
            max_size: Maximum number of items to store. None = unlimited.
                     For active stocks, consider 10000+ or unlimited.
        """
        if max_size is None:
            self.data = deque()  # Unlimited
        else:
            self.data = deque(maxlen=max_size)  # Limited
        
        self.lock = threading.Lock()
        self.last_update = time.time()
        self.max_size = max_size
        self.total_items_added = 0  # Track total even if some are dropped
    
    def add(self, item):
        with self.lock:
            self.data.append(item)
            self.last_update = time.time()
            self.total_items_added += 1
    
    def get_recent(self, seconds: int = 60):
        with self.lock:
            cutoff = time.time() - seconds
            return [item for item in self.data if item.get('timestamp', 0) > cutoff]
    
    def get_all(self):
        with self.lock:
            return list(self.data)
    
    def get_stats(self):
        with self.lock:
            return {
                'current_size': len(self.data),
                'max_size': self.max_size,
                'total_added': self.total_items_added,
                'last_update': self.last_update,
                'is_unlimited': self.max_size is None
            }
    
    def clear(self):
        with self.lock:
            self.data.clear()
            self.total_items_added = 0

def _get_or_create_stock_buffer(symbol: str, data_type: str, buffer_size: Optional[int] = None) -> ConfigurableStockDataBuffer:
    """Get or create a buffer for a stock symbol/data_type combination"""
    buffer_key = f"{symbol}_{data_type}"
    if buffer_key not in _stock_data_buffers:
        effective_size = buffer_size if buffer_size is not None else _stock_stream_config.get('buffer_size')
        _stock_data_buffers[buffer_key] = ConfigurableStockDataBuffer(effective_size)
    return _stock_data_buffers[buffer_key]

def _check_stock_stream_duration_limit():
    """Check if stock stream should stop due to duration limit"""
    if _stock_stream_config['duration_seconds'] and _stock_stream_start_time:
        elapsed = time.time() - _stock_stream_start_time
        if elapsed >= _stock_stream_config['duration_seconds']:
            return True
    return False

# Global handler functions for stock streaming
async def handle_stock_trade(trade):
    """Global handler for stock trade data"""
    try:
        if _check_stock_stream_duration_limit():
            return
        
        trade_data = {
            'type': 'trade',
            'symbol': trade.symbol,
            'price': float(trade.price),
            'size': trade.size,
            'exchange': trade.exchange,
            'timestamp': time.time(),
            'datetime': trade.timestamp.isoformat(),
            'conditions': getattr(trade, 'conditions', []),
            'tape': getattr(trade, 'tape', None)
        }
        
        buffer = _get_or_create_stock_buffer(trade.symbol, 'trades', _stock_stream_config.get('buffer_size'))
        buffer.add(trade_data)
        _stock_stream_stats['trades'] += 1
        
    except Exception as e:
        print(f"Error handling trade: {e}")

async def handle_stock_quote(quote):
    """Global handler for stock quote data"""
    try:
        if _check_stock_stream_duration_limit():
            return
        
        quote_data = {
            'type': 'quote',
            'symbol': quote.symbol,
            'bid_price': float(quote.bid_price),
            'ask_price': float(quote.ask_price),
            'bid_size': quote.bid_size,
            'ask_size': quote.ask_size,
            'spread': float(quote.ask_price - quote.bid_price),
            'timestamp': time.time(),
            'datetime': quote.timestamp.isoformat(),
            'bid_exchange': getattr(quote, 'bid_exchange', None),
            'ask_exchange': getattr(quote, 'ask_exchange', None)
        }
        
        buffer = _get_or_create_stock_buffer(quote.symbol, 'quotes', _stock_stream_config.get('buffer_size'))
        buffer.add(quote_data)
        _stock_stream_stats['quotes'] += 1
        
    except Exception as e:
        print(f"Error handling quote: {e}")

async def handle_stock_bar(bar):
    """Global handler for stock bar data"""
    try:
        if _check_stock_stream_duration_limit():
            return
        
        bar_data = {
            'type': 'bar',
            'symbol': bar.symbol,
            'open': float(bar.open),
            'high': float(bar.high),
            'low': float(bar.low),
            'close': float(bar.close),
            'volume': bar.volume,
            'trade_count': getattr(bar, 'trade_count', 0),
            'vwap': float(getattr(bar, 'vwap', 0)) if hasattr(bar, 'vwap') and bar.vwap else None,
            'timestamp': time.time(),
            'datetime': bar.timestamp.isoformat()
        }
        
        buffer = _get_or_create_stock_buffer(bar.symbol, 'bars', _stock_stream_config.get('buffer_size'))
        buffer.add(bar_data)
        _stock_stream_stats['bars'] += 1
        
    except Exception as e:
        print(f"Error handling bar: {e}")

async def handle_stock_status(status):
    """Global handler for stock status data"""
    try:
        if _check_stock_stream_duration_limit():
            return
        
        status_data = {
            'type': 'status',
            'symbol': status.symbol,
            'status': status.status,
            'reason': getattr(status, 'reason', None),
            'timestamp': time.time(),
            'datetime': status.timestamp.isoformat()
        }
        
        buffer = _get_or_create_stock_buffer(status.symbol, 'statuses', _stock_stream_config.get('buffer_size'))
        buffer.add(status_data)
        _stock_stream_stats['statuses'] += 1
        
    except Exception as e:
        print(f"Error handling status: {e}")

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
async def get_stock_bars(symbol: str, days: int = 5) -> str:
    """
    Retrieves and formats historical price bars for a stock.
    
    Args:
        symbol (str): Stock ticker symbol (e.g., AAPL, MSFT)
        days (int): Number of trading days to look back (default: 5)
    
    Returns:
        str: Formatted string containing historical price data including:
            - Date
            - Open
            - High
            - Low
            - Close
            - Volume
    """
    try:
        # Calculate start time based on days
        start_time = datetime.now().date() - timedelta(days=days)
        
        request_params = StockBarsRequest(
            symbol_or_symbols=symbol,
            timeframe=TimeFrame.Day,
            start=start_time
        )
        
        bars = stock_historical_data_client.get_stock_bars(request_params)
        
        # if symbol in bars and bars[symbol]:
        if bars[symbol]:
            result = f"Historical Data for {symbol} (Last {days} trading days):\n"
            result += "---------------------------------------------------\n"
            
            for bar in bars[symbol]:
                result += f"Date: {bar.timestamp.date()}, Open: ${bar.open:.2f}, High: ${bar.high:.2f}, Low: ${bar.low:.2f}, Close: ${bar.close:.2f}, Volume: {bar.volume}\n"
            
            return result
        else:
            return f"No historical data found for {symbol} in the last {days} days."
    except Exception as e:
        return f"Error fetching historical data for {symbol}: {str(e)}"

@mcp.tool()
async def get_stock_bars_intraday(
    symbol: str, 
    timeframe: str = "1Min", 
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 100,
    adjustment: str = "raw",
    feed: str = "sip",
    currency: str = "USD",
    sort: str = "asc"
) -> str:
    """
    Retrieves and formats intraday historical price bars for a stock with comprehensive customization options.
    This function matches Alpaca's native bars API capabilities with enhanced formatting and analysis.
    
    Args:
        symbol (str): Stock ticker symbol (e.g., 'AAPL', 'MSFT', 'NVDA')
        timeframe (str): Time interval for bars. Supports all Alpaca timeframes:
            - '[1-59]Min' or '[1-59]T': e.g., '1Min', '5Min', '30Min'
            - '[1-23]Hour' or '[1-23]H': e.g., '1Hour', '12Hour'
            - '1Day' or '1D': Daily bars
            - '1Week' or '1W': Weekly bars
            - '[1,2,3,4,6,12]Month' or 'M': e.g., '1Month', '3Month'
        start_date (Optional[str]): Start date in YYYY-MM-DD format (default: most recent trading day)
        end_date (Optional[str]): End date in YYYY-MM-DD format (default: today or most recent trading day)
        limit (int): Maximum number of bars to return (default: 100, max: 10000)
        adjustment (str): Corporate action adjustment ('raw', 'split', 'dividend', 'all')
        feed (str): Data feed source ('sip', 'iex', 'otc') - default: 'sip'
        currency (str): Currency for prices in ISO 4217 format (default: 'USD')
        sort (str): Sort order ('asc' for ascending, 'desc' for descending)
    
    Returns:
        str: Formatted string containing comprehensive intraday data including:
            - Timestamp (in ET timezone)
            - OHLCV data (Open, High, Low, Close, Volume)
            - Trade count and VWAP when available
            - Price changes and percentage moves
            - Volume analysis and trading activity metrics
            - Summary statistics for the period
    """
    try:
        # Enhanced timeframe parsing to support Alpaca's full syntax
        from alpaca.data.timeframe import TimeFrameUnit
        import re
        
        def parse_timeframe(tf_str):
            """Parse timeframe string into TimeFrame object"""
            tf_str = tf_str.upper()
            
            # Handle minute timeframes: 1Min, 5Min, 30Min, 1T, 5T, etc.
            if re.match(r'^\d+MIN$', tf_str) or re.match(r'^\d+T$', tf_str):
                minutes = int(re.findall(r'\d+', tf_str)[0])
                if 1 <= minutes <= 59:
                    return TimeFrame(minutes, TimeFrameUnit.Minute)
                else:
                    raise ValueError(f"Minutes must be 1-59, got {minutes}")
            
            # Handle hour timeframes: 1Hour, 12Hour, 1H, 12H, etc.
            elif re.match(r'^\d+HOUR$', tf_str) or re.match(r'^\d+H$', tf_str):
                hours = int(re.findall(r'\d+', tf_str)[0])
                if 1 <= hours <= 23:
                    return TimeFrame(hours, TimeFrameUnit.Hour)
                else:
                    raise ValueError(f"Hours must be 1-23, got {hours}")
            
            # Handle day timeframes: 1Day, 1D
            elif tf_str in ['1DAY', '1D']:
                return TimeFrame.Day
            
            # Handle week timeframes: 1Week, 1W
            elif tf_str in ['1WEEK', '1W']:
                return TimeFrame.Week
            
            # Handle month timeframes: 1Month, 3Month, etc.
            elif re.match(r'^\d+MONTH$', tf_str) or re.match(r'^\d+M$', tf_str):
                months = int(re.findall(r'\d+', tf_str)[0])
                if months in [1, 2, 3, 4, 6, 12]:
                    return TimeFrame(months, TimeFrameUnit.Month)
                else:
                    raise ValueError(f"Months must be 1,2,3,4,6,12, got {months}")
            
            else:
                raise ValueError(f"Invalid timeframe format: {tf_str}")
        
        try:
            timeframe_obj = parse_timeframe(timeframe)
        except ValueError as e:
            return f"Invalid timeframe '{timeframe}': {str(e)}\n\nSupported formats:\n- Minutes: 1Min-59Min or 1T-59T\n- Hours: 1Hour-23Hour or 1H-23H\n- Days: 1Day or 1D\n- Weeks: 1Week or 1W\n- Months: 1Month, 2Month, 3Month, 4Month, 6Month, 12Month (or 1M, 2M, etc.)"
        
        # Get market calendar to find the most recent trading day
        now = datetime.now()
        today = now.date()
        
        # Look back up to 10 days and forward 1 day to get current trading status
        calendar_start = now - timedelta(days=10)
        calendar_end = now + timedelta(days=1)
        
        try:
            calendar_request = GetCalendarRequest(
                start=calendar_start.date(),
                end=calendar_end.date()
            )
            calendar = trade_client.get_calendar(calendar_request)
            if not calendar:
                return "No trading days found in recent calendar data"
            
            # Find the most recent trading day (today or before, not future dates)
            most_recent_trading_day = None
            for day in reversed(calendar):  # Go backwards from latest date
                if day.date <= today:  # Only consider today or past dates
                    most_recent_trading_day = day.date
                    break
            
            # If no past trading day found, use today if it's a trading day
            if most_recent_trading_day is None:
                # Check if today is a trading day
                if any(day.date == today for day in calendar):
                    most_recent_trading_day = today
                else:
                    # Fallback to yesterday
                    most_recent_trading_day = (now - timedelta(days=1)).date()
            
        except Exception as calendar_error:
            # Fallback: use today first, then yesterday
            most_recent_trading_day = today
        
        # Set default dates if not provided
        if not end_date:
            end_date = most_recent_trading_day.strftime("%Y-%m-%d")
        if not start_date:
            start_date = most_recent_trading_day.strftime("%Y-%m-%d")
        
        
        # Parse dates and create datetime objects with proper timezone handling
        try:
            start_date_obj = datetime.strptime(start_date, "%Y-%m-%d")
            end_date_obj = datetime.strptime(end_date, "%Y-%m-%d")
            
            # For intraday data, we need to specify the full trading day
            # Set start to market open (9:30 AM ET) and end to market close (4:00 PM ET)
            from datetime import timezone, timedelta as td
            eastern = timezone(td(hours=-5))  # EST (adjust for EDT as needed)
            
            # Market hours: 9:30 AM to 4:00 PM ET
            start_datetime = start_date_obj.replace(hour=9, minute=30, second=0, microsecond=0)
            end_datetime = end_date_obj.replace(hour=16, minute=0, second=0, microsecond=0)
            
        except ValueError as ve:
            return f"Invalid date format. Use YYYY-MM-DD format. Error: {str(ve)}"
        
        # Validate parameters
        if limit <= 0 or limit > 10000:
            return "Limit must be between 1 and 10000"
        
        if adjustment not in ['raw', 'split', 'dividend', 'all']:
            return "Invalid adjustment. Must be one of: raw, split, dividend, all"
        
        if feed not in ['sip', 'iex', 'otc']:
            return "Invalid feed. Must be one of: sip, iex, otc"
        
        if sort.lower() not in ['asc', 'desc']:
            return "Invalid sort. Must be 'asc' or 'desc'"
        
        # Convert parameters to appropriate enums
        from alpaca.data.enums import DataFeed, Adjustment
        feed_enum = getattr(DataFeed, feed.upper())
        sort_enum = Sort.ASC if sort.lower() == 'asc' else Sort.DESC
        
        # Map adjustment parameter
        adjustment_map = {
            'raw': 'raw',
            'split': 'split',
            'dividend': 'dividend', 
            'all': 'all'
        }
        
        # Create enhanced request with all parameters
        if start_date == end_date:
            # For same-day requests, use just the date without specific times
            request_params = StockBarsRequest(
                symbol_or_symbols=symbol,
                timeframe=timeframe_obj,
                start=start_date_obj,
                limit=limit,
                adjustment=adjustment_map[adjustment],
                feed=feed_enum,
                sort=sort_enum
            )
        else:
            # For multi-day requests
            request_params = StockBarsRequest(
                symbol_or_symbols=symbol,
                timeframe=timeframe_obj,
                start=start_datetime,
                end=end_datetime,
                limit=limit,
                adjustment=adjustment_map[adjustment],
                feed=feed_enum,
                sort=sort_enum
            )
        
        # Get the bars
        bars = stock_historical_data_client.get_stock_bars(request_params)
        
        if symbol not in bars.data or not bars.data[symbol]:
            # If no data found, try with a wider date range
            if start_date == end_date:
                # Try looking back 7 days
                extended_start = (datetime.strptime(start_date, "%Y-%m-%d") - timedelta(days=7)).date()
                request_params_extended = StockBarsRequest(
                    symbol_or_symbols=symbol,
                    timeframe=timeframe_obj,
                    start=extended_start,
                    limit=limit,
                    adjustment=adjustment_map[adjustment],
                    feed=feed_enum,
                    sort=sort_enum
                )
                bars_extended = stock_historical_data_client.get_stock_bars(request_params_extended)
                
                if symbol in bars_extended.data and bars_extended.data[symbol]:
                    bars = bars_extended
                    start_date = extended_start.strftime("%Y-%m-%d")
                else:
                    return f"No {timeframe} data found for {symbol} between {start_date} and {end_date}\n\n📊 Troubleshooting:\n• Verify {symbol} is a valid stock symbol\n• Check if {start_date} was a trading day\n• Ensure your Alpaca subscription includes real-time intraday data\n• Try different timeframe (e.g., '1Day' instead of '1Min')\n• Check if market was open during requested period\n• Try feed='iex' for IEX-only data"
            else:
                return f"No {timeframe} data found for {symbol} between {start_date} and {end_date}\n\n📊 Troubleshooting:\n• Verify {symbol} is a valid stock symbol\n• Check if dates were trading days\n• Ensure your Alpaca subscription includes real-time intraday data\n• Try different timeframe (e.g., '1Day' instead of '1Min')\n• Check if market was open during requested period\n• Try feed='iex' for IEX-only data"
        
        # Enhanced formatting with comprehensive analysis
        bars_list = list(bars.data[symbol])
        bar_count = min(len(bars_list), limit)
        
        result = f"📊 {timeframe.upper()} HISTORICAL BARS: {symbol}\n"
        result += f"📅 Period: {start_date} to {end_date} | Feed: {feed.upper()} | Adjustment: {adjustment}\n"
        result += f"📈 Retrieved: {bar_count:,} bars | Sort: {sort.upper()}\n"
        result += "=" * 80 + "\n\n"
        
        if bar_count == 0:
            return result + "No bars found for the specified period."
        
        # Calculate summary statistics
        opens = [float(bar.open) for bar in bars_list[:bar_count]]
        highs = [float(bar.high) for bar in bars_list[:bar_count]]
        lows = [float(bar.low) for bar in bars_list[:bar_count]]
        closes = [float(bar.close) for bar in bars_list[:bar_count]]
        volumes = [int(bar.volume) for bar in bars_list[:bar_count]]
        
        # Price analysis
        period_open = opens[0] if sort.lower() == 'asc' else opens[-1]
        period_close = closes[-1] if sort.lower() == 'asc' else closes[0]
        period_high = max(highs)
        period_low = min(lows)
        period_change = period_close - period_open
        period_change_pct = (period_change / period_open * 100) if period_open > 0 else 0
        
        # Volume analysis
        total_volume = sum(volumes)
        avg_volume = total_volume / len(volumes) if volumes else 0
        max_volume = max(volumes) if volumes else 0
        
        # VWAP calculation
        vwap_bars = [bar for bar in bars_list[:bar_count] if hasattr(bar, 'vwap') and bar.vwap]
        avg_vwap = sum(float(bar.vwap) for bar in vwap_bars) / len(vwap_bars) if vwap_bars else None
        
        # Trade count analysis
        trade_counts = [bar.trade_count for bar in bars_list[:bar_count] if hasattr(bar, 'trade_count') and bar.trade_count]
        total_trades = sum(trade_counts) if trade_counts else 0
        avg_trades = total_trades / len(trade_counts) if trade_counts else 0
        
        # Summary statistics
        result += f"📈 PERIOD SUMMARY:\n"
        result += f"  Open: ${period_open:.4f} → Close: ${period_close:.4f}\n"
        result += f"  Change: ${period_change:+.4f} ({period_change_pct:+.2f}%)\n"
        result += f"  Range: ${period_low:.4f} - ${period_high:.4f} (${period_high - period_low:.4f} spread)\n"
        if avg_vwap:
            result += f"  Avg VWAP: ${avg_vwap:.4f}\n"
        result += f"  Total Volume: {total_volume:,} shares\n"
        result += f"  Avg Volume/Bar: {avg_volume:,.0f} shares\n"
        if total_trades > 0:
            result += f"  Total Trades: {total_trades:,} | Avg/Bar: {avg_trades:.0f}\n"
        result += "\n"
        
        # Trading activity analysis
        result += f"📊 TRADING ACTIVITY ANALYSIS:\n"
        if max_volume > avg_volume * 2:
            result += f"  🔥 High volume detected (peak: {max_volume:,} vs avg: {avg_volume:,.0f})\n"
        elif max_volume < avg_volume * 0.5:
            result += f"  📉 Low volume period (peak: {max_volume:,} vs avg: {avg_volume:,.0f})\n"
        else:
            result += f"  ⚖️ Normal volume activity (peak: {max_volume:,} vs avg: {avg_volume:,.0f})\n"
        
        if period_change_pct > 1.0:
            result += f"  🟢 Strong upward movement (+{period_change_pct:.2f}%)\n"
        elif period_change_pct < -1.0:
            result += f"  🔴 Strong downward movement ({period_change_pct:.2f}%)\n"
        else:
            result += f"  🟡 Sideways movement ({period_change_pct:+.2f}%)\n"
        
        # Price volatility
        price_range_pct = ((period_high - period_low) / period_open * 100) if period_open > 0 else 0
        if price_range_pct > 3.0:
            result += f"  ⚡ High volatility (range: {price_range_pct:.2f}% of open price)\n"
        elif price_range_pct > 1.0:
            result += f"  📊 Moderate volatility (range: {price_range_pct:.2f}% of open price)\n"
        else:
            result += f"  😴 Low volatility (range: {price_range_pct:.2f}% of open price)\n"
        
        result += "\n"
        
        # Individual bar details (show recent bars based on sort order)
        display_limit = min(15, bar_count)  # Show up to 15 bars
        result += f"🕐 RECENT {timeframe.upper()} BARS (showing {display_limit} of {bar_count}):\n"
        result += "─" * 80 + "\n"
        
        display_bars = bars_list[:display_limit] if sort.lower() == 'asc' else bars_list[-display_limit:]
        
        for i, bar in enumerate(display_bars):
            # Format timestamp
            timestamp_str = bar.timestamp.strftime("%Y-%m-%d %H:%M ET")
            
            # Calculate bar-specific metrics
            bar_change = float(bar.close) - float(bar.open)
            bar_change_pct = (bar_change / float(bar.open) * 100) if float(bar.open) > 0 else 0
            bar_range = float(bar.high) - float(bar.low)
            
            # VWAP and trade count
            vwap_str = f"${float(bar.vwap):.4f}" if hasattr(bar, 'vwap') and bar.vwap else 'N/A'
            trades_str = f"{bar.trade_count:,}" if hasattr(bar, 'trade_count') and bar.trade_count else 'N/A'
            
            # Trend indicator
            trend = "🟢" if bar_change > 0 else "🔴" if bar_change < 0 else "⚪"
            
            result += f"{timestamp_str} {trend}\n"
            result += f"  OHLC: ${float(bar.open):.4f} | ${float(bar.high):.4f} | ${float(bar.low):.4f} | ${float(bar.close):.4f}\n"
            result += f"  Change: ${bar_change:+.4f} ({bar_change_pct:+.2f}%) | Range: ${bar_range:.4f}\n"
            result += f"  Volume: {int(bar.volume):,} | Trades: {trades_str} | VWAP: {vwap_str}\n"
            
            if i < len(display_bars) - 1:  # Don't add separator after last bar
                result += "  " + "·" * 40 + "\n"
        
        result += "\n" + "=" * 80 + "\n"
        result += f"💡 TIP: Use sort='desc' for most recent bars first, or adjust limit for more data\n"
        result += f"📊 Data source: Alpaca Markets ({feed.upper()} feed) with {adjustment} adjustment"
        
        return result
        
    except Exception as e:
        return f"Error fetching intraday bars for {symbol}: {str(e)}\n\nTroubleshooting tips:\n1. Check your Alpaca API credentials\n2. Verify your data subscription level\n3. Ensure the symbol exists and is tradable\n4. Try a different date range"

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

@mcp.tool()
async def get_stock_snapshots(
    symbols: Union[str, List[str]],
    feed: Optional[DataFeed] = None,
    currency: Optional[SupportedCurrencies] = None
) -> str:
    """
    Retrieves comprehensive market snapshots for one or more stocks using Alpaca's native snapshots endpoint.
    Each snapshot includes latest trade, latest quote, minute bar, daily bar, and previous daily bar data.
    
    Args:
        symbols (Union[str, List[str]]): Single stock symbol or list of stock symbols
            (e.g., 'NVDA' or ['NVDA', 'AAPL', 'MSFT'])
        feed (Optional[DataFeed]): The source feed of the data:
            - sip: All US exchanges (default for unlimited subscription)
            - iex: Investors Exchange only  
            - otc: Over-the-counter exchanges
            - delayed_sip: SIP data with 15-minute delay
        currency (Optional[SupportedCurrencies]): Currency for prices in ISO 4217 format (default: USD)
    
    Returns:
        str: Formatted string containing comprehensive snapshots including:
            - Latest Quote (bid/ask prices, sizes, exchanges)
            - Latest Trade (price, size, exchange, conditions)
            - Current Minute Bar (OHLCV for current minute)
            - Daily Bar (OHLCV for current trading day)
            - Previous Daily Bar (OHLCV for previous trading day)
            - Calculated metrics (spreads, changes, volume analysis)
    """
    try:
        # Convert symbols to list and create comma-separated string
        if isinstance(symbols, str):
            symbol_list = [symbols]
            symbols_param = symbols
        else:
            symbol_list = symbols
            symbols_param = ','.join(symbols)
        
        # Build URL and parameters
        url = "https://data.alpaca.markets/v2/stocks/snapshots"
        params = {"symbols": symbols_param}
        
        if feed:
            if hasattr(feed, 'value'):
                params["feed"] = feed.value.lower()
            else:
                params["feed"] = str(feed).lower()
                
        if currency:
            if hasattr(currency, 'value'):
                params["currency"] = currency.value
            else:
                params["currency"] = str(currency)
        
        # Set up headers
        headers = {
            "accept": "application/json",
            "APCA-API-KEY-ID": API_KEY,
            "APCA-API-SECRET-KEY": API_SECRET
        }
        
        # Make the API request
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        
        # Parse response
        data = response.json()
        
        if not data:
            return f"No snapshot data found for symbols: {symbols_param}"
        
        # Format the response
        result = f"Stock Market Snapshots:\n"
        result += "=" * 50 + "\n\n"
        
        for symbol in symbol_list:
            if symbol not in data:
                result += f"❌ {symbol}: No data available\n\n"
                continue
                
            snapshot = data[symbol]
            result += f"📊 {symbol}\n"
            result += "-" * (len(symbol) + 3) + "\n"
            
            # Latest Quote
            if "latestQuote" in snapshot and snapshot["latestQuote"]:
                quote = snapshot["latestQuote"]
                bid_price = quote.get("bp", 0)
                ask_price = quote.get("ap", 0)
                bid_size = quote.get("bs", 0)
                ask_size = quote.get("as", 0)
                
                result += "💰 Latest Quote:\n"
                result += f"  Bid: ${bid_price:.2f} x {bid_size:,}\n"
                result += f"  Ask: ${ask_price:.2f} x {ask_size:,}\n"
                
                if bid_price > 0 and ask_price > 0:
                    spread = ask_price - bid_price
                    spread_pct = (spread / bid_price * 100) if bid_price > 0 else 0
                    result += f"  Spread: ${spread:.2f} ({spread_pct:.2f}%)\n"
                
                if quote.get("bx"):
                    result += f"  Bid Exchange: {quote['bx']}\n"
                if quote.get("ax"):
                    result += f"  Ask Exchange: {quote['ax']}\n"
                
                if quote.get("t"):
                    result += f"  Quote Time: {quote['t']}\n"
            
            # Latest Trade
            if "latestTrade" in snapshot and snapshot["latestTrade"]:
                trade = snapshot["latestTrade"]
                trade_price = trade.get("p", 0)
                trade_size = trade.get("s", 0)
                
                result += "\n🔄 Latest Trade:\n"
                result += f"  Price: ${trade_price:.4f}\n"
                result += f"  Size: {trade_size:,} shares\n"
                
                if trade.get("x"):
                    result += f"  Exchange: {trade['x']}\n"
                if trade.get("c"):
                    result += f"  Conditions: {', '.join(trade['c'])}\n"
                if trade.get("t"):
                    result += f"  Trade Time: {trade['t']}\n"
            
            # Current Minute Bar
            if "minuteBar" in snapshot and snapshot["minuteBar"]:
                bar = snapshot["minuteBar"]
                result += "\n📈 Current Minute Bar:\n"
                result += f"  Open: ${bar.get('o', 0):.2f}\n"
                result += f"  High: ${bar.get('h', 0):.2f}\n"
                result += f"  Low: ${bar.get('l', 0):.2f}\n"
                result += f"  Close: ${bar.get('c', 0):.2f}\n"
                result += f"  Volume: {bar.get('v', 0):,}\n"
                result += f"  Trade Count: {bar.get('n', 0):,}\n"
                if bar.get('vw'):
                    result += f"  VWAP: ${bar['vw']:.2f}\n"
                if bar.get('t'):
                    result += f"  Bar Time: {bar['t']}\n"
            
            # Current Daily Bar
            if "dailyBar" in snapshot and snapshot["dailyBar"]:
                daily = snapshot["dailyBar"]
                open_price = daily.get('o', 0)
                close_price = daily.get('c', 0)
                
                result += "\n📅 Today's Daily Bar:\n"
                result += f"  Open: ${open_price:.2f}\n"
                result += f"  High: ${daily.get('h', 0):.2f}\n"
                result += f"  Low: ${daily.get('l', 0):.2f}\n"
                result += f"  Close: ${close_price:.2f}\n"
                
                # Calculate daily change
                if open_price > 0:
                    daily_change = close_price - open_price
                    daily_change_pct = (daily_change / open_price * 100)
                    result += f"  Change: ${daily_change:+.2f} ({daily_change_pct:+.2f}%)\n"
                
                result += f"  Volume: {daily.get('v', 0):,}\n"
                result += f"  Trade Count: {daily.get('n', 0):,}\n"
                if daily.get('vw'):
                    result += f"  VWAP: ${daily['vw']:.2f}\n"
                if daily.get('t'):
                    result += f"  Date: {daily['t']}\n"
            
            # Previous Daily Bar
            if "prevDailyBar" in snapshot and snapshot["prevDailyBar"]:
                prev = snapshot["prevDailyBar"]
                prev_close = prev.get('c', 0)
                
                result += "\n📊 Previous Day:\n"
                result += f"  Open: ${prev.get('o', 0):.2f}\n"
                result += f"  High: ${prev.get('h', 0):.2f}\n"
                result += f"  Low: ${prev.get('l', 0):.2f}\n"
                result += f"  Close: ${prev_close:.2f}\n"
                result += f"  Volume: {prev.get('v', 0):,}\n"
                
                # Calculate overnight change
                if (prev_close > 0 and "dailyBar" in snapshot and 
                    snapshot["dailyBar"] and snapshot["dailyBar"].get('o', 0) > 0):
                    current_open = snapshot["dailyBar"]['o']
                    overnight_change = current_open - prev_close
                    overnight_change_pct = (overnight_change / prev_close * 100)
                    result += f"  Overnight Gap: ${overnight_change:+.2f} ({overnight_change_pct:+.2f}%)\n"
            
            # Market Analysis
            result += "\n🔍 Market Analysis:\n"
            
            # Trading activity
            if "dailyBar" in snapshot and snapshot["dailyBar"]:
                today_volume = snapshot["dailyBar"].get('v', 0)
                if "prevDailyBar" in snapshot and snapshot["prevDailyBar"]:
                    prev_volume = snapshot["prevDailyBar"].get('v', 0)
                    if prev_volume > 0:
                        volume_ratio = today_volume / prev_volume
                        if volume_ratio > 1.5:
                            result += "  Volume: Higher than average (strong interest)\n"
                        elif volume_ratio < 0.5:
                            result += "  Volume: Lower than average (light trading)\n"
                        else:
                            result += "  Volume: Normal trading activity\n"
                    else:
                        result += f"  Volume: {today_volume:,} shares today\n"
            
            # Price action relative to quote
            if ("latestTrade" in snapshot and snapshot["latestTrade"] and
                "latestQuote" in snapshot and snapshot["latestQuote"]):
                trade_price = snapshot["latestTrade"].get("p", 0)
                bid_price = snapshot["latestQuote"].get("bp", 0)
                ask_price = snapshot["latestQuote"].get("ap", 0)
                
                if bid_price > 0 and ask_price > 0:
                    if trade_price <= bid_price:
                        result += "  Last Trade: At/below bid (selling pressure)\n"
                    elif trade_price >= ask_price:
                        result += "  Last Trade: At/above ask (buying pressure)\n"
                    else:
                        result += "  Last Trade: Within spread (balanced)\n"
            
            # Liquidity assessment
            if "latestQuote" in snapshot and snapshot["latestQuote"]:
                total_size = snapshot["latestQuote"].get("bs", 0) + snapshot["latestQuote"].get("as", 0)
                if total_size > 1000:
                    result += "  Liquidity: High\n"
                elif total_size > 100:
                    result += "  Liquidity: Moderate\n"
                else:
                    result += "  Liquidity: Low\n"
            
            result += "\n" + "=" * 50 + "\n\n"
        
        return result.rstrip()
        
    except requests.exceptions.RequestException as e:
        return f"API request error: {str(e)}"
    except json.JSONDecodeError as e:
        return f"Error parsing response: {str(e)}"
    except Exception as e:
        return f"Error retrieving stock snapshots: {str(e)}"

# ============================================================================
# Real-Time Stock Market Data Streaming Tools
# ============================================================================

@mcp.tool()
async def start_global_stock_stream(
    symbols: List[str],
    data_types: List[str] = ["trades", "quotes"],
    feed: str = "sip",
    duration_seconds: Optional[int] = None,
    buffer_size_per_symbol: Optional[int] = None,
    replace_existing: bool = False
) -> str:
    """
    Start the global real-time stock market data stream (Alpaca allows only one stream connection).
    
    Args:
        symbols (List[str]): List of stock symbols to stream (e.g., ['AAPL', 'MSFT', 'NVDA'])
        data_types (List[str]): Types of stock data to stream. Options:
            - "trades": Real-time stock trade executions
            - "quotes": Stock bid/ask prices and sizes  
            - "bars": 1-minute OHLCV stock bars
            - "updated_bars": Corrections to stock minute bars
            - "daily_bars": Daily OHLCV stock bars
            - "statuses": Stock trading halt/resume notifications
        feed (str): Stock data feed source ("sip" for all exchanges, "iex" for IEX only)
        duration_seconds (Optional[int]): How long to run the stock stream in seconds. None = run indefinitely
        buffer_size_per_symbol (Optional[int]): Max items per stock symbol/data_type buffer. 
                                               None = unlimited (recommended for active stocks)
                                               High-velocity stocks may need 10000+ or unlimited
        replace_existing (bool): If True, stop existing stock stream and start new one
    
    Returns:
        str: Confirmation with stock stream details and data access instructions
    """
    global _global_stock_stream, _stock_stream_thread, _stock_stream_active, _stock_stream_start_time, _stock_stream_end_time
    
    try:
        # Check if stock stream already exists
        if _stock_stream_active and not replace_existing:
            current_symbols = set()
            for data_type, symbol_set in _stock_stream_subscriptions.items():
                current_symbols.update(symbol_set)
            
            return f"""
❌ Global stock stream already active!

Current Stock Stream:
└── Symbols: {', '.join(sorted(current_symbols)) if current_symbols else 'None'}
└── Data Types: {[dt for dt, symbols in _stock_stream_subscriptions.items() if symbols]}
└── Feed: {_stock_stream_config['feed'].upper()}
└── Runtime: {(time.time() - _stock_stream_start_time)/60:.1f} minutes

Options:
└── Use add_symbols_to_stock_stream() to add more symbols
└── Use stop_global_stock_stream() to stop current stream
└── Use replace_existing=True to replace current stream
            """
        
        # Stop existing stock stream if replacing
        if _stock_stream_active and replace_existing:
            await stop_global_stock_stream()
            await asyncio.sleep(2)  # Give time for cleanup
        
        # Validate parameters
        valid_data_types = ["trades", "quotes", "bars", "updated_bars", "daily_bars", "statuses"]
        invalid_types = [dt for dt in data_types if dt not in valid_data_types]
        if invalid_types:
            return f"Invalid data types: {invalid_types}. Valid options: {valid_data_types}"
        
        if feed.lower() not in ['sip', 'iex']:
            return "Feed must be 'sip' or 'iex'"
        
        # Convert symbols to uppercase
        symbols = [s.upper() for s in symbols]
        
        # Update global stock stream config
        _stock_stream_config.update({
            'feed': feed,
            'buffer_size': buffer_size_per_symbol,
            'duration_seconds': duration_seconds
        })
        
        # Create data feed enum
        feed_enum = DataFeed.SIP if feed.lower() == 'sip' else DataFeed.IEX
        
        # Create the single global stock stream
        _global_stock_stream = StockDataStream(
            api_key=API_KEY,
            secret_key=API_SECRET,
            feed=feed_enum,
            raw_data=False
        )
        
        # Subscribe to requested stock data types
        if "trades" in data_types:
            _global_stock_stream.subscribe_trades(handle_stock_trade, *symbols)
            _stock_stream_subscriptions['trades'].update(symbols)
        
        if "quotes" in data_types:
            _global_stock_stream.subscribe_quotes(handle_stock_quote, *symbols)
            _stock_stream_subscriptions['quotes'].update(symbols)
        
        if "bars" in data_types:
            _global_stock_stream.subscribe_bars(handle_stock_bar, *symbols)
            _stock_stream_subscriptions['bars'].update(symbols)
        
        if "updated_bars" in data_types:
            _global_stock_stream.subscribe_updated_bars(handle_stock_bar, *symbols)
            _stock_stream_subscriptions['updated_bars'].update(symbols)
        
        if "daily_bars" in data_types:
            _global_stock_stream.subscribe_daily_bars(handle_stock_bar, *symbols)
            _stock_stream_subscriptions['daily_bars'].update(symbols)
        
        if "statuses" in data_types:
            _global_stock_stream.subscribe_trading_statuses(handle_stock_status, *symbols)
            _stock_stream_subscriptions['statuses'].update(symbols)
        
        # Function to run the stock stream with duration monitoring
        def run_stock_stream():
            global _stock_stream_active, _stock_stream_start_time, _stock_stream_end_time
            
            try:
                _stock_stream_active = True
                _stock_stream_start_time = time.time()
                _stock_stream_end_time = _stock_stream_start_time + duration_seconds if duration_seconds else None
                
                print(f"Starting Alpaca stock stream for {len(symbols)} symbols...")
                
                # Start the stock stream
                _global_stock_stream.run()
                
            except Exception as e:
                print(f"Stock stream error: {e}")
            finally:
                _stock_stream_active = False
                print("Stock stream stopped")
        
        # Start the stock stream in a background thread
        _stock_stream_thread = threading.Thread(target=run_stock_stream, daemon=True)
        _stock_stream_thread.start()
        
        # Wait a moment for connection
        await asyncio.sleep(2)
        
        # Format response
        buffer_info = f"Unlimited" if buffer_size_per_symbol is None else f"{buffer_size_per_symbol:,} items"
        duration_info = f"{duration_seconds:,} seconds" if duration_seconds else "Indefinite"
        
        return f"""
🚀 GLOBAL STOCK STREAM STARTED SUCCESSFULLY!

📊 Stock Stream Configuration:
└── Symbols: {', '.join(symbols)} ({len(symbols)} stock symbols)
└── Data Types: {', '.join(data_types)}
└── Feed: {feed.upper()}
└── Duration: {duration_info}
└── Buffer Size per Symbol: {buffer_info}
└── Start Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

💾 Stock Data Storage:
└── Each stock symbol/data_type gets its own buffer
└── High-velocity stocks fully supported
└── Thread-safe concurrent access

📡 Access Your Stock Data:
└── get_stock_stream_data("AAPL", "trades") - Recent stock trades
└── get_stock_stream_buffer_stats() - Buffer statistics  
└── list_active_stock_streams() - Current stream status
└── get_stock_stream_analysis("NVDA", "momentum") - Real-time analysis

⚡ Stock Stream Management:
└── add_symbols_to_stock_stream(["TSLA", "META"]) - Add more stocks
└── stop_global_stock_stream() - Stop streaming

🔥 Pro Tips for Stock Trading:
└── For active stocks like NVDA, TSLA: unlimited buffers recommended
└── Use get_stock_stream_data() with time filters for analysis
└── Combine with stock snapshots for comprehensive market view
└── Stock stream data persists until manually cleared
        """
        
    except Exception as e:
        return f"Error starting global stock stream: {str(e)}"

@mcp.tool()
async def add_symbols_to_stock_stream(
    symbols: List[str],
    data_types: Optional[List[str]] = None
) -> str:
    """
    Add stock symbols to the existing global stock stream (if active).
    
    Args:
        symbols (List[str]): List of stock symbols to add
        data_types (Optional[List[str]]): Stock data types to subscribe for new symbols.
                                         If None, uses same types as existing subscriptions.
    
    Returns:
        str: Confirmation message with updated stock subscription details
    """
    global _global_stock_stream, _stock_stream_subscriptions
    
    try:
        if not _stock_stream_active or not _global_stock_stream:
            return "No active global stock stream. Use start_global_stock_stream() first."
        
        symbols = [s.upper() for s in symbols]
        
        # Determine data types to subscribe
        if data_types is None:
            # Use existing subscription types
            data_types = [dt for dt, symbol_set in _stock_stream_subscriptions.items() if symbol_set]
            if not data_types:
                return "No existing stock subscriptions found. Specify data_types parameter."
        
        # Add stock subscriptions
        added_subscriptions = []
        
        if "trades" in data_types and "trades" in [dt for dt, s in _stock_stream_subscriptions.items() if s]:
            _global_stock_stream.subscribe_trades(handle_stock_trade, *symbols)
            _stock_stream_subscriptions['trades'].update(symbols)
            added_subscriptions.append("trades")
        
        if "quotes" in data_types and "quotes" in [dt for dt, s in _stock_stream_subscriptions.items() if s]:
            _global_stock_stream.subscribe_quotes(handle_stock_quote, *symbols)
            _stock_stream_subscriptions['quotes'].update(symbols)
            added_subscriptions.append("quotes")
        
        if "bars" in data_types and "bars" in [dt for dt, s in _stock_stream_subscriptions.items() if s]:
            _global_stock_stream.subscribe_bars(handle_stock_bar, *symbols)
            _stock_stream_subscriptions['bars'].update(symbols)
            added_subscriptions.append("bars")
        
        # Create buffers for new stock symbols
        for symbol in symbols:
            for data_type in data_types:
                _get_or_create_stock_buffer(symbol, data_type, _stock_stream_config['buffer_size'])
        
        # Get current total stock symbols
        all_symbols = set()
        for symbol_set in _stock_stream_subscriptions.values():
            all_symbols.update(symbol_set)
        
        return f"""
✅ SYMBOLS ADDED TO STOCK STREAM

📈 Added: {', '.join(symbols)}
📊 Data Types: {', '.join(added_subscriptions)}
🔢 Total Stock Symbols: {len(all_symbols)}
💾 Buffers Created: {len(symbols) * len(data_types)}

Current Stock Stream:
└── All Symbols: {', '.join(sorted(all_symbols))}
└── Runtime: {(time.time() - _stock_stream_start_time)/60:.1f} minutes
└── Total Events: {sum(_stock_stream_stats.values()):,}
        """
        
    except Exception as e:
        return f"Error adding symbols to stock stream: {str(e)}"

@mcp.tool()
async def get_stock_stream_data(
    symbol: str,
    data_type: str,
    recent_seconds: Optional[int] = None,
    limit: Optional[int] = None
) -> str:
    """
    Retrieve streaming stock market data for a symbol with flexible filtering.
    
    Args:
        symbol (str): Stock symbol
        data_type (str): Type of stock data ("trades", "quotes", "bars", etc.)
        recent_seconds (Optional[int]): Get stock data from last N seconds. None = all data
        limit (Optional[int]): Maximum number of items to return. None = no limit
    
    Returns:
        str: Formatted streaming stock data with statistics
    """
    try:
        if not _stock_stream_active:
            return "No active stock stream. Use start_global_stock_stream() to begin streaming."
        
        symbol = symbol.upper()
        buffer_key = f"{symbol}_{data_type}"
        
        if buffer_key not in _stock_data_buffers:
            return f"No stock data buffer found for {symbol} {data_type}. Check if stock symbol is subscribed."
        
        buffer = _stock_data_buffers[buffer_key]
        
        # Get data based on filters
        if recent_seconds is not None:
            data = buffer.get_recent(recent_seconds)
            time_filter = f"last {recent_seconds}s"
        else:
            data = buffer.get_all()
            time_filter = "all time"
        
        # Apply limit if specified
        if limit is not None and len(data) > limit:
            data = data[-limit:]  # Get most recent items
            limit_info = f", limited to {limit} items"
        else:
            limit_info = ""
        
        if not data:
            return f"No {data_type} data found for {symbol} ({time_filter})"
        
        # Get buffer statistics
        buffer_stats = buffer.get_stats()
        
        # Format response
        result = f"📊 LIVE STOCK {data_type.upper()} DATA: {symbol}\n"
        result += f"Filter: {time_filter}{limit_info} | Found: {len(data)} items\n"
        result += f"Buffer: {buffer_stats['current_size']:,} current, {buffer_stats['total_added']:,} total added"
        if not buffer_stats['is_unlimited']:
            result += f", max {buffer_stats['max_size']:,}"
        result += "\n"
        result += "=" * 70 + "\n\n"
        
        # Format data based on type
        if data_type == "trades":
            if len(data) >= 2:
                # Calculate summary statistics
                total_volume = sum(item['size'] for item in data)
                avg_price = sum(item['price'] * item['size'] for item in data) / total_volume if total_volume > 0 else 0
                price_range = (min(item['price'] for item in data), max(item['price'] for item in data))
                
                # Calculate velocity (trades per minute)
                time_span = (data[-1]['timestamp'] - data[0]['timestamp']) / 60 if len(data) > 1 else 0
                trade_velocity = len(data) / time_span if time_span > 0 else 0
                
                result += f"📈 Stock Trading Summary:\n"
                result += f"  Total Stock Trades: {len(data):,}\n"
                result += f"  Total Volume: {total_volume:,} shares\n"
                result += f"  VWAP: ${avg_price:.4f}\n"
                result += f"  Price Range: ${price_range[0]:.4f} - ${price_range[1]:.4f}\n"
                result += f"  Trade Velocity: {trade_velocity:.1f} trades/min\n\n"
            
            # Show recent trades
            display_count = min(15, len(data))
            result += f"🔥 Recent Stock Trades (last {display_count}):\n"
            for trade in data[-display_count:]:
                timestamp_str = datetime.fromtimestamp(trade['timestamp']).strftime('%H:%M:%S.%f')[:-3]
                result += f"  {timestamp_str} | ${trade['price']:.4f} x {trade['size']:,} @ {trade['exchange']}"
                if trade.get('conditions'):
                    result += f" [{','.join(trade['conditions'])}]"
                result += "\n"
                
        elif data_type == "quotes":
            if data:
                latest_quote = data[-1]
                spreads = [item['spread'] for item in data]
                avg_spread = sum(spreads) / len(spreads)
                
                result += f"💰 Latest Stock Quote:\n"
                result += f"  Bid: ${latest_quote['bid_price']:.4f} x {latest_quote['bid_size']:,}\n"
                result += f"  Ask: ${latest_quote['ask_price']:.4f} x {latest_quote['ask_size']:,}\n"
                result += f"  Spread: ${latest_quote['spread']:.4f}\n"
                result += f"  Avg Spread: ${avg_spread:.4f}\n"
                result += f"  Quote Updates: {len(data)} in timeframe\n\n"
            
            # Show recent quotes
            display_count = min(10, len(data))
            result += f"📊 Recent Stock Quotes (last {display_count}):\n"
            for quote in data[-display_count:]:
                timestamp_str = datetime.fromtimestamp(quote['timestamp']).strftime('%H:%M:%S.%f')[:-3]
                result += f"  {timestamp_str} | ${quote['bid_price']:.4f}x{quote['bid_size']} / ${quote['ask_price']:.4f}x{quote['ask_size']}\n"
                
        elif data_type == "bars":
            if data:
                latest_bar = data[-1]
                
                result += f"📊 Latest Stock Bar:\n"
                result += f"  OHLC: ${latest_bar['open']:.4f} / ${latest_bar['high']:.4f} / ${latest_bar['low']:.4f} / ${latest_bar['close']:.4f}\n"
                result += f"  Volume: {latest_bar['volume']:,}\n"
                if latest_bar.get('vwap'):
                    result += f"  VWAP: ${latest_bar['vwap']:.4f}\n"
                result += f"  Bars Count: {len(data)}\n\n"
            
            # Show recent bars
            display_count = min(8, len(data))
            result += f"📈 Recent Stock Bars (last {display_count}):\n"
            for bar in data[-display_count:]:
                timestamp_str = datetime.fromtimestamp(bar['timestamp']).strftime('%H:%M')
                change = bar['close'] - bar['open']
                change_pct = (change / bar['open'] * 100) if bar['open'] > 0 else 0
                result += f"  {timestamp_str} | O:{bar['open']:.2f} H:{bar['high']:.2f} L:{bar['low']:.2f} C:{bar['close']:.2f} "
                result += f"({change:+.2f}, {change_pct:+.1f}%) Vol:{bar['volume']:,}\n"
        
        # Add buffer health info
        result += f"\n💾 Stock Data Buffer Health:\n"
        result += f"  Current Size: {buffer_stats['current_size']:,} items\n"
        result += f"  Total Added: {buffer_stats['total_added']:,} items\n"
        storage_info = 'Unlimited' if buffer_stats['is_unlimited'] else f"Limited to {buffer_stats['max_size']:,}"
        result += f"  Storage: {storage_info}\n"
        result += f"  Last Update: {datetime.fromtimestamp(buffer_stats['last_update']).strftime('%H:%M:%S')}\n"
        
        return result
        
    except Exception as e:
        return f"Error retrieving stock stream data: {str(e)}"

@mcp.tool()
async def get_stock_stream_buffer_stats() -> str:
    """
    Get comprehensive statistics about all stock stream buffers and performance.
    
    Returns:
        str: Detailed buffer statistics and stream performance metrics
    """
    try:
        if not _stock_stream_active:
            return "No active stock stream. Use start_global_stock_stream() to begin streaming."
        
        runtime_minutes = (time.time() - _stock_stream_start_time) / 60 if _stock_stream_start_time else 0
        
        result = f"📊 STOCK STREAM BUFFER STATISTICS\n"
        result += "=" * 50 + "\n\n"
        
        # Stream overview
        result += f"🔧 Stock Stream Status:\n"
        result += f"  Runtime: {runtime_minutes:.1f} minutes\n"
        result += f"  Feed: {_stock_stream_config['feed'].upper()}\n"
        
        if _stock_stream_config['duration_seconds']:
            remaining = (_stock_stream_config['duration_seconds'] - (time.time() - _stock_stream_start_time)) / 60
            result += f"  Remaining: {remaining:.1f} minutes\n"
        else:
            result += f"  Duration: Indefinite\n"
        
        buffer_limit = 'Unlimited' if _stock_stream_config['buffer_size'] is None else f"{_stock_stream_config['buffer_size']:,} per buffer"
        result += f"  Buffer Limit: {buffer_limit}\n\n"
        
        # Global statistics
        total_events = sum(_stock_stream_stats.values())
        result += f"📈 Global Stock Statistics:\n"
        result += f"  Total Events: {total_events:,}\n"
        
        for data_type, count in _stock_stream_stats.items():
            if count > 0:
                rate = count / runtime_minutes if runtime_minutes > 0 else 0
                result += f"  {data_type.title()}: {count:,} ({rate:.1f}/min)\n"
        
        # Buffer breakdown
        result += f"\n💾 Stock Buffer Breakdown:\n"
        result += f"  Total Buffers: {len(_stock_data_buffers)}\n\n"
        
        # Group by symbol for better readability
        symbols = set()
        for buffer_key in _stock_data_buffers.keys():
            symbol = buffer_key.split('_')[0]
            symbols.add(symbol)
        
        for symbol in sorted(symbols):
            symbol_buffers = {k: v for k, v in _stock_data_buffers.items() if k.startswith(f"{symbol}_")}
            
            result += f"📊 {symbol}:\n"
            symbol_total = 0
            
            for buffer_key, buffer in symbol_buffers.items():
                data_type = buffer_key.split('_', 1)[1]
                stats = buffer.get_stats()
                symbol_total += stats['current_size']
                
                result += f"  {data_type}: {stats['current_size']:,} items"
                if not stats['is_unlimited'] and stats['current_size'] == stats['max_size']:
                    result += " (FULL)"
                result += f" | Total added: {stats['total_added']:,}\n"
            
            result += f"  Subtotal: {symbol_total:,} items\n\n"
        
        # Performance metrics
        if runtime_minutes > 0 and total_events > 0:
            result += f"⚡ Performance:\n"
            result += f"  Events/minute: {total_events/runtime_minutes:.1f}\n"
            result += f"  Events/second: {total_events/(runtime_minutes*60):.2f}\n"
            
            # Estimate memory usage (rough approximation)
            avg_bytes_per_event = 200  # Rough estimate
            estimated_memory_mb = (total_events * avg_bytes_per_event) / (1024 * 1024)
            result += f"  Estimated Memory: {estimated_memory_mb:.1f} MB\n"
        
        # Subscription details
        result += f"\n🎯 Active Stock Subscriptions:\n"
        for data_type, symbol_set in _stock_stream_subscriptions.items():
            if symbol_set:
                result += f"  {data_type}: {', '.join(sorted(symbol_set))}\n"
        
        return result
        
    except Exception as e:
        return f"Error getting stock buffer stats: {str(e)}"

@mcp.tool()
async def clear_stock_stream_buffers(
    symbol: Optional[str] = None,
    data_type: Optional[str] = None
) -> str:
    """
    Clear stock stream buffers to free memory (useful for long-running streams).
    
    Args:
        symbol (Optional[str]): Specific symbol to clear. None = all symbols
        data_type (Optional[str]): Specific data type to clear. None = all data types
    
    Returns:
        str: Confirmation of buffers cleared
    """
    try:
        if not _stock_data_buffers:
            return "No stock stream buffers found to clear."
        
        cleared_count = 0
        cleared_items = 0
        
        if symbol and data_type:
            # Clear specific buffer
            buffer_key = f"{symbol.upper()}_{data_type}"
            if buffer_key in _stock_data_buffers:
                buffer = _stock_data_buffers[buffer_key]
                stats = buffer.get_stats()
                cleared_items = stats['current_size']
                buffer.clear()
                cleared_count = 1
                result = f"Cleared {buffer_key}: {cleared_items:,} items"
            else:
                result = f"Buffer {buffer_key} not found"
                
        elif symbol:
            # Clear all buffers for a symbol
            symbol = symbol.upper()
            for buffer_key, buffer in list(_stock_data_buffers.items()):
                if buffer_key.startswith(f"{symbol}_"):
                    stats = buffer.get_stats()
                    cleared_items += stats['current_size']
                    buffer.clear()
                    cleared_count += 1
            result = f"Cleared {cleared_count} buffers for {symbol}: {cleared_items:,} total items"
            
        elif data_type:
            # Clear all buffers for a data type
            for buffer_key, buffer in list(_stock_data_buffers.items()):
                if buffer_key.endswith(f"_{data_type}"):
                    stats = buffer.get_stats()
                    cleared_items += stats['current_size']
                    buffer.clear()
                    cleared_count += 1
            result = f"Cleared {cleared_count} {data_type} buffers: {cleared_items:,} total items"
            
        else:
            # Clear all buffers
            for buffer_key, buffer in _stock_data_buffers.items():
                stats = buffer.get_stats()
                cleared_items += stats['current_size']
                buffer.clear()
                cleared_count += 1
            result = f"Cleared all {cleared_count} buffers: {cleared_items:,} total items"
        
        return f"""
🗑️ STOCK BUFFERS CLEARED

{result}

💾 Memory Impact:
└── Freed approximately {cleared_items * 0.2:.1f} KB
└── Buffers remain active for new data
└── Stream continues normally

⚠️ Note: Historical data has been removed
└── Use get_stock_stream_data() to verify clearing
        """
        
    except Exception as e:
        return f"Error clearing stock buffers: {str(e)}"

@mcp.tool()
async def stop_global_stock_stream() -> str:
    """
    Stop the global stock streaming session and provide final statistics.
    
    Returns:
        str: Final statistics and confirmation message
    """
    global _global_stock_stream, _stock_stream_thread, _stock_stream_active, _stock_stream_subscriptions
    
    try:
        if not _stock_stream_active:
            return "No active stock stream to stop."
        
        # Calculate final statistics
        runtime_minutes = (time.time() - _stock_stream_start_time) / 60 if _stock_stream_start_time else 0
        total_events = sum(_stock_stream_stats.values())
        
        # Stop the stream
        _stock_stream_active = False
        
        if _global_stock_stream:
            try:
                _global_stock_stream.stop()
            except:
                pass  # Stream might already be stopped
        
        # Get final buffer statistics
        total_buffered_items = sum(len(buffer.get_all()) for buffer in _stock_data_buffers.values())
        
        # Clear subscriptions
        for data_type in _stock_stream_subscriptions:
            _stock_stream_subscriptions[data_type].clear()
        
        result = f"🛑 GLOBAL STOCK STREAM STOPPED\n"
        result += "=" * 40 + "\n\n"
        
        result += f"📊 Final Stock Statistics:\n"
        result += f"  Runtime: {runtime_minutes:.1f} minutes\n"
        result += f"  Total Events Processed: {total_events:,}\n"
        result += f"  Items in Buffers: {total_buffered_items:,}\n"
        
        if runtime_minutes > 0:
            result += f"  Average Rate: {total_events/runtime_minutes:.1f} events/min\n"
        
        # Breakdown by data type
        result += f"\n📈 Event Breakdown:\n"
        for data_type, count in _stock_stream_stats.items():
            if count > 0:
                percentage = (count / total_events * 100) if total_events > 0 else 0
                result += f"  {data_type.title()}: {count:,} ({percentage:.1f}%)\n"
        
        # Buffer retention info
        result += f"\n💾 Data Retention:\n"
        result += f"  Buffers: {len(_stock_data_buffers)} remain in memory\n"
        result += f"  Access: Use get_stock_stream_data() for historical analysis\n"
        result += f"  Cleanup: Use clear_stock_stream_buffers() to free memory\n"
        
        result += f"\n🔄 Restart Options:\n"
        result += f"  start_global_stock_stream() - Start fresh stream\n"
        result += f"  clear_stock_stream_buffers() - Free memory first\n"
        
        return result
        
    except Exception as e:
        return f"Error stopping stock stream: {str(e)}"

@mcp.tool()
async def list_active_stock_streams() -> str:
    """
    List all active stock streaming subscriptions and their status.
    
    Returns:
        str: Detailed information about active stock streams
    """
    try:
        if not _stock_stream_active:
            return "No active stock stream. Use start_global_stock_stream() to begin streaming."
        
        runtime_minutes = (time.time() - _stock_stream_start_time) / 60 if _stock_stream_start_time else 0
        
        result = f"📡 ACTIVE STOCK STREAMING STATUS\n"
        result += "=" * 50 + "\n\n"
        
        # Stream configuration
        result += f"🔧 Stream Configuration:\n"
        result += f"  Feed: {_stock_stream_config['feed'].upper()}\n"
        result += f"  Runtime: {runtime_minutes:.1f} minutes\n"
        buffer_size_info = 'Unlimited' if _stock_stream_config['buffer_size'] is None else f"{_stock_stream_config['buffer_size']:,} per buffer"
        result += f"  Buffer Size: {buffer_size_info}\n"
        
        if _stock_stream_config['duration_seconds']:
            remaining = (_stock_stream_config['duration_seconds'] - (time.time() - _stock_stream_start_time)) / 60
            result += f"  Duration: {_stock_stream_config['duration_seconds']/60:.1f} min ({remaining:.1f} min remaining)\n"
        else:
            result += f"  Duration: Indefinite\n"
        
        # Active subscriptions
        result += f"\n📊 Active Stock Subscriptions:\n"
        total_symbols = set()
        
        for data_type, symbol_set in _stock_stream_subscriptions.items():
            if symbol_set:
                result += f"  {data_type.upper()}: {', '.join(sorted(symbol_set))} ({len(symbol_set)} symbols)\n"
                total_symbols.update(symbol_set)
        
        result += f"\n🎯 Summary:\n"
        result += f"  Total Unique Symbols: {len(total_symbols)}\n"
        result += f"  Active Data Types: {len([dt for dt, symbols in _stock_stream_subscriptions.items() if symbols])}\n"
        result += f"  Total Subscriptions: {sum(len(symbols) for symbols in _stock_stream_subscriptions.values())}\n"
        
        # Event statistics
        total_events = sum(_stock_stream_stats.values())
        if total_events > 0:
            result += f"\n📈 Live Statistics:\n"
            result += f"  Total Events: {total_events:,}\n"
            
            for data_type, count in _stock_stream_stats.items():
                if count > 0:
                    rate = count / runtime_minutes if runtime_minutes > 0 else 0
                    result += f"  {data_type.title()}: {count:,} ({rate:.1f}/min)\n"
        
        # Buffer status
        result += f"\n💾 Buffer Status:\n"
        result += f"  Active Buffers: {len(_stock_data_buffers)}\n"
        
        total_items = sum(len(buffer.get_all()) for buffer in _stock_data_buffers.values())
        result += f"  Total Items Stored: {total_items:,}\n"
        
        # Quick access commands
        result += f"\n🚀 Quick Commands:\n"
        result += f"  get_stock_stream_data(\"AAPL\", \"trades\") - View recent trades\n"
        result += f"  get_stock_stream_buffer_stats() - Detailed buffer stats\n"
        result += f"  add_symbols_to_stock_stream([\"TSLA\"]) - Add more symbols\n"
        result += f"  stop_global_stock_stream() - Stop streaming\n"
        
        return result
        
    except Exception as e:
        return f"Error listing active stock streams: {str(e)}"

@mcp.tool()
async def get_stock_stream_analysis(
    symbol: str,
    analysis_type: str = "price_momentum"
) -> str:
    """
    Perform real-time analysis on streaming stock data.
    
    Args:
        symbol (str): Stock symbol to analyze
        analysis_type (str): Type of analysis to perform:
            - "price_momentum": Price movement and momentum indicators
            - "volume_analysis": Volume patterns and surges
            - "spread_analysis": Bid-ask spread patterns
            - "trade_frequency": Trading frequency and patterns
    
    Returns:
        str: Real-time analysis results
    """
    try:
        if not _stock_stream_active:
            return "No active stock stream. Use start_global_stock_stream() to begin streaming."
        
        symbol = symbol.upper()
        
        result = f"📊 REAL-TIME STOCK ANALYSIS: {symbol}\n"
        result += f"Analysis Type: {analysis_type.replace('_', ' ').title()}\n"
        result += "=" * 60 + "\n\n"
        
        if analysis_type == "price_momentum":
            # Get recent trade data
            trades_buffer_key = f"{symbol}_trades"
            quotes_buffer_key = f"{symbol}_quotes"
            
            if trades_buffer_key not in _stock_data_buffers:
                return f"No trade data available for {symbol}. Ensure symbol is subscribed to trades."
            
            trades_buffer = _stock_data_buffers[trades_buffer_key]
            trades_data = trades_buffer.get_recent(300)  # Last 5 minutes
            
            if len(trades_data) < 2:
                return f"Insufficient trade data for momentum analysis ({len(trades_data)} trades)"
            
            # Calculate momentum indicators
            prices = [trade['price'] for trade in trades_data]
            volumes = [trade['size'] for trade in trades_data]
            
            current_price = prices[-1]
            price_5min_ago = prices[0]
            price_change = current_price - price_5min_ago
            price_change_pct = (price_change / price_5min_ago * 100) if price_5min_ago > 0 else 0
            
            # Volume-weighted average price
            total_volume = sum(volumes)
            vwap = sum(trade['price'] * trade['size'] for trade in trades_data) / total_volume if total_volume > 0 else 0
            
            # Price volatility
            price_std = (sum((p - sum(prices)/len(prices))**2 for p in prices) / len(prices))**0.5
            
            result += f"🎯 Price Momentum Analysis:\n"
            result += f"  Current Price: ${current_price:.4f}\n"
            result += f"  5-min Change: ${price_change:+.4f} ({price_change_pct:+.2f}%)\n"
            result += f"  VWAP (5min): ${vwap:.4f}\n"
            result += f"  Price vs VWAP: {((current_price - vwap) / vwap * 100):+.2f}%\n"
            result += f"  Volatility: ${price_std:.4f}\n"
            result += f"  Trade Count: {len(trades_data)}\n"
            result += f"  Total Volume: {total_volume:,} shares\n"
            
            # Momentum signals
            result += f"\n📈 Momentum Signals:\n"
            if price_change_pct > 0.5:
                result += f"  🟢 Strong Upward Momentum (+{price_change_pct:.2f}%)\n"
            elif price_change_pct < -0.5:
                result += f"  🔴 Strong Downward Momentum ({price_change_pct:.2f}%)\n"
            else:
                result += f"  🟡 Neutral Momentum ({price_change_pct:.2f}%)\n"
            
            if current_price > vwap:
                result += f"  🟢 Trading above VWAP (bullish)\n"
            else:
                result += f"  🔴 Trading below VWAP (bearish)\n"
                
        elif analysis_type == "volume_analysis":
            trades_buffer_key = f"{symbol}_trades"
            
            if trades_buffer_key not in _stock_data_buffers:
                return f"No trade data available for {symbol}."
            
            trades_buffer = _stock_data_buffers[trades_buffer_key]
            recent_trades = trades_buffer.get_recent(300)  # Last 5 minutes
            all_trades = trades_buffer.get_recent(1800)   # Last 30 minutes for comparison
            
            if len(recent_trades) < 5:
                return f"Insufficient trade data for volume analysis"
            
            # Volume analysis
            recent_volume = sum(trade['size'] for trade in recent_trades)
            total_volume = sum(trade['size'] for trade in all_trades)
            avg_volume_per_5min = total_volume / 6 if len(all_trades) > 0 else recent_volume  # 30min / 6 = 5min periods
            
            volume_ratio = recent_volume / avg_volume_per_5min if avg_volume_per_5min > 0 else 1
            
            # Trade size analysis
            trade_sizes = [trade['size'] for trade in recent_trades]
            avg_trade_size = sum(trade_sizes) / len(trade_sizes)
            large_trades = [size for size in trade_sizes if size > avg_trade_size * 2]
            
            result += f"📊 Volume Analysis (5 minutes):\n"
            result += f"  Recent Volume: {recent_volume:,} shares\n"
            result += f"  Average 5min Volume: {avg_volume_per_5min:,.0f} shares\n"
            result += f"  Volume Ratio: {volume_ratio:.2f}x\n"
            result += f"  Trade Count: {len(recent_trades)}\n"
            result += f"  Average Trade Size: {avg_trade_size:,.0f} shares\n"
            result += f"  Large Trades (>2x avg): {len(large_trades)}\n"
            
            result += f"\n📈 Volume Signals:\n"
            if volume_ratio > 2.0:
                result += f"  🔥 High Volume Surge ({volume_ratio:.1f}x normal)\n"
            elif volume_ratio > 1.5:
                result += f"  🟡 Above Average Volume ({volume_ratio:.1f}x normal)\n"
            elif volume_ratio < 0.5:
                result += f"  📉 Low Volume ({volume_ratio:.1f}x normal)\n"
            else:
                result += f"  🟢 Normal Volume ({volume_ratio:.1f}x normal)\n"
                
        elif analysis_type == "spread_analysis":
            quotes_buffer_key = f"{symbol}_quotes"
            
            if quotes_buffer_key not in _stock_data_buffers:
                return f"No quote data available for {symbol}. Ensure symbol is subscribed to quotes."
            
            quotes_buffer = _stock_data_buffers[quotes_buffer_key]
            quotes_data = quotes_buffer.get_recent(300)  # Last 5 minutes
            
            if len(quotes_data) < 5:
                return f"Insufficient quote data for spread analysis"
            
            # Spread analysis
            spreads = [quote['spread'] for quote in quotes_data]
            avg_spread = sum(spreads) / len(spreads)
            current_spread = spreads[-1]
            min_spread = min(spreads)
            max_spread = max(spreads)
            
            # Liquidity analysis
            latest_quote = quotes_data[-1]
            total_liquidity = latest_quote['bid_size'] + latest_quote['ask_size']
            
            result += f"💰 Spread Analysis (5 minutes):\n"
            result += f"  Current Spread: ${current_spread:.4f}\n"
            result += f"  Average Spread: ${avg_spread:.4f}\n"
            result += f"  Spread Range: ${min_spread:.4f} - ${max_spread:.4f}\n"
            result += f"  Current Bid: ${latest_quote['bid_price']:.4f} x {latest_quote['bid_size']:,}\n"
            result += f"  Current Ask: ${latest_quote['ask_price']:.4f} x {latest_quote['ask_size']:,}\n"
            result += f"  Total Liquidity: {total_liquidity:,} shares\n"
            
            result += f"\n📊 Liquidity Signals:\n"
            if current_spread <= avg_spread * 0.8:
                result += f"  🟢 Tight Spread (good liquidity)\n"
            elif current_spread >= avg_spread * 1.2:
                result += f"  🔴 Wide Spread (poor liquidity)\n"
            else:
                result += f"  🟡 Normal Spread\n"
            
            if total_liquidity > 1000:
                result += f"  🟢 High Liquidity ({total_liquidity:,} shares)\n"
            elif total_liquidity > 100:
                result += f"  🟡 Moderate Liquidity ({total_liquidity:,} shares)\n"
            else:
                result += f"  🔴 Low Liquidity ({total_liquidity:,} shares)\n"
        
        else:
            return f"Unknown analysis type: {analysis_type}. Available: price_momentum, volume_analysis, spread_analysis, trade_frequency"
        
        # Add timestamp
        result += f"\n⏰ Analysis Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        result += f"🔄 Refresh: Call this function again for updated analysis\n"
        
        return result
        
    except Exception as e:
        return f"Error performing stock stream analysis: {str(e)}"

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
        time_in_force (str): Time in force for the order (default: DAY)
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

        # Validate time_in_force
        try:
            tif_enum = TimeInForce[time_in_force.upper()]
        except KeyError:
            return f"Invalid time_in_force: {time_in_force}."

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
        calendar = trade_client.get_calendar(start=start_date, end=end_date)
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
    ca_types: List[CorporateActionType],
    since: date,
    until: date,
    symbol: Optional[str] = None,
    cusip: Optional[str] = None,
    date_type: Optional[CorporateActionDateType] = None
) -> str:
    """
    Retrieves and formats corporate action announcements.
    
    Args:
        ca_types (List[CorporateActionType]): List of corporate action types to filter by
        since (date): Start date for the announcements
        until (date): End date for the announcements
        symbol (Optional[str]): Optional stock symbol to filter by
        cusip (Optional[str]): Optional CUSIP to filter by
        date_type (Optional[CorporateActionDateType]): Optional date type to filter by
    
    Returns:
        str: Formatted string containing corporate announcement details
    """
    try:
        request = GetCorporateAnnouncementsRequest(
            ca_types=ca_types,
            since=since,
            until=until,
            symbol=symbol,
            cusip=cusip,
            date_type=date_type
        )
        announcements = trade_client.get_corporate_announcements(request)
        result = "Corporate Announcements:\n----------------------\n"
        for ann in announcements:
            result += f"""
                        ID: {ann.id}
                        Corporate Action ID: {ann.corporate_action_id}
                        Type: {ann.ca_type}
                        Sub Type: {ann.ca_sub_type}
                        Initiating Symbol: {ann.initiating_symbol}
                        Target Symbol: {ann.target_symbol}
                        Declaration Date: {ann.declaration_date}
                        Ex Date: {ann.ex_date}
                        Record Date: {ann.record_date}
                        Payable Date: {ann.payable_date}
                        Cash: {ann.cash}
                        Old Rate: {ann.old_rate}
                        New Rate: {ann.new_rate}
                        ----------------------
                        """
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
        expiration_date (Optional[date]): Optional expiration date for the options
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
    """
    try:
        # Create the request object with all available parameters
        request = GetOptionContractsRequest(
            underlying_symbols=[underlying_symbol],
            expiration_date=expiration_date,
            strike_price_gte=strike_price_gte,
            strike_price_lte=strike_price_lte,
            type=type,
            status=status,
            root_symbol=root_symbol,
            limit=limit
        )
        
        # Get the option contracts
        response = trade_client.get_option_contracts(request)
        
        if not response or not response.option_contracts:
            return f"No option contracts found for {underlying_symbol} matching the criteria."
        
        # Format the response
        result = f"Option Contracts for {underlying_symbol}:\n"
        result += "----------------------------------------\n"
        
        for contract in response.option_contracts:
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
    
    Args:
        legs (List[Dict[str, Any]]): List of option legs, where each leg is a dictionary containing:
            - symbol (str): Option contract symbol (e.g., 'AAPL230616C00150000')
            - side (str): 'buy' or 'sell'
            - ratio_qty (int): Quantity ratio for the leg (1-4)
        order_class (Optional[Union[str, OrderClass]]): Order class ('simple', 'bracket', 'oco', 'oto', 'mleg' or OrderClass enum)
            Defaults to 'simple' for single leg, 'mleg' for multi-leg
        quantity (int): Base quantity for the order (default: 1)
        time_in_force (TimeInForce): Time in force for the order (default: DAY)
        extended_hours (bool): Whether to allow execution during extended hours (default: False)
    
    Returns:
        str: Formatted string containing order details including:
            - Order ID and Client Order ID
            - Order Class and Type
            - Time in Force and Status
            - Quantity
            - Leg Details (for multi-leg orders):
                * Symbol and Side
                * Ratio Quantity
                * Status
                * Asset Class
                * Created/Updated Timestamps
                * Filled Price (if filled)
                * Filled Time (if filled)
    
    Note:
        Some option strategies may require specific account permissions:
        - Level 1: Covered calls, Covered puts, Cash-Secured put, etc.
        - Level 2: Long calls, Long puts, cash-secured puts, etc.
        - Level 3: Spreads and combinations: Butterfly Spreads, Straddles, Strangles, Calendar Spreads (except for short call calendar spread, short strangles, short straddles)
        - Level 4: Uncovered options (naked calls/puts), Short Strangles, Short Straddles, Short Call Calendar Spread, etc.
        If you receive a permission error, please check your account's option trading level.
    """
    try:
        # Validate legs
        if not legs:
            return "Error: No option legs provided"
        if len(legs) > 4:
            return "Error: Maximum of 4 legs allowed for option orders"
        
        # Validate quantity
        if quantity <= 0:
            return "Error: Quantity must be positive"
        
        # Convert order_class string to enum if needed
        if isinstance(order_class, str):
            order_class = order_class.upper()
            if order_class == 'SIMPLE':
                order_class = OrderClass.SIMPLE
            elif order_class == 'BRACKET':
                order_class = OrderClass.BRACKET
            elif order_class == 'OCO':
                order_class = OrderClass.OCO
            elif order_class == 'OTO':
                order_class = OrderClass.OTO
            elif order_class == 'MLEG':
                order_class = OrderClass.MLEG
            else:
                return f"Invalid order class: {order_class}. Must be one of: simple, bracket, oco, oto, mleg"
        
        # Determine order class if not provided
        if order_class is None:
            order_class = OrderClass.MLEG if len(legs) > 1 else OrderClass.SIMPLE
        
        # Convert legs to OptionLegRequest objects
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
        
        # Create market order request
        if order_class == OrderClass.MLEG:
            order_data = MarketOrderRequest(
                qty=quantity,
                order_class=order_class,
                time_in_force=time_in_force,
                extended_hours=extended_hours,
                client_order_id=f"mcp_opt_{int(time.time())}",
                type=OrderType.MARKET,
                legs=order_legs  # Set legs directly in the constructor for multi-leg orders
            )
        else:
            # For single-leg orders
            order_data = MarketOrderRequest(
                symbol=order_legs[0].symbol,
                qty=quantity,
                order_class=order_class,
                time_in_force=time_in_force,
                extended_hours=extended_hours,
                client_order_id=f"mcp_opt_{int(time.time())}",
                type=OrderType.MARKET
            )
        
        # Submit order
        order = trade_client.submit_order(order_data)
        
        # Format the response
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
        
    except APIError as api_error:
        error_message = str(api_error)
        if "40310000" in error_message and "not eligible to trade uncovered option contracts" in error_message:
            # Check if it's a short straddle by examining the legs
            is_short_straddle = False
            is_short_strangle = False
            is_short_calendar = False
            
            if order_class == OrderClass.MLEG and len(order_legs) == 2:
                # Check for short straddle (same strike, same expiration, both short)
                if (order_legs[0].side == OrderSide.SELL and 
                    order_legs[1].side == OrderSide.SELL and
                    order_legs[0].symbol.split('C')[0] == order_legs[1].symbol.split('P')[0]):
                    is_short_straddle = True
                # Check for short strangle (different strikes, same expiration, both short)
                elif (order_legs[0].side == OrderSide.SELL and 
                      order_legs[1].side == OrderSide.SELL):
                    is_short_strangle = True
                # Check for short calendar spread (same strike, different expirations, both short)
                elif (order_legs[0].side == OrderSide.SELL and 
                      order_legs[1].side == OrderSide.SELL):
                    # Extract option type (C for call, P for put) and expiration dates
                    leg1_type = 'C' if 'C' in order_legs[0].symbol else 'P'
                    leg2_type = 'C' if 'C' in order_legs[1].symbol else 'P'
                    leg1_exp = order_legs[0].symbol.split(leg1_type)[1][:6]
                    leg2_exp = order_legs[1].symbol.split(leg2_type)[1][:6]
                    
                    # Check if it's a short call calendar spread (both calls, longer-term is sold)
                    if (leg1_type == 'C' and leg2_type == 'C' and 
                        leg1_exp != leg2_exp):
                        is_short_calendar = True
            
            if is_short_straddle:
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
            elif is_short_strangle:
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
            elif is_short_calendar:
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
            else:
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
            
    except Exception as e:
        return f"""
        Unexpected error placing option order: {str(e)}
        
        Please try:
        1. Verifying all input parameters
        2. Checking your account status
        3. Ensuring market is open
        4. Contacting support if the issue persists
        """


# Run the server
if __name__ == "__main__":
    mcp.run(transport='stdio')