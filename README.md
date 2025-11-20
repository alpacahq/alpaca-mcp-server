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
<a href="https://alpaca.markets/sdks/python/" target="_blank"><img src="https://img.shields.io/badge/Python_SDK-DCDCDC?logo=python&logoColor=000" alt="Python SDK"></a>

</div>

<p align="center">
  A comprehensive Model Context Protocol (MCP) server for Alpaca's Trading API. Enable natural language trading operations through AI assistants like Claude, Cursor, and VS Code. Supports stocks, options, crypto, portfolio management, and real-time market data.
</p>

## Table of Contents

- [Prerequisites](#prerequisites)
- [Start here](#start-here)
- [Getting Your API Keys](#getting-your-api-keys)
- [Switching API Keys for Live Trading](#switching-api-keys-for-live-trading)
- [Quick Local Installation for MCP Server](#quick-local-installation-for-mcp-server)
- [Features](#features)
- [Example Prompts](#example-prompts)
- [Example Outputs](#example-outputs)
- [Available Tools](#available-tools)
- [MCP Client Configuration](#mcp-client-configuration)
- [OAuth Bearer Token Support](#oauth-bearer-token-support)
- [HTTP Transport for Remote Usage](#http-transport-for-remote-usage)
- [Disclosure](#disclosure)

## Prerequisites
You need the following prerequisites to configure and run the Alpaca MCP Server.
- **Terminal** (macOS/Linux) | **Command Prompt or PowerShell** (Windows)
- **Python 3.10+** (Check the [official installation guide](https://www.python.org/downloads/) and confirm the version by typing the following command: `python3 --version` in Terminal)
- **uv** (Install using the [official guide](https://docs.astral.sh/uv/getting-started/installation/))\
  **Tip:** `uv` can be installed either through a package manager (like `Homebrew`) or directly using `curl | sh`.
- **Alpaca Trading API keys** (free paper trading account available)
- **MCP client** (Claude Desktop, Cursor, VS Code, etc.)

**Note: Using an MCP server requires installation and configuration of both the MCP server and MCP client.**

## Start here
**Note:** These steps assume all [Prerequisites](#prerequisites) have been installed.
- **Claude Desktop**
  - **Local**: Use `uvx` or `install.py` → see [Claude Desktop Configuration](#claude-desktop-configuration)
- **Claude Mobile**
  - **Remote Hosting**: Deploy to cloud service → see [Claude Mobile Configuration](#claude-mobile-configuration)
- **ChatGPT**
  - **Remote Hosting**: Deploy to cloud service → see [ChatGPT Configuration](#chatgpt-configuration)
- **Cursor**
  - **Local (Cursor Directory)**: Use the Cursor Directory entry and connect in a few clicks → see [Cursor Configuration](#cursor-configuration)
  - **Local (install.py)**: Use `install.py` to set up and auto-configure Cursor → see [Cursor Configuration](#cursor-configuration)
- **VS Code**
  - **Local**: Use `uvx` → see [VS Code Configuration](#vs-code-configuration)
- **PyCharm**
  - **Local**: Use `uvx` → see [PyCharm Configuration](#pycharm-configuration)
- **Claude Code**
  - **Local**: Use `uvx` or Docker → see [Claude Code Configuration](#claude-code-configuration)
- **Gemini CLI**
  - **Local**: Use `uvx` → see [Gemini CLI Configuration](#gemini-cli-configuration)

Note: How to show hidden files
- macOS Finder: Command + Shift + .
- Linux file managers: Ctrl + H
- Windows File Explorer: Alt, V, H
- Terminal (macOS/Linux): `ls -a`

## Getting Your API Keys

1. Visit [Alpaca Trading API Account Dashboard](https://app.alpaca.markets/paper/dashboard/overview)
2. Create a free paper trading account
3. Generate API keys from the dashboard

## Switching API Keys for Live Trading

To enable **live trading with real funds** or switch between different accounts, update API credentials in **two places**:

1. **`.env` file** (used by MCP server)
2. **MCP client config JSON** (used by MCP client like Claude Desktop, Cursor, etc.)

**Important:** The MCP client configuration overrides the `.env` file. When using an MCP client, the credentials in the client's JSON config take precedence.

<details>
<summary><b>Step 1: Update MCP Server Config .env file</b></summary>

Method 1: Run the init command again to update your `.env` file
```bash
# Follow the prompts to update your keys and toggle paper/live trading
uvx alpaca-mcp-server init
```
Method 2: Manually Update

```
ALPACA_API_KEY = "your_alpaca_api_key_for_live_account"
ALPACA_SECRET_KEY = "your_alpaca_secret_key_for_live_account"
ALPACA_PAPER_TRADE = False
TRADE_API_URL = None
TRADE_API_WSS = None
DATA_API_URL = None
STREAM_DATA_WSS = None
```
</details>

<details>
<summary><b>Step 2: Update MCP Client Config Json file</b></summary>

Step 2-1: Edit your MCP client configuration file:
   - **Claude Desktop**: `~/Library/Application Support/Claude/claude_desktop_config.json` (Mac) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows)
   - **Cursor**: `~/.cursor/mcp.json`
   - **VS Code**: `.vscode/mcp.json` (workspace) or user `settings.json`

Step 2-2: Update the API keys in the `env` section:

   For uvx installations:
   ```json
   {
     "mcpServers": {
       "alpaca": {
         "command": "uvx",
         "args": ["alpaca-mcp-server", "serve"],
         "env": {
           "ALPACA_API_KEY": "your_alpaca_api_key_for_live_account",
           "ALPACA_SECRET_KEY": "your_alpaca_secret_key_for_live_account"
         }
       }
     }
   }
   ```
**Then, restart your MCP client (Claude Desktop, Cursor, etc.)**
</details>

## Quick Local Installation for MCP Server
<details>
<summary><b>Method 1: One-click installation with uvx from PyPI</b></summary>

**Note: Using an MCP server requires installation and configuration of both the MCP server and MCP client.**

```bash
# Install and configure
uvx alpaca-mcp-server init
```

**Note:** If you don't have `uv` yet, install it first and then restart your terminal so `uv`/`uvx` are recognized. See the official guide: https://docs.astral.sh/uv/getting-started/installation/

**Then add to your MCP client config** :

**Config file locations:**
- **Claude Desktop**: `~/Library/Application Support/Claude/claude_desktop_config.json` (Mac) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows)
- **Cursor**: `~/.cursor/mcp.json` (Mac/Linux) or `%USERPROFILE%\.cursor\mcp.json` (Windows)


```json
{
  "mcpServers": {
    "alpaca": {
      "command": "uvx",
      "args": ["alpaca-mcp-server", "serve"],
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
<summary><b>Method 2: Install.py for Cursor or Claude Desktop</b></summary>

  Clone the repository and navigate to the directory:
  ```bash
  git clone https://github.com/alpacahq/alpaca-mcp-server.git
  cd alpaca-mcp-server
  ```
  Execute the following commands in your terminal:
  ```bash
  cd alpaca-mcp-server
  python3 install.py
  ```

</details>

<details>
<summary><b>Method 3: One-click installation from Cursor Directory for Cursor IDE</b></summary>

**Note:** These steps assume all [Prerequisites](#prerequisites) have been installed.
Cursor users can install Alpaca's MCP Server directly from the Cursor Directory in just a few clicks.

**1. Find Alpaca in the [Cursor Directory](https://cursor.directory/mcp/alpaca)**\
**2. Click "Add to Cursor" to launch Cursor on your computer**\
**3. Enter your API Key and Secret Key**\
**4. You’re all set to start using it**

</details>

<details>
<summary><b>Method 4: Docker</b></summary>

  ```bash
  # Clone and build
  git clone https://github.com/alpacahq/alpaca-mcp-server.git
  cd alpaca-mcp-server
  docker build -t mcp/alpaca:latest .
  ```

  Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:
  ```json
  {
    "mcpServers": {
      "alpaca-docker": {
        "command": "docker",
        "args": [
          "run", "--rm", "-i",
          "-e", "ALPACA_API_KEY=your_key",
          "-e", "ALPACA_SECRET_KEY=your_secret",
          "-e", "ALPACA_PAPER_TRADE=True",
          "mcp/alpaca:latest"
        ]
      }
    }
  }
  ```
</details>

<details>
<summary><b>Project Structure</b></summary>

After installing/cloning and activating the virtual environment, your directory structure should look like this:
```
alpaca-mcp-server/          ← This is the workspace folder (= project root)
├── src/                    ← Source code package
│   └── alpaca_mcp_server/  ← Main package directory
│       ├── __init__.py
│       ├── cli.py          ← Command-line interface
│       ├── config.py       ← Configuration management
│       ├── helper.py       ← Helper function management
│       └── server.py       ← MCP server implementation
├── .github/                ← GitHub settings
│   ├── core/               ← Core utility modules
│   └── workflows/          ← GitHub Actions workflows
├── .vscode/                ← VS Code settings (for VS Code users)
│   └── mcp.json
├── .venv/                  ← Virtual environment folder
│   └── bin/python
├── charts/                 ← Kubernetes deployment configurations
│   └── alpaca-mcp-server/  ← Helm chart for GKE deployment
├── .env.example            ← Environment template (use this to create `.env` file)
├── .gitignore              
├── Dockerfile              ← Docker configuration (for Docker use)
├── .dockerignore           ← Docker ignore (for Docker use)
├── pyproject.toml          ← Package configuration
├── requirements.txt        ← Python dependencies
├── install.py              ← Installation script
└── README.md
```

</details>


## Features

- **Market Data**
  - Real-time quotes, trades, and price bars for stocks, crypto, and options
  - Historical data with flexible timeframes (1Min to 1Month)
  - Comprehensive stock snapshots and trade-level history
  - Option contract quotes and Greeks
- **Account Management**
  - View balances, buying power, and account status
  - Inspect all open and closed positions
- **Position Management**
  - Get detailed info on individual holdings
  - Liquidate all or partial positions by share count or percentage
- **Order Management**
  - Place stocks, ETFs, crypto, and options orders
  - Support for market, limit, stop, stop-limit, and trailing-stop orders
  - Cancel orders individually or in bulk
  - Retrieve full order history
- **Options Trading**
  - Search option contracts by expiration, strike price, and type
  - Place single-leg or multi-leg options strategies (spreads, straddles, etc.)
  - Get latest quotes, Greeks, and implied volatility
- **Crypto Trading**
  - Place market, limit, and stop-limit crypto orders
  - Support for GTC and IOC time in force
  - Handle quantity or notional-based orders
- **Market Status & Corporate Actions**
  - Check if markets are open
  - Fetch market calendar and trading sessions
  - View upcoming / historical corporate announcements (earnings, splits, dividends)
- **Watchlist Management**
  - Create, update, and view personal watchlists
  - Manage multiple watchlists for tracking assets
- **Asset Search**
  - Query details for stocks, ETFs, crypto, and options
  - Filter assets by status, class, exchange, and attributes
- **OAuth 2.0 Support**
  - Authorization header passthrough for hosted MCP servers
  - Multi-tenant support - each LLM chatbot request can use a different user's OAuth token
  - Automatic detection of Authorization headers in incoming HTTP requests
  - Seamlessly forwards authentication to Alpaca Trading API
  - Backward compatible with traditional API key/secret authentication

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

> At this moment, you can only view and update trading watchlists created via Alpaca’s Trading API through the API itself
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

## Example Outputs

<details>
<summary><b>View Example Outputs</b></summary>

The MCP server provides detailed, well-formatted responses for various trading queries. Here are some examples:

### Option Greeks Analysis
Query: "What are the option Greeks for TSLA250620P00500000?"

Response:
Option Details:
- Current Bid/Ask: $142.62 / $143.89
- Last Trade: $138.85
- Implied Volatility: 92.54%

Greeks:
- Delta: -0.8968 (Very Bearish)
- Gamma: 0.0021 (Low Rate of Change)
- Theta: -0.2658 (Time Decay: $26.58/day)
- Vega: 0.1654 (Volatility Sensitivity)
- Rho: -0.3060 (Interest Rate Sensitivity)

Key Insights:
- High Implied Volatility (92.54%)
- Deep In-the-Money (Delta: -0.90)
- Significant Time Decay ($27/day)

### Multi-Leg Option Order
Query: "Place a bull call spread using AAPL June 6th options: one with a 190.00 strike and the other with a 200.00 strike."

Response:
Order Details:
- Order ID: fc1c04b1-8afa-4b2d-aab1-49613bbed7cb
- Order Class: Multi-Leg (MLEG)
- Status: Pending New
- Quantity: 1 spread

Spread Legs:
1. Long Leg (BUY):
   - AAPL250606C00190000 ($190.00 strike)
   - Status: Pending New

2. Short Leg (SELL):
   - AAPL250606C00200000 ($200.00 strike)
   - Status: Pending New

Strategy Summary:
- Max Profit: $10.00 per spread
- Max Loss: Net debit paid
- Breakeven: $190 + net debit paid

These examples demonstrate the server's ability to provide:
- Detailed market data analysis
- Comprehensive order execution details
- Clear strategy explanations
- Well-formatted, easy-to-read responses

</details>

## Available Tools

<details open>
<summary><b>Account & Positions</b></summary>

* `get_account_info()` – View balance, margin, and account status
* `get_all_positions()` – List all held assets
* `get_open_position(symbol)` – Detailed info on a specific position

</details>
<details>
<summary><b>Assets</b></summary>

* `get_asset(symbol)` – Search asset metadata
* `get_all_assets(status=None, asset_class=None, exchange=None, attributes=None)` – List all tradable instruments with filtering options

</details>
<details>
<summary><b>Corporate Actions</b></summary>

* `get_corporate_actions(ca_types=None, start=None, end=None, symbols=None, cusips=None, ids=None, limit=1000, sort="asc")` – Historical and future corporate actions (e.g., earnings, dividends, splits)

</details>
<details>
<summary><b>Portfolio</b></summary>

* `get_portfolio_history(timeframe=None, period=None, start=None, end=None, date_end=None, intraday_reporting=None, pnl_reset=None, extended_hours=None, cashflow_types=None)` – Retrieve account portfolio history with equity and P/L over time

</details>
<details>
<summary><b>Watchlists</b></summary>

* `create_watchlist(name, symbols)` – Create a new list
* `get_watchlists()` – Retrieve all saved watchlists
* `update_watchlist_by_id(watchlist_id, name=None, symbols=None)` – Modify an existing list
* `get_watchlist_by_id(watchlist_id)` – Get a specific watchlist by its ID
* `add_asset_to_watchlist_by_id(watchlist_id, symbol)` – Add an asset to a watchlist
* `remove_asset_from_watchlist_by_id(watchlist_id, symbol)` – Remove an asset from a watchlist
* `delete_watchlist_by_id(watchlist_id)` – Delete a specific watchlist

</details>
<details>
<summary><b>Market Calendar & Clock</b></summary>

* `get_calendar(start_date, end_date)` – Holidays and trading days
* `get_clock()` – Market open/close schedule and current status

</details>
<details>
<summary><b>Stock Market Data</b></summary>

* `get_stock_bars(symbol, days=5, hours=0, minutes=15, timeframe="1Day", limit=1000, start=None, end=None, sort=Sort.ASC, feed=None, currency=None, asof=None)` – OHLCV historical bars with flexible timeframes (1Min, 5Min, 1Hour, 1Day, etc.)
* `get_stock_quotes(symbol, days=1, hours=0, minutes=15, limit=1000, sort=Sort.ASC, feed=None, currency=None, asof=None)` – Historical quote data (level 1 bid/ask) for a stock
* `get_stock_trades(symbol, days=1, minutes=15, hours=0, limit=1000, sort=Sort.ASC, feed=None, currency=None, asof=None)` – Trade-level history
* `get_stock_latest_bar(symbol, feed=None, currency=None)` – Most recent OHLC bar
* `get_stock_latest_quote(symbol_or_symbols, feed=None, currency=None)` – Real-time bid/ask quote for one or more symbols
* `get_stock_latest_trade(symbol, feed=None, currency=None)` – Latest market trade price
* `get_stock_snapshot(symbol_or_symbols, feed=None, currency=None)` – Comprehensive snapshot with latest quote, trade, minute bar, daily bar, and previous daily bar

</details>
<details>
<summary><b>Crypto Market Data</b></summary>

* `get_crypto_bars(symbol_or_symbols, days=1, timeframe="1Hour", limit=None, start=None, end=None, feed=CryptoFeed.US)` – Historical price bars for cryptocurrency with configurable timeframe
* `get_crypto_quotes(symbol_or_symbols, days=3, limit=None, start=None, end=None, feed=CryptoFeed.US)` – Historical quote data (bid/ask) for crypto
* `get_crypto_trades(symbol_or_symbols, days=1, limit=None, start=None, end=None, sort=None, feed=CryptoFeed.US)` – Historical trade prints for cryptocurrency
* `get_crypto_latest_quote(symbol_or_symbols, feed=CryptoFeed.US)` – Latest quote for one or more crypto symbols
* `get_crypto_latest_bar(symbol_or_symbols, feed=CryptoFeed.US)` – Latest minute bar for crypto
* `get_crypto_latest_trade(symbol_or_symbols, feed=CryptoFeed.US)` – Latest trade for crypto
* `get_crypto_snapshot(symbol_or_symbols, feed=CryptoFeed.US)` – Comprehensive crypto snapshot including latest trade, quote, minute bar, daily and previous daily bars
* `get_crypto_latest_orderbook(symbol_or_symbols, feed=CryptoFeed.US)` – Latest orderbook for crypto

</details>
<details>
<summary><b>Options Market Data</b></summary>

* `get_option_contracts(underlying_symbol, expiration_date=None, expiration_date_gte=None, expiration_date_lte=None, expiration_expression=None, strike_price_gte=None, strike_price_lte=None, type=None, status=None, root_symbol=None, limit=None)` – Get option contracts with flexible filtering
* `get_option_latest_quote(option_symbol, feed=None)` – Latest bid/ask on contract
* `get_option_snapshot(symbol_or_symbols, feed=None)` – Get Greeks and underlying

</details>
<details>
<summary><b>Trading (Orders)</b></summary>

* `get_orders(status=None, limit=None, after=None, until=None, direction=None, nested=None, side=None, symbols=None)` – Retrieve all or filtered orders
* `place_stock_order(symbol, side, quantity, order_type="market", limit_price=None, stop_price=None, trail_price=None, trail_percent=None, time_in_force="day", extended_hours=False, client_order_id=None)` – Place a stock order of any type (market, limit, stop, stop_limit, trailing_stop)
* `place_crypto_order(symbol, side, order_type="market", time_in_force="gtc", qty=None, notional=None, limit_price=None, stop_price=None, client_order_id=None)` – Place a crypto order supporting market, limit, and stop_limit types with GTC/IOC time in force
* `place_option_market_order(legs, order_class=None, quantity=1, time_in_force="day", extended_hours=False)` – Execute option strategy (single or multi-leg)

</details>
<details>
<summary><b>Trading (Position Management)</b></summary>

* `cancel_all_orders()` – Cancel all open orders
* `cancel_order_by_id(order_id)` – Cancel a specific order
* `close_position(symbol, qty=None, percentage=None)` – Close part or all of a position
* `close_all_positions(cancel_orders=False)` – Liquidate entire portfolio
* `exercise_options_position(symbol_or_contract_id)` – Exercise a held option contract, converting it into the underlying asset

</details>


## MCP Client Configuration

Below you'll find step-by-step guides for connecting the Alpaca MCP server to various MCP clients. Choose the section that matches your preferred development environment or AI assistant.

<a id="claude-desktop-configuration"></a>
<details open>
<summary><b>Claude Desktop Configuration</b></summary><br>

**Note: These steps assume all [Prerequisites](#prerequisites) have been installed.**

### Method 1: uvx (Recommended)

**Simple and modern approach:**

1. Install and configure the server:
   ```bash
   uvx alpaca-mcp-server init
   ```

2. Open Claude Desktop → Settings → Developer → Edit Config

3. Add this configuration:
   ```json
   {
     "mcpServers": {
       "alpaca": {
         "type": "stdio",
         "command": "uvx",
         "args": ["alpaca-mcp-server", "serve"],
         "env": {
           "ALPACA_API_KEY": "your_alpaca_api_key",
           "ALPACA_SECRET_KEY": "your_alpaca_secret_key"
         }
       }
     }
   }
   ```

4. Restart Claude Desktop and start trading!

### Method 2: install.py (Alternative local setup)

```bash
git clone https://github.com/alpacahq/alpaca-mcp-server.git
cd alpaca-mcp-server
python3 install.py
```

Choose `claude` when prompted. The installer sets up `.venv`, writes `.env`, and updates `claude_desktop_config.json`. Restart Claude Desktop.

</details>

<a id="claude-mobile-configuration"></a>
<details>
<summary><b>Claude Mobile Configuration (Remote Hosting)</b></summary><br>

**Note: These steps assume all [Prerequisites](#prerequisites) have been installed.** 

> As of Nov 20, 2025, Alpaca does not provide a hosted Remote MCP Server. To use Alpaca's MCP Server on the Claude mobile app, you need to host it remotely on a cloud service, then connect it as a Connector on Claude desktop to access it from the mobile app. For more information, visit "[Connecting Claude to a tool](https://support.claude.com/en/articles/11724452-using-the-connectors-directory-to-extend-claude-s-capabilities)" or our learn article “[How to Deploy Alpaca’s MCP Server Remotely on Claude Mobile App](https://alpaca.markets/learn/how-to-deploy-alpaca-mcp-server-remotely-on-claude-mobile-app)”.

## Overview of Setting Up
Below is an example overview showing one approach to set up a remote Alpaca MCP Server using <b>Docker</b> and connect it to the Claude mobile app. Other deployment methods are also possible.

1. Install Alpaca’s MCP Server locally, then build and push a Docker image
2. Deploy the Alpaca’s MCP Server remotely using a cloud service
3. Connect it to Claude AI to execute trades through natural language


## Step 1: Install the Alpaca’s MCP Server
Start by installing Alpaca’s MCP Server on your local machine. Open Terminal (macOS/Linux) or Command Prompt/PowerShell (Windows), then enter the following commands:
```bash
git clone https://github.com/alpacahq/alpaca-mcp-server.git
cd alpaca-mcp-server
```

## Step 2: Login to Docker and Containerize to Push
Before proceeding, install Docker (or Docker Desktop for a GUI). After installation, run the following command to verify Docker is installed on your computer:
```bash
docker version
docker info
```

Then, log in to Docker Hub through CLI. You’ll be prompted for your Docker Hub username and password. This is required for pushing Docker images to Docker hub later.
```bash
docker login
```

Once you log in to your Docker account, use your Docker username and a custom image name (e.g., `alpaca-mcp-server`) to build and push the Docker image to Docker Hub. We use the tag `v0.1` in this example.
```bash
# Build for most cloud platforms
docker buildx build -t username/custom-docker-image-name:v0.1 --platform=linux/amd64,linux/arm64

# Push to Docker Hub
docker push username/custom-docker-image-name:v0.1 
```

You can do a sanity check locally by running the following command in terminal:
```bash
docker run --rm -p 8000:8000 -e PORT=8000 username/custom-docker-image-name:v0.1 python -m alpaca_mcp_server.server --transport streamable-http --host 0.0.0.0 --port 8000
```

## Step 3: Deploy Alpaca MCP Server Using Your Preferred Cloud Service
Now that we've pushed the Docker image (containerized Alpaca's MCP Server) to Docker Hub, we can host it as a web service using a cloud platform such as AWS, Azure, or GCP. **You can use any cloud platform you prefer.** 

### Method 1: Render
For a simpler approach, visit our learn article “[How to Deploy Alpaca’s MCP Server Remotely on Claude Mobile App](https://alpaca.markets/learn/how-to-deploy-alpaca-mcp-server-remotely-on-claude-mobile-app)” where we demonstrate using [Render](https://render.com/) instead.

### Method 2: Google Kubernetes Engine (GKE)
We also provide a [Helm chart](https://helm.sh/) under `alpaca-mcp-server/charts/alpaca-mcp-server` for deploying the Alpaca's MCP Server to [Kubernetes](https://kubernetes.io/) (Google Kubernetes Engine) as an example.

**Step 1: Deploy to GKE**
Required Configuration Updates:

Before deploying with Helm, you must update the following values in `charts/alpaca-mcp-server/values.yaml`:

Docker Image Configuration:
```yaml
image:
  repository: username/custom-docker-image-name  # Your Docker Hub repository
  tag: "v0.1"                                    # Your image tag
env:
  secrets: 
    ALPACA_API_KEY: "your-actual-api-key"
    ALPACA_SECRET_KEY: "your-actual-secret-key"
    ALPACA_BASE_URL: "https://paper-api.alpaca.markets"  # or https://api.alpaca.markets for live
ingress:
  hosts:
    - host: your-domain.com              # Replace with your domain
  tls: 
    - secretName: cert-your-domain       # Replace with your cert secret name
      hosts:
        - your-domain.com                # Replace with your domain**Deploy with Helm:**
```
Once you've updated `values.yaml`, deploy with:

```bash
helm upgrade --install alpaca-mcp-server ./charts/alpaca-mcp-server --create-namespace
```

**Step 2: Connect with Claude Web**
Once deploy Alpaca's MCP Server, it will be accessible at `https://your-domain.com`. Go to [Claude Webpage](https://claude.ai/new).

From a chat:
* Click the "Search and tools" button on the lower left of your chat interface.
* From the menu, select Manage connectors.”
* Add custom connector" and enter your preferred MCP Server name (e.g., Alpaca's MCP Server) and the URL `https://your-domain.com/mcp` in "Remote MCP Server URL" (ensure it ends with `/mcp`)

**Step 3. Use Alpaca’s MCP Server on Claude Mobile App**
Once you successfully connect Alpaca's MCP Server to Claude web, it will also be available as a connector in the Claude mobile app.

* Open the Claude mobile app. On the chat screen, tap the plus (+) icon next to the message box to open additional options.
* In the menu that appears, scroll and tap Manage Connectors to view all available and custom connectors.
* In the Connectors list, look for Alpaca’s MCP Server under Custom Connectors. Tap it to enable and start using it within your Claude’s mobile app.

</details>

<a id="chatgpt-configuration"></a>
<details>
<summary><b>ChatGPT Configuration (Remote Hosting)</b></summary><br>

**Note: These steps assume all [Prerequisites](#prerequisites) have been installed.** 

> As of Nov 20, 2025, Alpaca does not provide a hosted Remote MCP Server. To use Alpaca's MCP Server on the ChatGPT app, you need to host it remotely on a cloud service, then connect it as a Connector on ChatGPT web or mobile app to access it. For more information, visit "[Connectors in ChatGPT](https://help.openai.com/en/articles/11487775-connectors-in-chatgpt)" or our learn article “[How to Deploy Alpaca’s MCP Server Remotely on Claude Mobile App](https://alpaca.markets/learn/how-to-deploy-alpaca-mcp-server-remotely-on-claude-mobile-app)” as a reference.

### Overview of Setting Up
Below is an example overview showing one approach to set up a remote Alpaca MCP Server using <b>Docker</b> and connect it to the ChatGPT. Other deployment methods are also possible.

1. Install Alpaca’s MCP Server locally, then build and push a Docker image
2. Deploy the Alpaca’s MCP Server remotely using a cloud service
3. Connect it to ChatGPT to execute trades through natural language

For more information, refer to [Claude Mobile Configuration](#claude-mobile-configuration) above or visit our learn article "[How to Deploy Alpaca's MCP Server Remotely on Claude Mobile App](https://alpaca.markets/learn/how-to-deploy-alpaca-mcp-server-remotely-on-claude-mobile-app)" as a reference.

</details>

<a id="cursor-configuration"></a>
<details>
<summary><b>Cursor Configuration</b></summary><br>

**Note: These steps assume all [Prerequisites](#prerequisites) have been installed.**

The official Cursor MCP setup document is available here: https://docs.cursor.com/context/mcp

## Method 1: Cursor Directory UI (Recommended)

For Cursor users, you can quickly install Alpaca from the Cursor Directory in just a few clicks.

**1. Find Alpaca in the [Cursor Directory](https://cursor.directory/mcp/alpaca)**\
**2. Click "Add to Cursor" to launch Cursor on your computer**\
**3. Enter your API Key and Secret Key**\
**4. You’re all set to start using it**

## Method 2: install.py (Alternative local setup)

```bash
git clone https://github.com/alpacahq/alpaca-mcp-server.git
cd alpaca-mcp-server
python3 install.py
```

During the prompts, choose `cursor` and enter your API keys. The installer creates a `.venv`, writes a `.env`, and auto-updates `~/.cursor/mcp.json`. Restart Cursor to load the config.

**Note: If `uv` is not installed, the installer can help you install it. You may need to restart your terminal after installing `uv` so `uv`/`uvx` are recognized.**


## Use JSON Configuration to update API keys

If you want to confirm your configuration or change the API keys, open and edit `~/.cursor/mcp.json` (macOS/Linux) or `%USERPROFILE%\.cursor\mcp.json` (Windows):

```json
{
  "mcpServers": {
    "alpaca": {
      "type": "stdio",
      "command": "uvx",
      "args": ["alpaca-mcp-server", "serve"],
      "env": {
        "ALPACA_API_KEY": "your_alpaca_api_key",
        "ALPACA_SECRET_KEY": "your_alpaca_secret_key"
      }
    }
  }
}
```

</details>

<a id="vs-code-configuration"></a>
<details>
<summary><b>VS Code Configuration</b></summary><br>

To use Alpaca MCP Server with VS Code, please follow the steps below.

VS Code supports MCP servers through GitHub Copilot's agent mode.
The official VS Code setup document is available here: https://code.visualstudio.com/docs/copilot/chat/mcp-servers

**Note: These steps assume all [Prerequisites](#prerequisites) have been installed.**

## 1. Enable MCP Support in VS Code

1. Open VS Code Settings (Ctrl/Cmd + ,)
2. Search for "chat.mcp.enabled" to check the box to enable MCP support
3. Search for "github.copilot.chat.experimental.mcp" to check the box to use instruction files

## 2. Configure the MCP Server (uvx recommended)

**Recommendation:** Use **workspace-specific** configuration (`.vscode/mcp.json`) instead of user-wide configuration. This allows different projects to use different API keys (multiple paper accounts or live trading) and keeps trading tools isolated from other development work.

**For workspace-specific settings:**

1. Create `.vscode/mcp.json` in your project root.
2. Add the Alpaca MCP server configuration manually to the mcp.json file:

    ```json
    {
      "mcp": {
        "servers": {
          "alpaca": {
            "type": "stdio",
            "command": "uvx",
            "args": ["alpaca-mcp-server", "serve"],
            "env": {
              "ALPACA_API_KEY": "your_alpaca_api_key",
              "ALPACA_SECRET_KEY": "your_alpaca_secret_key"
            }
          }
        }
      }
    }
    ```

    **Note:** Replace `${workspaceFolder}` with your actual project path. For example:
      - Linux/macOS: `/Users/username/Documents/alpaca-mcp-server`
      - Windows: `C:\\Users\\username\\Documents\\alpaca-mcp-server`
    

**For user-wide settings:**

To configure an MCP server for all your workspaces, you can add the server configuration to your user settings.json file. This allows you to reuse the same server configuration across multiple projects.
Specify the server in the `mcp` VS Code user settings (`settings.json`) to enable the MCP server across all workspaces.
```json
{
  "mcp": {
    "servers": {
      "alpaca": {
        "type": "stdio",
        "command": "bash",
        "args": ["-c", "cd ${workspaceFolder} && source ./.venv/bin/activate && alpaca-mcp-server serve"],
        "env": {
          "ALPACA_API_KEY": "your_alpaca_api_key",
          "ALPACA_SECRET_KEY": "your_alpaca_secret_key"
        }
      }
    }
  }
}
```

</details>

<a id="pycharm-configuration"></a>
<details>
<summary><b>PyCharm Configuration</b></summary><br>

**Note: These steps assume all [Prerequisites](#prerequisites) have been installed.**

To use the Alpaca MCP Server with PyCharm, please follow the steps below. The official setup guide for configuring the MCP Server in PyCharm is available here: https://www.jetbrains.com/help/ai-assistant/configure-an-mcp-server.html

PyCharm supports MCP servers through its integrated MCP client functionality. This configuration ensures proper logging behavior and prevents common startup issues.

## 1. Open PyCharm Settings
   - Go to `File → Settings`
   - Navigate to `Tools → Model Context Protocol (MCP)` (or similar location depending on PyCharm version)

## 2. Add New MCP Server
   - Click `Add` or `+` to create a new server configuration. You can also import the settings from Claude by clicking the corresponding button.
   - **Name**: Enter any name you prefer for this server configuration (e.g., Alpaca MCP).
   - **type**: "stdio",
   - **Command**: "uvx",
   - **Arguments**: ["alpaca-mcp-server", "serve"]

## 3. Set Environment Variables
   Add the following environment variables in the Environment Variables parameter:
   ```
   ALPACA_API_KEY="your_alpaca_api_key"
   ALPACA_SECRET_KEY="your_alpaca_secret_key"
   MCP_CLIENT=pycharm
   ```

</details>

<a id="claude-code-configuration"></a>
<details>
<summary><b>Claude Code Configuration</b></summary><br>

**Note: These steps assume all [Prerequisites](#prerequisites) have been installed.**

## Method 1: Using uvx (Recommended)

1) Install and Initialize the server (creates a local `.env`):
```bash
uvx alpaca-mcp-server init
```

2) Register the MCP server via Claude Code:
```bash
claude mcp add alpaca --scope user --transport stdio uvx alpaca-mcp-server serve \
  --env ALPACA_API_KEY=your_alpaca_api_key \
  --env ALPACA_SECRET_KEY=your_alpaca_secret_key
```
   - `--scope user` adds the server globally (available in all projects)
   - Omit `--scope user` to add it only to the current project

## Method 2: Using Docker

Requires Docker installed and the image built locally (see [Docker Configuration](#docker-configuration)).

```bash
claude mcp add alpaca-docker --scope user --transport stdio \
  --env ALPACA_API_KEY=your_alpaca_api_key \
  --env ALPACA_SECRET_KEY=your_alpaca_secret_key \
  --env ALPACA_PAPER_TRADE=True \
  -- docker run -i --rm \
  -e ALPACA_API_KEY \
  -e ALPACA_SECRET_KEY \
  -e ALPACA_PAPER_TRADE \
  mcp/alpaca:latest
```
   - `--scope user` adds the server globally (available in all projects)
   - Omit `--scope user` to add it only to the current project

## Verify

- Launch the Claude Code CLI: `claude`
- Run `/mcp` and confirm the `alpaca` server and tools are listed
- If the server doesn't appear, try `claude mcp list` to review registered servers

</details>

<a id="gemini-cli-configuration"></a>
<details>
<summary><b>Gemini CLI Configuration</b></summary><br>

**Note: These steps assume all [Prerequisites](#prerequisites) have been installed. Also, Gemini CLI requires Node.js version 20 or higher.**

## 1. Install [Gemini-CLI](https://github.com/google-gemini/gemini-cli) and authenticate yourself by login with Google, Gemini API Key, or Vertex AI depending on your purposes. 

## 2. Install Alpaca's MCP Server

Install and Initialize the server (creates a local `.env`):
```bash
uvx alpaca-mcp-server init
```

## 3. Configure the MCP server in settings.json
Configure MCP servers in `settings.json` using the `mcpServers` object for specific server definitions and the `mcp` object for global settings. Gemini CLI uses this configuration to locate and connect to servers, supporting multiple servers with different transport mechanisms.

```json
{
  "mcpServers": {
    "alpaca": {
      "type": "stdio",
      "command": "uvx",
      "args": ["alpaca-mcp-server", "serve"],
      "env": {
        "ALPACA_API_KEY": "your_alpaca_api_key",
        "ALPACA_SECRET_KEY": "your_alpaca_secret_key"
      }
    }
  }
}
```

For more information, visit the [How to set up your MCP server in Gemini CLI](https://github.com/google-gemini/gemini-cli/blob/main/docs/tools/mcp-server.md#how-to-set-up-your-mcp-server).

</details>

<a id="docker-configuration"></a>
<details>
<summary><b>Docker Configuration</b></summary>

## Docker Configuration (locally)

**Note: These steps assume all [Prerequisites](#prerequisites) have been installed.**
For more practical instruction, visit

**Build the image:**
```bash
git clone https://github.com/alpacahq/alpaca-mcp-server.git
cd alpaca-mcp-server
docker build -t mcp/alpaca:latest .
```

**Add to Claude Desktop config** (`~/Library/Application Support/Claude/claude_desktop_config.json`):
```json
{
  "mcpServers": {
    "alpaca-docker": {
      "command": "docker",
      "args": [
        "run", "--rm", "-i",
        "-e", "ALPACA_API_KEY=your_alpaca_api_key",
        "-e", "ALPACA_SECRET_KEY=your_alpaca_secret_key",
        "-e", "ALPACA_PAPER_TRADE=True",
        "mcp/alpaca:latest"
      ]
    }
  }
}
```

Replace `your_alpaca_api_key` and `your_alpaca_secret_key` with your actual Alpaca credentials, then restart Claude Desktop.

</details>

## OAuth Bearer Token Support
<a id="oauth-bearer-token-support"></a>
<details>
<summary><b>OAuth Bearer Token Support</b></summary>

The Alpaca MCP Server supports OAuth 2.0 bearer token authentication for hosted deployments where LLM chatbots need to authenticate on behalf of end users. This is particularly useful for multi-tenant scenarios where different users access the same MCP server instance.

### How It Works

When the MCP server receives an HTTP request with an `Authorization` header:
1. The header is extracted from the incoming request
2. The header is passed along directly to all Alpaca Trading API calls
3. Alpaca authenticates the request using the OAuth token in the header

This is a **passthrough authentication** mechanism - the MCP server simply forwards the Authorization header from your LLM chatbot to Alpaca's API.

### Using OAuth Authentication

#### Client-Side (LLM Chatbot)

Your LLM chatbot should include the Authorization header with each HTTP request to the MCP server:

```http
Authorization: Bearer <access-token>
```

Example using cURL:
```bash
curl -X POST https://your-mcp-server.com/mcp \
  -H "Authorization: Bearer YOUR_OAUTH_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "method": "tools/call", "params": {"name": "get_account_info"}}'
```

#### Server-Side Configuration

No special configuration required! The MCP server automatically:
- Detects the `Authorization` header in incoming HTTP requests (when using `--transport streamable-http`)
- Passes the header to Alpaca Trading API calls
- Falls back to environment variable credentials if no Authorization header is present

### Obtaining OAuth Tokens

To get OAuth tokens for your users, follow [Alpaca's OAuth 2.0 flow](https://docs.alpaca.markets/docs/using-oauth2-and-trading-api):

1. **Request User Authorization**: Redirect users to Alpaca's authorization endpoint with your client_id
2. **Handle Callback**: Alpaca redirects back with an authorization code
3. **Exchange for Access Token**: POST to Alpaca's token endpoint with the code
4. **Use Token**: Include the access token in the Authorization header when calling your MCP server

Example token exchange:
```bash
curl -X POST https://api.alpaca.markets/oauth/token \
  -d "grant_type=authorization_code" \
  -d "code=67f74f5a-a2cc-4ebd-88b4-22453fe07994" \
  -d "client_id=YOUR_CLIENT_ID" \
  -d "client_secret=YOUR_CLIENT_SECRET" \
  -d "redirect_uri=YOUR_REDIRECT_URI"
```

### Security Considerations

- **HTTPS Only**: Always use HTTPS in production to protect OAuth tokens in transit
- **Token Storage**: Store tokens securely on the client side
- **Token Expiration**: Implement token refresh logic as per Alpaca's OAuth documentation
- **No Server-Side Storage**: The MCP server does not store or cache tokens - they are passed through per-request

### Example: Multi-Tenant Deployment

```python
# Your LLM chatbot making authenticated requests to the MCP server
import requests

# Token obtained from Alpaca OAuth flow for this specific user
user_oauth_token = "79500537-5796-4230-9661-7f7108877c60"

response = requests.post(
    "https://your-mcp-server.com/mcp",
    headers={
        "Authorization": f"Bearer {user_oauth_token}",
        "Content-Type": "application/json"
    },
    json={
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {
            "name": "get_account_info",
            "arguments": {}
        }
    }
)

print(response.json())
```

</details>

## HTTP Transport for Remote Usage

**Note:** You typically don't need to manually start the server for local usage. MCP clients like Claude Desktop and Cursor will automatically start the server when configured. Use this section only for remote access setups.

<details>
<summary><b>Expand for Remote Server Setup Instructions</b></summary>

For users who need to run the MCP server on a remote machine (e.g., Ubuntu server) and connect from a different machine (e.g., Windows Claude Desktop), use HTTP transport:

### Server Setup (Remote Machine)
```bash
# Start server with HTTP transport (default: 127.0.0.1:8000)
alpaca-mcp-server serve --transport http

# Start server with custom host/port for remote access
alpaca-mcp-server serve --transport http --host 0.0.0.0 --port 9000

# For systemd service (example from GitHub issue #6)
# Update your start script to use HTTP transport
#!/bin/bash
cd /root/alpaca-mcp-server
source .venv/bin/activate
exec alpaca-mcp-server serve --transport http --host 0.0.0.0 --port 8000
```

**Remote Access Options:**
1. **Direct binding**: Use `--host 0.0.0.0` to bind to all interfaces for direct remote access
2. **SSH tunneling**: `ssh -L 8000:localhost:8000 user@your-server` for secure access (recommended for localhost binding)
3. **Reverse proxy**: Use nginx/Apache to expose the service securely with authentication

### Client Setup
Update your Claude Desktop configuration to use HTTP:
```json
{
  "mcpServers": {
    "alpaca": {
      "type": "http",
      "url": "http://your-server-ip:8000/mcp",
      "env": {
        "ALPACA_API_KEY": "your_alpaca_api_key",
        "ALPACA_SECRET_KEY": "your_alpaca_secret_key"
      }
    }
  }
}
```

### Troubleshooting HTTP Transport Issues
- **Port not listening**: Ensure the server started successfully and check firewall settings
- **Connection refused**: Verify the server is running on the expected host:port
- **ENOENT errors**: Make sure you're using the updated server command with `--transport http`
- **Remote access**: Use `--host 0.0.0.0` for direct access, or SSH tunneling for localhost binding
- **Port conflicts**: Use `--port <PORT>` to specify a different port if default is busy

**Available transport options:**
- `--transport stdio` (default): Standard input/output for local client connections (automatically used by MCP clients)
- `--transport http`: HTTP transport for remote client connections (default: 127.0.0.1:8000)
- `--transport sse`: Server-Sent Events transport for remote connections (deprecated)
- `--host HOST`: Host to bind the server to for HTTP/SSE transport (default: 127.0.0.1)
- `--port PORT`: Port to bind the server to for HTTP/SSE transport (default: 8000)

**Note:** For more information about MCP transport methods, see the [official MCP transport documentation](https://modelcontextprotocol.io/docs/concepts/transports).

</details>

## Troubleshooting

- **uv/uvx not found**: Install uv from the official guide (https://docs.astral.sh/uv/getting-started/installation/) and then restart your terminal so `uv`/`uvx` are on PATH.
- **`.env` not applied**: Ensure the server starts in the same directory as `.env`. Remember MCP client `env` overrides `.env`.
- **Credentials missing**: Set `ALPACA_API_KEY` and `ALPACA_SECRET_KEY` in `.env` or in the client's `env` block. Paper mode default is `ALPACA_PAPER_TRADE = True`.
- **Client didn’t pick up new config**: Restart the client (Cursor, Claude Desktop, VS Code) after changes.
- **HTTP port conflicts**: If using `--transport http`, change `--port` to a free port.


## Disclosure
Insights generated by our MCP server and connected AI agents are for educational and informational purposes only and should not be taken as investment advice. Alpaca does not recommend any specific securities or investment strategies.Please conduct your own due diligence before making any decisions. All firms mentioned operate independently and are not liable for one another.

Options trading is not suitable for all investors due to its inherent high risk, which can potentially result in significant losses. Please read Characteristics and Risks of Standardized Options ([Options Disclosure Document](https://www.theocc.com/company-information/documents-and-archives/options-disclosure-document?ref=alpaca.markets)) before investing in options.

Alpaca does not prepare, edit, endorse, or approve Third Party Content. Alpaca does not guarantee the accuracy, timeliness, completeness or usefulness of Third Party Content, and is not responsible or liable for any content, advertising, products, or other materials on or available from third party sites.

All investments involve risk, and the past performance of a security, or financial product does not guarantee future results or returns. There is no guarantee that any investment strategy will achieve its objectives. Please note that diversification does not ensure a profit, or protect against loss. There is always the potential of losing money when you invest in securities, or other financial products. Investors should consider their investment objectives and risks carefully before investing.

The algorithm’s calculations are based on historical and real-time market data but may not account for all market factors, including sudden price moves, liquidity constraints, or execution delays. Model assumptions, such as volatility estimates and dividend treatments, can impact performance and accuracy. Trades generated by the algorithm are subject to brokerage execution processes, market liquidity, order priority, and timing delays. These factors may cause deviations from expected trade execution prices or times. Users are responsible for monitoring algorithmic activity and understanding the risks involved. Alpaca is not liable for any losses incurred through the use of this system.

Past hypothetical backtest results do not guarantee future returns, and actual results may vary from the analysis.

The Paper Trading API is offered by AlpacaDB, Inc. and does not require real money or permit a user to transact in real securities in the market. Providing use of the Paper Trading API is not an offer or solicitation to buy or sell securities, securities derivative or futures products of any kind, or any type of trading or investment advice, recommendation or strategy, given or in any manner endorsed by AlpacaDB, Inc. or any AlpacaDB, Inc. affiliate and the information made available through the Paper Trading API is not an offer or solicitation of any kind in any jurisdiction where AlpacaDB, Inc. or any AlpacaDB, Inc. affiliate (collectively, “Alpaca”) is not authorized to do business.

Securities brokerage services are provided by Alpaca Securities LLC ("Alpaca Securities"), member [FINRA](https://www.finra.org/)/[SIPC](https://www.sipc.org/), a wholly-owned subsidiary of AlpacaDB, Inc. Technology and services are offered by AlpacaDB, Inc.

Cryptocurrency services are provided by Alpaca Crypto LLC ("Alpaca Crypto"), a FinCEN registered money services business (NMLS # 2160858), and a wholly-owned subsidiary of AlpacaDB, Inc. Alpaca Crypto is not a member of SIPC or FINRA. Cryptocurrencies are not stocks and your cryptocurrency investments are not protected by either FDIC or SIPC.  Cryptocurrency assets are highly volatile and speculative, involving substantial risk of loss, and are not insured by the FDIC or any government agency. Customers should be aware of the various risks prior to engaging these services, including potential loss of principal, cybersecurity considerations, regulatory developments, and the evolving nature of digital asset technology. For additional information on the risks of cryptocurrency, please click [here](https://files.alpaca.markets/disclosures/library/CryptoRiskDisclosures.pdf).

This is not an offer, solicitation of an offer, or advice to buy or sell securities or cryptocurrencies or open a brokerage account or cryptocurrency account in any jurisdiction where Alpaca Securities or Alpaca Crypto, respectively, are not registered or licensed, as applicable.

## Security Notice

This server can place real trades and access your portfolio. Treat your API keys as sensitive credentials. Review all actions proposed by the LLM carefully, especially for complex options strategies or multi-leg trades.

**HTTP Transport Security**: When using HTTP transport, the server defaults to localhost (127.0.0.1:8000) for security. For remote access, you can bind to all interfaces with `--host 0.0.0.0`, use SSH tunneling (`ssh -L 8000:localhost:8000 user@server`), or set up a reverse proxy with authentication for secure access.

## Usage Analytics Notice
The user agent for API calls defaults to 'ALPACA-MCP-SERVER' to help Alpaca identify MCP server usage and improve user experience. You can opt out by modifying the 'USER_AGENT' constant in '.github/core/user_agent_mixin.py' or by removing the 'UserAgentMixin' from the client class definitions in 'src/alpaca_mcp_server/server.py' — though we kindly hope you'll keep it enabled to support ongoing improvements.

### MCP Registry Metadata
mcp-name: io.github.alpacahq/alpaca-mcp-server