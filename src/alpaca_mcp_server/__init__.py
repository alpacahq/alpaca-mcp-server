# __init__.py
#
# Alpaca MCP Server Package Initialization
# Location: /src/alpaca_mcp_server/__init__.py
# Purpose: Package initialization and version information for the Alpaca MCP Server

"""
Alpaca MCP Server - Trading API Integration for Model Context Protocol

This package provides a comprehensive MCP server implementation for Alpaca
Trading API, enabling natural language trading operations through AI assistants.

Key Features:
- Stock, ETF, options, and crypto trading
- Portfolio management and account information
- Real-time market data and historical data
- Watchlist management
- Corporate actions and market calendar
"""

# Package version (should match pyproject.toml)
__version__ = "1.0.9"

# Package metadata
__author__ = "Alpaca"
__license__ = "MIT"
__description__ = "Alpaca Trading API integration for Model Context Protocol (MCP)"

# Export version information
__all__ = ["__version__"]