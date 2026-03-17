## Summary

Complete rewrite of the Alpaca MCP server using FastMCP's `from_openapi()` to auto-generate tools from bundled OpenAPI specs, replacing the hand-written tool functions from v1.

- **58 auto-generated tools** from `trading-api.json` and `market-data-api.json` specs via `FastMCP.from_openapi()`, with curated names and descriptions for v1 parity
- **3 hand-crafted order overrides** (`place_stock_order`, `place_crypto_order`, `place_option_order`) for the complex `POST /v2/orders` endpoint with bracket order auto-inference, `position_intent` for options, and ReadTimeout handling with idempotency guidance
- **6 hand-crafted market data overrides** (`get_stock_bars/quotes/trades`, `get_crypto_bars/quotes/trades`) adding relative-time convenience params (`days`, `hours`, `minutes`) so LLMs don't need to compute ISO timestamps, plus timeframe normalization and `asof` support
- **Architecture**: `toolsets.py` (domain-based operation allowlists), `names.py` (curated tool names/descriptions), `overrides.py` + `market_data_overrides.py` (hand-crafted tools), `server.py` (server builder), `cli.py` (flat CLI with credential validation)
- **Removed** `config.py`, `helpers.py`, `alpaca-py` SDK dependency; **Added** `fastmcp>=2.0.0`, `httpx>=0.27.0`
- **`ALPACA_TOOLSETS`** env var for filtering tools by domain (account, trading, stock-data, crypto-data, etc.)
- **`scripts/sync-specs.sh`** + `AGENTS.md` for keeping OpenAPI specs up to date
- **`tests/test_integrity.py`** for data integrity checks across toolsets, names, overrides, and specs

## Commits

1. **v2.0.0: Rewrite server with FastMCP from_openapi()** — Core architecture with 61 tools (58 auto + 3 order overrides)
2. **Restore package metadata in __init__.py** — Bring back docstring/author/license
3. **Clean up cli.py** — Remove implicit `.env` loading and HOST/PORT envvar collisions
4. **Flatten CLI to single command** — Drop `serve` subcommand for MCP ecosystem consistency
5. **Add hand-crafted overrides for 6 historical market data tools** — Relative time params, timeframe normalization, robust error handling

## Verification Steps

1. Install: `uv sync`
2. Run integrity tests: `uv run pytest tests/ -v`
3. Run server: `uv run alpaca-mcp-server --api-key <key> --secret-key <secret>`
4. Verify tools list with an MCP client (should see 64 tools total)
