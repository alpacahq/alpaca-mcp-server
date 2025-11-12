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
- [MCP Client Configuration](#mcp-client-configuration)
- [HTTP Transport for Remote Usage](#http-transport-for-remote-usage)
- [Available Tools](#available-tools)


## Prerequisites
You need the following prerequisites to configure and run the Alpaca MCP Server.
- **Terminal** (macOS/Linux) | **Command Prompt or PowerShell** (Windows)
- **Python 3.10+** (Check the [official installation guide](https://www.python.org/downloads/) and confirm the version by typing the following command: `python3 --version` in Terminal)
- **uv** (Install using the [official guide](https://docs.astral.sh/uv/getting-started/installation/))\
  **Tip:** `uv` can be installed either through a package manager (like `Homebrew`) or directly using `curl | sh`.
- **Alpaca Trading API keys** (free paper trading account available)
- **MCP client** (Claude Desktop, Cursor, VS Code, etc.)



## Start here
**Note:** These steps assume all [Prerequisites](#prerequisites) have been installed.
- **Claude Desktop**
  - **Local**: Use `uvx` (recommended) or `install.py` → see [Claude Desktop Configuration](#claude-desktop-configuration)
- **Claude Code**
  - **Local**: Use `uvx` (recommended) or Docker → see [Claude Code Configuration](#claude-code-configuration)
- **Cursor**
  - **Local (Cursor Directory)**: Use the Cursor Directory entry and connect in a few clicks → see [Quick Start](#quick-start-local-installation)
  - **Local (install.py)**: Use `install.py` to set up and auto-configure Cursor → see [Cursor Configuration](#cursor-configuration)
- **VS Code**
  - **Local**: Use `uvx` → see [VS Code Configuration](#vs-code-configuration)
- **PyCharm**
  - **Local**: Use `uvx` → see [PyCharm Configuration](#pycharm-configuration)

**Note: How to show hidden files**
- macOS Finder: Command + Shift + .
- Linux file managers: Ctrl + H
- Windows File Explorer: Alt, V, H
- Terminal (macOS/Linux): `ls -a`

## Getting Your API Keys

1. Visit [Alpaca Trading API Account Dashboard](https://app.alpaca.markets/paper/dashboard/overview)
2. Create a free paper trading account
3. Generate API keys from the dashboard

## Switching API Keys for Live Trading

To enable **live trading with real funds** or switch between different accounts, you need to update API credentials in **two places**:

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
For Cursor users, you can quickly install Alpaca from the Cursor Directory in just a few clicks.

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
├── tests/                  ← Test files
│   └── test_get_stock_quote.py
├── .github/                ← GitHub settings
│   ├── core/               ← Core utility modules
│   └── workflows/          ← GitHub Actions workflows
├── .vscode/                ← VS Code settings (for VS Code users)
│   └── mcp.json
├── .venv/                   ← Virtual environment folder
│   └── bin/python
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


## MCP Client Configuration

Below you'll find step-by-step guides for connecting the Alpaca MCP server to various MCP clients. Choose the section that matches your preferred development environment or AI assistant.

<a id="claude-desktop-configuration"></a>
<details open>
<summary><b>Claude Desktop Configuration</b></summary>

### Claude Desktop Configuration
**Note: These steps assume all [Prerequisites](#prerequisites) have been installed.**

#### Method 1: uvx (Recommended)

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

#### Method 2: install.py (Alternative local setup)

```bash
git clone https://github.com/alpacahq/alpaca-mcp-server
cd alpaca-mcp-server
python3 install.py
```

Choose `claude` when prompted. The installer sets up `.venv`, writes `.env`, and updates `claude_desktop_config.json`. Restart Claude Desktop.

</details>

<a id="claude-code-configuration"></a>
<details>
<summary><b>Claude Code Configuration</b></summary>

### Claude Code Configuration

Use this local setup to register the server with Claude Code.

Prerequisites:
- Claude Code CLI installed and authenticated (see Anthropic docs below)
- Alpaca API keys (paper or live)

#### Option 1: Using uvx (Recommended)

Requires uv installed: https://docs.astral.sh/uv/getting-started/installation/

1) Initialize the server (creates a local `.env`):
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

#### Option 2: Using Docker

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

#### Verify

- Launch the Claude Code CLI: `claude`
- Run `/mcp` and confirm the `alpaca` server and tools are listed
- If the server doesn't appear, try `claude mcp list` to review registered servers

</details>

<a id="cursor-configuration"></a>
<details>
<summary><b>Cursor Configuration</b></summary>

### Cursor Configuration

To use Alpaca MCP Server with Cursor, please follow the steps below. The official Cursor MCP setup document is available here: https://docs.cursor.com/context/mcp

**Note: These steps assume all [Prerequisites](#prerequisites) have been installed.**

#### Local setup via install.py (recommended for local)

```bash
git clone https://github.com/alpacahq/alpaca-mcp-server
cd alpaca-mcp-server
python3 install.py
```

During the prompts, choose `cursor` and enter your API keys. The installer creates a `.venv`, writes a `.env`, and auto-updates `~/.cursor/mcp.json`. Restart Cursor to load the config.

Note: If `uv` is not installed, the installer can help you install it. You may need to restart your terminal after installing `uv` so `uv`/`uvx` are recognized. Reference: https://docs.astral.sh/uv/getting-started/installation/

#### Configure the MCP Server

**Method 1: Using Cursor Directory UI**
For Cursor users, you can quickly install Alpaca from the Cursor Directory in just a few clicks.

**1. Find Alpaca in the [Cursor Directory](https://cursor.directory/mcp/alpaca)**\
**2. Click "Add to Cursor" to launch Cursor on your computer**\
**3. Enter your API Key and Secret Key**\
**4. You’re all set to start using it**

**Method 2: Using JSON Configuration**

Create or edit `~/.cursor/mcp.json` (macOS/Linux) or `%USERPROFILE%\.cursor\mcp.json` (Windows):

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
<summary><b>VS Code Configuration</b></summary>

### VS Code Configuration

To use Alpaca MCP Server with VS Code, please follow the steps below.

VS Code supports MCP servers through GitHub Copilot's agent mode.
The official VS Code setup document is available here: https://code.visualstudio.com/docs/copilot/chat/mcp-servers

**Note: These steps assume all [Prerequisites](#prerequisites) have been installed.**

#### 1. Enable MCP Support in VS Code

1. Open VS Code Settings (Ctrl/Cmd + ,)
2. Search for "chat.mcp.enabled" to check the box to enable MCP support
3. Search for "github.copilot.chat.experimental.mcp" to check the box to use instruction files

#### 2. Configure the MCP Server (uvx recommended)

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
<summary><b>PyCharm Configuration</b></summary>

### PyCharm Configuration

To use the Alpaca MCP Server with PyCharm, please follow the steps below. The official setup guide for configuring the MCP Server in PyCharm is available here: https://www.jetbrains.com/help/ai-assistant/configure-an-mcp-server.html

PyCharm supports MCP servers through its integrated MCP client functionality. This configuration ensures proper logging behavior and prevents common startup issues.

**Note: These steps assume all [Prerequisites](#prerequisites) have been installed.**

1. **Open PyCharm Settings**
   - Go to `File → Settings`
   - Navigate to `Tools → Model Context Protocol (MCP)` (or similar location depending on PyCharm version)

2. **Add New MCP Server**
   - Click `Add` or `+` to create a new server configuration. You can also import the settings from Claude by clicking the corresponding button.
   - **Name**: Enter any name you prefer for this server configuration (e.g., Alpaca MCP).
   - **type**: "stdio",
   - **Command**: "uvx",
   - **Arguments**: ["alpaca-mcp-server", "serve"]

3. **Set Environment Variables**
   Add the following environment variables in the Environment Variables parameter:
   ```
   ALPACA_API_KEY="your_alpaca_api_key"
   ALPACA_SECRET_KEY="your_alpaca_secret_key"
   MCP_CLIENT=pycharm
   ```

</details>

<a id="docker-configuration"></a>
<details>
<summary><b>Docker Configuration</b></summary>

### Docker Configuration (locally)

**Note: These steps assume all [Prerequisites](#prerequisites) have been installed.**

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


## Available Tools

<details>
<summary><b>View All Available Tools</b></summary>

### Account & Positions

* `get_account_info()` – View balance, margin, and account status
* `get_positions()` – List all held assets
* `get_open_position(symbol)` – Detailed info on a specific position
* `close_position(symbol, qty|percentage)` – Close part or all of a position
* `close_all_positions(cancel_orders)` – Liquidate entire portfolio

### Stock Market Data

* `get_stock_quote(symbol_or_symbols)` – Real-time bid/ask quote for one or more symbols
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

</details>

## Troubleshooting

- **uv/uvx not found**: Install uv from the official guide (https://docs.astral.sh/uv/getting-started/installation/) and then restart your terminal so `uv`/`uvx` are on PATH.
- **`.env` not applied**: Ensure the server starts in the same directory as `.env`. Remember MCP client `env` overrides `.env`.
- **Credentials missing**: Set `ALPACA_API_KEY` and `ALPACA_SECRET_KEY` in `.env` or in the client's `env` block. Paper mode default is `ALPACA_PAPER_TRADE = True`.
- **Client didn’t pick up new config**: Restart the client (Cursor, Claude Desktop, VS Code) after changes.
- **HTTP port conflicts**: If using `--transport http`, change `--port` to a free port.

## Security Notice

This server can place real trades and access your portfolio. Treat your API keys as sensitive credentials. Review all actions proposed by the LLM carefully, especially for complex options strategies or multi-leg trades.

**HTTP Transport Security**: When using HTTP transport, the server defaults to localhost (127.0.0.1:8000) for security. For remote access, you can bind to all interfaces with `--host 0.0.0.0`, use SSH tunneling (`ssh -L 8000:localhost:8000 user@server`), or set up a reverse proxy with authentication for secure access.

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

## Usage Analytics Notice

The user agent for API calls defaults to 'ALPACA-MCP-SERVER' to help Alpaca identify MCP server usage and improve user experience. You can opt out by modifying the 'USER_AGENT' constant in '.github/core/user_agent_mixin.py' or by removing the 'UserAgentMixin' from the client class definitions in 'src/alpaca_mcp_server/server.py' — though we kindly hope you'll keep it enabled to support ongoing improvements.

### MCP Registry Metadata
mcp-name: io.github.alpacahq/alpaca-mcp-server
