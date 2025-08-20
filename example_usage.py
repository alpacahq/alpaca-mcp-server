#!/usr/bin/env python3
"""
Example Usage of the Fractional Trading Algorithm

This script demonstrates how to use the FractionalTradingAlgorithm class
programmatically with different configurations.
"""

from fractional_trading_algorithm import FractionalTradingAlgorithm, load_environment
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def example_conservative_strategy():
    """Example of a conservative trading strategy"""
    print("\n=== CONSERVATIVE STRATEGY EXAMPLE ===")
    
    config = {
        'MAX_PRICE': 20.0,           # Lower price threshold
        'MIN_AVG_VOLUME': 500000,    # Higher volume requirement
        'CAPITAL': 1000.0,           # Smaller capital allocation
        'EQUITIES_TOP': 25,          # Fewer long positions
        'SHORTS_TOP': 0,             # No short positions
        'ZSCORE_THRESHOLD': 2.0,     # Higher z-score threshold
        'TRAIL_PCT': 3.0,            # Tighter trailing stop
        'TIME_EXIT_MIN': 1440        # Shorter holding time (1 day)
    }
    
    algorithm = FractionalTradingAlgorithm(config)
    algorithm.run(dry_run=True)

def example_aggressive_strategy():
    """Example of an aggressive trading strategy"""
    print("\n=== AGGRESSIVE STRATEGY EXAMPLE ===")
    
    config = {
        'MAX_PRICE': 50.0,           # Higher price threshold
        'MIN_AVG_VOLUME': 100000,    # Lower volume requirement
        'CAPITAL': 5000.0,           # Larger capital allocation
        'EQUITIES_TOP': 100,         # More long positions
        'SHORTS_TOP': 25,            # More short positions
        'ZSCORE_THRESHOLD': 1.0,     # Lower z-score threshold
        'TRAIL_PCT': 8.0,            # Wider trailing stop
        'TIME_EXIT_MIN': 5760        # Longer holding time (4 days)
    }
    
    algorithm = FractionalTradingAlgorithm(config)
    algorithm.run(dry_run=True)

def example_balanced_strategy():
    """Example of a balanced trading strategy"""
    print("\n=== BALANCED STRATEGY EXAMPLE ===")
    
    config = {
        'MAX_PRICE': 30.0,           # Moderate price threshold
        'MIN_AVG_VOLUME': 300000,    # Moderate volume requirement
        'CAPITAL': 3000.0,           # Moderate capital allocation
        'EQUITIES_TOP': 60,          # Moderate number of long positions
        'SHORTS_TOP': 15,            # Moderate number of short positions
        'ZSCORE_THRESHOLD': 1.5,     # Standard z-score threshold
        'TRAIL_PCT': 5.0,            # Standard trailing stop
        'TIME_EXIT_MIN': 2880        # Standard holding time (2 days)
    }
    
    algorithm = FractionalTradingAlgorithm(config)
    algorithm.run(dry_run=True)

def example_sector_focused():
    """Example of a sector-focused strategy with tighter controls"""
    print("\n=== SECTOR-FOCUSED STRATEGY EXAMPLE ===")
    
    config = {
        'MAX_PRICE': 15.0,           # Focus on lower-priced stocks
        'MIN_AVG_VOLUME': 750000,    # High volume requirement for liquidity
        'CAPITAL': 1500.0,           # Moderate capital allocation
        'EQUITIES_TOP': 40,          # Focused selection
        'SHORTS_TOP': 5,             # Limited short exposure
        'ZSCORE_THRESHOLD': 1.8,     # Higher threshold for quality
        'TRAIL_PCT': 4.0,            # Tighter risk control
        'TIME_EXIT_MIN': 2160        # Shorter holding time
    }
    
    algorithm = FractionalTradingAlgorithm(config)
    algorithm.run(dry_run=True)

def main():
    """Main function to run all examples"""
    print("Fractional Trading Algorithm - Example Usage")
    print("=" * 50)
    
    try:
        # Load environment variables
        load_environment()
        print("Environment loaded successfully")
        
        # Run different strategy examples
        example_conservative_strategy()
        example_balanced_strategy()
        example_aggressive_strategy()
        example_sector_focused()
        
        print("\n" + "=" * 50)
        print("All examples completed successfully!")
        print("\nTo run with actual trading (not dry run):")
        print("1. Modify the config in any example function")
        print("2. Change dry_run=True to dry_run=False")
        print("3. Ensure your Alpaca account has sufficient funds")
        print("4. Test with small amounts first!")
        
    except Exception as e:
        logger.error(f"Example execution failed: {e}")
        print(f"\nError running examples: {e}")

if __name__ == "__main__":
    main()
