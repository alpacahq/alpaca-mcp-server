"""HTTP transport security tests."""

from unittest.mock import MagicMock, patch

import httpx
import pytest
from click.testing import CliRunner

from alpaca_mcp_server.cli import main
from alpaca_mcp_server.server import build_server


def _protected_http_app():
    return build_server().http_app(
        host_origin_protection=True,
        allowed_hosts=["mcp.example.com"],
        allowed_origins=["https://trusted.example"],
    )


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
