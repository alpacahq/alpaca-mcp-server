<p align="center">
  <img src="https://raw.githubusercontent.com/alpacahq/alpaca-mcp-server/main/assets/01-primary-alpaca-logo.png" alt="Alpaca logo" width="220">
</p>

<div align="center">

<a href="https://x.com/alpacahq?lang=en" target="_blank"><img src="https://img.shields.io/badge/X-DCDCDC?logo=x&logoColor=000" alt="X"></a>
<a href="https://www.reddit.com/r/alpacamarkets/" target="_blank"><img src="https://img.shields.io/badge/Reddit-DCDCDC?logo=reddit&logoColor=000" alt="Reddit"></a>
<a href="https://alpaca.markets/slack" target="_blank"><img src="https://img.shields.io/badge/Slack-DCDCDC?logo=slack&logoColor=000" alt="Slack"></a>
<a href="https://www.linkedin.com/company/alpacamarkets/" target="_blank"><img src="https://img.shields.io/badge/LinkedIn-DCDCDC" alt="LinkedIn"></a>
<a href="https://forum.alpaca.markets/" target="_blank"><img src="https://img.shields.io/badge/Forum-DCDCDC?logo=discourse&logoColor=000" alt="Forum"></a>
<a href="https://docs.alpaca.markets/docs/getting-started" target="_blank"><img src="https://img.shields.io/badge/Docs-DCDCDC" alt="Docs"></a>

</div>

<p align="center">
  A Model Context Protocol (MCP) server for Alpaca's Trading API. Enable natural language trading through AI assistants like Claude, Cursor, and VS Code. Supports stocks, options, crypto, portfolio management, and real-time market data.
</p>

## Table of Contents

- [Prerequisites](#prerequisites)
- [Getting Your API Keys](#getting-your-api-keys)
- [Setup](#setup)
- [Configuration](#configuration)
- [Features](#features)
- [Example Prompts](#example-prompts)
- [Available Tools](#available-tools)
- [Testing](#testing)
- [Project Structure](#project-structure)
- [Troubleshooting](#troubleshooting)
- [Disclosure](#disclosure)

## Prerequisites

- **Python 3.10+** ([installation guide](https://www.python.org/downloads/))
- **uv** ([installation guide](https://docs.astral.sh/uv/getting-started/installation/))
- **Alpaca Trading API keys** (free paper trading account)
- **MCP client** (Claude Desktop, Cursor, VS Code, etc.)

## Getting Your API Keys

1. Visit the [Alpaca Dashboard](https://app.alpaca.markets/paper/dashboard/overview)
2. Create a free paper trading account
3. Generate API keys from the dashboard

## Setup

Add the server to your MCP client config, then restart the client. No `init` command, no `.env` files — credentials are set in **one place only**.

### Claude Desktop

Edit `~/Library/Application Support/Claude/claude_desktop_config.json` (Mac) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "alpaca": {
      "command": "uvx",
      "args": ["alpaca-mcp-server"],
      "env": {
        "ALPACA_API_KEY": "your_alpaca_api_key",
        "ALPACA_SECRET_KEY": "your_alpaca_secret_key"
      }
    }
  }
}
```

### Cursor

Install from the [Cursor Directory](https://cursor.directory/mcp/alpaca) in a few clicks, or add to `~/.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "alpaca": {
      "command": "uvx",
      "args": ["alpaca-mcp-server"],
      "env": {
        "ALPACA_API_KEY": "your_alpaca_api_key",
        "ALPACA_SECRET_KEY": "your_alpaca_secret_key"
      }
    }
  }
}
```

### VS Code

Create `.vscode/mcp.json` in your project root. See the [official docs](https://code.visualstudio.com/docs/copilot/chat/mcp-servers).

```json
{
  "mcp": {
    "servers": {
      "alpaca": {
        "type": "stdio",
        "command": "uvx",
        "args": ["alpaca-mcp-server"],
        "env": {
          "ALPACA_API_KEY": "your_alpaca_api_key",
          "ALPACA_SECRET_KEY": "your_alpaca_secret_key"
        }
      }
    }
  }
}
```

<details>
<summary><b>PyCharm</b></summary><br>

See the [official guide](https://www.jetbrains.com/help/ai-assistant/configure-an-mcp-server.html).

1. Go to File → Settings → Tools → Model Context Protocol (MCP)
2. Add a new server:
   - **Type**: stdio
   - **Command**: uvx
   - **Arguments**: alpaca-mcp-server
3. Set environment variables:
   ```
   ALPACA_API_KEY=your_alpaca_api_key
   ALPACA_SECRET_KEY=your_alpaca_secret_key
   ```

</details>

<details>
<summary><b>Claude Code</b></summary><br>

```bash
claude mcp add alpaca --scope user --transport stdio uvx alpaca-mcp-server \
  --env ALPACA_API_KEY=your_alpaca_api_key \
  --env ALPACA_SECRET_KEY=your_alpaca_secret_key
```

Verify with `/mcp` in the Claude Code CLI.

</details>

<details>
<summary><b>Gemini CLI</b></summary><br>

See the [Gemini CLI MCP docs](https://github.com/google-gemini/gemini-cli/blob/main/docs/tools/mcp-server.md).

Add to your `settings.json`:

```json
{
  "mcpServers": {
    "alpaca": {
      "type": "stdio",
      "command": "uvx",
      "args": ["alpaca-mcp-server"],
      "env": {
        "ALPACA_API_KEY": "your_alpaca_api_key",
        "ALPACA_SECRET_KEY": "your_alpaca_secret_key"
      }
    }
  }
}
```

</details>

<details>
<summary><b>Docker</b></summary><br>

```bash
git clone https://github.com/alpacahq/alpaca-mcp-server.git
cd alpaca-mcp-server
docker build -t mcp/alpaca:latest .
```

Add to your MCP client config:

```json
{
  "mcpServers": {
    "alpaca": {
      "command": "docker",
      "args": [
        "run", "--rm", "-i",
        "-e", "ALPACA_API_KEY=your_key",
        "-e", "ALPACA_SECRET_KEY=your_secret",
        "-e", "ALPACA_PAPER_TRADE=true",
        "mcp/alpaca:latest"
      ]
    }
  }
}
```

</details>

## Configuration

All configuration is through environment variables set in your MCP client config. No files are written to disk.

| Variable | Required | Default | Description |
|---|---|---|---|
| `ALPACA_API_KEY` | Yes | — | Your Alpaca API key |
| `ALPACA_SECRET_KEY` | Yes | — | Your Alpaca secret key |
| `ALPACA_PAPER_TRADE` | No | `true` | Set to `false` for live trading |
| `ALPACA_TOOLSETS` | No | all | Comma-separated list of toolsets to enable |

### Switching to Live Trading

Update the `env` block in your MCP client config and restart:

```json
{
  "env": {
    "ALPACA_API_KEY": "your_live_api_key",
    "ALPACA_SECRET_KEY": "your_live_secret_key",
    "ALPACA_PAPER_TRADE": "false"
  }
}
```

### Toolset Filtering

By default, all tools are enabled. To limit the server to specific toolsets, set `ALPACA_TOOLSETS`:

```json
{
  "env": {
    "ALPACA_API_KEY": "...",
    "ALPACA_SECRET_KEY": "...",
    "ALPACA_TOOLSETS": "stock-data,crypto-data"
  }
}
```

Available toolsets:

| Toolset | Description |
|---|---|
| `account` | Account info, config, portfolio history, activities |
| `trading` | Orders, positions, exercise options |
| `watchlists` | Watchlist CRUD operations |
| `assets` | Asset lookup, option contracts, calendar, clock |
| `stock-data` | Stock bars, quotes, trades, snapshots, screeners |
| `crypto-data` | Crypto bars, quotes, trades, snapshots, orderbooks |
| `options-data` | Option bars, quotes, trades, snapshots, chain, exchange codes |
| `corporate-actions` | Corporate action announcements |

## Features

- **Market Data** — Real-time quotes, trades, and price bars for stocks, crypto, and options. Historical data with flexible timeframes. Option Greeks and implied volatility.
- **Account Management** — View balances, buying power, account status, and portfolio history.
- **Order Management** — Place market, limit, stop, stop-limit, and trailing-stop orders for stocks, crypto, and options. Cancel orders individually or in bulk.
- **Options Trading** — Search contracts by expiration/strike/type. Place single-leg or multi-leg strategies. Get latest quotes, Greeks, and IV.
- **Crypto Trading** — Market, limit, and stop-limit orders with GTC/IOC. Quantity or notional-based.
- **Position Management** — View, close, or liquidate positions. Exercise option contracts.
- **Market Status** — Market open/close times, calendar, corporate actions.
- **Watchlists** — Create, update, and manage watchlists.
- **Asset Search** — Query details for stocks, ETFs, crypto, and options with filtering.

## Example Prompts

<details open>
<summary><b>Basic Trading</b></summary>

1. What's my current account balance and buying power on Alpaca?
2. Show me my current positions in my Alpaca account.
3. Buy 5 shares of AAPL at market price.
4. Sell 5 shares of TSLA with a limit price of $300.
5. Cancel all open stock orders.
6. Cancel the order with ID abc123.
7. Liquidate my entire position in GOOGL.
8. Close 10% of my position in NVDA.
9. Place a limit order to buy 100 shares of MSFT at $450.
10. Place a market order to sell 25 shares of META.

</details>

<details>
<summary><b>Crypto Trading</b></summary>

11. Place a market order to buy 0.01 ETH/USD.
12. Place a limit order to sell 0.01 BTC/USD at $110,000.

</details>

<details>
<summary><b>Option Trading</b></summary>

13. Show me available option contracts for AAPL expiring next month.
14. Get the latest quote for the AAPL250613C00200000 option.
15. Retrieve the option snapshot for the SPY250627P00400000 option.
16. Liquidate my position in 2 contracts of QQQ calls expiring next week.
17. Place a market order to buy 1 call option on AAPL expiring next Friday.
18. What are the option Greeks for the TSLA250620P00500000 option?
19. Find TSLA option contracts with strike prices within 5% of the current market price.
20. Get SPY call options expiring the week of June 16th, 2025, within 10% of market price.
21. Place a bull call spread using AAPL June 6th options: one with a 190.00 strike and the other with a 200.00 strike.
22. Exercise my NVDA call option contract NVDA250919C001680.

</details>

<details>
<summary><b>Market Information</b></summary>

> To access the latest 15-minute data, you need to subscribe to the [Algo Trader Plus Plan](https://alpaca.markets/data).
23. What are the market open and close times today?
24. Show me the market calendar for next week.
25. Show me recent cash dividends and stock splits for AAPL, MSFT, and GOOGL in the last 3 months.
26. Get all corporate actions for SPY including dividends, splits, and any mergers in the past year.
27. What are the upcoming corporate actions scheduled for SPY in the next 6 months?

</details>

<details>
<summary><b>Historical & Real-time Data</b></summary>

28. Show me AAPL's daily price history for the last 5 trading days.
29. What was the closing price of TSLA yesterday?
30. Get the latest bar for GOOGL.
31. What was the latest trade price for NVDA?
32. Show me the most recent quote for MSFT.
33. Retrieve the last 100 trades for AMD.
34. Show me 1-minute bars for AMZN from the last 2 hours.
35. Get 5-minute intraday bars for TSLA from last Tuesday through last Friday.
36. Get a comprehensive stock snapshot for AAPL showing latest quote, trade, minute bar, daily bar, and previous daily bar all in one view.
37. Compare market snapshots for TSLA, NVDA, and MSFT to analyze their current bid/ask spreads, latest trade prices, and daily performance.

</details>

<details>
<summary><b>Orders</b></summary>

38. Show me all my open and filled orders from this week.
39. What orders do I have for AAPL?
40. List all limit orders I placed in the past 3 days.
41. Filter all orders by status: filled.
42. Get me the order history for yesterday.

</details>

<details>
<summary><b>Watchlists</b></summary>

> At this moment, you can only view and update trading watchlists created via Alpaca's Trading API through the API itself
43. Create a new watchlist called "Tech Stocks" with AAPL, MSFT, and NVDA.
44. Update my "Tech Stocks" watchlist to include TSLA and AMZN.
45. What stocks are in my "Dividend Picks" watchlist?
46. Remove META from my "Growth Portfolio" watchlist.
47. List all my existing watchlists.

</details>

<details>
<summary><b>Asset Information</b></summary>

48. Search for details about the asset 'AAPL'.
49. Show me the top 5 tradable crypto assets by trading volume.
50. Get all NASDAQ active US equity assets and filter the results to show only tradable securities

</details>

<details>
<summary><b>Combined Scenarios</b></summary>

51. Get today's market clock and show me my buying power before placing a limit buy order for TSLA at $340.
52. Place a bull call spread with SPY July 3rd options: sell one 5% above and buy one 3% below the current SPY price.

</details>

## Available Tools

<details open>
<summary><b>Account & Portfolio</b></summary>

* `get_account_info` — Balance, margin, and account status
* `get_account_config` — Trading restrictions, margin settings, PDT checks
* `update_account_config` — Update account configuration settings
* `get_portfolio_history` — Equity and P/L over time
* `get_account_activities` — Fills, dividends, transfers
* `get_account_activities_by_type` — Activities filtered by type

</details>

<details>
<summary><b>Trading (Orders)</b></summary>

* `get_orders` — Retrieve orders with filters
* `get_order_by_id` — Single order by ID
* `get_order_by_client_id` — Single order by client order ID
* `replace_order_by_id` — Replace an existing open order
* `cancel_order_by_id` — Cancel a specific order
* `cancel_all_orders` — Cancel all open orders
* `place_stock_order` — Stocks/ETFs (market, limit, stop, stop-limit, trailing-stop, brackets)
* `place_crypto_order` — Crypto (market, limit, stop-limit)
* `place_option_order` — Options (single-leg or multi-leg)

</details>

<details>
<summary><b>Positions</b></summary>

* `get_all_positions` — All current positions
* `get_open_position` — Details for a specific position
* `close_position` — Close a specific position
* `close_all_positions` — Liquidate entire portfolio
* `exercise_options_position` — Exercise a held option contract
* `do_not_exercise_options_position` — Do-not-exercise instruction

</details>

<details>
<summary><b>Watchlists</b></summary>

* `create_watchlist` — Create a new watchlist
* `get_watchlists` — List all watchlists
* `get_watchlist_by_id` — Get a specific watchlist
* `update_watchlist_by_id` — Update a watchlist
* `delete_watchlist_by_id` — Delete a watchlist
* `add_asset_to_watchlist_by_id` — Add an asset to a watchlist
* `remove_asset_from_watchlist_by_id` — Remove an asset from a watchlist

</details>

<details>
<summary><b>Assets & Market Info</b></summary>

* `get_all_assets` — List assets with optional filtering
* `get_asset` — Detailed info for a specific asset
* `get_option_contracts` — Option contracts for underlying symbol(s)
* `get_option_contract` — Single option contract by symbol or ID
* `get_calendar` — Market calendar for a date range
* `get_clock` — Current market status and next open/close
* `get_corporate_action_announcements` — Corporate action announcements
* `get_corporate_action_announcement` — Single announcement by ID

</details>

<details>
<summary><b>Stock Data</b></summary>

* `get_stock_bars` — Historical OHLCV bars
* `get_stock_quotes` — Historical bid/ask quotes
* `get_stock_trades` — Historical trades
* `get_stock_latest_bar` — Latest minute bar
* `get_stock_latest_quote` — Latest quote
* `get_stock_latest_trade` — Latest trade
* `get_stock_snapshot` — Comprehensive snapshot
* `get_most_active_stocks` — Most active by volume/trade count
* `get_market_movers` — Top gainers and losers

</details>

<details>
<summary><b>Crypto Data</b></summary>

* `get_crypto_bars` — Historical OHLCV bars
* `get_crypto_quotes` — Historical quotes
* `get_crypto_trades` — Historical trades
* `get_crypto_latest_bar` — Latest minute bar
* `get_crypto_latest_quote` — Latest quote
* `get_crypto_latest_trade` — Latest trade
* `get_crypto_snapshot` — Comprehensive snapshot
* `get_crypto_latest_orderbook` — Latest orderbook

</details>

<details>
<summary><b>Options Data</b></summary>

* `get_option_bars` — Historical OHLCV bars
* `get_option_trades` — Historical trades
* `get_option_latest_trade` — Latest trade
* `get_option_latest_quote` — Latest quote with bid/ask and exchange info
* `get_option_snapshot` — Snapshot with Greeks and IV
* `get_option_chain` — Full option chain for an underlying
* `get_option_exchange_codes` — Exchange code to name mapping

</details>

<details>
<summary><b>Corporate Actions</b></summary>

* `get_corporate_actions` — Corporate action announcements from market data

</details>

## Testing

The project includes a multi-layered test suite that runs in CI on every pull request:

- **Integrity tests** — Validate consistency between OpenAPI specs, toolset definitions, and tool name/description overrides. No network or credentials required.
- **Server construction tests** — Build the server with mocked credentials and verify the correct number of tools are exposed. No network required.
- **Paper API integration tests** — Execute real calls against the Alpaca paper trading API, covering account info, market data, order lifecycle, watchlists, positions, and more. Requires `ALPACA_API_KEY` and `ALPACA_SECRET_KEY`.

Run the full suite locally:

```bash
# Core tests (no credentials needed)
pytest tests/test_integrity.py tests/test_server_construction.py -v

# Integration tests (requires paper API keys)
ALPACA_API_KEY=... ALPACA_SECRET_KEY=... pytest tests/ -m integration -v
```

## Project Structure

```
alpaca-mcp-server/
├── src/
│   └── alpaca_mcp_server/
│       ├── __init__.py
│       ├── cli.py            ← CLI entry point
│       ├── server.py         ← FastMCP server built from OpenAPI specs
│       ├── names.py          ← Tool name and description overrides
│       ├── toolsets.py       ← Toolset → operationId allowlists
│       ├── overrides.py      ← Hand-crafted tools for complex trading endpoints
│       ├── market_data_overrides.py ← Hand-crafted tools for historical data
│       └── specs/
│           ├── trading-api.json
│           └── market-data-api.json
├── tests/
│   ├── conftest.py           ← Shared fixtures and paper-account cleanup
│   ├── test_integrity.py     ← Spec ↔ toolset ↔ names consistency checks
│   ├── test_server_construction.py ← Server build verification
│   └── test_paper_integration.py   ← Paper API integration tests
├── scripts/
│   └── sync-specs.sh        ← Download latest OpenAPI specs
├── .github/
│   └── workflows/
│       └── ci.yml            ← CI pipeline (core + integration)
├── AGENTS.md                 ← Instructions for coding agents
├── pyproject.toml
└── README.md
```

## Troubleshooting

- **uv/uvx not found**: Install uv from the official guide (https://docs.astral.sh/uv/getting-started/installation/) and then restart your terminal so `uv`/`uvx` are on PATH.
- **Credentials missing**: Set `ALPACA_API_KEY` and `ALPACA_SECRET_KEY` in the client's `env` block. Paper mode default is `ALPACA_PAPER_TRADE = True`.
- **Client didn't pick up new config**: Restart the client (Cursor, Claude Desktop, VS Code) after changes.
- **HTTP port conflicts**: If using `--transport streamable-http`, change `--port` to a free port.


## Disclosure
Insights generated by our MCP server and connected AI agents are for educational and informational purposes only and should not be taken as investment advice. Alpaca does not recommend any specific securities or investment strategies.Please conduct your own due diligence before making any decisions. All firms mentioned operate independently and are not liable for one another.

Options trading is not suitable for all investors due to its inherent high risk, which can potentially result in significant losses. Please read Characteristics and Risks of Standardized Options ([Options Disclosure Document](https://www.theocc.com/company-information/documents-and-archives/options-disclosure-document?ref=alpaca.markets)) before investing in options.

Alpaca does not prepare, edit, endorse, or approve Third Party Content. Alpaca does not guarantee the accuracy, timeliness, completeness or usefulness of Third Party Content, and is not responsible or liable for any content, advertising, products, or other materials on or available from third party sites.

All investments involve risk, and the past performance of a security, or financial product does not guarantee future results or returns. There is no guarantee that any investment strategy will achieve its objectives. Please note that diversification does not ensure a profit, or protect against loss. There is always the potential of losing money when you invest in securities, or other financial products. Investors should consider their investment objectives and risks carefully before investing.

The algorithm's calculations are based on historical and real-time market data but may not account for all market factors, including sudden price moves, liquidity constraints, or execution delays. Model assumptions, such as volatility estimates and dividend treatments, can impact performance and accuracy. Trades generated by the algorithm are subject to brokerage execution processes, market liquidity, order priority, and timing delays. These factors may cause deviations from expected trade execution prices or times. Users are responsible for monitoring algorithmic activity and understanding the risks involved. Alpaca is not liable for any losses incurred through the use of this system.

Past hypothetical backtest results do not guarantee future returns, and actual results may vary from the analysis.

The Paper Trading API is offered by AlpacaDB, Inc. and does not require real money or permit a user to transact in real securities in the market. Providing use of the Paper Trading API is not an offer or solicitation to buy or sell securities, securities derivative or futures products of any kind, or any type of trading or investment advice, recommendation or strategy, given or in any manner endorsed by AlpacaDB, Inc. or any AlpacaDB, Inc. affiliate and the information made available through the Paper Trading API is not an offer or solicitation of any kind in any jurisdiction where AlpacaDB, Inc. or any AlpacaDB, Inc. affiliate (collectively, "Alpaca") is not authorized to do business.

Securities brokerage services are provided by Alpaca Securities LLC ("Alpaca Securities"), member [FINRA](https://www.finra.org/)/[SIPC](https://www.sipc.org/), a wholly-owned subsidiary of AlpacaDB, Inc. Technology and services are offered by AlpacaDB, Inc.

Cryptocurrency services are provided by Alpaca Crypto LLC ("Alpaca Crypto"), a FinCEN registered money services business (NMLS # 2160858), and a wholly-owned subsidiary of AlpacaDB, Inc. Alpaca Crypto is not a member of SIPC or FINRA. Cryptocurrencies are not stocks and your cryptocurrency investments are not protected by either FDIC or SIPC.  Cryptocurrency assets are highly volatile and speculative, involving substantial risk of loss, and are not insured by the FDIC or any government agency. Customers should be aware of the various risks prior to engaging these services, including potential loss of principal, cybersecurity considerations, regulatory developments, and the evolving nature of digital asset technology. For additional information on the risks of cryptocurrency, please click [here](https://files.alpaca.markets/disclosures/library/CryptoRiskDisclosures.pdf).

This is not an offer, solicitation of an offer, or advice to buy or sell securities or cryptocurrencies or open a brokerage account or cryptocurrency account in any jurisdiction where Alpaca Securities or Alpaca Crypto, respectively, are not registered or licensed, as applicable.

## Privacy Policy
For information about how Alpaca handles your data, please review:
- [Privacy Policy](https://s3.amazonaws.com/files.alpaca.markets/disclosures/PrivacyPolicy.pdf)
- [Disclosure Library](https://alpaca.markets/disclosures)

### Data Collection
- **What is collected**: User agent string ('ALPACA-MCP-SERVER') for API calls
- **How it's used**: To identify MCP server usage and improve user experience
- **Third-party sharing**: Not shared with third parties
- **Retention**: Retained per Alpaca's standard data retention policy
- **Opt-out**: Modify the 'USER_AGENT' constant in '.github/core/user_agent_mixin.py' or remove 'UserAgentMixin' from client class definitions

## Security Notice

This server can place real trades and access your portfolio. Treat your API keys as sensitive credentials. Review all actions proposed by the LLM carefully, especially for complex options strategies or multi-leg trades.

**HTTP Transport Security**: When using HTTP transport, the server defaults to localhost (127.0.0.1:8000) for security. For remote access, you can bind to all interfaces with `--host 0.0.0.0`, use SSH tunneling (`ssh -L 8000:localhost:8000 user@server`), or set up a reverse proxy with authentication for secure access.

## Support
For issues or questions, please contact us at support@alpaca.markets.

GitHub Issues: https://github.com/alpacahq/alpaca-mcp-server/issues
GitHub Pull requests: https://github.com/alpacahq/alpaca-mcp-server/pulls

### MCP Registry Metadata
mcp-name: io.github.alpacahq/alpaca-mcp-server
