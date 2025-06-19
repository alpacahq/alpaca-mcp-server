"""Main MCP server implementation with prompt-driven architecture."""

import sys
import os

# Handle both direct execution and module import
if __name__ == "__main__" or not __package__:
    # Add parent directory to path for direct execution
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from alpaca_mcp_server.config.settings import settings
else:
    from .config.settings import settings

from mcp.server.fastmcp import FastMCP
from typing import Optional

# Import all tool modules
if __name__ == "__main__" or not __package__:
    from alpaca_mcp_server.tools import (
        account_tools,
        position_tools,
        order_tools,
        market_data_tools,
        market_info_tools,
        options_tools,
        watchlist_tools,
        asset_tools,
        corporate_action_tools,
        streaming_tools,
        monitoring_tools,
        fastapi_monitoring_tools,
    )
    from alpaca_mcp_server.tools.peak_trough_analysis_tool import (
        analyze_peaks_and_troughs as peak_trough_analysis,
    )
    from alpaca_mcp_server.tools.plot_py_tool import (
        generate_stock_plot as plot_py_generate_stock_plot,
    )
    from alpaca_mcp_server.tools.cleanup_tool import (
        cleanup_server,
        list_cleanup_candidates,
    )
    from alpaca_mcp_server.prompts import (
        account_analysis_prompt,
        position_management_prompt,
        market_analysis_prompt,
        tools_reference_prompt,
        startup_prompt,
        scan_prompt,
    )
else:
    from .tools import (
        account_tools,
        position_tools,
        order_tools,
        market_data_tools,
        monitoring_tools,
        market_info_tools,
        options_tools,
        watchlist_tools,
        asset_tools,
        corporate_action_tools,
        streaming_tools,
        fastapi_monitoring_tools,
    )
    from .tools.peak_trough_analysis_tool import (
        analyze_peaks_and_troughs as peak_trough_analysis,
    )
    from .tools.plot_py_tool import (
        generate_stock_plot as plot_py_generate_stock_plot,
    )
    from .tools.cleanup_tool import (
        cleanup_server,
        list_cleanup_candidates,
    )
    from .prompts import (
        account_analysis_prompt,
        position_management_prompt,
        market_analysis_prompt,
        tools_reference_prompt,
        startup_prompt,
        scan_prompt,
    )

# Import resource modules
if __name__ == "__main__" or not __package__:
    from alpaca_mcp_server.resources import (
        account_resources,
        market_resources,
        position_resources,
        portfolio_resources,
        streaming_resources,
        market_momentum,
        intraday_pnl,
        data_quality,
        server_health,
        session_status,
        api_monitor,
        help_system,
    )
else:
    from .resources import (
        account_resources,
        market_resources,
        position_resources,
        portfolio_resources,
        streaming_resources,
        market_momentum,
        intraday_pnl,
        data_quality,
        server_health,
        session_status,
        api_monitor,
        help_system,
    )

# Create the FastMCP server instance
mcp = FastMCP(
    name=settings.server_name,
    version=settings.version,
    dependencies=["alpaca-py>=0.40.1", "python-dotenv>=1.1.0"],
)

# Apply Claude Code compatibility patches
if __name__ == "__main__" or not __package__:
    from alpaca_mcp_server.compatibility import apply_claude_code_compatibility
    from alpaca_mcp_server.claude_code_tool_fix import (
        apply_claude_code_tool_registration_fix,
        force_claude_code_protocol_compliance,
        add_claude_code_debug_tools,
    )
else:
    from .compatibility import apply_claude_code_compatibility
    from .claude_code_tool_fix import (
        apply_claude_code_tool_registration_fix,
        force_claude_code_protocol_compliance,
        add_claude_code_debug_tools,
    )

print("🔧 Applying Claude Code MCP compatibility patches...")
_compatibility_patch = apply_claude_code_compatibility(mcp)
mcp = apply_claude_code_tool_registration_fix(mcp)
mcp = force_claude_code_protocol_compliance(mcp)
mcp = add_claude_code_debug_tools(mcp)

# ============================================================================
# PROMPTS - Guided Trading Workflows (Highest Leverage)
# ============================================================================


@mcp.prompt()
async def list_trading_capabilities() -> str:
    """List all Alpaca trading capabilities with guided workflows."""
    # Import locally to avoid any naming conflicts
    if __name__ == "__main__" or not __package__:
        from alpaca_mcp_server.prompts.list_trading_capabilities import (
            list_trading_capabilities as ltc_func,
        )
    else:
        from .prompts.list_trading_capabilities import (
            list_trading_capabilities as ltc_func,
        )

    return await ltc_func()


@mcp.prompt()
async def account_analysis() -> str:
    """Complete portfolio health check with actionable insights."""
    return await account_analysis_prompt.account_analysis()


@mcp.prompt()
async def position_management(symbol: Optional[str] = None) -> str:
    """Strategic position review and optimization."""
    return await position_management_prompt.position_management(symbol)


@mcp.prompt()
async def market_analysis(
    symbols: list = None, timeframe: str = "1Day", analysis_type: str = "comprehensive"
) -> str:
    """Real-time market analysis with trading opportunities."""
    return await market_analysis_prompt.market_analysis(
        symbols, timeframe, analysis_type
    )


@mcp.prompt()
async def list_all_tools() -> str:
    """List all available MCP tools with descriptions and usage examples."""
    return await tools_reference_prompt.list_all_tools()


# Duplicate registration removed - see line 925 for the actual startup prompt


# ============================================================================
# TOOLS - Individual Trading Actions (Composed by Prompts)
# ============================================================================


# Account & Position Management Tools
@mcp.tool()
async def get_account_info() -> str:
    """Get current account information including balances and status."""
    return await account_tools.get_account_info()


@mcp.tool()
async def get_positions() -> str:
    """Get all current positions in the portfolio."""
    return await account_tools.get_positions()


@mcp.tool()
async def get_open_position(symbol: str) -> str:
    """Get details for a specific open position."""
    return await account_tools.get_open_position(symbol)


@mcp.tool()
async def close_position(symbol: str, qty: str = None, percentage: str = None) -> str:
    """Close a specific position."""
    return await position_tools.close_position(symbol, qty, percentage)


@mcp.tool()
async def close_all_positions(cancel_orders: bool = False) -> str:
    """Close all open positions."""
    return await position_tools.close_all_positions(cancel_orders)


# Market Data Tools
@mcp.tool()
async def get_stock_quote(symbol: str, help: str = None) -> str:
    """Get latest quote for a stock."""
    # Check for help parameter
    if help == "--help" or help == "help":
        return help_system.get_help_system().get_tool_help("get_stock_quote")

    return await market_data_tools.get_stock_quote(symbol)


@mcp.tool()
async def get_stock_snapshots(symbols: str) -> str:
    """Get comprehensive market snapshots."""
    return await market_data_tools.get_stock_snapshots(symbols)


@mcp.tool()
async def get_stock_bars(symbol: str, days: int = 5) -> str:
    """Get historical price bars."""
    return await market_data_tools.get_stock_bars(symbol, days)


@mcp.tool()
async def get_stock_bars_intraday(
    symbol: str,
    timeframe: str = "1Min",
    start_date: str = None,
    end_date: str = None,
    limit: int = 10000,
) -> str:
    """Get intraday historical bars with analysis."""
    return await market_data_tools.get_stock_bars_intraday(
        symbol, timeframe, start_date, end_date, limit
    )


@mcp.tool()
async def get_stock_trades(symbol: str, days: int = 5, limit: int = None) -> str:
    """Get recent trades for a stock."""
    return await market_data_tools.get_stock_trades(symbol, days, limit)


@mcp.tool()
async def get_stock_latest_trade(symbol: str) -> str:
    """Get the latest trade for a stock."""
    return await market_data_tools.get_stock_latest_trade(symbol)


@mcp.tool()
async def get_stock_latest_bar(symbol: str) -> str:
    """Get the latest minute bar for a stock."""
    return await market_data_tools.get_stock_latest_bar(symbol)


# Market Info Tools
@mcp.tool()
async def get_market_clock() -> str:
    """Get current market status and next open/close times."""
    return await market_info_tools.get_market_clock()


@mcp.tool()
async def get_market_calendar(start_date: str, end_date: str) -> str:
    """Get market calendar for specified date range."""
    return await market_info_tools.get_market_calendar(start_date, end_date)


# Options Tools
@mcp.tool()
async def get_option_contracts(
    underlying_symbol: str,
    expiration_date: str = None,
    strike_price_gte: str = None,
    strike_price_lte: str = None,
    type: str = None,
    limit: int = None,
) -> str:
    """Get option contracts for underlying symbol."""
    return await options_tools.get_option_contracts(
        underlying_symbol,
        expiration_date,
        strike_price_gte,
        strike_price_lte,
        type,
        None,
        None,
        limit,
    )


@mcp.tool()
async def get_option_latest_quote(symbol: str) -> str:
    """Get latest quote for an option contract."""
    return await options_tools.get_option_latest_quote(symbol)


@mcp.tool()
async def get_option_snapshot(symbol: str) -> str:
    """Get comprehensive option snapshot with Greeks."""
    return await options_tools.get_option_snapshot(symbol)


# Stock Technical Analysis Tool
@mcp.tool()
async def get_stock_peak_trough_analysis(
    symbols: str = "AUTO",
    timeframe: str = "1Min",
    days: int = 1,
    limit: int = 1000,
    window_len: int = 21,
    lookahead: int = 1,
    delta: float = 0.0,
    min_peak_distance: int = 5,
) -> str:
    """
    Get stock peak and trough analysis for day trading signals using zero-phase Hanning filtering.

    This professional technical analysis tool:
    1. Fetches intraday bar data for specified symbols
    2. Applies zero-phase low-pass Hanning filtering to remove noise
    3. Detects peaks/troughs using advanced algorithms
    4. Returns precise entry/exit levels for day trading

    Perfect for identifying support/resistance levels and timing entries based on
    yesterday's trading lessons: "SCAN LONGER before entry" - this tool provides
    the technical analysis to find optimal entry points.

    Args:
        symbols: "AUTO" for current scanner results, or manual symbols (e.g., "AAPL,MSFT,NVDA")
        timeframe: "1Min", "5Min", "15Min", "30Min", "1Hour" (default: "1Min")
        days: Historical days to analyze (1-30, default: 1)
        limit: Max bars to fetch (1-10000, default: 1000)
        window_len: Hanning filter smoothing (3-101, default: 21)
        lookahead: Peak detection sensitivity (1-50, default: 1)
        delta: Minimum peak amplitude (default: 0.0 for penny stocks)
        min_peak_distance: Min bars between peaks (default: 5)

    Returns detailed analysis with BUY/LONG and SELL/SHORT signals.
    """
    return await peak_trough_analysis(
        symbols, timeframe, days, limit, window_len, lookahead, delta, min_peak_distance
    )


# Day Trading Scanner Tools
@mcp.tool()
async def scan_day_trading_opportunities(
    symbols: str = "ALL",
    min_trades_per_minute: int = 500,
    min_percent_change: float = 10.0,
    max_symbols: int = 20,
    sort_by: str = "trades",
) -> str:
    """
    Scan for EXPLOSIVE UP-ONLY day-trading opportunities with extreme volatility.

    UPDATED FILTER CRITERIA:
    1. ONLY UP STOCKS - No negative movers ever
    2. Minimum +10% daily gain for consideration  
    3. Minimum 500 trades/minute for extreme liquidity
    4. EXPLOSIVE VOLATILITY FOCUS - Penny stocks and rocket ships preferred

    Args:
        symbols: Comma-separated symbols to scan (default: ALL tradeable assets)
        min_trades_per_minute: Minimum trades in current minute bar (default: 500 for extreme liquidity)
        min_percent_change: Minimum % change from reference (default: 10.0% for explosive moves)
        max_symbols: Maximum results to return (default: 20)
        sort_by: Sort results by "trades", "percent_change", or "volume"

    Returns:
        Formatted analysis with EXPLOSIVE UP-ONLY trading opportunities.
    """
    from .tools.day_trading_scanner import (
        scan_day_trading_opportunities as scanner_func,
    )

    return await scanner_func(
        symbols, min_trades_per_minute, min_percent_change, max_symbols, sort_by
    )


@mcp.tool()
async def scan_explosive_momentum(
    symbols: str = "CVAC,CGTL,GNLN,NEHC,SOUN,RIOT,MARA,COIN,HOOD,RBLX",
    min_percent_change: float = 15.0,
) -> str:
    """
    Quick scanner for explosive momentum moves like NEHC.

    Optimized for finding extreme percentage movers with high activity.
    Lower trade threshold but higher % change requirement for explosive stocks.

    Args:
        symbols: Comma-separated symbols (default: volatile/momentum stocks)
        min_percent_change: Minimum absolute % change (default: 15.0% for explosive moves)

    Returns:
        Top explosive momentum opportunities sorted by % change.
    """
    from .tools.day_trading_scanner import scan_explosive_momentum as explosive_func

    return await explosive_func(symbols, min_percent_change)


# After-Hours and Enhanced Analytics Tools
@mcp.tool()
async def scan_after_hours_opportunities(
    symbols: str = "AAPL,MSFT,NVDA,TSLA,GOOGL,AMZN,META,NFLX,COIN,HOOD,AMC,GME,PLTR,SOFI,RIVN,LCID",
    min_volume: int = 100000,
    min_percent_change: float = 2.0,
    max_symbols: int = 15,
    sort_by: str = "percent_change",
) -> str:
    """
    Scan for after-hours trading opportunities with enhanced analytics.

    Focuses on:
    1. Extended hours price movements
    2. Volume analysis relative to average
    3. News-driven momentum detection
    4. Liquidity assessment for safe entry/exit

    Args:
        symbols: Comma-separated symbols for after-hours scanning
        min_volume: Minimum after-hours volume threshold
        min_percent_change: Minimum % change from regular session close
        max_symbols: Maximum results to return
        sort_by: Sort results by "percent_change", "volume", or "price"

    Returns:
        Formatted analysis of after-hours opportunities
    """
    from .tools.after_hours_scanner import (
        scan_after_hours_opportunities as scanner_func,
    )

    return await scanner_func(
        symbols, min_volume, min_percent_change, max_symbols, sort_by
    )


@mcp.tool()
async def get_enhanced_streaming_analytics(
    symbol: str, analysis_minutes: int = 15, include_orderbook: bool = True
) -> str:
    """
    Enhanced streaming analytics with real-time calculations.

    Provides:
    1. Real-time momentum analysis
    2. Volume-weighted average price (VWAP)
    3. Order flow analysis
    4. Support/resistance detection
    5. Volatility measurements

    Args:
        symbol: Stock symbol to analyze
        analysis_minutes: Minutes of historical data to include
        include_orderbook: Include bid/ask analysis

    Returns:
        Comprehensive real-time analytics
    """
    from .tools.after_hours_scanner import (
        get_enhanced_streaming_analytics as analytics_func,
    )

    return await analytics_func(symbol, analysis_minutes, include_orderbook)


# Watchlist Tools
@mcp.tool()
async def create_watchlist(name: str, symbols: list) -> str:
    """Create a new watchlist with specified symbols."""
    return await watchlist_tools.create_watchlist(name, symbols)


@mcp.tool()
async def get_watchlists() -> str:
    """Get all watchlists for the account."""
    return await watchlist_tools.get_watchlists()


@mcp.tool()
async def update_watchlist(
    watchlist_id: str, name: str = None, symbols: list = None
) -> str:
    """Update an existing watchlist."""
    return await watchlist_tools.update_watchlist(watchlist_id, name, symbols)


# Asset Tools
@mcp.tool()
async def get_all_assets(
    status: str = None,
    asset_class: str = None,
    exchange: str = None,
    attributes: str = None,
) -> str:
    """Get all available assets with optional filtering."""
    return await asset_tools.get_all_assets(status, asset_class, exchange, attributes)


@mcp.tool()
async def get_asset_info(symbol: str) -> str:
    """Get detailed information about a specific asset."""
    return await asset_tools.get_asset_info(symbol)


# Corporate Actions Tools
@mcp.tool()
async def get_corporate_announcements(
    ca_types: list,
    since: str,
    until: str,
    symbol: Optional[str] = None,
    cusip: str = None,
    date_type: str = None,
) -> str:
    """Get corporate action announcements for specified criteria."""
    return await corporate_action_tools.get_corporate_announcements(
        ca_types, since, until, symbol, cusip, date_type
    )


# Real-time Streaming Tools (Critical for Day Trading)
@mcp.tool()
async def start_global_stock_stream(
    symbols: list,
    data_types: list = ["trades", "quotes"],
    feed: str = "sip",
    duration_seconds: int = None,
    buffer_size_per_symbol: int = None,
    replace_existing: bool = False,
) -> str:
    """Start global real-time stock data stream for day trading."""
    return await streaming_tools.start_global_stock_stream(
        symbols,
        data_types,
        feed,
        duration_seconds,
        buffer_size_per_symbol,
        replace_existing,
    )


@mcp.tool()
async def stop_global_stock_stream() -> str:
    """Stop the global stock streaming session."""
    return await streaming_tools.stop_global_stock_stream()


@mcp.tool()
async def add_symbols_to_stock_stream(symbols: list, data_types: list = None) -> str:
    """Add symbols to existing stock stream."""
    return await streaming_tools.add_symbols_to_stock_stream(symbols, data_types)


@mcp.tool()
async def get_stock_stream_data(
    symbol: str, data_type: str, recent_seconds: int = None, limit: int = None
) -> str:
    """Get streaming data for analysis."""
    return await streaming_tools.get_stock_stream_data(
        symbol, data_type, recent_seconds, limit
    )


@mcp.tool()
async def list_active_stock_streams() -> str:
    """List all active streaming subscriptions."""
    return await streaming_tools.list_active_stock_streams()


@mcp.tool()
async def get_stock_stream_buffer_stats() -> str:
    """Get detailed streaming buffer statistics."""
    return await streaming_tools.get_stock_stream_buffer_stats()


@mcp.tool()
async def clear_stock_stream_buffers() -> str:
    """Clear streaming buffers to free memory."""
    return await streaming_tools.clear_stock_stream_buffers()


# Stream-Centric Concurrent Architecture Tools (New)
@mcp.tool()
async def stream_aware_price_monitor(symbol: str, analysis_seconds: int = 10) -> str:
    """Enhanced real-time price monitoring using shared stream with concurrent analysis."""
    return await streaming_tools.stream_aware_price_monitor(symbol, analysis_seconds)


@mcp.tool()
async def stream_optimized_order_placement(
    symbol: str, side: str, quantity: float, order_type: str = "limit"
) -> str:
    """Place order using optimal pricing from active stream."""
    return await streaming_tools.stream_optimized_order_placement(
        symbol, side, quantity, order_type
    )


# Order Management Tools
@mcp.tool()
async def place_stock_order(
    symbol: str,
    side: str,
    quantity: float,
    order_type: str = "market",
    time_in_force: str = "day",
    limit_price: Optional[float] = None,
    stop_price: Optional[float] = None,
    trail_price: Optional[float] = None,
    trail_percent: Optional[float] = None,
    extended_hours: bool = False,
    client_order_id: Optional[str] = None,
) -> str:
    """Place a stock order of any type."""
    return await order_tools.place_stock_order(
        symbol,
        side,
        quantity,
        order_type,
        time_in_force,
        limit_price,
        stop_price,
        trail_price,
        trail_percent,
        extended_hours,
        client_order_id,
    )


@mcp.tool()
async def get_orders(status: str = "all", limit: int = 10) -> str:
    """Get orders with specified status."""
    return await order_tools.get_orders(status, limit)


@mcp.tool()
async def cancel_order_by_id(order_id: str) -> str:
    """Cancel a specific order by ID."""
    return await order_tools.cancel_order_by_id(order_id)


@mcp.tool()
async def cancel_all_orders() -> str:
    """Cancel all open orders."""
    return await order_tools.cancel_all_orders()


@mcp.tool()
async def place_option_market_order(
    legs: list, order_class: Optional[str] = None, quantity: int = 1
) -> str:
    """Place single or multi-leg options market order."""
    return await order_tools.place_option_market_order(legs, order_class, quantity)


# ============================================================================
# RESOURCES - Dynamic Trading Context
# ============================================================================


@mcp.resource("account://status")
async def get_account_status() -> dict:
    """Real-time account health and trading capacity."""
    return await account_resources.get_account_status()


@mcp.resource("positions://current")
async def get_current_positions() -> dict:
    """Live position data with P&L updates."""
    return await position_resources.get_current_positions()


@mcp.resource("market://conditions")
async def get_market_conditions() -> dict:
    """Current market status and conditions."""
    return await market_resources.get_market_conditions()


@mcp.resource("portfolio://performance")
async def get_portfolio_performance() -> dict:
    """Real-time portfolio performance metrics and P&L analysis."""
    return await portfolio_resources.get_portfolio_performance()


@mcp.resource("portfolio://allocation")
async def get_portfolio_allocation() -> dict:
    """Asset allocation breakdown with winners/losers analysis."""
    return await portfolio_resources.get_portfolio_allocation()


@mcp.resource("portfolio://risk")
async def get_portfolio_risk() -> dict:
    """Portfolio risk metrics and exposure analysis."""
    return await portfolio_resources.get_portfolio_risk()


@mcp.resource("streams://status")
async def get_stream_status() -> dict:
    """Real-time streaming status and buffer statistics."""
    return await streaming_resources.get_stream_status()


@mcp.resource("streams://performance")
async def get_stream_performance() -> dict:
    """Streaming performance metrics and health indicators."""
    return await streaming_resources.get_stream_performance()


@mcp.resource("market://momentum")
async def get_market_momentum_resource() -> dict:
    """Real-time market momentum for SPY with default parameters."""
    return await market_momentum.get_market_momentum()


@mcp.resource("positions://intraday_pnl")
async def get_intraday_pnl_resource() -> dict:
    """Track today's intraday P&L with default parameters."""
    return await intraday_pnl.get_intraday_pnl()


@mcp.resource("data://quality")
async def get_data_quality_resource() -> dict:
    """Monitor data feed quality with default parameters."""
    return await data_quality.get_data_quality()


@mcp.resource("server://health")
async def get_server_health_resource() -> dict:
    """Comprehensive server health monitoring."""
    return await server_health.get_server_health()


@mcp.resource("server://session")
async def get_session_status_resource() -> dict:
    """Trading session and market status."""
    return await session_status.get_session_status()


@mcp.resource("server://apis")
async def get_api_status_resource() -> dict:
    """Monitor API connections and performance."""
    return await api_monitor.get_api_status()


# ============================================================================
# HELP SYSTEM RESOURCES - Tool Documentation and Introspection
# ============================================================================


@mcp.resource("help://tools")
async def get_all_tools_help_resource() -> str:
    """Comprehensive help for all available tools organized by category."""
    return await help_system.get_all_tools_help_resource()


@mcp.resource("help://tools/{tool_name}")
async def get_tool_help_resource(tool_name: str) -> str:
    """Detailed help for a specific tool including parameters and examples."""
    return await help_system.get_tool_help_resource(tool_name)


@mcp.resource("help://prompts")
async def get_all_prompts_help_resource() -> str:
    """Comprehensive help for all available workflows/prompts."""
    return await help_system.get_all_prompts_help_resource()


@mcp.resource("help://prompts/{prompt_name}")
async def get_prompt_help_resource(prompt_name: str) -> str:
    """Detailed help for a specific workflow/prompt including parameters and examples."""
    return await help_system.get_prompt_help_resource(prompt_name)


@mcp.resource("help://search/{query}")
async def search_tools_resource(query: str) -> str:
    """Search tools by name, description, or category."""
    return await help_system.search_tools_resource(query)


# ============================================================================
# RESOURCE MIRROR TOOLS - For Claude Code Compatibility
# ============================================================================


@mcp.tool()
async def resource_account_status() -> dict:
    """Tool mirror of account://status resource."""
    return await account_resources.get_account_status()


@mcp.tool()
async def resource_current_positions() -> dict:
    """Tool mirror of positions://current resource."""
    return await position_resources.get_current_positions()


@mcp.tool()
async def resource_market_conditions() -> dict:
    """Tool mirror of market://conditions resource."""
    return await market_resources.get_market_conditions()


@mcp.tool()
async def resource_market_momentum(
    symbol: str = "SPY",
    timeframe_minutes: int = 1,
    analysis_hours: int = 2,
    sma_short: int = 5,
    sma_long: int = 20,
) -> dict:
    """Tool mirror of market://momentum resource."""
    return await market_momentum.get_market_momentum(
        symbol=symbol,
        timeframe_minutes=timeframe_minutes,
        analysis_hours=analysis_hours,
        sma_short=sma_short,
        sma_long=sma_long,
    )


@mcp.tool()
async def resource_intraday_pnl(
    days_back: int = 0,
    include_open_positions: bool = True,
    min_trade_value: float = 0.0,
    symbol_filter: Optional[str] = None,
) -> dict:
    """Tool mirror of positions://intraday_pnl resource."""
    return await intraday_pnl.get_intraday_pnl(
        days_back=days_back,
        include_open_positions=include_open_positions,
        min_trade_value=min_trade_value,
        symbol_filter=symbol_filter,
    )


@mcp.tool()
async def resource_data_quality(
    test_symbols: Optional[list] = None,
    latency_threshold_ms: float = 500.0,
    quote_age_threshold_seconds: float = 60.0,
    spread_threshold_pct: float = 1.0,
) -> dict:
    """Tool mirror of data://quality resource."""
    return await data_quality.get_data_quality(
        test_symbols=test_symbols,
        latency_threshold_ms=latency_threshold_ms,
        quote_age_threshold_seconds=quote_age_threshold_seconds,
        spread_threshold_pct=spread_threshold_pct,
    )


@mcp.tool()
async def resource_server_health() -> dict:
    """Tool mirror of server://health resource."""
    return await server_health.get_server_health()


@mcp.tool()
async def resource_session_status() -> dict:
    """Tool mirror of server://session resource."""
    return await session_status.get_session_status()


@mcp.tool()
async def resource_api_status() -> dict:
    """Tool mirror of server://apis resource."""
    return await api_monitor.get_api_status()


@mcp.tool()
async def health_check() -> str:
    """Quick server health and status check."""
    try:
        health = await server_health.get_server_health()
        session = await session_status.get_session_status()

        status_emoji = (
            "🟢"
            if health.get("server_status") == "healthy"
            else "🟡"
            if health.get("server_status") == "degraded"
            else "🔴"
        )
        market_emoji = "🔔" if session.get("alpaca_market_open") else "🔕"

        return f"""
{status_emoji} Server Status: {health.get("server_status", "unknown").upper()}
{market_emoji} Market: {session.get("session_description", "unknown")}

Quick Stats:
• Memory: {health.get("process_metrics", {}).get("memory_usage_mb", 0):.1f} MB
• CPU: {health.get("process_metrics", {}).get("cpu_usage_percent", 0):.1f}%
• Uptime: {health.get("uptime_formatted", "unknown")}
• APIs: {health.get("connection_health", {}).get("healthy_connections", 0)}/{health.get("connection_health", {}).get("total_connections", 0)}

Market Session:
• Phase: {session.get("session_phase", "unknown")}
• Extended Hours: {session.get("is_extended_hours", False)}
• Next: {session.get("next_event", "unknown")} in {session.get("time_to_next_formatted", "unknown")}

Capabilities: {health.get("capabilities", {}).get("tools", 0)} tools, {health.get("capabilities", {}).get("resources", 0)} resources
        """

    except Exception as e:
        return f"❌ Health check failed: {str(e)}"


@mcp.tool()
async def get_extended_market_clock() -> str:
    """Enhanced market clock with pre/post market sessions."""
    from .tools.enhanced_market_clock import get_extended_market_clock

    return await get_extended_market_clock()


@mcp.tool()
async def validate_extended_hours_order(
    symbol: str, order_type: str, extended_hours: Optional[bool] = None
) -> dict:
    """Validate if order can be placed in current market session."""
    from .tools.extended_hours_orders import validate_extended_hours_order

    return await validate_extended_hours_order(symbol, order_type, extended_hours)


@mcp.tool()
async def place_extended_hours_order(
    symbol: str,
    side: str,
    quantity: float,
    order_type: str = "limit",
    limit_price: Optional[float] = None,
    extended_hours: Optional[bool] = None,
    time_in_force: str = "day",
) -> str:
    """Place order with automatic extended hours detection."""
    from .tools.extended_hours_orders import place_extended_hours_order

    return await place_extended_hours_order(
        symbol, side, quantity, order_type, limit_price, extended_hours, time_in_force
    )


@mcp.tool()
async def get_extended_hours_info() -> str:
    """Get comprehensive information about extended hours trading."""
    from .tools.extended_hours_orders import get_extended_hours_info

    return await get_extended_hours_info()


@mcp.tool()
async def generate_advanced_technical_plots(
    symbols: str,
    timeframe: str = "1Min",
    days: int = 1,
    window_len: int = 21,
    lookahead: int = 1,
    plot_mode: str = "single",
    display_plots: bool = False,
    dpi: int = 100,
) -> str:
    """
    Generate professional peak/trough analysis plots with zero-phase filtering.

    Creates publication-quality technical analysis plots showing:
    - Original and filtered price data using Hanning window
    - Peak/trough detection with actual price annotations
    - Multiple plotting modes: single, combined, overlay
    - Professional styling with auto-positioned legends
    - Signal summary tables with latest trading levels
    - Precise support/resistance levels for trading

    Perfect for visual technical analysis and identifying entry/exit levels.
    Integrates seamlessly with other workflow tools for complete analysis.

    Args:
        symbols: Comma-separated symbols (e.g., "AAPL,MSFT,TSLA")
        timeframe: Bar timeframe ("1Min", "5Min", "15Min", "30Min", "1Hour", "1Day")
        days: Number of trading days to analyze (1-30)
        window_len: Hanning filter window length (3-101, must be odd)
        lookahead: Peak detection sensitivity (1-50, higher=more sensitive)
        plot_mode: "single", "combined", "overlay", or "all"

    Returns:
        Comprehensive analysis with plot locations and trading signals
    """
    from .tools.advanced_plotting_tool import generate_peak_trough_plots

    return await generate_peak_trough_plots(
        symbols,
        timeframe,
        days,
        window_len,
        lookahead,
        plot_mode,
        True,  # save_plots
        display_plots,  # display_plots
        dpi,
    )


@mcp.tool()
async def generate_stock_plot(
    symbols: str,
    timeframe: str = "1Min",
    days: int = 1,
    window: int = 21,
    lookahead: int = 1,
    feed: str = "sip",
    no_plot: bool = False,
    verbose: bool = False,
) -> str:
    """
    Generate stock analysis plots using the plot.py script with ImageMagick display.

    This tool integrates the standalone plot.py script as an MCP tool, providing
    professional technical analysis plots with automatic ImageMagick display.

    Features:
    - Zero-phase Hanning filtering for noise reduction
    - Peak/trough detection with precise price annotations
    - Real-time market data from Alpaca API
    - Professional styling with NYC/EDT timezone
    - Automatic plot display via ImageMagick
    - Multi-symbol support in single API call

    Args:
        symbols: Comma-separated stock symbols (e.g., "AAPL,MSFT,TSLA")
        timeframe: Bar timeframe - "1Min", "5Min", "15Min", "30Min", "1Hour", "1Day"
        days: Number of trading days to analyze (1-30)
        window: Hanning filter window length (3-101, must be odd)
        lookahead: Peak detection sensitivity (1-50, higher = more sensitive)
        feed: Data feed - "sip", "iex", or "otc"
        no_plot: Skip plotting and only show analysis (useful for batch processing)
        verbose: Enable detailed logging output

    Returns:
        Comprehensive analysis results with plot locations and trading signals
    """
    from .tools.plot_py_tool import generate_stock_plot as plot_py_func
    
    return await plot_py_func(
        symbols, timeframe, days, window, lookahead, feed, no_plot, verbose
    )


# ============================================================================
# HELP SYSTEM TOOLS - CLI-style Help Interface
# ============================================================================


@mcp.tool()
async def get_tool_help(tool_name: str) -> str:
    """
    Get comprehensive help for a specific tool (like --help in CLI tools).

    Args:
        tool_name: Name of the tool to get help for

    Returns:
        Detailed help including parameters, examples, and related tools

    Examples:
        get_tool_help("get_stock_quote")
        get_tool_help("scan_day_trading_opportunities")
    """
    return help_system.get_help_system().get_tool_help(tool_name)


@mcp.tool()
async def get_all_tools_help() -> str:
    """
    Get help for all available tools organized by category.

    Returns:
        Comprehensive listing of all tools with descriptions
    """
    return help_system.get_help_system().get_all_tools_help()


@mcp.tool()
async def get_prompt_help(prompt_name: str) -> str:
    """
    Get comprehensive help for a specific workflow/prompt.

    Args:
        prompt_name: Name of the prompt/workflow to get help for

    Returns:
        Detailed help including parameters and usage examples

    Examples:
        get_prompt_help("master_scanning_workflow")
        get_prompt_help("account_analysis")
    """
    return help_system.get_help_system().get_prompt_help(prompt_name)


@mcp.tool()
async def get_all_prompts_help() -> str:
    """
    Get help for all available workflows/prompts.

    Returns:
        Comprehensive listing of all workflows with descriptions
    """
    return help_system.get_help_system().get_all_prompts_help()


@mcp.tool()
async def search_tools(query: str) -> str:
    """
    Search tools by name, description, or category.

    Args:
        query: Search term to find matching tools

    Returns:
        List of tools matching the search query

    Examples:
        search_tools("order")
        search_tools("streaming")
        search_tools("scanner")
    """
    return help_system.get_help_system().search_tools(query)


@mcp.tool()
async def get_mcp_tool_schema(tool_name: str) -> dict:
    """
    Get MCP-compliant tool schema for a specific tool.

    Args:
        tool_name: Name of the tool to get schema for

    Returns:
        MCP-compliant tool schema with inputSchema and annotations

    Examples:
        get_mcp_tool_schema("get_stock_quote")
        get_mcp_tool_schema("place_stock_order")
    """
    return help_system.get_help_system().get_mcp_tool_schema(tool_name) or {}


@mcp.tool()
async def export_mcp_tools_list() -> dict:
    """
    Export all tools in MCP tools/list response format.

    Returns:
        Complete MCP tools/list response with all tool schemas

    This provides the exact format that MCP clients expect for tool discovery.
    """
    return help_system.get_help_system().export_mcp_tools_list()


@mcp.tool()
async def debug_mcp_tools() -> str:
    """Debug function to verify MCP tool registration for Claude Code compatibility."""
    import json

    # Get all registered tools from tool manager
    tool_manager = getattr(mcp, "_tool_manager", None)
    tools_dict = getattr(tool_manager, "_tools", {}) if tool_manager else {}

    tools_info = {
        "total_tools": len(tools_dict),
        "tool_names": list(tools_dict.keys())[:10]
        if tools_dict
        else [],  # First 10 for brevity
        "sample_tool_schema": None,
        "claude_code_mode": getattr(mcp, "_claude_code_mode", False),
        "server_name": getattr(mcp, "name", "unknown"),
        "server_version": getattr(mcp, "version", "unknown"),
        "has_tool_manager": tool_manager is not None,
        "tool_manager_type": str(type(tool_manager)) if tool_manager else None,
    }

    # Get a sample tool schema for verification
    if tools_dict:
        sample_name = list(tools_dict.keys())[0]
        sample_tool = tools_dict[sample_name]
        if hasattr(sample_tool, "get_schema"):
            try:
                tools_info["sample_tool_schema"] = sample_tool.get_schema()
            except Exception as e:
                tools_info["sample_tool_schema_error"] = str(e)
        else:
            tools_info["sample_tool_info"] = {
                "name": sample_name,
                "type": str(type(sample_tool)),
                "has_schema": hasattr(sample_tool, "get_schema"),
                "callable": callable(sample_tool),
            }

    return json.dumps(tools_info, indent=2)


@mcp.tool()
async def cc_debug_tools() -> str:
    """Claude Code debug: List all registered tools"""
    import json

    tool_manager = getattr(mcp, "_tool_manager", None)
    tools_dict = getattr(tool_manager, "_tools", {}) if tool_manager else {}

    tools_info = {
        "server_name": getattr(mcp, "name", "alpaca-trading"),
        "total_tools": len(tools_dict),
        "tool_names": list(tools_dict.keys()),
        "server_connected": True,
        "claude_code_compatible": True,
        "fastmcp_version": getattr(mcp, "version", "unknown"),
    }

    return json.dumps(tools_info, indent=2)


@mcp.tool()
async def cc_force_refresh() -> str:
    """Claude Code: Force tool list refresh"""
    return "Tool list refresh requested - restart Claude Code to see updated tools"


@mcp.tool()
async def cc_test_simple() -> str:
    """Simple test tool for Claude Code"""
    return "✅ Claude Code can execute MCP tools successfully!"


# ============================================================================
# CLEANUP AND MAINTENANCE TOOLS
# ============================================================================


@mcp.tool()
async def cleanup(
    remove_logs: bool = True,
    remove_caches: bool = True,
    remove_backups: bool = True,
    dry_run: bool = False
) -> str:
    """
    Clean up unnecessary temporary files from the MCP server.
    
    This tool removes files that are NOT necessary for MCP server operations:
    - Log files (*.log)
    - Cache directories (.mypy_cache, .pytest_cache, __pycache__)
    - Backup files (*.backup, *.bak, *~)
    - PID files (*.pid)
    - Temporary files (*.tmp, *.temp)
    
    PRESERVES essential files:
    - State files in monitoring_data/
    - Alert history in monitoring_data/alerts/
    - Configuration files
    - All source code and tools
    
    Args:
        remove_logs: Remove all log files (default: True)
        remove_caches: Remove cache directories (default: True)
        remove_backups: Remove backup files (default: True)
        dry_run: Only show what would be deleted without actually deleting (default: False)
    
    Returns:
        Detailed report of cleanup operations
    """
    return await cleanup_server(remove_logs, remove_caches, remove_backups, dry_run)


@mcp.tool()
async def list_cleanup_candidates() -> str:
    """
    List all files that would be cleaned up without deleting them.
    
    This is a safe way to see what the cleanup tool would remove.
    Equivalent to running cleanup(dry_run=True).
    
    Returns:
        Report of files that can be cleaned up
    """
    return await list_cleanup_candidates()


# ============================================================================
# PROMPT REGISTRATIONS
# ============================================================================


@mcp.prompt()
async def startup() -> str:
    """Execute comprehensive day trading startup checks with parallel execution and high-liquidity scanner."""
    return await startup_prompt.startup()


@mcp.prompt()
async def scan() -> str:
    """Scan for day trading opportunities using high-liquidity scanner and technical analysis.

    Uses default parameters: 500 trades/minute threshold, 20 result limit, combined.lis file.
    For custom parameters, use the scan_day_trading_opportunities tool directly.
    """
    return await scan_prompt.scan(500, 20, "combined.lis")


# Stream-Centric Trading Prompts (New Concurrent Architecture)
@mcp.prompt()
async def stream_centric_trading_cycle(symbols: str = "AUTO") -> str:
    """Universal trading cycle with single-stream concurrent architecture.
    
    Args:
        symbols: Comma-separated symbols (e.g., "AAPL,MSFT") or "AUTO" for scanner results
    """
    if __name__ == "__main__" or not __package__:
        from alpaca_mcp_server.prompts.stream_centric_trading_prompt import (
            stream_centric_trading_cycle as sctc_func,
        )
    else:
        from .prompts.stream_centric_trading_prompt import (
            stream_centric_trading_cycle as sctc_func,
        )
    return await sctc_func(symbols)


@mcp.prompt()
async def stream_concurrent_monitoring_cycle(symbols: str = "AUTO") -> str:
    """Continuous monitoring cycle using stream-centric concurrent architecture.
    
    Args:
        symbols: Comma-separated symbols or "AUTO" for current stream symbols
    """
    if __name__ == "__main__" or not __package__:
        from alpaca_mcp_server.prompts.stream_centric_trading_prompt import (
            stream_concurrent_monitoring_cycle as scmc_func,
        )
    else:
        from .prompts.stream_centric_trading_prompt import (
            stream_concurrent_monitoring_cycle as scmc_func,
        )
    return await scmc_func(symbols)


# ============================================================================
# SERVER INITIALIZATION
# ============================================================================


def get_server():
    """Get the MCP server instance."""
    return mcp


@mcp.prompt()
async def day_trading_workflow(symbol: Optional[str] = None) -> str:
    """Complete day trading analysis and setup workflow for any symbol."""
    from .prompts.day_trading_workflow import day_trading_workflow as dtw_func

    return await dtw_func(symbol)


@mcp.prompt()
async def master_scanning_workflow(scan_type: str = "comprehensive") -> str:
    """Master scanner workflow using all available scanner tools simultaneously."""
    from .prompts.master_scanning_workflow import master_scanning_workflow as msw_func

    return await msw_func(scan_type)


@mcp.prompt()
async def pro_technical_workflow(symbol: str, timeframe: str = "comprehensive") -> str:
    """Professional technical analysis workflow using advanced algorithms and peak/trough detection."""
    from .prompts.pro_technical_workflow import pro_technical_workflow as ptw_func

    return await ptw_func(symbol, timeframe)


@mcp.prompt()
async def market_session_workflow(session_type: str = "full_day") -> str:
    """Complete market session strategy using timing tools and session-specific analysis."""
    if __name__ == "__main__" or not __package__:
        from alpaca_mcp_server.prompts.market_session_workflow import (
            market_session_workflow as msw_func,
        )
    else:
        from .prompts.market_session_workflow import market_session_workflow as msw_func

    return await msw_func(session_type)


# ============================================================================
# HYBRID MONITORING TOOLS - Genuine Automated Monitoring
# ============================================================================


@mcp.tool()
async def start_hybrid_monitoring(
    check_interval: int = 2,
    signal_confidence_threshold: float = 0.75,
    max_concurrent_positions: int = 5,
    watchlist_size_limit: int = 20,
    enable_auto_alerts: bool = True,
    alert_channels: list = None
) -> dict:
    """Start the hybrid trading monitoring service."""
    return await monitoring_tools.start_hybrid_monitoring(
        check_interval,
        signal_confidence_threshold,
        max_concurrent_positions,
        watchlist_size_limit,
        enable_auto_alerts,
        alert_channels
    )


@mcp.tool()
async def stop_hybrid_monitoring() -> dict:
    """Stop the hybrid trading monitoring service."""
    return await monitoring_tools.stop_hybrid_monitoring()


@mcp.tool()
async def get_hybrid_monitoring_status() -> dict:
    """Get current status of the hybrid monitoring service."""
    return await monitoring_tools.get_hybrid_monitoring_status()


@mcp.tool()
async def verify_monitoring_active() -> dict:
    """Verify that monitoring is actually running and provide proof."""
    return await monitoring_tools.verify_monitoring_active()


@mcp.tool()
async def add_symbols_to_watchlist(symbols: list) -> dict:
    """Add symbols to the monitoring watchlist."""
    return await monitoring_tools.add_symbols_to_watchlist(symbols)


@mcp.tool()
async def remove_symbols_from_watchlist(symbols: list) -> dict:
    """Remove symbols from the monitoring watchlist."""
    return await monitoring_tools.remove_symbols_from_watchlist(symbols)


@mcp.tool()
async def get_current_watchlist() -> dict:
    """Get the current monitoring watchlist."""
    return await monitoring_tools.get_current_watchlist()


@mcp.tool()
async def get_current_trading_signals() -> dict:
    """Get current trading signals detected by the monitoring service."""
    return await monitoring_tools.get_current_trading_signals()


@mcp.tool()
async def get_profit_spike_alerts(count: int = 5) -> dict:
    """Get latest profit spike alerts generated by real-time streaming monitoring."""
    return await monitoring_tools.get_profit_spike_alerts(count)


@mcp.tool()
async def check_positions_after_order(order_info: dict = None) -> dict:
    """
    Force immediate position check after order execution.
    This ensures real-time feedback on position changes for continuous monitoring.
    
    Args:
        order_info: Optional dict with order details (symbol, action, etc.)
        
    Returns:
        Position status with current count and symbols
    """
    return await monitoring_tools.check_positions_after_order(order_info)


@mcp.tool()
async def ping_monitoring_service() -> dict:
    """
    Ping the hybrid monitoring service to verify it's alive and responsive.
    Returns comprehensive health metrics including uptime, response time, and monitoring status.
    
    Use this to verify service health and troubleshoot monitoring issues.
    
    Returns:
        Service health status with metrics (alive, responsive, uptime, check_count, etc.)
    """
    return await fastapi_monitoring_tools.ping_fastapi_monitoring_service()


@mcp.tool()
async def get_monitoring_alerts(count: int = 10) -> dict:
    """Get recent monitoring alerts."""
    return await monitoring_tools.get_monitoring_alerts(count)


# FastAPI Monitoring Service Tools
@mcp.tool()
async def start_fastapi_monitoring_service() -> dict:
    """
    Start the FastAPI monitoring service.
    Creates a persistent HTTP-based monitoring service with REST endpoints.
    """
    return await fastapi_monitoring_tools.start_fastapi_monitoring_service()


@mcp.tool()
async def stop_fastapi_monitoring_service() -> dict:
    """
    Stop the FastAPI monitoring service gracefully.
    """
    return await fastapi_monitoring_tools.stop_fastapi_monitoring_service()


@mcp.tool()
async def get_fastapi_monitoring_status() -> dict:
    """
    Get comprehensive status from the FastAPI monitoring service.
    Returns live service health, watchlist, positions, and monitoring metrics.
    """
    return await fastapi_monitoring_tools.get_fastapi_monitoring_status()


@mcp.tool()
async def get_current_watchlist() -> dict:
    """
    Get the current watchlist from the live FastAPI monitoring service.
    This queries the actual running service, not just state files.
    """
    return await fastapi_monitoring_tools.get_current_watchlist()


@mcp.tool()
async def add_symbols_to_fastapi_watchlist(symbols: list) -> dict:
    """
    Add symbols to the FastAPI monitoring service watchlist.
    
    Args:
        symbols: List of stock symbols to add to monitoring
    """
    return await fastapi_monitoring_tools.add_symbols_to_fastapi_watchlist(symbols)


@mcp.tool()
async def remove_symbols_from_fastapi_watchlist(symbols: list) -> dict:
    """
    Remove symbols from the FastAPI monitoring service watchlist.
    
    Args:
        symbols: List of stock symbols to remove from monitoring
    """
    return await fastapi_monitoring_tools.remove_symbols_from_fastapi_watchlist(symbols)


@mcp.tool()
async def get_fastapi_positions() -> dict:
    """
    Get current positions from the FastAPI monitoring service.
    Returns live position data with profit/loss information.
    """
    return await fastapi_monitoring_tools.get_fastapi_positions()


@mcp.tool()
async def check_positions_after_order_fastapi(order_info: dict = None) -> dict:
    """
    Check positions immediately after an order using the FastAPI service.
    
    Args:
        order_info: Optional order information for tracking
    """
    return await fastapi_monitoring_tools.check_positions_after_order_fastapi(order_info)


@mcp.tool()
async def get_fastapi_signals() -> dict:
    """
    Get current trading signals from the FastAPI monitoring service.
    Returns active signals detected by the monitoring system.
    """
    return await fastapi_monitoring_tools.get_fastapi_signals()


# Initialize help system after all tools and prompts are registered
help_system.initialize_help_system(mcp)

# Server is designed to be run through main.py or as a module
# Use: python -m alpaca_mcp_server or python alpaca_mcp_server/main.py

if __name__ == "__main__":
    mcp.run()
