# Automated Fractional-Stock Trading Algorithm

A simple, functional, and minimal automated trading algorithm that uses Alpaca's MCP server to implement a momentum-based fractional stock trading strategy.

## Overview

This algorithm implements a systematic approach to fractional stock trading by:

1. **Scanning the Universe**: Identifies U.S. equities that are fractionable, trade under a price threshold, and meet volume requirements
2. **Computing Indicators**: Calculates 12-month and 6-month momentum, 50/200-day moving averages, and 20-day z-scores
3. **Position Selection**: Selects long positions based on momentum and moving average criteria, with optional short positions
4. **Risk Management**: Implements trailing stops and time-based exits for all positions
5. **Fractional Trading**: Uses Alpaca's fractional share support for precise position sizing

## Features

- **Simple & Functional**: Focus on core trading logic without unnecessary complexity
- **Fractional Shares**: Full support for fractional share orders
- **Risk Controls**: Built-in trailing stops and time-based exits
- **Dry Run Mode**: Test the algorithm without placing actual trades
- **Comprehensive Logging**: Detailed logging for monitoring and debugging
- **Configurable Parameters**: Easy customization of all trading parameters

## Prerequisites

- Python 3.8 or higher
- Alpaca trading account with API keys
- `.env` file with your Alpaca credentials
- The `alpaca_mcp_server.py` file in the same directory

## Installation

1. **Clone or download the files** to your local directory
2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```
3. **Ensure your `.env` file** is in the same directory with:
   ```
   ALPACA_API_KEY=your_api_key_here
   ALPACA_SECRET_KEY=your_secret_key_here
   ALPACA_PAPER_TRADE=True
   ```

## Configuration

The algorithm uses these default parameters (all configurable via command line):

| Parameter | Default | Description |
|-----------|---------|-------------|
| `MAX_PRICE` | $25.00 | Maximum share price for screening |
| `MIN_AVG_VOLUME` | 250,000 | Minimum average daily volume |
| `CAPITAL` | $2,000 | Total capital to allocate |
| `EQUITIES_TOP` | 75 | Number of long positions to open |
| `SHORTS_TOP` | 10 | Number of short positions (0 to disable) |
| `ZSCORE_THRESHOLD` | 1.5 | Minimum z-score for shorting |
| `TRAIL_PCT` | 5.0% | Trailing stop percentage |
| `TIME_EXIT_MIN` | 2,880 | Maximum holding time in minutes |

## Usage

### Basic Usage

```bash
# Run with default settings
python fractional_trading_algorithm.py

# Dry run to see selections without trading
python fractional_trading_algorithm.py --dry-run
```

### Custom Configuration

```bash
# Custom capital allocation
python fractional_trading_algorithm.py --capital 5000 --max-price 50

# Conservative settings (fewer positions, no shorts)
python fractional_trading_algorithm.py --equities-top 50 --shorts-top 0 --trail-pct 3

# Aggressive settings
python fractional_trading_algorithm.py --equities-top 100 --shorts-top 20 --zscore-threshold 2.0
```

### Command Line Options

| Option | Short | Description |
|--------|-------|-------------|
| `--capital` | `-c` | Total capital to allocate |
| `--max-price` | `-m` | Maximum share price for screening |
| `--min-avg-volume` | | Minimum average daily volume |
| `--equities-top` | `-e` | Number of long positions |
| `--shorts-top` | `-s` | Number of short positions |
| `--zscore-threshold` | `-z` | Minimum z-score for shorting |
| `--trail-pct` | `-t` | Trailing stop percentage |
| `--time-exit-min` | | Maximum holding time in minutes |
| `--dry-run` | | Display selections without executing |
| `--help` | `-h` | Show help message |

## Strategy Logic

### Universe Screening
- **Asset Class**: U.S. equities only
- **Status**: Active trading status
- **Price**: Under specified maximum price threshold
- **Volume**: Above specified minimum average daily volume
- **Fractionability**: Assumes all U.S. equities support fractional shares

### Technical Indicators
1. **12-Month Momentum**: Price change over 12 months (excluding most recent month)
2. **6-Month Momentum**: Price change over 6 months (excluding most recent month)
3. **Moving Averages**: 50-day and 200-day simple moving averages
4. **Z-Score**: 20-day price deviation from moving average

### Position Selection
- **Longs**: Top momentum names above 200-day MA with low z-score
- **Shorts**: Bottom momentum names below 200-day MA with high z-score
- **Momentum Score**: Weighted combination of 12M (60%) and 6M (40%) momentum

### Risk Management
- **Position Sizing**: Equal capital allocation across all positions
- **Trailing Stops**: Configurable percentage-based trailing stops
- **Time Exits**: Maximum holding time for all positions
- **Fractional Shares**: Precise position sizing using fractional shares

## Example Output

### Dry Run Mode
```
============================================================
FRACTIONAL TRADING ALGORITHM - DRY RUN
============================================================

Configuration:
  MAX_PRICE: 25.0
  MIN_AVG_VOLUME: 250000
  CAPITAL: 2000.0
  EQUITIES_TOP: 75
  SHORTS_TOP: 10
  ZSCORE_THRESHOLD: 1.5
  TRAIL_PCT: 5.0
  TIME_EXIT_MIN: 2880

Selected Positions:
  Longs: 75 positions
  Shorts: 10 positions

Long Positions:
  AAPL: $24.50 | 12M: 15.2% | 6M: 8.7% | Z-Score: 0.8 | Shares: 81.63
  MSFT: $23.80 | 12M: 12.8% | 6M: 6.9% | Z-Score: 0.5 | Shares: 84.03
  ...

Short Positions:
  XYZ: $18.20 | 12M: -12.5% | 6M: -8.3% | Z-Score: 2.1 | Shares: 109.89
  ...

Total Position Value: $1998.45
Capital Utilization: 99.9%
============================================================
```

## Logging

The algorithm creates detailed logs in `trading_algorithm.log` including:
- Configuration parameters
- Universe scanning results
- Data retrieval progress
- Indicator computation
- Position selection
- Order placement results
- Error handling

## Error Handling

The algorithm includes comprehensive error handling for:
- **Environment Loading**: Clear messages if `.env` file cannot be read
- **API Errors**: Graceful handling of Alpaca API errors
- **Data Issues**: Continues processing if individual symbols fail
- **Validation**: Input parameter validation with helpful error messages
- **Rate Limiting**: Built-in delays to respect API rate limits

## Safety Features

- **Dry Run Mode**: Test without placing trades
- **Parameter Validation**: All inputs validated before execution
- **Error Logging**: Comprehensive error tracking
- **Rate Limiting**: Respects API rate limits
- **Graceful Degradation**: Continues processing despite individual failures

## Limitations

- **Data Quality**: Depends on Alpaca's data quality and availability
- **Market Hours**: Designed for regular market hours trading
- **Risk**: All trading involves risk; this is not financial advice
- **Performance**: Limited to first 100 symbols for performance reasons
- **Fractionability**: Assumes all U.S. equities support fractional shares

## Troubleshooting

### Common Issues

1. **Environment Variables Not Loaded**
   - Ensure `.env` file is in the same directory as the script
   - Check file permissions and format

2. **No Eligible Symbols Found**
   - Verify your Alpaca API credentials
   - Check if the market is open
   - Adjust price and volume thresholds

3. **API Rate Limit Errors**
   - The algorithm includes built-in rate limiting
   - Reduce the number of symbols processed if needed

4. **Data Parsing Errors**
   - Check the log file for specific error details
   - Verify Alpaca MCP server is working correctly

### Getting Help

- Check the log file (`trading_algorithm.log`) for detailed error information
- Verify your Alpaca account status and API permissions
- Ensure the MCP server is running and accessible
- Test with `--dry-run` first to verify the algorithm logic

## Disclaimer

This software is for educational and informational purposes only. It is not financial advice and should not be used as the sole basis for investment decisions. All trading involves risk, including the potential loss of principal. Past performance does not guarantee future results.

## License

MIT License - see LICENSE file for details.

## Support

For issues related to:
- **Alpaca API**: Contact Alpaca support
- **MCP Server**: Check the `alpaca_mcp_server.py` documentation
- **Algorithm Logic**: Review the code and logs for debugging

---

**Remember**: Always test with small amounts and dry runs before using real capital. This algorithm is designed to be simple and functional, but trading always involves risk.
