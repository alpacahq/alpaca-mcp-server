"""
Tool name and description overrides for the Alpaca MCP Server.

Maps OpenAPI operationIds to user-friendly MCP tool names and curated
descriptions ported from the v1 server. These keep the v1 tool naming
convention while using FastMCP's from_openapi() under the hood.

Each key is the operationId from the OpenAPI spec. Values contain:
  - name:        the MCP tool name exposed to clients
  - description: curated description shown to LLMs
"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ToolOverride:
    name: str
    description: str


TOOLS: dict[str, ToolOverride] = {
    # --- Account ---
    "getAccount": ToolOverride(
        name="get_account_info",
        description=(
            "Retrieves and formats the current account information "
            "including balances and status."
        ),
    ),
    "getAccountConfig": ToolOverride(
        name="get_account_config",
        description=(
            "Retrieves the current account configuration settings, including "
            "trading restrictions, margin settings, PDT checks, and options trading level."
        ),
    ),
    "patchAccountConfig": ToolOverride(
        name="update_account_config",
        description=(
            "Updates one or more account configuration settings. Only the fields you "
            "provide will be changed; all others retain their current values."
        ),
    ),
    "getAccountPortfolioHistory": ToolOverride(
        name="get_portfolio_history",
        description=(
            "Retrieves account portfolio history (equity and P/L) over a requested time window."
        ),
    ),
    "getAccountActivities": ToolOverride(
        name="get_account_activities",
        description=(
            "Returns a list of account activities such as fills, dividends, and transfers."
        ),
    ),
    "getAccountActivitiesByActivityType": ToolOverride(
        name="get_account_activities_by_type",
        description=(
            "Returns account activity entries for a specific type of activity."
        ),
    ),

    # --- Trading: Orders ---
    "getAllOrders": ToolOverride(
        name="get_orders",
        description="Retrieves and formats orders with the specified filters.",
    ),
    "getOrderByOrderID": ToolOverride(
        name="get_order_by_id",
        description="Retrieves a single order by its ID.",
    ),
    "getOrderByClientOrderId": ToolOverride(
        name="get_order_by_client_id",
        description=(
            "Retrieves a single order specified by the client order ID. "
            "Note: if the order was replaced, this returns the original order "
            "(status \"replaced\") with a replaced_by field pointing to the new order ID."
        ),
    ),
    "patchOrderByOrderId": ToolOverride(
        name="replace_order_by_id",
        description=(
            "Replaces an existing open order with updated parameters. "
            "At least one optional field must be provided."
        ),
    ),
    "deleteOrderByOrderID": ToolOverride(
        name="cancel_order_by_id",
        description="Cancel a specific order by its ID.",
    ),
    "deleteAllOrders": ToolOverride(
        name="cancel_all_orders",
        description="Cancel all open orders.",
    ),

    # --- Trading: Positions ---
    "getAllOpenPositions": ToolOverride(
        name="get_all_positions",
        description="Retrieves all current positions in the portfolio as JSON.",
    ),
    "getOpenPosition": ToolOverride(
        name="get_open_position",
        description="Retrieves and formats details for a specific open position.",
    ),
    "deleteOpenPosition": ToolOverride(
        name="close_position",
        description=(
            "Closes a specific position for a single symbol by placing a sell order. "
            "If the market is closed, the sell order will remain queued and execute "
            "at the next market open."
        ),
    ),
    "deleteAllOpenPositions": ToolOverride(
        name="close_all_positions",
        description=(
            "Closes all open positions by placing sell orders for each. "
            "If the market is closed, the sell orders will remain queued and execute "
            "at the next market open."
        ),
    ),
    "optionExercise": ToolOverride(
        name="exercise_options_position",
        description="Exercises a held option contract, converting it into the underlying asset.",
    ),
    "optionDoNotExercise": ToolOverride(
        name="do_not_exercise_options_position",
        description="Submits a do-not-exercise instruction for a held option contract.",
    ),

    # --- Watchlists ---
    "getWatchlists": ToolOverride(
        name="get_watchlists",
        description="Get all watchlists for the account.",
    ),
    "postWatchlist": ToolOverride(
        name="create_watchlist",
        description="Creates a new watchlist with specified symbols.",
    ),
    "getWatchlistById": ToolOverride(
        name="get_watchlist_by_id",
        description="Get a specific watchlist by its ID.",
    ),
    "updateWatchlistById": ToolOverride(
        name="update_watchlist_by_id",
        description=(
            "Update an existing watchlist. IMPORTANT: this replaces the entire watchlist. "
            "You must include the symbols parameter with the full list of desired symbols, "
            "otherwise all assets will be removed."
        ),
    ),
    "deleteWatchlistById": ToolOverride(
        name="delete_watchlist_by_id",
        description="Delete a specific watchlist by its ID.",
    ),
    "addAssetToWatchlist": ToolOverride(
        name="add_asset_to_watchlist_by_id",
        description="Add an asset by symbol to a specific watchlist.",
    ),
    "removeAssetFromWatchlist": ToolOverride(
        name="remove_asset_from_watchlist_by_id",
        description="Remove an asset by symbol from a specific watchlist.",
    ),

    # --- Assets & Market Info ---
    "get-v2-assets": ToolOverride(
        name="get_all_assets",
        description=(
            "Get all available assets with optional filtering. "
            "WARNING: The unfiltered response is very large (thousands of assets). "
            "Always narrow results with the status, asset_class, or exchange parameters. "
            "To look up a single asset, use get_asset instead."
        ),
    ),
    "get-v2-assets-symbol_or_asset_id": ToolOverride(
        name="get_asset",
        description="Retrieves and formats detailed information about a specific asset.",
    ),
    "get-options-contracts": ToolOverride(
        name="get_option_contracts",
        description="Retrieves option contracts for underlying symbol(s).",
    ),
    "get-option-contract-symbol_or_id": ToolOverride(
        name="get_option_contract",
        description="Retrieves a single option contract by symbol or contract ID.",
    ),
    "LegacyCalendar": ToolOverride(
        name="get_calendar",
        description=(
            "Retrieves and formats market calendar for specified date range. "
            "WARNING: Always provide start and end dates (YYYY-MM-DD). "
            "Without date bounds the response contains the entire multi-year "
            "calendar and will be extremely large."
        ),
    ),
    "LegacyClock": ToolOverride(
        name="get_clock",
        description="Retrieves and formats current market status and next open/close times.",
    ),
    "get-v2-corporate_actions-announcements": ToolOverride(
        name="get_corporate_action_announcements",
        description=(
            "Retrieves corporate action announcements (dividends, mergers, splits, spinoffs). "
            "Use a narrow date range and filter by symbol when possible — "
            "broad queries can return very large responses."
        ),
    ),
    "get-v2-corporate_actions-announcements-id": ToolOverride(
        name="get_corporate_action_announcement",
        description="Retrieves a single corporate action announcement by ID.",
    ),

    # --- Stock Data ---
    "StockBars": ToolOverride(
        name="get_stock_bars",
        description=(
            "Retrieves and formats historical price bars for stocks "
            "with configurable timeframe and time range."
        ),
    ),
    "StockQuotes": ToolOverride(
        name="get_stock_quotes",
        description="Retrieves and formats historical quote data (level 1 bid/ask) for stocks.",
    ),
    "StockTrades": ToolOverride(
        name="get_stock_trades",
        description="Retrieves and formats historical trades for stocks.",
    ),
    "StockLatestBars": ToolOverride(
        name="get_stock_latest_bar",
        description="Get the latest minute bar for one or more stocks.",
    ),
    "StockLatestQuotes": ToolOverride(
        name="get_stock_latest_quote",
        description="Retrieves and formats the latest quote for one or more stocks.",
    ),
    "StockLatestTrades": ToolOverride(
        name="get_stock_latest_trade",
        description="Get the latest trade for one or more stocks.",
    ),
    "StockSnapshots": ToolOverride(
        name="get_stock_snapshot",
        description=(
            "Retrieves comprehensive snapshots of stock symbols including latest trade, "
            "quote, minute bar, daily bar, and previous daily bar."
        ),
    ),
    "MostActives": ToolOverride(
        name="get_most_active_stocks",
        description="Screens the market for most active stocks by volume or trade count.",
    ),
    "Movers": ToolOverride(
        name="get_market_movers",
        description="Returns the top market movers (gainers and losers) based on real-time SIP data.",
    ),

    # --- Crypto Data ---
    "CryptoBars": ToolOverride(
        name="get_crypto_bars",
        description=(
            "Retrieves and formats historical price bars for cryptocurrencies "
            "with configurable timeframe and time range."
        ),
    ),
    "CryptoQuotes": ToolOverride(
        name="get_crypto_quotes",
        description="Returns historical quote data for one or more crypto symbols.",
    ),
    "CryptoTrades": ToolOverride(
        name="get_crypto_trades",
        description="Returns historical trade data for one or more crypto symbols.",
    ),
    "CryptoLatestBars": ToolOverride(
        name="get_crypto_latest_bar",
        description=(
            "Returns the latest minute bar for one or more crypto symbols. "
            "The loc parameter is required — always set loc to \"us\"."
        ),
    ),
    "CryptoLatestQuotes": ToolOverride(
        name="get_crypto_latest_quote",
        description=(
            "Returns the latest quote for one or more crypto symbols. "
            "The loc parameter is required — always set loc to \"us\"."
        ),
    ),
    "CryptoLatestTrades": ToolOverride(
        name="get_crypto_latest_trade",
        description=(
            "Returns the latest trade for one or more crypto symbols. "
            "The loc parameter is required — always set loc to \"us\"."
        ),
    ),
    "CryptoSnapshots": ToolOverride(
        name="get_crypto_snapshot",
        description=(
            "Returns a snapshot for one or more crypto symbols including latest trade, "
            "quote, minute bar, daily bar, and previous daily bar. "
            "The loc parameter is required — always set loc to \"us\"."
        ),
    ),
    "CryptoLatestOrderbooks": ToolOverride(
        name="get_crypto_latest_orderbook",
        description=(
            "Returns the latest orderbook for one or more crypto symbols. "
            "The loc parameter is required — always set loc to \"us\". "
            "Note: the response includes the full order book depth and can be large."
        ),
    ),

    # --- Options Data ---
    "optionBars": ToolOverride(
        name="get_option_bars",
        description="Retrieves historical bar (OHLCV) data for one or more option contracts.",
    ),
    "OptionTrades": ToolOverride(
        name="get_option_trades",
        description="Retrieves historical trade data for one or more option contracts.",
    ),
    "OptionLatestTrades": ToolOverride(
        name="get_option_latest_trade",
        description="Retrieves the latest trade for one or more option contracts.",
    ),
    "OptionLatestQuotes": ToolOverride(
        name="get_option_latest_quote",
        description=(
            "Retrieves and formats the latest quote for one or more option contracts "
            "including bid/ask prices, sizes, and exchange information."
        ),
    ),
    "OptionSnapshots": ToolOverride(
        name="get_option_snapshot",
        description=(
            "Retrieves comprehensive snapshots of option contracts including latest trade, "
            "quote, implied volatility, and Greeks."
        ),
    ),
    "OptionChain": ToolOverride(
        name="get_option_chain",
        description=(
            "Retrieves option chain data for an underlying symbol, including latest trade, "
            "quote, implied volatility, and greeks for each contract. "
            "The response can be very large. Use the type (call/put), "
            "strike_price_gte/lte, expiration_date, and limit parameters "
            "to narrow results."
        ),
    ),
    "OptionMetaExchanges": ToolOverride(
        name="get_option_exchange_codes",
        description=(
            "Retrieves the mapping of exchange codes to exchange names for option market data. "
            "Useful for interpreting exchange fields returned by other option data tools."
        ),
    ),

    # --- Corporate Actions (Market Data) ---
    "CorporateActions": ToolOverride(
        name="get_corporate_actions",
        description="Retrieves and formats corporate action announcements.",
    ),

    # --- News ---
    "News": ToolOverride(
        name="get_news",
        description=(
            "Retrieves news articles for stocks and crypto. "
            "Filter by symbols, date range, and sort order. "
            "Returns headlines, summaries, URLs, and associated ticker symbols."
        ),
    ),
}

# Derived lookups used by server.py
TOOL_NAMES: dict[str, str] = {op_id: t.name for op_id, t in TOOLS.items()}
TOOL_DESCRIPTIONS: dict[str, str] = {op_id: t.description for op_id, t in TOOLS.items()}
