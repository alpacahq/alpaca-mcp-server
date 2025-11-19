# cli.py
#
# Command Line Interface for Alpaca MCP Server
# Location: /src/alpaca_mcp_server/cli.py
# Purpose: Provides the 'alpaca-mcp' command with init and serve subcommands

import sys
from pathlib import Path
from typing import Optional

import click

# Import our server and configuration classes
from .server import AlpacaMCPServer
from .config import ConfigManager
from . import __version__


@click.group()
@click.version_option(version=__version__, prog_name="alpaca-mcp")
def main():
    """
    Alpaca MCP Server - Trading API integration for Model Context Protocol.

    A comprehensive MCP server for Alpaca's Trading API, enabling natural language
    trading operations through AI assistants like Claude Desktop and Cursor.

    Features:
    - Stock, ETF, options, and crypto trading
    - Portfolio management and account information
    - Real-time market data and historical data
    - Watchlist management and corporate actions

    Get started:
        alpaca-mcp init     # Configure API keys
        alpaca-mcp serve    # Start the server
    """
    pass


@main.command()
@click.option(
    '--api-key',
    help='WARNING: do not pass sensitive keys on the command line; will prompt if omitted'
)
@click.option(
    '--secret-key',
    help='WARNING: do not pass sensitive keys on the command line; will prompt if omitted'
)
@click.option(
    '--paper/--live',
    default=True,
    help='Use paper trading (default) or live trading'
)
@click.option(
    '--config-file',
    type=click.Path(path_type=Path),
    help='Path to .env configuration file (default: .env in current directory)'
)
def init(api_key: Optional[str], secret_key: Optional[str],
         paper: bool, config_file: Optional[Path]):
    """
    Initialize Alpaca MCP server configuration.

    This command creates or updates a .env file with your Alpaca API credentials
    and trading configuration. API keys can be provided as options or entered
    interactively when prompted.

    SECURITY WARNING: Passing API keys as command-line arguments (--api-key, --secret-key)
    is insecure. Command-line arguments are recorded in shell history and visible in process
    listings. For secure credential handling, omit these options to use the interactive prompt,
    or set the ALPACA_API_KEY and ALPACA_SECRET_KEY environment variables.

    Examples:
        alpaca-mcp init                     # Interactive configuration
        alpaca-mcp init --paper             # Force paper trading mode
        alpaca-mcp init --live              # Enable live trading mode
        alpaca-mcp init --config-file ~/my.env  # Use custom config file
    """
    try:
        # Initialize configuration manager
        config = ConfigManager(config_file)

        # Display header
        click.echo("Alpaca MCP Server Configuration")
        click.echo("=" * 40)

        # Show current configuration if it exists
        if config.env_file.exists():
            click.echo(f"Updating existing configuration: {config.env_file}")
            click.echo()
            click.echo("Current configuration:")
            click.echo(config.get_config_summary())
            click.echo()
        else:
            click.echo(f"Creating new configuration: {config.env_file}")
            click.echo()

        # Set up the .env file with interactive prompts
        success = config.setup_env_file(
            api_key=api_key,
            secret_key=secret_key,
            paper_trade=paper
        )

        if success:
            click.echo()
            click.echo("Configuration completed successfully!")
            click.echo()
            click.echo("Next steps:")
            click.echo("1. Start the server: alpaca-mcp serve")
            click.echo("2. Configure your MCP client (Claude Desktop, Cursor, etc.)")
            click.echo("3. Test with: 'What is my Alpaca account balance?'")
            click.echo()
            click.echo("Tip: Run 'alpaca-mcp serve --help' for server options")
        else:
            click.echo("Error: Configuration failed. Please try again.")
            sys.exit(1)

    except Exception as e:
        click.echo(f"Error during initialization: {e}")
        sys.exit(1)


@main.command()
@click.option(
    '--transport',
    type=click.Choice(['stdio', 'streamable-http']),
    default='stdio',
    help='Transport method: stdio or streamable-http (default: stdio)'
)
@click.option(
    '--host',
    default='127.0.0.1',
    help='Host to bind for streamable-http transport (default: 127.0.0.1)'
)
@click.option(
    '--port',
    type=int,
    default=8000,
    help='Port to bind for streamable-http transport (default: 8000)'
)
@click.option(
    '--config-file',
    type=click.Path(path_type=Path),
    help='Path to .env configuration file (default: .env in current directory)'
)
def serve(transport: str, host: str, port: int, config_file: Optional[Path]):
    """
    Start the Alpaca MCP server.

    This command starts the MCP server with the specified transport method.
    The server will load configuration from the .env file and connect to
    Alpaca's Trading API.

    Transport methods:
        stdio: Standard input/output (default, for MCP clients)
        streamable-http: HTTP transport for remote connections

    Examples:
        alpaca-mcp serve                           # Start with stdio transport
        alpaca-mcp serve --transport streamable-http          # Start HTTP server
        alpaca-mcp serve --transport streamable-http --port 9000  # Custom port
        alpaca-mcp serve --config-file ~/trading.env   # Custom config
    """
    try:
        # Determine configuration source (env file or environment variables)
        config_path = config_file or Path(".env")
        config = ConfigManager(config_path)
        using_env_only = not config_path.exists()

        # Validate configuration
        if not config.validate_config():
            click.echo("Error: No Alpaca API credentials found.")
            click.echo()
            if using_env_only:
                click.echo("Provide credentials via environment variables:")
                click.echo("   ALPACA_API_KEY=your_key_here")
                click.echo("   ALPACA_SECRET_KEY=your_secret_here")
                click.echo()
                click.echo("Or run 'alpaca-mcp init' to create a .env file.")
            else:
                click.echo(config.get_config_summary())
                click.echo()
                click.echo("Update the credentials above or export them as environment variables.")
            sys.exit(1)
        # Display startup information (unless in stdio mode for MCP clients)
        if transport != "stdio":
            click.echo("Starting Alpaca MCP Server")
            click.echo(f"   Transport: {transport}")
            source_hint = "environment variables" if using_env_only else config_path
            click.echo(f"   Config: {source_hint}")
            if transport == "streamable-http":
                click.echo(f"   URL: http://{host}:{port}")
            click.echo()

        # Initialize and start the server
        server = AlpacaMCPServer(config_path)
        server.run(transport=transport, host=host, port=port)

    except KeyboardInterrupt:
        click.echo("\nServer stopped by user")
    except Exception as e:
        click.echo(f"Server error: {e}")
        # Show helpful error messages for common issues
        if "credentials not found" in str(e).lower():
            click.echo()
            click.echo("Make sure your .env file contains valid API keys:")
            click.echo("   ALPACA_API_KEY=your_key_here")
            click.echo("   ALPACA_SECRET_KEY=your_secret_here")
            click.echo()
            click.echo("   Run 'alpaca-mcp init' to configure.")
        sys.exit(1)


@main.command()
@click.option(
    '--config-file',
    type=click.Path(path_type=Path),
    help='Path to .env configuration file (default: .env in current directory)'
)
def status(config_file: Optional[Path]):
    """
    Show current server configuration and status.

    Displays information about the current configuration file,
    API key status, and server readiness.
    """
    try:
        # Initialize configuration manager
        config = ConfigManager(config_file)

        click.echo("Alpaca MCP Server Status")
        click.echo("=" * 35)
        click.echo()

        # Show configuration summary
        click.echo(config.get_config_summary())
        click.echo()

        # Show validation status
        if config.validate_config():
            click.echo("Configuration is valid - server ready to start")
            click.echo()
            click.echo("Start server: alpaca-mcp serve")
        else:
            click.echo("Configuration is incomplete")
            click.echo()
            click.echo("Fix configuration: alpaca-mcp init")

    except Exception as e:
        click.echo(f"Error checking status: {e}")
        sys.exit(1)


# Entry point for console script
if __name__ == "__main__":
    main()