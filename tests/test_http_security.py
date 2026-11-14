"""HTTP transport security tests."""

import os
import subprocess
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import httpx
import pytest
from click.testing import CliRunner
from fastmcp.server.http import HostOriginGuardMiddleware

from alpaca_mcp_server.cli import main
from alpaca_mcp_server.server import build_server


def _protected_http_app() -> Any:
    return build_server().http_app(
        host_origin_protection=True,
        allowed_hosts=["mcp.example.com"],
        allowed_origins=["https://trusted.example"],
    )


def _default_protected_http_app() -> Any:
    return build_server().http_app(host_origin_protection=True)


def test_streamable_http_enables_strict_host_origin_protection() -> None:
    server = MagicMock()

    with (
        patch.dict(
            "os.environ",
            {
                "ALPACA_API_KEY": "test-key",
                "ALPACA_SECRET_KEY": "test-secret",
            },
        ),
        patch("alpaca_mcp_server.server.build_server", return_value=server),
    ):
        result = CliRunner().invoke(main, ["--transport", "streamable-http"])

    assert result.exit_code == 0, result.output
    server.run.assert_called_once_with(
        transport="streamable-http",
        host="127.0.0.1",
        port=8000,
        host_origin_protection=True,
    )


@pytest.mark.asyncio
async def test_streamable_http_rejects_untrusted_host() -> None:
    transport = httpx.ASGITransport(app=_protected_http_app())

    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://mcp.example.com",
    ) as client:
        response = await client.post("/mcp", headers={"Host": "attacker.example"})

    assert response.status_code == 421
    assert response.text == "Misdirected Request"


@pytest.mark.asyncio
async def test_streamable_http_rejects_untrusted_origin() -> None:
    transport = httpx.ASGITransport(app=_protected_http_app())

    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://mcp.example.com",
    ) as client:
        response = await client.post(
            "/mcp",
            headers={"Origin": "https://attacker.example"},
        )

    assert response.status_code == 403
    assert response.text == "Forbidden Origin"


@pytest.mark.asyncio
async def test_default_streamable_http_rejects_untrusted_host() -> None:
    transport = httpx.ASGITransport(app=_default_protected_http_app())

    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://127.0.0.1",
    ) as client:
        response = await client.post("/mcp", headers={"Host": "attacker.example"})

    assert response.status_code == 421
    assert response.text == "Misdirected Request"


@pytest.mark.asyncio
async def test_default_streamable_http_accepts_loopback_host() -> None:
    transport = httpx.ASGITransport(
        app=_default_protected_http_app(),
        raise_app_exceptions=False,
    )

    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://127.0.0.1",
    ) as client:
        response = await client.post("/mcp", headers={"Host": "127.0.0.1"})

    assert response.status_code not in {403, 421}


@pytest.mark.asyncio
async def test_cli_streamable_http_app_rejects_untrusted_host() -> None:
    server = build_server()
    captured: dict[str, Any] = {}

    def fake_run(**kwargs: Any) -> None:
        captured.update(kwargs)

    server.run = fake_run  # type: ignore[method-assign]

    with (
        patch.dict(
            "os.environ",
            {
                "ALPACA_API_KEY": "test-key",
                "ALPACA_SECRET_KEY": "test-secret",
            },
        ),
        patch("alpaca_mcp_server.server.build_server", return_value=server),
    ):
        result = CliRunner().invoke(main, ["--transport", "streamable-http"])

    assert result.exit_code == 0, result.output
    assert captured["host_origin_protection"] is True

    app = server.http_app(
        transport=captured["transport"],
        host_origin_protection=captured["host_origin_protection"],
        allowed_hosts=captured.get("allowed_hosts"),
        allowed_origins=captured.get("allowed_origins"),
        middleware=captured.get("middleware"),
    )
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://127.0.0.1",
    ) as client:
        response = await client.post("/mcp", headers={"Host": "attacker.example"})

    assert response.status_code == 421
    assert response.text == "Misdirected Request"


def test_sse_enables_strict_host_origin_protection() -> None:
    server = MagicMock()

    with (
        patch.dict(
            "os.environ",
            {
                "ALPACA_API_KEY": "test-key",
                "ALPACA_SECRET_KEY": "test-secret",
            },
        ),
        patch("alpaca_mcp_server.server.build_server", return_value=server),
    ):
        result = CliRunner().invoke(main, ["--transport", "sse"])

    assert result.exit_code == 0, result.output
    server.run.assert_called_once()
    kwargs = server.run.call_args.kwargs
    assert kwargs["transport"] == "sse"
    assert kwargs["host_origin_protection"] is True
    middleware = kwargs.get("middleware") or []
    assert any(
        getattr(item, "cls", None) is HostOriginGuardMiddleware
        for item in middleware
    )


def _capture_cli_http_app(*cli_args: str, extra_env: dict[str, str] | None = None) -> Any:
    server = build_server()
    captured: dict[str, Any] = {}

    def fake_run(**kwargs: Any) -> None:
        captured.update(kwargs)

    env = {
        "ALPACA_API_KEY": "test-key",
        "ALPACA_SECRET_KEY": "test-secret",
        **(extra_env or {}),
    }

    with (
        patch.dict("os.environ", env, clear=False),
        patch("alpaca_mcp_server.server.build_server", return_value=server),
        patch.object(server, "run", side_effect=fake_run),
    ):
        result = CliRunner().invoke(main, list(cli_args))

    assert result.exit_code == 0, result.output
    return server.http_app(
        transport=captured["transport"],
        host_origin_protection=captured["host_origin_protection"],
        allowed_hosts=captured.get("allowed_hosts"),
        allowed_origins=captured.get("allowed_origins"),
        middleware=captured.get("middleware"),
    )


@pytest.mark.asyncio
async def test_cli_streamable_http_allows_configured_docker_host_via_flag() -> None:
    app = _capture_cli_http_app(
        "--transport",
        "streamable-http",
        "--host",
        "0.0.0.0",
        "--port",
        "8000",
        "--allowed-host",
        "alpaca",
    )
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)

    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://alpaca:8000",
    ) as client:
        allowed_resp = await client.post("/mcp", headers={"Host": "alpaca:8000"})
        blocked_resp = await client.post("/mcp", headers={"Host": "attacker.example"})

    assert allowed_resp.status_code not in {403, 421}
    assert blocked_resp.status_code == 421
    assert blocked_resp.text == "Misdirected Request"


@pytest.mark.asyncio
async def test_cli_streamable_http_allows_explicit_bound_hostname() -> None:
    app = _capture_cli_http_app(
        "--transport",
        "streamable-http",
        "--host",
        "alpaca",
        "--port",
        "8000",
    )
    # Uvicorn populates ASGI scope["server"] with the resolved numeric socket IP,
    # not the DNS hostname passed to --host.
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)

    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://172.18.0.2:8000",
    ) as client:
        allowed_resp = await client.post("/mcp", headers={"Host": "alpaca:8000"})
        blocked_resp = await client.post("/mcp", headers={"Host": "attacker.example"})

    assert allowed_resp.status_code not in {403, 421}
    assert blocked_resp.status_code == 421


@pytest.mark.asyncio
async def test_cli_streamable_http_wildcard_bind_without_allowlist_rejects_docker_host() -> None:
    app = _capture_cli_http_app(
        "--transport",
        "streamable-http",
        "--host",
        "0.0.0.0",
        "--port",
        "8000",
    )
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)

    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://0.0.0.0:8000",
    ) as client:
        response = await client.post("/mcp", headers={"Host": "alpaca:8000"})

    assert response.status_code == 421
    assert response.text == "Misdirected Request"


def test_cli_accepts_comma_separated_fastmcp_allowed_hosts_in_fresh_process() -> None:
    code = (
        "from unittest.mock import MagicMock, patch\n"
        "from click.testing import CliRunner\n"
        "from alpaca_mcp_server.cli import main\n"
        "srv = MagicMock()\n"
        "with patch('alpaca_mcp_server.server.build_server', return_value=srv):\n"
        "    res = CliRunner().invoke(\n"
        "        main,\n"
        "        ['--transport', 'streamable-http', '--host', '0.0.0.0', '--allowed-host', 'extra.internal'],\n"
        "    )\n"
        "assert res.exit_code == 0, res.output\n"
        "kwargs = srv.run.call_args.kwargs\n"
        "assert kwargs['allowed_hosts'] == ['alpaca', 'mcp.internal', 'extra.internal'], kwargs\n"
    )
    env = {
        **os.environ,
        "ALPACA_API_KEY": "test-key",
        "ALPACA_SECRET_KEY": "test-secret",
        "FASTMCP_HTTP_ALLOWED_HOSTS": "alpaca,mcp.internal",
    }
    proc = subprocess.run(
        [sys.executable, "-c", code],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, f"stdout={proc.stdout}\nstderr={proc.stderr}"


def test_cli_accepts_comma_separated_allowlists_from_env_file_in_fresh_process(
    tmp_path: Path,
) -> None:
    env_file = tmp_path / "mcp.env"
    env_file.write_text(
        "ALPACA_API_KEY=test-key\n"
        "ALPACA_SECRET_KEY=test-secret\n"
        "FASTMCP_HTTP_ALLOWED_HOSTS=alpaca,mcp.internal\n"
        "FASTMCP_HTTP_ALLOWED_ORIGINS=https://one.example,https://two.example\n",
        encoding="utf-8",
    )
    code = (
        "import builtins, sys\n"
        "from unittest.mock import MagicMock\n"
        "from click.testing import CliRunner\n"
        "from alpaca_mcp_server.cli import main\n"
        "assert 'fastmcp' not in sys.modules\n"
        "srv = MagicMock()\n"
        "orig_import = builtins.__import__\n"
        "def hooked_import(name, globals=None, locals=None, fromlist=(), level=0):\n"
        "    mod = orig_import(name, globals, locals, fromlist, level)\n"
        "    if mod.__name__ == 'alpaca_mcp_server.server':\n"
        "        mod.build_server = lambda: srv\n"
        "    return mod\n"
        "builtins.__import__ = hooked_import\n"
        "try:\n"
        "    res = CliRunner().invoke(\n"
        "        main,\n"
        "        ['--env-file', sys.argv[1], '--transport', 'streamable-http', '--host', '0.0.0.0'],\n"
        "    )\n"
        "finally:\n"
        "    builtins.__import__ = orig_import\n"
        "assert res.exit_code == 0, res.output\n"
        "import fastmcp\n"
        "assert fastmcp.settings.http_allowed_hosts == ['alpaca', 'mcp.internal']\n"
        "assert fastmcp.settings.http_allowed_origins == ['https://one.example', 'https://two.example']\n"
        "kwargs = srv.run.call_args.kwargs\n"
        "assert kwargs['allowed_hosts'] == ['alpaca', 'mcp.internal'], kwargs\n"
        "assert kwargs['allowed_origins'] == ['https://one.example', 'https://two.example'], kwargs\n"
    )
    env = {
        k: v
        for k, v in os.environ.items()
        if k
        not in {
            "ALPACA_API_KEY",
            "ALPACA_SECRET_KEY",
            "FASTMCP_HTTP_ALLOWED_HOSTS",
            "FASTMCP_HTTP_ALLOWED_ORIGINS",
        }
    }
    proc = subprocess.run(
        [sys.executable, "-c", code, str(env_file)],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, f"stdout={proc.stdout}\nstderr={proc.stderr}"


@pytest.mark.asyncio
async def test_cli_sse_forwards_allowed_hosts_and_origins_to_guard_middleware() -> None:
    app = _capture_cli_http_app(
        "--transport",
        "sse",
        "--host",
        "0.0.0.0",
        "--allowed-origin",
        "https://trusted.example",
        extra_env={"FASTMCP_HTTP_ALLOWED_HOSTS": '["alpaca"]'},
    )
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)

    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://0.0.0.0:8000",
    ) as client:
        allowed_resp = await client.post(
            "/messages/",
            headers={
                "Host": "alpaca:8000",
                "Origin": "https://trusted.example",
            },
        )
        bad_host_resp = await client.post(
            "/messages/",
            headers={"Host": "attacker.example"},
        )
        bad_origin_resp = await client.post(
            "/messages/",
            headers={
                "Host": "alpaca:8000",
                "Origin": "https://attacker.example",
            },
        )

    assert allowed_resp.status_code not in {403, 421}
    assert bad_host_resp.status_code == 421
    assert bad_origin_resp.status_code == 403


def test_cli_rejects_malformed_json_allowed_hosts_env() -> None:
    server = MagicMock()
    env = {
        "ALPACA_API_KEY": "test-key",
        "ALPACA_SECRET_KEY": "test-secret",
        "FASTMCP_HTTP_ALLOWED_HOSTS": "[not-valid-json",
    }

    with (
        patch.dict("os.environ", env, clear=False),
        patch("alpaca_mcp_server.server.build_server", return_value=server),
    ):
        result = CliRunner().invoke(main, ["--transport", "streamable-http"])

    assert result.exit_code != 0
    assert "Invalid FASTMCP_HTTP_ALLOWED_HOSTS" in result.output
