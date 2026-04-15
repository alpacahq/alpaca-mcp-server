"""
CLI entry point for the Alpaca MCP Server.
"""

import os
import sys
from pathlib import Path
from typing import Optional

import click

from . import __version__

# Older Docker/Helm configs invoked `alpaca-mcp-server serve ...`; the CLI has no subcommands.
if len(sys.argv) > 1 and sys.argv[1] == "serve":
    sys.argv.pop(1)


def _default_port() -> int:
    """HTTP bind port; honors Render/Fly-style ``PORT`` when ``--port`` is omitted."""
    return int(os.environ.get("PORT", "8000"))


@click.command()
@click.version_option(version=__version__, prog_name="alpaca-mcp-server")
@click.option(
    "--transport",
    type=click.Choice(["stdio", "streamable-http", "sse"]),
    default="stdio",
    help="Transport protocol (default: stdio)",
)
@click.option("--host", default="127.0.0.1", help="Host to bind (HTTP transport only)")
@click.option(
    "--port",
    type=int,
    default=_default_port,
    help="Port to bind (HTTP transport only; defaults to $PORT or 8000)",
)
@click.option(
    "--env-file",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help="Load environment variables from this file before starting",
)
def main(transport: str, host: str, port: int, env_file: Optional[Path]):
    """Alpaca MCP Server — Trading API integration for Model Context Protocol."""
    if env_file is not None:
        from dotenv import load_dotenv

        load_dotenv(env_file, override=False)

    if not os.environ.get("ALPACA_API_KEY") or not os.environ.get("ALPACA_SECRET_KEY"):
        click.echo(
            "Error: ALPACA_API_KEY and ALPACA_SECRET_KEY must be set.\n"
            "Set them in your MCP client config's env block or pass --env-file.",
            err=True,
        )
        sys.exit(1)

    from .server import build_server

    server = build_server()

    if transport == "stdio":
        server.run(transport="stdio")
    else:
        server.run(transport=transport, host=host, port=port)
