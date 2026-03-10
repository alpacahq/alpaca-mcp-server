"""
CLI entry point for the Alpaca MCP Server.
"""

from pathlib import Path
from typing import Optional

import click

from . import __version__


@click.group()
@click.version_option(version=__version__, prog_name="alpaca-mcp-server")
def main():
    """Alpaca MCP Server — Trading API integration for Model Context Protocol."""
    pass


@main.command()
@click.option(
    "--transport",
    type=click.Choice(["stdio", "streamable-http"]),
    default="stdio",
    help="Transport method (default: stdio)",
)
@click.option("--host", default="127.0.0.1", help="Host to bind (HTTP transport only)")
@click.option("--port", type=int, default=8000, help="Port to bind (HTTP transport only)")
@click.option(
    "--env-file",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help="Path to .env file for credentials (optional, never reads .env implicitly)",
)
def serve(transport: str, host: str, port: int, env_file: Optional[Path]):
    """Start the Alpaca MCP server."""
    if env_file is not None:
        from dotenv import load_dotenv

        load_dotenv(env_file, override=False)

    from .server import build_server

    server = build_server()

    if transport == "stdio":
        server.run(transport="stdio")
    else:
        server.run(transport="streamable-http", host=host, port=port)
