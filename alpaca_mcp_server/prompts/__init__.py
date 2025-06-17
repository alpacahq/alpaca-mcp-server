"""Prompts module for Alpaca MCP Server - Guided trading workflows."""

# Import all prompt modules
from .list_trading_capabilities import list_trading_capabilities
from .account_analysis_prompt import account_analysis
from .position_management_prompt import position_management
from .market_analysis_prompt import market_analysis
from .startup_prompt import startup
from .scan_prompt import scan

__all__ = [
    "list_trading_capabilities",
    "account_analysis",
    "position_management",
    "market_analysis",
    "startup",
    "scan",
]

# Day trading workflow - complete agentic trading analysis
from .day_trading_workflow import day_trading_workflow
from .master_scanning_workflow import master_scanning_workflow
from .pro_technical_workflow import pro_technical_workflow
from .market_session_workflow import market_session_workflow
from .stream_centric_trading_prompt import stream_centric_trading_cycle, stream_concurrent_monitoring_cycle

__all__.extend(
    [
        "day_trading_workflow",
        "master_scanning_workflow",
        "pro_technical_workflow", 
        "market_session_workflow",
        "stream_centric_trading_cycle",
        "stream_concurrent_monitoring_cycle",
    ]
)
