#!/usr/bin/env python3
"""
Simple Test Script for the Fractional Trading Algorithm

This script tests the basic functionality without requiring
actual Alpaca API access or real market data.
"""

import sys
import os
import unittest
from unittest.mock import Mock, patch, MagicMock
import pandas as pd
import numpy as np

# Add the current directory to the path so we can import our module
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fractional_trading_algorithm import FractionalTradingAlgorithm

class TestFractionalTradingAlgorithm(unittest.TestCase):
    """Test cases for the FractionalTradingAlgorithm class"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.config = {
            'MAX_PRICE': 25.0,
            'MIN_AVG_VOLUME': 250000,
            'CAPITAL': 2000.0,
            'EQUITIES_TOP': 75,
            'SHORTS_TOP': 10,
            'ZSCORE_THRESHOLD': 1.5,
            'TRAIL_PCT': 5.0,
            'TIME_EXIT_MIN': 2880
        }
        self.algorithm = FractionalTradingAlgorithm(self.config)
    
    def test_config_validation(self):
        """Test configuration validation"""
        # Test valid config
        self.algorithm.validate_config()
        
        # Test invalid config
        invalid_config = self.config.copy()
        invalid_config['CAPITAL'] = -1000
        
        with self.assertRaises(ValueError):
            invalid_algorithm = FractionalTradingAlgorithm(invalid_config)
    
    def test_asset_eligibility(self):
        """Test asset eligibility checking"""
        # Test valid symbols
        self.assertTrue(self.algorithm._is_asset_eligible('AAPL'))
        self.assertTrue(self.algorithm._is_asset_eligible('MSFT'))
        
        # Test invalid symbols
        self.assertFalse(self.algorithm._is_asset_eligible('AAPL123'))
        self.assertFalse(self.algorithm._is_asset_eligible('123'))
        self.assertFalse(self.algorithm._is_asset_eligible(''))
    
    def test_compute_symbol_indicators(self):
        """Test technical indicator computation"""
        # Create sample price data
        dates = pd.date_range('2023-01-01', periods=365, freq='D')
        prices = np.linspace(20, 25, 365) + np.random.normal(0, 0.5, 365)
        volumes = np.random.randint(100000, 1000000, 365)
        
        df = pd.DataFrame({
            'close': prices,
            'volume': volumes
        }, index=dates)
        
        # Compute indicators
        indicators = self.algorithm._compute_symbol_indicators(df)
        
        # Verify indicators exist
        self.assertIsNotNone(indicators)
        self.assertIn('momentum_12m', indicators)
        self.assertIn('momentum_6m', indicators)
        self.assertIn('ma_50', indicators)
        self.assertIn('ma_200', indicators)
        self.assertIn('z_score', indicators)
        self.assertIn('current_price', indicators)
        self.assertIn('avg_volume', indicators)
        
        # Verify data types
        self.assertIsInstance(indicators['momentum_12m'], (int, float))
        self.assertIsInstance(indicators['momentum_6m'], (int, float))
        self.assertIsInstance(indicators['ma_50'], (int, float))
        self.assertIsInstance(indicators['ma_200'], (int, float))
        self.assertIsInstance(indicators['z_score'], (int, float))
        self.assertIsInstance(indicators['current_price'], (int, float))
        self.assertIsInstance(indicators['avg_volume'], (int, float))
    
    def test_position_selection(self):
        """Test position selection logic"""
        # Create sample indicators data
        indicators = {
            'AAPL': {
                'momentum_12m': 15.0,
                'momentum_6m': 8.0,
                'ma_50': 22.0,
                'ma_200': 20.0,
                'z_score': 0.5,
                'current_price': 24.0,
                'avg_volume': 300000
            },
            'MSFT': {
                'momentum_12m': 12.0,
                'momentum_6m': 6.0,
                'ma_50': 23.0,
                'ma_200': 21.0,
                'z_score': 0.3,
                'current_price': 25.0,
                'avg_volume': 400000
            },
            'XYZ': {
                'momentum_12m': -10.0,
                'momentum_6m': -5.0,
                'ma_50': 18.0,
                'ma_200': 22.0,
                'z_score': 2.0,
                'current_price': 17.0,
                'avg_volume': 250000
            }
        }
        
        # Test position selection
        longs, shorts = self.algorithm.select_positions(indicators)
        
        # Verify results
        self.assertIsInstance(longs, list)
        self.assertIsInstance(shorts, list)
        
        # AAPL and MSFT should be selected as longs (above 200-day MA, low z-score)
        self.assertIn('AAPL', longs)
        self.assertIn('MSFT', longs)
        
        # XYZ should be selected as short (below 200-day MA, high z-score)
        self.assertIn('XYZ', shorts)
    
    def test_position_sizing(self):
        """Test position size calculation"""
        longs = ['AAPL', 'MSFT']
        shorts = ['XYZ']
        indicators = {
            'AAPL': {'current_price': 24.0},
            'MSFT': {'current_price': 25.0},
            'XYZ': {'current_price': 17.0}
        }
        
        position_sizes = self.algorithm.calculate_position_sizes(longs, shorts, indicators)
        
        # Verify all symbols have position sizes
        self.assertIn('AAPL', position_sizes)
        self.assertIn('MSFT', position_sizes)
        self.assertIn('XYZ', position_sizes)
        
        # Verify position sizes are positive
        for symbol, size in position_sizes.items():
            self.assertGreater(size, 0)
        
        # Verify total allocation equals capital
        total_value = sum(position_sizes[symbol] * indicators[symbol]['current_price'] 
                         for symbol in position_sizes)
        self.assertAlmostEqual(total_value, self.config['CAPITAL'], places=2)
    
    def test_parse_bars_response(self):
        """Test parsing of bars response"""
        # Sample response format from the MCP server
        sample_response = """
Historical Data for AAPL (1Day bars, 2023-01-01 00:00 to 2024-01-01 00:00):
---------------------------------------------------
Time: 2023-01-01, Open: $20.50, High: $21.20, Low: $20.30, Close: $21.00, Volume: 500000
Time: 2023-01-02, Open: $21.00, High: $21.80, Low: $20.90, Close: $21.50, Volume: 600000
Time: 2023-01-03, Open: $21.50, High: $22.10, Low: $21.40, Close: $21.90, Volume: 550000
        """
        
        df = self.algorithm._parse_bars_response(sample_response, 'AAPL')
        
        # Verify DataFrame was created
        self.assertIsNotNone(df)
        self.assertIsInstance(df, pd.DataFrame)
        self.assertFalse(df.empty)
        
        # Verify columns exist
        expected_columns = ['open', 'high', 'low', 'close', 'volume']
        for col in expected_columns:
            self.assertIn(col, df.columns)
        
        # Verify data was parsed correctly
        self.assertEqual(len(df), 3)  # 3 days of data
        self.assertEqual(df['close'].iloc[0], 21.00)
        self.assertEqual(df['volume'].iloc[1], 600000)

def run_tests():
    """Run all tests"""
    print("Running Fractional Trading Algorithm Tests...")
    print("=" * 50)
    
    # Create test suite
    suite = unittest.TestLoader().loadTestsFromTestCase(TestFractionalTradingAlgorithm)
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Print summary
    print("\n" + "=" * 50)
    if result.wasSuccessful():
        print("✅ All tests passed successfully!")
    else:
        print("❌ Some tests failed!")
        print(f"Failures: {len(result.failures)}")
        print(f"Errors: {len(result.errors)}")
    
    return result.wasSuccessful()

if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
