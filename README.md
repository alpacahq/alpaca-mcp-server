# Alpaca MCP Server

This is a Model Context Protocol (MCP) server implementation for Alpaca's Trading API. It enables large language models (LLMs) on Claude Desktop, Cursor, or VScode to interact with Alpaca's trading infrastructure using natural language (English). This server supports stock trading, options trading, portfolio management, watchlist handling, and real-time market data access.

## Features

- **Market Data**
  - Real-time quotes, trades, and price bars for stocks
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
  - Place stock, crypto, and option orders
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
  - Query details for stocks, crypto, and other Alpaca-supported assets
  - Filter assets by status, class, exchange, and attributes

## Getting Started
### 0. Prerequisites

- Python (version requirements can be found at: https://modelcontextprotocol.io/quickstart/server)
- GitHub account
- Alpaca API keys (with paper or live trading access)
- Claude for Desktop or another compatible MCP client

### 1. Installation

1. Clone the repository and navigate to the directory:
   ```bash
   git clone https://github.com/alpacahq/alpaca-mcp-server.git
   cd alpaca-mcp-server
   ```

2. Create and activate a virtual environment and Install the required packages:

    **Option A: Using pip (traditional)**

    ```bash
    python3 -m venv .venv
    source .venv/bin/activate  # On Windows: .venv\Scripts\activate
    pip install -r requirements.txt
    ```

    **Option B: Using uv (modern, faster)**

    To use uv, you'll first need to install it. See the [official uv installation guide](https://docs.astral.sh/uv/getting-started/installation/) for detailed installation instructions for your platform.
    ```bash
    uv venv .venv
    source .venv/bin/activate # On Windows: .venv\Scripts\activate
    uv pip install -r requirements.txt
    ```
    **Note:** The virtual environment will use the Python version that was used to create it. If you run the command with Python 3.10 or newer, your virtual environment will also use Python 3.10+. If you want to confirm the version, you can run `python3 --version` after activating the virtual environment. 


### Project Structure

After cloning and activating the virtual environment, your directory structure should look like this:
```
alpaca-mcp-server/          ← This is the workspace folder (= project root)
├── alpaca_mcp_server.py    ← Script is directly in workspace root
├── .github/                ← VS Code settings (for VS Code users)
│ ├── core/                 ← Core utility modules
│ └── workflows/            ← GitHub Actions workflows
├── .vscode/                ← VS Code settings (for VS Code users)
│   └── mcp.json
├── venv/                   ← Virtual environment folder
│   └── bin/python
├── .env.example            ← Environment template (use this to create `.env` file)
├── .gitignore              
├── Dockerfile              ← Docker configuration (for Docker use)
├── .dockerignore           ← Docker ignore (for Docker use)
├── requirements.txt           
└── README.md
```

### 2. Create and edit a .env file for your credentials in the project directory

1. Copy the example environment file in the project root by running this command:
   ```bash
   cp .env.example .env
   ```

2. Replace the credentials (e.g. API keys) in the `.env` file:

   ```
   ALPACA_API_KEY = "your_alpaca_api_key_for_paper_account"
   ALPACA_SECRET_KEY = "your_alpaca_secret_key_for_paper_account"
   ALPACA_PAPER_TRADE = True
   TRADE_API_URL = None
   TRDE_API_WSS = None
   DATA_API_URL = None
   STREAM_DATA_WSS = None
   ```

### 3. Start the MCP Server

Open a terminal in the project root directory and run the following command:

**For local usage (default - stdio transport):**
```bash
python alpaca_mcp_server.py
```

**For remote usage (HTTP transport):**
```bash
python alpaca_mcp_server.py --transport http
```

**Available transport options:**
- `--transport stdio` (default): Standard input/output for local client connections
- `--transport http`: HTTP transport for remote client connections (default: 127.0.0.1:8000)
- `--transport sse`: Server-Sent Events transport for remote connections (deprecated)
- `--host HOST`: Host to bind the server to for HTTP/SSE transport (default: 127.0.0.1)
- `--port PORT`: Port to bind the server to for HTTP/SSE transport (default: 8000)

**Note:** For more information about MCP transport methods, see the [official MCP transport documentation](https://modelcontextprotocol.io/docs/concepts/transports).

### 4. API Key Configuration for Live Trading

This MCP server connects to Alpaca's **paper trading API** by default for safe testing.
To enable **live trading with real funds**, update the following configuration files:

### Set Your API Credentials in Two Places:

1. **Update environment file in the project directory**

    Provide your live account keys as environment variables in the `.env` file:
    ```
    ALPACA_API_KEY = "your_alpaca_api_key_for_live_account"
    ALPACA_SECRET_KEY = "your_alpaca_secret_key_for_live_account"
    ALPACA_PAPER_TRADE = False
    TRADE_API_URL = None
    TRADE_API_WSS = None
    DATA_API_URL = None
    STREAM_DATA_WSS = None
    ```

2. **Update Configuration file**

   For example, when using Claude Desktop, provide your live account keys as environment variables in `claude_desktop_config.json`:

   ```json
   {
     "mcpServers": {
       "alpaca": {
         "command": "<project_root>/venv/bin/python",
         "args": [
           "/path/to/alpaca_mcp_server.py"
         ],
         "env": {
           "ALPACA_API_KEY": "your_alpaca_api_key_for_live_account",
           "ALPACA_SECRET_KEY": "your_alpaca_secret_key_for_live_account"
         }
       }
     }
   }
   ```

## MCP Client Configuration

Below you'll find step-by-step guides for connecting the Alpaca MCP server to various MCP clients. Choose the section that matches your preferred development environment or AI assistant.

### Claude Desktop Usage

To use Alpaca MCP Server with Claude Desktop, please follow the steps below. The official Claude Desktop setup document is available here: https://modelcontextprotocol.io/quickstart/user

#### Configure Claude Desktop

1. Open Claude Desktop
2. Navigate to: `Settings → Developer → Edit Config`
3. Update your `claude_desktop_config.json`:

  **Note:**\
    Replace <project_root> with the path to your cloned alpaca-mcp-server directory. This should point to the Python executable inside the virtual environment you created with `python3 -m venv venv` in the terminal.

**For local usage (stdio transport - recommended):**
```json
{
  "mcpServers": {
    "alpaca": {
      "command": "<project_root>/venv/bin/python",
      "args": [
        "/path/to/alpaca-mcp-server/alpaca_mcp_server.py"
      ],
      "env": {
        "ALPACA_API_KEY": "your_alpaca_api_key_for_paper_account",
        "ALPACA_SECRET_KEY": "your_alpaca_secret_key_for_paper_account"
      }
    }
  }
}
```

**For remote usage (HTTP transport):**
```json
{
  "mcpServers": {
    "alpaca": {
      "transport": "http",
      "url": "http://your-server-ip:8000/mcp",
      "env": {
        "ALPACA_API_KEY": "your_alpaca_api_key_for_paper_account",
        "ALPACA_SECRET_KEY": "your_alpaca_secret_key_for_paper_account"
      }
    }
  }
}
```

### Claude Code Usage

To use Alpaca MCP Server with Claude Code, please follow the steps below.

The `claude mcp add command` is part of [Claude Code](https://www.anthropic.com/claude-code). If you have the Claude MCP CLI tool installed (e.g. by `npm install -g @anthropic-ai/claude-code`), you can use this command to add the server to Claude Code:

```bash
claude mcp add alpaca \
  /path/to/your/alpaca-mcp-server/venv/bin/python \
  /path/to/your/alpaca-mcp-server/alpaca_mcp_server.py \
  -e ALPACA_API_KEY=your_api_key \
  -e ALPACA_SECRET_KEY=your_secret_key
```

**Note:** Replace the paths with your actual project directory paths. This command automatically adds the MCP server configuration to Claude Code without manual JSON editing.

The Claude MCP CLI tool needs to be installed separately. Check following the official pages for availability and installation instructions
* [Learn how to set up MCP with Claude Code](https://docs.anthropic.com/en/docs/claude-code/mcp)
* [Install, authenticate, and start using Claude Code on your development machine](https://docs.anthropic.com/en/docs/claude-code/setup)

### Cursor Usage

To use Alpaca MCP Server with Cursor, please follow the steps below. The official Cursor MCP setup document is available here: https://docs.cursor.com/context/mcp

**Prerequisites**
- Cursor IDE installed with Claude AI enabled
- Python and virtual environment set up (follow Installation steps above)

#### Configure the MCP Server

**Method 1: Using JSON Configuration**

Create or edit `~/.cursor/mcp.json` (macOS/Linux) or `%USERPROFILE%\.cursor\mcp.json` (Windows):

```json
{
  "mcpServers": {
    "alpaca": {
      "command": "/path/to/your/alpaca-mcp-server/venv/bin/python",
      "args": [
        "/path/to/your/alpaca-mcp-server/alpaca_mcp_server.py"
      ],
      "env": {
        "ALPACA_API_KEY": "your_alpaca_api_key",
        "ALPACA_SECRET_KEY": "your_alpaca_secret_key"
      }
    }
  }
}
```

**Method 2: Using Cursor Settings UI**

1. Open Cursor Settings → **Tools & Integrations** → **MCP Tools**
2. Click **"+ New MCP Server"**
3. Configure with the same details as the JSON method above

**Note:** Replace the paths with your actual project directory paths and API credentials.

### VS Code Usage

To use Alpaca MCP Server with VS Code, please follow the steps below.

VS Code supports MCP servers through GitHub Copilot's agent mode.
The official VS Code setup document is available here: https://code.visualstudio.com/docs/copilot/chat/mcp-servers

**Prerequisites**
- VS Code with GitHub Copilot extension installed and active subscription
- Python and virtual environment set up (follow Installation steps above)
- MCP support enabled in VS Code (see below)

#### 1. Enable MCP Support in VS Code

1. Open VS Code Settings (Ctrl/Cmd + ,)
2. Search for "chat.mcp.enabled" to check the box to enable MCP support
3. Search for "github.copilot.chat.experimental.mcp" to check the box to use instruction files

#### 2. Configure the MCP Server

**Recommendation:** Use **workspace-specific** configuration (`.vscode/mcp.json`) instead of user-wide configuration. This allows different projects to use different API keys (multiple paper accounts or live trading) and keeps trading tools isolated from other development work.

**For workspace-specific settings:**

1. Create `.vscode/mcp.json` in your project root.
2. Add the Alpaca MCP server configuration manually to the mcp.json file:

    For Linux/macOS:
    ```json
    {
      "mcp": {
        "servers": {
          "alpaca": {
            "type": "stdio",
            "command": "bash",
            "args": ["-c", "cd ${workspaceFolder} && source ./venv/bin/activate && python alpaca_mcp_server.py"],
            "env": {
              "ALPACA_API_KEY": "your_alpaca_api_key",
              "ALPACA_SECRET_KEY": "your_alpaca_secret_key"
            }
          }
        }
      }
    }
    ```

    For Windows:
    ```json
    {
      "mcp": {
        "servers": {
          "alpaca": {
            "type": "stdio", 
            "command": "cmd",
            "args": ["/c", "cd /d ${workspaceFolder} && .\\venv\\Scripts\\activate && python alpaca_mcp_server.py"],
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
        "args": ["-c", "cd ${workspaceFolder} && source ./venv/bin/activate && python alpaca_mcp_server.py"],
        "env": {
          "ALPACA_API_KEY": "your_alpaca_api_key",
          "ALPACA_SECRET_KEY": "your_alpaca_secret_key"
        }
      }
    }
  }
}
```

### PyCharm Usage

To use the Alpaca MCP Server with PyCharm, please follow the steps below. The official setup guide for configuring the MCP Server in PyCharm is available here: https://www.jetbrains.com/help/ai-assistant/configure-an-mcp-server.html

PyCharm supports MCP servers through its integrated MCP client functionality. This configuration ensures proper logging behavior and prevents common startup issues.

1. **Open PyCharm Settings**
   - Go to `File → Settings`
   - Navigate to `Tools → Model Context Protocol (MCP)` (or similar location depending on PyCharm version)

2. **Add New MCP Server**
   - Click `Add` or `+` to create a new server configuration. You can also import the settings from Claude by clicking the corresponding button.
   - **Name**: Enter any name you prefer for this server configuration (e.g., Alpaca MCP).
   - **Command**: "/path/to/your/alpaca-mcp-server/venv/bin/python"
   - **Arguments**: "alpaca_mcp_server.py"
   - **Working directory**: "/path/to/your/alpaca-mcp-server"

3. **Set Environment Variables**
   Add the following environment variables in the Environment Variables parameter:
   ```
   ALPACA_API_KEY="your_alpaca_api_key"
   ALPACA_SECRET_KEY="your_alpaca_secret_key"
   MCP_CLIENT=pycharm
   ```

### Docker Usage

To use Alpaca MCP Server with Docker, please follow the steps below.

**Prerequisite:**  
You must have [Docker installed](https://docs.docker.com/get-docker/) on your system.

#### Run the latest published image (recommended for most users)
```bash
docker run -it --rm \
  -e ALPACA_API_KEY=your_alpaca_api_key \
  -e ALPACA_SECRET_KEY=your_alpaca_secret_key \
  ghcr.io/chand1012/alpaca-mcp-server:latest
```
This pulls and runs the latest published version of the server. Replace `your_alpaca_api_key` and `your_alpaca_secret_key` with your actual keys. If the server exposes a port (e.g., 8080), add `-p 8080:8080` to the command.

#### Build and run locally (for development or custom changes)
```bash
docker build -t alpaca-mcp-server .
docker run -it --rm \
  -e ALPACA_API_KEY=your_alpaca_api_key \
  -e ALPACA_SECRET_KEY=your_alpaca_secret_key \
  alpaca-mcp-server
```
Use this if you want to run a modified or development version of the server.

#### Using with Claude Desktop
```json
{
  "mcpServers": {
    "alpaca": {
      "command": "docker",
      "args": [
        "run",
        "-i",
        "--rm",
        "-e", "ALPACA_API_KEY",
        "-e", "ALPACA_SECRET_KEY",
        "ghcr.io/chand1012/alpaca-mcp-server:latest"
      ],
      "env": {
        "ALPACA_API_KEY": "your_alpaca_api_key",
        "ALPACA_SECRET_KEY": "your_alpaca_secret_key"
      }
    }
  }
}
```
Environment variables can be set either with `-e` flags or in the `"env"` object, but not both. For Claude Desktop, use the `"env"` object.

**Security Note:**  Never share your API keys or commit them to public repositories. Be cautious when passing secrets as environment variables, especially in shared or production environments.

**For more advanced Docker usage:**  See the [official Docker documentation](https://docs.docker.com/).


## Available Tools

### Account & Positions

* `get_account_info()` – View balance, margin, and account status
* `get_positions()` – List all held assets
* `get_open_position(symbol)` – Detailed info on a specific position
* `close_position(symbol, qty|percentage)` – Close part or all of a position
* `close_all_positions(cancel_orders)` – Liquidate entire portfolio

### Stock Market Data

* `get_stock_quote(symbol)` – Real-time bid/ask quote
* `get_stock_bars(symbol, days=5, timeframe="1Day", limit=None, start=None, end=None)` – OHLCV historical bars with flexible timeframes (1Min, 5Min, 1Hour, 1Day, etc.)
* `get_stock_latest_trade(symbol, feed=None, currency=None)` – Latest market trade price
* `get_stock_latest_bar(symbol, feed=None, currency=None)` – Most recent OHLC bar
* `get_stock_snapshot(symbol_or_symbols, feed=None, currency=None)` – Comprehensive snapshot with latest quote, trade, minute bar, daily bar, and previous daily bar
* `get_stock_trades(symbol, days=5, limit=None, sort=Sort.ASC, feed=None, currency=None, asof=None)` – Trade-level history

### Orders

* `get_orders(status, limit)` – Retrieve all or filtered orders
* `place_stock_order(symbol, side, quantity, order_type="market", limit_price=None, stop_price=None, trail_price=None, trail_percent=None, time_in_force="day", extended_hours=False, client_order_id=None)` – Place a stock order of any type (market, limit, stop, stop_limit, trailing_stop)
* `cancel_order_by_id(order_id)` – Cancel a specific order
* `cancel_all_orders()` – Cancel all open orders

### Crypto

* `place_crypto_order(symbol, side, order_type="market", time_in_force="gtc", qty=None, notional=None, limit_price=None, stop_price=None, client_order_id=None)` – Place a crypto order supporting market, limit, and stop_limit types with GTC/IOC time in force

### Options

* `get_option_contracts(underlying_symbol, expiration_date=None, expiration_date_gte=None, expiration_date_lte=None, expiration_expression=None, strike_price_gte=None, strike_price_lte=None, type=None, status=None, root_symbol=None, limit=None)` – – Get option contracts with flexible filtering.
* `get_option_latest_quote(option_symbol)` – Latest bid/ask on contract
* `get_option_snapshot(symbol_or_symbols)` – Get Greeks and underlying
* `place_option_market_order(legs, order_class=None, quantity=1, time_in_force=TimeInForce.DAY, extended_hours=False)` – Execute option strategy
* `exercise_options_position(symbol_or_contract_id)` – Exercise a held option contract, converting it into the underlying asset

### Market Info & Corporate Actions

* `get_market_clock()` – Market open/close schedule
* `get_market_calendar(start, end)` – Holidays and trading days
* `get_corporate_announcements(ca_types, start, end, symbols)` – Historical and future corporate actions (e.g., earnings, dividends, splits)

### Watchlists

* `create_watchlist(name, symbols)` – Create a new list
* `update_watchlist(watchlist_id, name=None, symbols=None)` – Modify an existing list
* `get_watchlists()` – Retrieve all saved watchlists

### Assets

* `get_asset_info(symbol)` – Search asset metadata
* `get_all_assets(status=None, asset_class=None, exchange=None, attributes=None)` – List all tradable instruments with filtering options

## Example Natural Language Queries
See the "Example Queries" section below for real examples covering everything from trading to corporate data to option strategies.

### Basic Trading
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

### Crypto Trading
11. Place a market order to buy 0.01 ETH/USD.
12. Place a limit order to sell 0.01 BTC/USD at $110,000.

### Option Trading
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

### Market Information
23. What are the market open and close times today?
24. Show me the market calendar for next week.
25. Show me recent cash dividends and stock splits for AAPL, MSFT, and GOOGL in the last 3 months.
26. Get all corporate actions for SPY including dividends, splits, and any mergers in the past year.
27. What are the upcoming corporate actions scheduled for SPY in the next 6 months?

### Historical & Real-time Data
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

### Orders
38. Show me all my open and filled orders from this week.
39. What orders do I have for AAPL?
40. List all limit orders I placed in the past 3 days.
41. Filter all orders by status: filled.
42. Get me the order history for yesterday.

### Watchlists
> At this moment, you can only view and update trading watchlists created via Alpaca’s Trading API through the API itself
43. Create a new watchlist called "Tech Stocks" with AAPL, MSFT, and NVDA.
44. Update my "Tech Stocks" watchlist to include TSLA and AMZN.
45. What stocks are in my "Dividend Picks" watchlist?
46. Remove META from my "Growth Portfolio" watchlist.
47. List all my existing watchlists.

### Asset Information
48. Search for details about the asset 'AAPL'.
49. Show me the top 5 tradable crypto assets by trading volume.
50. Get all NASDAQ active US equity assets and filter the results to show only tradable securities

### Combined Scenarios
51. Get today's market clock and show me my buying power before placing a limit buy order for TSLA at $340.
52. Place a bull call spread with SPY July 3rd options: buy one 5% above and sell one 3% below the current SPY price.

## Example Outputs

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

The server maintains this level of detail and formatting across all supported queries, making it easy to understand and act on the information provided.

## HTTP Transport for Remote Usage

For users who need to run the MCP server on a remote machine (e.g., Ubuntu server) and connect from a different machine (e.g., Windows Claude Desktop), use HTTP transport:

### Server Setup (Remote Machine)
```bash
# Start server with HTTP transport (default: 127.0.0.1:8000)
python alpaca_mcp_server.py --transport http

# Start server with custom host/port for remote access
python alpaca_mcp_server.py --transport http --host 0.0.0.0 --port 9000

# For systemd service (example from GitHub issue #6)
# Update your start script to use HTTP transport
#!/bin/bash
cd /root/alpaca-mcp-server
source venv/bin/activate
exec python3 -u alpaca_mcp_server.py --transport http --host 0.0.0.0 --port 8000
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
      "transport": "http",
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

## Security Notice

This server can place real trades and access your portfolio. Treat your API keys as sensitive credentials. Review all actions proposed by the LLM carefully, especially for complex options strategies or multi-leg trades.

**HTTP Transport Security**: When using HTTP transport, the server defaults to localhost (127.0.0.1:8000) for security. For remote access, you can bind to all interfaces with `--host 0.0.0.0`, use SSH tunneling (`ssh -L 8000:localhost:8000 user@server`), or set up a reverse proxy with authentication for secure access.

## Usage Analytics Notice

The user agent for API calls defaults to 'ALPACA-MCP-SERVER' to help Alpaca identify MCP server usage and improve user experience. You can opt out by modifying the 'USER_AGENT' constant in '.github/core/user_agent_mixin.py' or by removing the 'UserAgentMixin' from the client class definitions in 'alpaca_mcp_server.py' — though we kindly hope you'll keep it enabled to support ongoing improvements.

## License

MIT


## Disclosure
Please note that the content on this page is for informational purposes only. Alpaca does not recommend any specific securities or investment strategies.

Options trading is not suitable for all investors due to its inherent high risk, which can potentially result in significant losses. Please read Characteristics and Risks of Standardized Options ([Options Disclosure Document](https://www.theocc.com/company-information/documents-and-archives/options-disclosure-document?ref=alpaca.markets)) before investing in options.


Alpaca does not prepare, edit, endorse, or approve Third Party Content. Alpaca does not guarantee the accuracy, timeliness, completeness or usefulness of Third Party Content, and is not responsible or liable for any content, advertising, products, or other materials on or available from third party sites.

All investments involve risk, and the past performance of a security, or financial product does not guarantee future results or returns. There is no guarantee that any investment strategy will achieve its objectives. Please note that diversification does not ensure a profit, or protect against loss. There is always the potential of losing money when you invest in securities, or other financial products. Investors should consider their investment objectives and risks carefully before investing.

The algorithm’s calculations are based on historical and real-time market data but may not account for all market factors, including sudden price moves, liquidity constraints, or execution delays. Model assumptions, such as volatility estimates and dividend treatments, can impact performance and accuracy. Trades generated by the algorithm are subject to brokerage execution processes, market liquidity, order priority, and timing delays. These factors may cause deviations from expected trade execution prices or times. Users are responsible for monitoring algorithmic activity and understanding the risks involved. Alpaca is not liable for any losses incurred through the use of this system.

Past hypothetical backtest results do not guarantee future returns, and actual results may vary from the analysis.

The Paper Trading API is offered by AlpacaDB, Inc. and does not require real money or permit a user to transact in real securities in the market. Providing use of the Paper Trading API is not an offer or solicitation to buy or sell securities, securities derivative or futures products of any kind, or any type of trading or investment advice, recommendation or strategy, given or in any manner endorsed by AlpacaDB, Inc. or any AlpacaDB, Inc. affiliate and the information made available through the Paper Trading API is not an offer or solicitation of any kind in any jurisdiction where AlpacaDB, Inc. or any AlpacaDB, Inc. affiliate (collectively, “Alpaca”) is not authorized to do business.

Securities brokerage services are provided by Alpaca Securities LLC ("Alpaca Securities"), member [FINRA](https://www.finra.org/)/[SIPC](https://www.sipc.org/), a wholly-owned subsidiary of AlpacaDB, Inc. Technology and services are offered by AlpacaDB, Inc.

This is not an offer, solicitation of an offer, or advice to buy or sell securities or open a brokerage account in any jurisdiction where Alpaca Securities is not registered or licensed, as applicable.