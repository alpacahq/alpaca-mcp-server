"""
CLI entry point for the Alpaca MCP Server.
"""

import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Literal

import click

from . import __version__

Transport = Literal["stdio", "streamable-http", "sse"]
_IMPLICIT_OR_WILDCARD_BIND_HOSTS = frozenset(
    {"", "*", "0.0.0.0", "::", "127.0.0.1", "localhost", "::1"}
)

# Older Docker/Helm configs invoked `alpaca-mcp-server serve ...`; the CLI has no subcommands.
if len(sys.argv) > 1 and sys.argv[1] == "serve":
    sys.argv.pop(1)


def _default_port() -> int:
    """HTTP bind port; honors Render/Fly-style ``PORT`` when ``--port`` is omitted."""
    return int(os.environ.get("PORT", "8000"))


def _parse_env_allowlist(var_name: str) -> list[str] | None:
    """Parse a JSON array or comma-separated allowlist env var and normalize it for FastMCP."""
    raw = os.environ.get(var_name)
    if raw is None:
        return None

    stripped = raw.strip()
    if not stripped:
        os.environ[var_name] = "[]"
        return None

    if stripped.startswith("["):
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise click.ClickException(
                f"Invalid {var_name}: expected a JSON array of strings or comma-separated values."
            ) from exc
        if not isinstance(parsed, list) or not all(isinstance(item, str) for item in parsed):
            raise click.ClickException(
                f"Invalid {var_name}: expected a JSON array of strings."
            )
        items = [item.strip() for item in parsed if item.strip()]
        return items or None

    items = [item.strip() for item in stripped.split(",") if item.strip()]
    os.environ[var_name] = json.dumps(items)
    return items or None


for _allowlist_env_var in ("FASTMCP_HTTP_ALLOWED_HOSTS", "FASTMCP_HTTP_ALLOWED_ORIGINS"):
    _raw_env_val = os.environ.get(_allowlist_env_var)
    if _raw_env_val is not None and not _raw_env_val.strip().startswith("["):
        _normalized_items = [
            _part.strip() for _part in _raw_env_val.split(",") if _part.strip()
        ]
        os.environ[_allowlist_env_var] = json.dumps(_normalized_items)


def _is_implicit_or_wildcard_bind_host(host: str) -> bool:
    """Return True for wildcard bind addresses or default loopback hosts."""
    normalized = host.strip().lower().strip("[]")
    return normalized in _IMPLICIT_OR_WILDCARD_BIND_HOSTS


def _merge_allowlist(*sources: Sequence[str] | None) -> list[str] | None:
    """Combine allowlist entries in order without duplicates."""
    merged: dict[str, None] = {}
    for source in sources:
        if not source:
            continue
        for entry in source:
            cleaned = entry.strip()
            if cleaned:
                merged.setdefault(cleaned, None)
    return list(merged) or None


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
    "--allowed-host",
    "allowed_hosts",
    multiple=True,
    help="Additional Host header value to trust for HTTP transports (repeatable)",
)
@click.option(
    "--allowed-origin",
    "allowed_origins",
    multiple=True,
    help="Additional Origin header value to trust for HTTP transports (repeatable)",
)
@click.option(
    "--env-file",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help="Load environment variables from this file before starting",
)
def main(
    transport: Transport,
    host: str,
    port: int,
    allowed_hosts: tuple[str, ...],
    allowed_origins: tuple[str, ...],
    env_file: Path | None,
) -> None:
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

    env_allowed_hosts = _parse_env_allowlist("FASTMCP_HTTP_ALLOWED_HOSTS")
    env_allowed_origins = _parse_env_allowlist("FASTMCP_HTTP_ALLOWED_ORIGINS")

    from .server import build_server

    server = build_server()

    if transport == "stdio":
        server.run(transport="stdio")
        return

    import fastmcp

    configured_hosts = (
        env_allowed_hosts
        if env_allowed_hosts is not None
        else fastmcp.settings.http_allowed_hosts
    )
    configured_origins = (
        env_allowed_origins
        if env_allowed_origins is not None
        else fastmcp.settings.http_allowed_origins
    )
    bound_host_allowlist = (
        [host.strip()] if not _is_implicit_or_wildcard_bind_host(host) else None
    )
    resolved_allowed_hosts = _merge_allowlist(
        configured_hosts,
        allowed_hosts,
        bound_host_allowlist,
    )
    resolved_allowed_origins = _merge_allowlist(
        configured_origins,
        allowed_origins,
    )

    if transport == "streamable-http":
        run_kwargs: dict[str, Any] = {
            "transport": transport,
            "host": host,
            "port": port,
            "host_origin_protection": True,
        }
        if resolved_allowed_hosts is not None:
            run_kwargs["allowed_hosts"] = resolved_allowed_hosts
        if resolved_allowed_origins is not None:
            run_kwargs["allowed_origins"] = resolved_allowed_origins
        server.run(**run_kwargs)
    else:
        from fastmcp.server.http import HostOriginGuardMiddleware
        from starlette.middleware import Middleware

        guard_kwargs: dict[str, Any] = {"mode": "strict"}
        if resolved_allowed_hosts is not None:
            guard_kwargs["allowed_hosts"] = resolved_allowed_hosts
        if resolved_allowed_origins is not None:
            guard_kwargs["allowed_origins"] = resolved_allowed_origins

        # FastMCP's SSE app ignores host_origin_protection; attach the same guard.
        server.run(
            transport=transport,
            host=host,
            port=port,
            host_origin_protection=True,
            middleware=[Middleware(HostOriginGuardMiddleware, **guard_kwargs)],
        )
