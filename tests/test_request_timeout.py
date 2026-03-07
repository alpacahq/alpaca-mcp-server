import pytest
from requests.exceptions import Timeout as RequestsTimeout

from alpaca_mcp_server import server


class _RecordingBase:
    def _one_request(self, method: str, url: str, opts: dict, retry: int) -> dict:
        return {
            "method": method,
            "url": url,
            "opts": opts,
            "retry": retry,
        }


class _TimeoutBase:
    def _one_request(self, method: str, url: str, opts: dict, retry: int) -> dict:
        raise RequestsTimeout("timed out")


class _RecordingClient(server.RequestTimeoutMixin, _RecordingBase):
    pass


class _TimeoutClient(server.RequestTimeoutMixin, _TimeoutBase):
    pass


def test_get_request_timeout_seconds_defaults_when_unset(monkeypatch):
    monkeypatch.delenv("ALPACA_HTTP_TIMEOUT_SECONDS", raising=False)

    assert server._get_request_timeout_seconds() == server.DEFAULT_REQUEST_TIMEOUT_SECONDS


def test_get_request_timeout_seconds_defaults_when_invalid(monkeypatch):
    monkeypatch.setenv("ALPACA_HTTP_TIMEOUT_SECONDS", "not-a-number")
    assert server._get_request_timeout_seconds() == server.DEFAULT_REQUEST_TIMEOUT_SECONDS

    monkeypatch.setenv("ALPACA_HTTP_TIMEOUT_SECONDS", "0")
    assert server._get_request_timeout_seconds() == server.DEFAULT_REQUEST_TIMEOUT_SECONDS


def test_request_timeout_mixin_injects_default_timeout(monkeypatch):
    monkeypatch.setenv("ALPACA_HTTP_TIMEOUT_SECONDS", "7.5")

    client = _RecordingClient()
    result = client._one_request("GET", "https://example.com", {"headers": {}}, 0)

    assert result["opts"]["timeout"] == 7.5


def test_request_timeout_mixin_preserves_explicit_timeout(monkeypatch):
    monkeypatch.setenv("ALPACA_HTTP_TIMEOUT_SECONDS", "7.5")

    client = _RecordingClient()
    result = client._one_request(
        "GET",
        "https://example.com",
        {"headers": {}, "timeout": 2},
        0,
    )

    assert result["opts"]["timeout"] == 2


def test_request_timeout_mixin_raises_clear_timeout_error(monkeypatch):
    monkeypatch.setenv("ALPACA_HTTP_TIMEOUT_SECONDS", "7.5")

    client = _TimeoutClient()

    with pytest.raises(server.AlpacaRequestTimeoutError, match="timed out after 7.5s"):
        client._one_request("GET", "https://example.com", {"headers": {}}, 0)
