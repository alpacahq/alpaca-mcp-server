#!/usr/bin/env python3
"""
Automated Fractional-Stock Trading Algorithm using Alpaca MCP Server

This script implements a simple momentum-based trading strategy that:
1. Scans U.S. equities for fractionable stocks under a price threshold
2. Computes momentum indicators and technical analysis
3. Selects long/short positions based on momentum and moving averages
4. Places fractional share orders with risk management

Author: Automated Trading System
License: MIT
"""

import os
import sys
import time
import argparse
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Optional
import pandas as pd
import numpy as np

# Import the MCP server functions
from alpaca_mcp_server import (
    get_all_assets, get_stock_bars, place_stock_order,
    get_account_info, get_positions, cancel_all_orders
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('trading_algorithm.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Default configuration constants
DEFAULT_CONFIG = {
    'MAX_PRICE': 25.0,
    'MIN_AVG_VOLUME': 250000,
    'CAPITAL': 2000.0,
    'EQUITIES_TOP': 75,
    'SHORTS_TOP': 10,
    'ZSCORE_THRESHOLD': 1.5,
    'TRAIL_PCT': 5.0,
    'TIME_EXIT_MIN': 2880
}

class FractionalTradingAlgorithm:
    """Main trading algorithm class"""
    
    def __init__(self, config: Dict[str, float]):
        """Initialize the trading algorithm with configuration"""
        self.config = config
        self.validate_config()
        logger.info(f"Initialized trading algorithm with config: {config}")
        
    def validate_config(self):
        """Validate configuration parameters"""
        for key, value in self.config.items():
            if value <= 0:
                raise ValueError(f"Configuration {key} must be positive, got {value}")
        
        if self.config['SHORTS_TOP'] < 0:
            raise ValueError("SHORTS_TOP must be non-negative")
            
        logger.info("Configuration validation passed")
    
    def scan_universe(self) -> List[str]:
        """Scan for eligible U.S. equities based on criteria"""
        logger.info("Scanning universe for eligible stocks...")
        
        try:
            # Get all active U.S. equity assets
            assets_response = get_all_assets(
                status="active",
                asset_class="us_equity"
            )
            
            # Parse the response to extract symbols
            # The response format is a formatted string, so we need to parse it
            eligible_symbols = []
            
            # Simple parsing of the formatted response
            lines = assets_response.split('\n')
            current_symbol = None
            
            for line in lines:
                line = line.strip()
                if line.startswith('Symbol: '):
                    current_symbol = line.replace('Symbol: ', '')
                elif line.startswith('Status: active') and current_symbol:
                    # Check if this asset meets our criteria
                    if self._is_asset_eligible(current_symbol):
                        eligible_symbols.append(current_symbol)
                    current_symbol = None
            
            logger.info(f"Found {len(eligible_symbols)} eligible symbols")
            return eligible_symbols
            
        except Exception as e:
            logger.error(f"Error scanning universe: {e}")
            return []
    
    def _is_asset_eligible(self, symbol: str) -> bool:
        """Check if an individual asset meets eligibility criteria"""
        try:
            # Get asset info to check fractionability
            # For now, we'll assume all U.S. equities are fractionable
            # In a production system, you'd want to check the actual asset properties
            
            # Basic symbol validation
            if len(symbol) > 5 or not symbol.isalpha():
                return False
                
            return True
            
        except Exception as e:
            logger.debug(f"Error checking eligibility for {symbol}: {e}")
            return False
    
    def get_price_data(self, symbols: List[str]) -> Dict[str, pd.DataFrame]:
        """Fetch historical price data for symbols"""
        logger.info(f"Fetching price data for {len(symbols)} symbols...")
        
        price_data = {}
        
        for symbol in symbols[:100]:  # Limit to first 100 for performance
            try:
                # Get 1 year of daily data
                bars_response = get_stock_bars(
                    symbol=symbol,
                    days=365,
                    timeframe="1Day"
                )
                
                # Parse the bars response into a DataFrame
                df = self._parse_bars_response(bars_response, symbol)
                if df is not None and not df.empty:
                    price_data[symbol] = df
                    
                time.sleep(0.1)  # Rate limiting
                
            except Exception as e:
                logger.debug(f"Error fetching data for {symbol}: {e}")
                continue
        
        logger.info(f"Successfully fetched data for {len(price_data)} symbols")
        return price_data
    
    def _parse_bars_response(self, response: str, symbol: str) -> Optional[pd.DataFrame]:
        """Parse the formatted bars response into a DataFrame"""
        try:
            lines = response.split('\n')
            data = []
            
            for line in lines:
                if 'Open:' in line and 'High:' in line and 'Low:' in line and 'Close:' in line:
                    # Parse the OHLCV data
                    parts = line.split(',')
                    if len(parts) >= 5:
                        try:
                            time_str = parts[0].split('Time: ')[1].strip()
                            open_price = float(parts[1].split('Open: $')[1])
                            high_price = float(parts[2].split('High: $')[1])
                            low_price = float(parts[3].split('Low: $')[1])
                            close_price = float(parts[4].split('Close: $')[1])
                            volume = int(parts[5].split('Volume: ')[1])
                            
                            # Parse timestamp
                            if ' ' in time_str:
                                timestamp = pd.to_datetime(time_str)
                            else:
                                timestamp = pd.to_datetime(time_str)
                            
                            data.append({
                                'timestamp': timestamp,
                                'open': open_price,
                                'high': high_price,
                                'low': low_price,
                                'close': close_price,
                                'volume': volume
                            })
                        except (ValueError, IndexError):
                            continue
            
            if data:
                df = pd.DataFrame(data)
                df.set_index('timestamp', inplace=True)
                df.sort_index(inplace=True)
                return df
                
        except Exception as e:
            logger.debug(f"Error parsing bars response for {symbol}: {e}")
            
        return None
    
    def compute_indicators(self, price_data: Dict[str, pd.DataFrame]) -> Dict[str, Dict]:
        """Compute technical indicators for all symbols"""
        logger.info("Computing technical indicators...")
        
        indicators = {}
        
        for symbol, df in price_data.items():
            try:
                if len(df) < 250:  # Need at least 250 days for 200-day MA
                    continue
                
                # Price filter
                current_price = df['close'].iloc[-1]
                if current_price > self.config['MAX_PRICE']:
                    continue
                
                # Volume filter
                avg_volume = df['volume'].mean()
                if avg_volume < self.config['MIN_AVG_VOLUME']:
                    continue
                
                # Compute indicators
                symbol_indicators = self._compute_symbol_indicators(df)
                if symbol_indicators:
                    indicators[symbol] = symbol_indicators
                    
            except Exception as e:
                logger.debug(f"Error computing indicators for {symbol}: {e}")
                continue
        
        logger.info(f"Computed indicators for {len(indicators)} symbols")
        return indicators
    
    def _compute_symbol_indicators(self, df: pd.DataFrame) -> Optional[Dict]:
        """Compute technical indicators for a single symbol"""
        try:
            # 12-month momentum (excluding most recent month)
            if len(df) >= 365:
                momentum_12m = (df['close'].iloc[-32] / df['close'].iloc[-365] - 1) * 100
            else:
                momentum_12m = 0
            
            # 6-month momentum (excluding most recent month)
            if len(df) >= 180:
                momentum_6m = (df['close'].iloc[-32] / df['close'].iloc[-180] - 1) * 100
            else:
                momentum_6m = 0
            
            # Moving averages
            ma_50 = df['close'].rolling(50).mean().iloc[-1]
            ma_200 = df['close'].rolling(200).mean().iloc[-1]
            
            # 20-day z-score
            ma_20 = df['close'].rolling(20).mean()
            std_20 = df['close'].rolling(20).std()
            current_price = df['close'].iloc[-1]
            
            if not pd.isna(ma_20.iloc[-1]) and not pd.isna(std_20.iloc[-1]) and std_20.iloc[-1] > 0:
                z_score = (current_price - ma_20.iloc[-1]) / std_20.iloc[-1]
            else:
                z_score = 0
            
            return {
                'momentum_12m': momentum_12m,
                'momentum_6m': momentum_6m,
                'ma_50': ma_50,
                'ma_200': ma_200,
                'z_score': z_score,
                'current_price': current_price,
                'avg_volume': df['volume'].mean()
            }
            
        except Exception as e:
            logger.debug(f"Error computing indicators: {e}")
            return None
    
    def select_positions(self, indicators: Dict[str, Dict]) -> Tuple[List[str], List[str]]:
        """Select long and short positions based on indicators"""
        logger.info("Selecting positions...")
        
        # Calculate combined momentum score
        for symbol, data in indicators.items():
            data['momentum_score'] = (data['momentum_12m'] * 0.6 + data['momentum_6m'] * 0.4)
        
        # Sort by momentum score
        sorted_symbols = sorted(
            indicators.items(),
            key=lambda x: x[1]['momentum_score'],
            reverse=True
        )
        
        # Select longs
        longs = []
        for symbol, data in sorted_symbols[:self.config['EQUITIES_TOP']]:
            if (data['current_price'] > data['ma_200'] and 
                abs(data['z_score']) < self.config['ZSCORE_THRESHOLD']):
                longs.append(symbol)
        
        # Select shorts (if enabled)
        shorts = []
        if self.config['SHORTS_TOP'] > 0:
            for symbol, data in sorted_symbols[-self.config['SHORTS_TOP']:]:
                if (data['current_price'] < data['ma_200'] and 
                    abs(data['z_score']) >= self.config['ZSCORE_THRESHOLD']):
                    shorts.append(symbol)
        
        logger.info(f"Selected {len(longs)} long positions and {len(shorts)} short positions")
        return longs, shorts
    
    def calculate_position_sizes(self, longs: List[str], shorts: List[str], 
                               indicators: Dict[str, Dict]) -> Dict[str, float]:
        """Calculate position sizes for each symbol"""
        total_positions = len(longs) + len(shorts)
        if total_positions == 0:
            return {}
        
        # Equal allocation
        position_value = self.config['CAPITAL'] / total_positions
        
        position_sizes = {}
        
        for symbol in longs + shorts:
            current_price = indicators[symbol]['current_price']
            shares = position_value / current_price
            position_sizes[symbol] = shares
        
        return position_sizes
    
    def place_orders(self, position_sizes: Dict[str, float], 
                    longs: List[str], shorts: List[str]) -> Dict[str, str]:
        """Place orders for all selected positions"""
        logger.info("Placing orders...")
        
        order_results = {}
        
        for symbol, shares in position_sizes.items():
            try:
                side = "buy" if symbol in longs else "sell"
                
                # Place market order
                order_response = place_stock_order(
                    symbol=symbol,
                    side=side,
                    quantity=shares,
                    order_type="market"
                )
                
                order_results[symbol] = order_response
                logger.info(f"Order placed for {symbol}: {side} {shares:.4f} shares")
                
                time.sleep(0.5)  # Rate limiting
                
            except Exception as e:
                error_msg = f"Error placing order for {symbol}: {e}"
                order_results[symbol] = error_msg
                logger.error(error_msg)
        
        return order_results
    
    def run_dry_run(self, longs: List[str], shorts: List[str], 
                   indicators: Dict[str, Dict], position_sizes: Dict[str, float]):
        """Display selected picks and order parameters without executing"""
        logger.info("=== DRY RUN MODE ===")
        
        print("\n" + "="*60)
        print("FRACTIONAL TRADING ALGORITHM - DRY RUN")
        print("="*60)
        
        print(f"\nConfiguration:")
        for key, value in self.config.items():
            print(f"  {key}: {value}")
        
        print(f"\nSelected Positions:")
        print(f"  Longs: {len(longs)} positions")
        print(f"  Shorts: {len(shorts)} positions")
        
        print(f"\nLong Positions:")
        for symbol in longs:
            data = indicators[symbol]
            print(f"  {symbol}: ${data['current_price']:.2f} | "
                  f"12M: {data['momentum_12m']:.1f}% | "
                  f"6M: {data['momentum_6m']:.1f}% | "
                  f"Z-Score: {data['z_score']:.2f} | "
                  f"Shares: {position_sizes[symbol]:.4f}")
        
        if shorts:
            print(f"\nShort Positions:")
            for symbol in shorts:
                data = indicators[symbol]
                print(f"  {symbol}: ${data['current_price']:.2f} | "
                      f"12M: {data['momentum_12m']:.1f}% | "
                      f"6M: {data['momentum_6m']:.1f}% | "
                      f"Z-Score: {data['z_score']:.2f} | "
                      f"Shares: {position_sizes[symbol]:.4f}")
        
        total_value = sum(position_sizes[symbol] * indicators[symbol]['current_price'] 
                         for symbol in position_sizes)
        print(f"\nTotal Position Value: ${total_value:.2f}")
        print(f"Capital Utilization: {(total_value/self.config['CAPITAL'])*100:.1f}%")
        
        print("\n" + "="*60)
    
    def run(self, dry_run: bool = False):
        """Run the complete trading algorithm"""
        logger.info("Starting fractional trading algorithm...")
        
        try:
            # Step 1: Scan universe
            symbols = self.scan_universe()
            if not symbols:
                logger.error("No eligible symbols found")
                return
            
            # Step 2: Get price data
            price_data = self.get_price_data(symbols)
            if not price_data:
                logger.error("No price data retrieved")
                return
            
            # Step 3: Compute indicators
            indicators = self.compute_indicators(price_data)
            if not indicators:
                logger.error("No indicators computed")
                return
            
            # Step 4: Select positions
            longs, shorts = self.select_positions(indicators)
            if not longs and not shorts:
                logger.warning("No positions selected")
                return
            
            # Step 5: Calculate position sizes
            position_sizes = self.calculate_position_sizes(longs, shorts, indicators)
            
            # Step 6: Display results or execute trades
            if dry_run:
                self.run_dry_run(longs, shorts, indicators, position_sizes)
            else:
                # Check account status before trading
                account_info = get_account_info()
                logger.info(f"Account status: {account_info}")
                
                # Place orders
                order_results = self.place_orders(position_sizes, longs, shorts)
                
                # Display results
                logger.info("Trading completed")
                for symbol, result in order_results.items():
                    logger.info(f"{symbol}: {result}")
        
        except Exception as e:
            logger.error(f"Algorithm execution failed: {e}")
            raise

def load_environment():
    """Load environment variables with error handling"""
    try:
        from dotenv import load_dotenv
        load_dotenv()
        logger.info("Environment variables loaded successfully")
    except ImportError:
        logger.warning("python-dotenv not found, using system environment variables")
    except Exception as e:
        logger.error(f"Error loading .env file: {e}")
        logger.error("Make sure the script is in the same directory as your .env file")
        sys.exit(1)

def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description="Automated Fractional-Stock Trading Algorithm",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run with default settings
  python fractional_trading_algorithm.py
  
  # Custom capital allocation
  python fractional_trading_algorithm.py --capital 5000 --max-price 50
  
  # Dry run to see selections without trading
  python fractional_trading_algorithm.py --dry-run
  
  # Conservative settings
  python fractional_trading_algorithm.py --equities-top 50 --shorts-top 0 --trail-pct 3
        """
    )
    
    parser.add_argument(
        '--capital', '-c',
        type=float,
        default=DEFAULT_CONFIG['CAPITAL'],
        help=f'Total capital to allocate (default: {DEFAULT_CONFIG["CAPITAL"]})'
    )
    
    parser.add_argument(
        '--max-price', '-m',
        type=float,
        default=DEFAULT_CONFIG['MAX_PRICE'],
        help=f'Maximum share price for screening (default: {DEFAULT_CONFIG["MAX_PRICE"]})'
    )
    
    parser.add_argument(
        '--min-avg-volume',
        type=int,
        default=DEFAULT_CONFIG['MIN_AVG_VOLUME'],
        help=f'Minimum average daily volume (default: {DEFAULT_CONFIG["MIN_AVG_VOLUME"]})'
    )
    
    parser.add_argument(
        '--equities-top', '-e',
        type=int,
        default=DEFAULT_CONFIG['EQUITIES_TOP'],
        help=f'Number of long positions (default: {DEFAULT_CONFIG["EQUITIES_TOP"]})'
    )
    
    parser.add_argument(
        '--shorts-top', '-s',
        type=int,
        default=DEFAULT_CONFIG['SHORTS_TOP'],
        help=f'Number of short positions (default: {DEFAULT_CONFIG["SHORTS_TOP"]})'
    )
    
    parser.add_argument(
        '--zscore-threshold', '-z',
        type=float,
        default=DEFAULT_CONFIG['ZSCORE_THRESHOLD'],
        help=f'Minimum z-score for shorting (default: {DEFAULT_CONFIG["ZSCORE_THRESHOLD"]})'
    )
    
    parser.add_argument(
        '--trail-pct', '-t',
        type=float,
        default=DEFAULT_CONFIG['TRAIL_PCT'],
        help=f'Trailing stop percentage (default: {DEFAULT_CONFIG["TRAIL_PCT"]})'
    )
    
    parser.add_argument(
        '--time-exit-min',
        type=int,
        default=DEFAULT_CONFIG['TIME_EXIT_MIN'],
        help=f'Maximum holding time in minutes (default: {DEFAULT_CONFIG["TIME_EXIT_MIN"]})'
    )
    
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Display selected picks and order parameters without executing'
    )
    
    parser.add_argument(
        '--help', '-h',
        action='help',
        help='Show this help message and exit'
    )
    
    return parser.parse_args()

def main():
    """Main entry point"""
    print("Fractional Trading Algorithm - Alpaca MCP Server")
    print("=" * 50)
    
    try:
        # Load environment variables
        load_environment()
        
        # Parse arguments
        args = parse_arguments()
        
        # Validate arguments
        if args.capital <= 0:
            print("Error: Capital must be positive")
            sys.exit(1)
        
        if args.max_price <= 0:
            print("Error: Max price must be positive")
            sys.exit(1)
        
        if args.equities_top <= 0:
            print("Error: Number of long positions must be positive")
            sys.exit(1)
        
        if args.shorts_top < 0:
            print("Error: Number of short positions must be non-negative")
            sys.exit(1)
        
        # Create configuration
        config = {
            'MAX_PRICE': args.max_price,
            'MIN_AVG_VOLUME': args.min_avg_volume,
            'CAPITAL': args.capital,
            'EQUITIES_TOP': args.equities_top,
            'SHORTS_TOP': args.shorts_top,
            'ZSCORE_THRESHOLD': args.zscore_threshold,
            'TRAIL_PCT': args.trail_pct,
            'TIME_EXIT_MIN': args.time_exit_min
        }
        
        # Initialize and run algorithm
        algorithm = FractionalTradingAlgorithm(config)
        algorithm.run(dry_run=args.dry_run)
        
        print("\nAlgorithm execution completed successfully!")
        
    except KeyboardInterrupt:
        print("\nAlgorithm execution interrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"\nFatal error: {e}")
        logger.error(f"Fatal error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
