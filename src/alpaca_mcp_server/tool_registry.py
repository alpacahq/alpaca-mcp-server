"""
Tool registry for the Alpaca MCP Server.

Maps OpenAPI operationIds to user-friendly MCP tool names, curated
descriptions, and output risk classifications. These keep the v1 tool
naming convention while using FastMCP's from_openapi() under the hood.

Each key is the operationId from the OpenAPI spec. Values contain:
  - name:        the MCP tool name exposed to clients
  - description: curated description shown to LLMs
  - output_risk: classification of how much untrusted external text the
                 tool output may contain (see OutputRisk)
"""

from dataclasses import dataclass
from typing import Literal

OutputRisk = Literal["api_structured", "external_text"]


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    name: str
    description: str
    output_risk: OutputRisk = "api_structured"


TOOLS: dict[str, ToolDefinition] = {
    # --- Account ---
    "getAccount": ToolDefinition(
        name="get_account_info",
        description=(
            "Retrieves and formats the current account information "
            "including balances and status."
        ),
    ),
    "getAccountConfig": ToolDefinition(
        name="get_account_config",
        description=(
            "Retrieves the current account configuration settings, including "
            "trading restrictions, margin settings, PDT checks, and options trading level."
        ),
    ),
    "patchAccountConfig": ToolDefinition(
        name="update_account_config",
        description=(
            "Updates one or more account configuration settings. Only the fields you "
            "provide will be changed; all others retain their current values."
        ),
    ),
    "getAccountPortfolioHistory": ToolDefinition(
        name="get_portfolio_history",
        description=(
            "Retrieves account portfolio history (equity and P/L) over a requested time window."
        ),
    ),
    "getAccountActivities": ToolDefinition(
        name="get_account_activities",
        description=(
            "Returns a list of account activities such as fills, dividends, and transfers."
        ),
    ),
    "getAccountActivitiesByActivityType": ToolDefinition(
        name="get_account_activities_by_type",
        description=(
            "Returns account activity entries for a specific type of activity."
        ),
    ),

    # --- Trading: Orders ---
    "getAllOrders": ToolDefinition(
        name="get_orders",
        description="Retrieves and formats orders with the specified filters.",
    ),
    "getOrderByOrderID": ToolDefinition(
        name="get_order_by_id",
        description="Retrieves a single order by its ID.",
    ),
    "getOrderByClientOrderId": ToolDefinition(
        name="get_order_by_client_id",
        description=(
            "Retrieves a single order specified by the client order ID. "
            "Note: if the order was replaced, this returns the original order "
            "(status \"replaced\") with a replaced_by field pointing to the new order ID."
        ),
    ),
    "patchOrderByOrderId": ToolDefinition(
        name="replace_order_by_id",
        description=(
            "Replaces an existing open order with updated parameters. "
            "At least one optional field must be provided."
        ),
    ),
    "deleteOrderByOrderID": ToolDefinition(
        name="cancel_order_by_id",
        description="Cancel a specific order by its ID.",
    ),
    "deleteAllOrders": ToolDefinition(
        name="cancel_all_orders",
        description="Cancel all open orders.",
    ),

    # --- Trading: Positions ---
    "getAllOpenPositions": ToolDefinition(
        name="get_all_positions",
        description="Retrieves all current positions in the portfolio as JSON.",
    ),
    "getOpenPosition": ToolDefinition(
        name="get_open_position",
        description="Retrieves and formats details for a specific open position.",
    ),
    "deleteOpenPosition": ToolDefinition(
        name="close_position",
        description=(
            "Closes a specific position for a single symbol by placing a sell order. "
            "If the market is closed, the sell order will remain queued and execute "
            "at the next market open."
        ),
    ),
    "deleteAllOpenPositions": ToolDefinition(
        name="close_all_positions",
        description=(
            "Closes all open positions by placing sell orders for each. "
            "If the market is closed, the sell orders will remain queued and execute "
            "at the next market open."
        ),
    ),
    "optionExercise": ToolDefinition(
        name="exercise_options_position",
        description="Exercises a held option contract, converting it into the underlying asset.",
    ),
    "optionDoNotExercise": ToolDefinition(
        name="do_not_exercise_options_position",
        description="Submits a do-not-exercise instruction for a held option contract.",
    ),

    # --- Watchlists ---
    "getWatchlists": ToolDefinition(
        name="get_watchlists",
        description="Get all watchlists for the account.",
    ),
    "postWatchlist": ToolDefinition(
        name="create_watchlist",
        description="Creates a new watchlist with specified symbols.",
    ),
    "getWatchlistById": ToolDefinition(
        name="get_watchlist_by_id",
        description="Get a specific watchlist by its ID.",
    ),
    "updateWatchlistById": ToolDefinition(
        name="update_watchlist_by_id",
        description=(
            "Update an existing watchlist. IMPORTANT: this replaces the entire watchlist. "
            "You must include the symbols parameter with the full list of desired symbols, "
            "otherwise all assets will be removed."
        ),
    ),
    "deleteWatchlistById": ToolDefinition(
        name="delete_watchlist_by_id",
        description="Delete a specific watchlist by its ID.",
    ),
    "addAssetToWatchlist": ToolDefinition(
        name="add_asset_to_watchlist_by_id",
        description="Add an asset by symbol to a specific watchlist.",
    ),
    "removeAssetFromWatchlist": ToolDefinition(
        name="remove_asset_from_watchlist_by_id",
        description="Remove an asset by symbol from a specific watchlist.",
    ),

    # --- Assets & Market Info ---
    "get-v2-assets": ToolDefinition(
        name="get_all_assets",
        description=(
            "Get all available assets with optional filtering. "
            "WARNING: The unfiltered response is very large (thousands of assets). "
            "Always narrow results with the status, asset_class, or exchange parameters. "
            "To look up a single asset, use get_asset instead."
        ),
    ),
    "get-v2-assets-symbol_or_asset_id": ToolDefinition(
        name="get_asset",
        description="Retrieves and formats detailed information about a specific asset.",
    ),
    "get-options-contracts": ToolDefinition(
        name="get_option_contracts",
        description="Retrieves option contracts for underlying symbol(s).",
    ),
    "get-option-contract-symbol_or_id": ToolDefinition(
        name="get_option_contract",
        description="Retrieves a single option contract by symbol or contract ID.",
    ),
    "LegacyCalendar": ToolDefinition(
        name="get_calendar",
        description=(
            "Retrieves and formats market calendar for specified date range. "
            "WARNING: Always provide start and end dates (YYYY-MM-DD). "
            "Without date bounds the response contains the entire multi-year "
            "calendar and will be extremely large."
        ),
    ),
    "LegacyClock": ToolDefinition(
        name="get_clock",
        description="Retrieves and formats current market status and next open/close times.",
    ),
    "get-v2-corporate_actions-announcements": ToolDefinition(
        name="get_corporate_action_announcements",
        description=(
            "Retrieves corporate action announcements (dividends, mergers, splits, spinoffs). "
            "Use a narrow date range and filter by symbol when possible — "
            "broad queries can return very large responses."
        ),
    ),
    "get-v2-corporate_actions-announcements-id": ToolDefinition(
        name="get_corporate_action_announcement",
        description="Retrieves a single corporate action announcement by ID.",
    ),

    # --- Stock Data ---
    "StockBars": ToolDefinition(
        name="get_stock_bars",
        description=(
            "Retrieves and formats historical price bars for stocks "
            "with configurable timeframe and time range."
        ),
    ),
    "StockQuotes": ToolDefinition(
        name="get_stock_quotes",
        description="Retrieves and formats historical quote data (level 1 bid/ask) for stocks.",
    ),
    "StockTrades": ToolDefinition(
        name="get_stock_trades",
        description="Retrieves and formats historical trades for stocks.",
    ),
    "StockLatestBars": ToolDefinition(
        name="get_stock_latest_bar",
        description="Get the latest minute bar for one or more stocks.",
    ),
    "StockLatestQuotes": ToolDefinition(
        name="get_stock_latest_quote",
        description="Retrieves and formats the latest quote for one or more stocks.",
    ),
    "StockLatestTrades": ToolDefinition(
        name="get_stock_latest_trade",
        description="Get the latest trade for one or more stocks.",
    ),
    "StockSnapshots": ToolDefinition(
        name="get_stock_snapshot",
        description=(
            "Retrieves comprehensive snapshots of stock symbols including latest trade, "
            "quote, minute bar, daily bar, and previous daily bar."
        ),
    ),
    "MostActives": ToolDefinition(
        name="get_most_active_stocks",
        description="Screens the market for most active stocks by volume or trade count.",
    ),
    "Movers": ToolDefinition(
        name="get_market_movers",
        description="Returns the top market movers (gainers and losers) based on real-time SIP data.",
    ),

    # --- Crypto Data ---
    "CryptoBars": ToolDefinition(
        name="get_crypto_bars",
        description=(
            "Retrieves and formats historical price bars for cryptocurrencies "
            "with configurable timeframe and time range."
        ),
    ),
    "CryptoQuotes": ToolDefinition(
        name="get_crypto_quotes",
        description="Returns historical quote data for one or more crypto symbols.",
    ),
    "CryptoTrades": ToolDefinition(
        name="get_crypto_trades",
        description="Returns historical trade data for one or more crypto symbols.",
    ),
    "CryptoLatestBars": ToolDefinition(
        name="get_crypto_latest_bar",
        description=(
            "Returns the latest minute bar for one or more crypto symbols. "
            "The loc parameter is required — always set loc to \"us\"."
        ),
    ),
    "CryptoLatestQuotes": ToolDefinition(
        name="get_crypto_latest_quote",
        description=(
            "Returns the latest quote for one or more crypto symbols. "
            "The loc parameter is required — always set loc to \"us\"."
        ),
    ),
    "CryptoLatestTrades": ToolDefinition(
        name="get_crypto_latest_trade",
        description=(
            "Returns the latest trade for one or more crypto symbols. "
            "The loc parameter is required — always set loc to \"us\"."
        ),
    ),
    "CryptoSnapshots": ToolDefinition(
        name="get_crypto_snapshot",
        description=(
            "Returns a snapshot for one or more crypto symbols including latest trade, "
            "quote, minute bar, daily bar, and previous daily bar. "
            "The loc parameter is required — always set loc to \"us\"."
        ),
    ),
    "CryptoLatestOrderbooks": ToolDefinition(
        name="get_crypto_latest_orderbook",
        description=(
            "Returns the latest orderbook for one or more crypto symbols. "
            "The loc parameter is required — always set loc to \"us\". "
            "Note: the response includes the full order book depth and can be large."
        ),
    ),

    # --- Options Data ---
    "optionBars": ToolDefinition(
        name="get_option_bars",
        description="Retrieves historical bar (OHLCV) data for one or more option contracts.",
    ),
    "OptionTrades": ToolDefinition(
        name="get_option_trades",
        description="Retrieves historical trade data for one or more option contracts.",
    ),
    "OptionLatestTrades": ToolDefinition(
        name="get_option_latest_trade",
        description="Retrieves the latest trade for one or more option contracts.",
    ),
    "OptionLatestQuotes": ToolDefinition(
        name="get_option_latest_quote",
        description=(
            "Retrieves and formats the latest quote for one or more option contracts "
            "including bid/ask prices, sizes, and exchange information."
        ),
    ),
    "OptionSnapshots": ToolDefinition(
        name="get_option_snapshot",
        description=(
            "Retrieves comprehensive snapshots of option contracts including latest trade, "
            "quote, implied volatility, and Greeks."
        ),
    ),
    "OptionChain": ToolDefinition(
        name="get_option_chain",
        description=(
            "Retrieves option chain data for an underlying symbol, including latest trade, "
            "quote, implied volatility, and greeks for each contract. "
            "The response can be very large. Use the type (call/put), "
            "strike_price_gte/lte, expiration_date, and limit parameters "
            "to narrow results."
        ),
    ),
    "OptionMetaExchanges": ToolDefinition(
        name="get_option_exchange_codes",
        description=(
            "Retrieves the mapping of exchange codes to exchange names for option market data. "
            "Useful for interpreting exchange fields returned by other option data tools."
        ),
    ),

    # --- Corporate Actions (Market Data) ---
    "CorporateActions": ToolDefinition(
        name="get_corporate_actions",
        description="Retrieves and formats corporate action announcements.",
    ),

    # --- News ---
    "News": ToolDefinition(
        name="get_news",
        description=(
            "Retrieves news articles for stocks and crypto. "
            "Filter by symbols, date range, and sort order. "
            "Returns headlines, summaries, URLs, and associated ticker symbols."
        ),
        output_risk="external_text",
    ),

    # --- Fixed Income Data ---
    "FixedIncomeLatestQuotes": ToolDefinition(
        name="get_fixed_income_latest_quotes",
        description=(
            "Returns the latest quotes for fixed income securities (bonds, treasuries). "
            "Provide a comma-separated list of ISINs (e.g. 'US912797SX61,US912810SK51'). "
            "Returns bid/ask prices, sizes, and yield-to-maturity for each security."
        ),
    ),

    # --- Index Data ---
    "IndexLatestValues": ToolDefinition(
        name="get_index_latest_values",
        description=(
            "Returns the latest values for market indices "
            "(e.g. SPX, VIX, DJI). Provide a comma-separated list of index symbols."
        ),
    ),
    "IndexValues": ToolDefinition(
        name="get_index_values",
        description=(
            "Returns historical values for market indices over a time interval. "
            "Supports pagination, sorting, and date range filtering. "
            "Provide a comma-separated list of index symbols."
        ),
    ),

}

# Derived lookups used by server.py and security.py
TOOL_NAMES: dict[str, str] = {op_id: t.name for op_id, t in TOOLS.items()}
TOOL_DESCRIPTIONS: dict[str, str] = {op_id: t.description for op_id, t in TOOLS.items()}
TOOL_OUTPUT_RISK_BY_NAME: dict[str, OutputRisk] = {
    t.name: t.output_risk for t in TOOLS.values()
}
