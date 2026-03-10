"""
Toolset definitions for the Alpaca MCP Server.

Each toolset maps to a set of operationIds from the OpenAPI specs. Only endpoints
listed here are exposed as MCP tools. New endpoints are excluded by default —
add their operationId to the appropriate toolset to include them.
"""

TOOLSETS: dict[str, dict] = {
    "account": {
        "spec": "trading",
        "operations": {
            "getAccount",
            "getAccountConfig",
            "patchAccountConfig",
            "getAccountPortfolioHistory",
            "getAccountActivities",
            "getAccountActivitiesByActivityType",
        },
    },
    "trading": {
        "spec": "trading",
        "operations": {
            "getAllOrders",
            "getOrderByOrderID",
            "getOrderByClientOrderId",
            "patchOrderByOrderId",
            "deleteOrderByOrderID",
            "deleteAllOrders",
            # postOrder is excluded — replaced by overrides
            # (place_stock_order, place_crypto_order, place_option_order)
            "getAllOpenPositions",
            "getOpenPosition",
            "deleteOpenPosition",
            "deleteAllOpenPositions",
            "optionExercise",
            "optionDoNotExercise",
        },
    },
    "watchlists": {
        "spec": "trading",
        "operations": {
            "getWatchlists",
            "postWatchlist",
            "getWatchlistById",
            "updateWatchlistById",
            "deleteWatchlistById",
            "addAssetToWatchlist",
            "removeAssetFromWatchlist",
        },
    },
    "assets": {
        "spec": "trading",
        "operations": {
            "get-v2-assets",
            "get-v2-assets-symbol_or_asset_id",
            "get-options-contracts",
            "get-option-contract-symbol_or_id",
            "LegacyCalendar",
            "LegacyClock",
            "get-v2-corporate_actions-announcements",
            "get-v2-corporate_actions-announcements-id",
        },
    },
    "stock-data": {
        "spec": "market-data",
        "operations": {
            "StockBars",
            "StockQuotes",
            "StockTrades",
            "StockLatestBars",
            "StockLatestQuotes",
            "StockLatestTrades",
            "StockSnapshots",
            "MostActives",
            "Movers",
        },
    },
    "crypto-data": {
        "spec": "market-data",
        "operations": {
            "CryptoBars",
            "CryptoQuotes",
            "CryptoTrades",
            "CryptoLatestBars",
            "CryptoLatestQuotes",
            "CryptoLatestTrades",
            "CryptoSnapshots",
            "CryptoLatestOrderbooks",
        },
    },
    "options-data": {
        "spec": "market-data",
        "operations": {
            "optionBars",
            "OptionTrades",
            "OptionLatestTrades",
            "OptionLatestQuotes",
            "OptionSnapshots",
            "OptionChain",
            "OptionMetaExchanges",
        },
    },
    "corporate-actions": {
        "spec": "market-data",
        "operations": {
            "CorporateActions",
        },
    },
}

OVERRIDE_OPERATION_IDS = {
    "postOrder",
}


def get_active_operations(active_toolsets: set[str] | None = None) -> dict[str, set[str]]:
    """Return allowed operationIds grouped by spec name.

    Args:
        active_toolsets: Set of toolset names to enable. None means all.

    Returns:
        Dict mapping spec name ("trading" / "market-data") to sets of operationIds.
    """
    spec_ops: dict[str, set[str]] = {}
    for ts_name, ts_config in TOOLSETS.items():
        if active_toolsets is not None and ts_name not in active_toolsets:
            continue
        spec = ts_config["spec"]
        spec_ops.setdefault(spec, set()).update(ts_config["operations"])
    return spec_ops
