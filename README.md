# Alpaca MCP Server

This is a Model Context Protocol (MCP) server implementation for Alpaca's Trading API. It enables large language models (LLMs) on Claude Desktop, Cursor, or VScode to interact with Alpaca's trading infrastructure using natural language. This server supports stock trading, options trading, portfolio management, watchlist handling, and real-time market data access.

## Features

- **Market Data**
  - Real-time quotes, trades, and price bars for stocks
  - Historical price data and trading history
  - Option contract quotes and Greeks (via snapshots)
- **Account Management**
  - View balances, buying power, and account status
  - Inspect all open and closed positions
- **Position Management**
  - Get detailed info on individual holdings
  - Liquidate all or partial positions by share count or percentage
- **Order Management**
  - Place stock and option orders (market or limit)
  - Cancel orders individually or in bulk
  - Retrieve full order history
- **Options Trading**
  - Search and view option contracts by expiration or strike price
  - Place multi-leg options strategies
  - Get latest quotes and Greeks for contracts
- **Market Status & Corporate Actions**
  - Check if markets are open
  - Fetch market calendar and trading sessions
  - View upcoming corporate announcements (earnings, splits, dividends)
- **Watchlist Management**
  - Create, update, and view personal watchlists
  - Manage multiple watchlists for tracking assets
- **Asset Search**
  - Query details for stocks and other Alpaca-supported assets

## Prerequisites

- Python 3.10+
- Alpaca API keys (with paper or live trading access)
- Claude for Desktop or another compatible MCP client

## Installation

1. Clone the repository and move to the repository:
   ```bash
   git clone https://github.com/alpacahq/alpaca-mcp-server.git
   cd alpaca-mcp-server
   ```

2. Install the required packages:

   ```bash
   pip install mcp alpaca-py python-dotenv
   ```

## Usage (for Paper Trading) with Claude Desktop

### Edit a `.env` file for your credentials in the project directory

   ```
   ALPACA_API_KEY = "your_alpaca_api_key_for_paper_account"
   ALPACA_SECRET_KEY = "your_alpaca_secret_key_for_paper_account"
   ```

### Start the MCP Server

Open a terminal and run the command below from the project directory:

```bash
python alpaca_mcp_server.py
```

Or use a module invocation:

```bash
python -m alpaca_mcp_server
```

### Claude for Desktop Configuration

1. Open Claude Desktop
2. Navigate to: `Settings → Developer → Edit Config`
3. Update your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "alpaca": {
      "command": "python",
      "args": [
        "/path/to/alpaca_mcp_server.py"
      ],
      "env": {
        "ALPACA_API_KEY": "your_alpaca_api_key_for_paper_account",
        "ALPACA_SECRET_KEY": "your_alpaca_secret_key_for_paper_account"
      }
    }
  }
}
```

## API Key Configuration for Live Trading

This MCP server connects to Alpaca's **paper trading API** by default for safe testing.
To enable **live trading with real funds**, update the following configuration files:

### 🔐 Set Your API Credentials in Two Places:

1. **Claude for Desktop Configuration**

   In `claude_desktop_config.json`, provide your keys for your live account as environment variables:

   ```json
   {
     "mcpServers": {
       "alpaca": {
         "command": "python",
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

2. **`.env` in the project directory**

   ```
   ALPACA_API_KEY = "your_alpaca_api_key_for_live_account"
   ALPACA_SECRET_KEY = "your_alpaca_secret_key_for_live_account"
   PAPER = False
   ```

## Available Tools

### Account & Positions

* `get_account_info()` – View balance, margin, and account status
* `get_positions()` – List all held assets
* `get_open_position(symbol)` – Detailed info on a specific position
* `close_position(symbol, qty|percentage)` – Close part or all of a position
* `close_all_positions(cancel_orders)` – Liquidate entire portfolio

### Stock Market Data

* `get_stock_quote(symbol)` – Real-time bid/ask quote
* `get_stock_bars(symbol, start_date, end_date)` – OHLCV historical bars
* `get_stock_latest_trade(symbol)` – Latest market trade price
* `get_stock_latest_bar(symbol)` – Most recent OHLC bar
* `get_stock_trades(symbol, start_time, end_time)` – Trade-level history

### Orders

* `get_orders(status, limit)` – Retrieve all or filtered orders
* `place_stock_order(symbol, side, quantity, order_type="market", limit_price=None, stop_price=None, trail_price=None, trail_percent=None, time_in_force="day", extended_hours=False, client_order_id=None)` – Place a stock order of any type (market, limit, stop, stop_limit, trailing_stop)
* `cancel_order_by_id(order_id)` – Cancel a specific order
* `cancel_all_orders()` – Cancel all open orders

### Options

* `get_option_contracts(underlying_symbol, expiration_date)` – Fetch contracts
* `get_option_latest_quote(option_symbol)` – Latest bid/ask on contract
* `get_option_snapshot(symbol_or_symbols)` – Get Greeks and underlying
* `place_option_market_order(legs, order_class, quantity)` – Execute option strategy

### Market Info & Corporate Actions

* `get_market_clock()` – Market open/close schedule
* `get_market_calendar(start, end)` – Holidays and trading days
* `get_corporate_announcements(...)` – Earnings, dividends, splits

### Watchlists

* `create_watchlist(name, symbols)` – Create a new list
* `update_watchlist(id, name, symbols)` – Modify an existing list
* `get_watchlists()` – Retrieve all saved watchlists

### Assets

* `get_asset_info(symbol)` – Search asset metadata
* `get_all_assets(status)` – List all tradable instruments

## Example Natural Language Queries
See the "Example Queries" section below for 50 real examples covering everything from trading to corporate data to option strategies.

### Basic Trading
1. What's my current account balance and buying power?
2. Show me my current positions.
3. Buy 10 shares of AAPL at market price.
4. Sell 5 shares of TSLA with a limit price of $300.
5. Cancel all open stock orders.
6. Cancel the order with ID abc123.
7. Liquidate my entire position in GOOGL.
8. Close 10% of my position in NVDA.
9. How many shares of AMZN do I currently hold?
10. Place a limit order to buy 100 shares of MSFT at $450.
11. Place a market order to sell 25 shares of META.

### Option Trading
12. Show me available option contracts for AAPL expiring next month.
13. Get the latest quote for AAPL250613C00200000.
14. Retrieve the option snapshot for SPY250627P00400000.
15. Liquidate my position in 2 contracts of QQQ calls expiring next week.
16. Place a market order to buy 1 call option on AAPL expiring next Friday.
17. What are the option Greeks for TSLA250620P00500000?
18. Find all TSLA option contracts with strike prices within 5% of the current market price.
19. Get all contracts for SPY expiring in June that are call options.
20. Place a bull call spread using AAPL June 6th options: one with a 190.00 strike and the other with a 200.00 strike.

### Market Information
21. Is the US stock market currently open?
22. What are the market open and close times today?
23. Show me the market calendar for next week.
24. Are there any corporate announcements for major tech stocks this month?
25. What are the next dividend announcements for SPY?
26. List earnings announcements coming tomorrow.

### Historical & Real-time Data
27. Show me AAPL's daily price history for the last 5 trading days.
28. What was the closing price of TSLA yesterday?
29. Get the latest bar for GOOG.
30. What was the latest trade price for NVDA?
31. Show me the most recent quote for MSFT.
32. Retrieve the last 100 trades for AMD.
33. Show me intraday bars for AMZN from last Tuesday through last Friday.

### Orders
34. Show me all my open and filled orders from this week.
35. What orders do I have for AAPL?
36. List all limit orders I placed in the past 3 days.
37. Filter all orders by status: filled.
38. Get me the order history for yesterday.

### Watchlists
39. Create a new watchlist called "Tech Stocks" with AAPL, MSFT, and NVDA.
40. Update my "Tech Stocks" watchlist to include TSLA and AMZN.
41. What stocks are in my "Dividend Picks" watchlist?
42. Remove META from my "Growth Portfolio" watchlist.
43. List all my existing watchlists.

### Asset Information
44. Search for details about the asset 'AAPL'.
45. List all tradeable US Large-cap stocks.
46. Show me the top 5 tradable crypto assets by trading volume.
47. Filter all assets with status 'active'.
48. Show me details for the stock with symbol 'GOOGL'.

### Combined Scenarios
49. Get today's market clock and show me my buying power before placing a limit buy order for TSLA at $340.
50. Place a bull call spread with SPY July 3rd options: buy one 5% above and sell one 3% below the current SPY price.

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

## ⚠️ Security Notice

This server can place real trades and access your portfolio. Treat your API keys as sensitive credentials. Review all actions proposed by the LLM carefully, especially for complex options strategies or multi-leg trades.

## License

MIT
