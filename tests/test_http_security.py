"""HTTP transport security tests."""

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
