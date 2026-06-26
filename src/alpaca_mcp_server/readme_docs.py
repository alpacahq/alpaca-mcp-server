from __future__ import annotations

import json
from collections.abc import Callable
from types import TracebackType
from typing import Any, Protocol, cast

from fastmcp import FastMCP
from fastmcp.client import Client
from fastmcp.client.transports import StreamableHttpTransport

SEARCH_ALPACA_DOCS = "search_alpaca_docs"
FETCH_ALPACA_DOC = "fetch_alpaca_doc"
SEARCH_ALPACA_API_SPECS = "search_alpaca_api_specs"
LIST_ALPACA_API_ENDPOINTS = "list_alpaca_api_endpoints"
GET_ALPACA_ENDPOINT_DOCS = "get_alpaca_endpoint_docs"

DEFAULT_README_MCP_URL = "https://docs.alpaca.markets/mcp?project=us"
README_DOCS_FALLBACK_MESSAGE = (
    "ReadMe MCP lookup failed. Use Alpaca's public docs and LLM indexes as "
    "the fallback source."
)
README_DOCS_FALLBACK_URLS = (
    "https://docs.alpaca.markets/us/reference/api-references",
    "https://docs.alpaca.markets/llms.txt",
    "https://docs.alpaca.markets/llms-full.txt",
)
DEFAULT_SPEC_TITLE = "Trading API"
ALLOWED_SPEC_TITLES = (
    "Trading API",
    "Market Data API",
    "Authentication API",
)

README_DOC_TOOL_NAMES = {
    SEARCH_ALPACA_DOCS,
    FETCH_ALPACA_DOC,
    SEARCH_ALPACA_API_SPECS,
    LIST_ALPACA_API_ENDPOINTS,
    GET_ALPACA_ENDPOINT_DOCS,
}


class ReadMeMCPClient(Protocol):
    async def __aenter__(self) -> "ReadMeMCPClient":
        ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool | None:
        ...

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        ...


ReadMeClientFactory = Callable[[], ReadMeMCPClient]


def default_readme_client_factory() -> ReadMeMCPClient:
    transport = StreamableHttpTransport(url=DEFAULT_README_MCP_URL)
    return cast(ReadMeMCPClient, Client(transport))


def _error(message: str, **extra: Any) -> dict[str, Any]:
    err: dict[str, Any] = {"message": message}
    err.update(extra)
    return {"error": err}


def _readme_tool_error(message: str, **extra: Any) -> dict[str, Any]:
    return _error(
        message,
        fallback={
            "message": README_DOCS_FALLBACK_MESSAGE,
            "urls": list(README_DOCS_FALLBACK_URLS),
        },
        **extra,
    )


def _clean_args(values: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in values.items() if value is not None}


def _normalize_spec_title(title: str) -> str | None:
    for allowed in ALLOWED_SPEC_TITLES:
        if title.casefold() == allowed.casefold():
            return allowed
    return None


def _unsupported_spec_title(title: str) -> dict[str, Any]:
    allowed = ", ".join(ALLOWED_SPEC_TITLES)
    return _error(f"Unsupported Alpaca API spec title: {title}. Use one of: {allowed}.")


def _allowed_spec_groups(groups: list[Any]) -> list[dict[str, Any]]:
    allowed: list[dict[str, Any]] = []
    for group in groups:
        if not isinstance(group, dict):
            continue
        title = group.get("title")
        if isinstance(title, str) and _normalize_spec_title(title) is not None:
            allowed.append(group)
    return allowed


def _normalize_tool_result(result: Any) -> dict[str, Any]:
    data = getattr(result, "data", None)
    if isinstance(data, dict):
        return cast(dict[str, Any], data)
    if data is not None:
        return {"result": data}

    blocks: list[dict[str, Any]] = []
    for block in getattr(result, "content", []) or []:
        text = getattr(block, "text", None)
        if text is not None:
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                blocks.append({"type": "text", "text": text})
                continue
            if isinstance(parsed, dict):
                return cast(dict[str, Any], parsed)
            return {"result": parsed}

        model_dump = getattr(block, "model_dump", None)
        if callable(model_dump):
            blocks.append(cast(dict[str, Any], model_dump()))
        else:
            blocks.append({"value": repr(block)})

    return {"content": blocks}


async def _call_readme_tool(
    client_factory: ReadMeClientFactory,
    upstream_tool: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    try:
        async with client_factory() as client:
            result = await client.call_tool(
                upstream_tool,
                _clean_args(arguments),
                raise_on_error=False,
            )
    except Exception as exc:
        return _readme_tool_error(f"ReadMe MCP error: {exc}")

    normalized = _normalize_tool_result(result)
    if getattr(result, "is_error", False) or normalized.get("isError") is True:
        return _readme_tool_error("ReadMe MCP error", detail=normalized)

    return normalized


async def _search_allowed_endpoint_specs(
    client_factory: ReadMeClientFactory,
    query: str,
) -> dict[str, Any]:
    result = await _call_readme_tool(
        client_factory,
        "search-endpoints",
        {"pattern": query},
    )
    if "error" in result:
        return result

    groups = result.get("result")
    if not isinstance(groups, list):
        return result

    return {"query": query, "specs": _allowed_spec_groups(groups)}


def _read_only_annotations(title: str) -> dict[str, Any]:
    return {
        "title": title,
        "readOnlyHint": True,
        "destructiveHint": False,
        "openWorldHint": True,
    }


def register_readme_docs_tools(
    server: FastMCP,
    client_factory: ReadMeClientFactory | None = None,
) -> None:
    use_client_factory = client_factory or default_readme_client_factory

    @server.tool(
        description=(
            "Search Alpaca documentation pages and guides. Use for conceptual "
            "or product questions about setup, account rules, funding, "
            "trading, market data, events, or FAQs. Read-only; not for exact "
            "API method/path lookup; prefer search_alpaca_api_specs for "
            "endpoint, parameter, or schema questions."
        ),
        annotations=_read_only_annotations("Search Alpaca Docs"),
    )
    async def search_alpaca_docs(query: str) -> dict[str, Any]:
        return await _call_readme_tool(use_client_factory, "search", {"query": query})

    @server.tool(
        description=(
            "Fetch one Alpaca ReadMe documentation page by page ID. Use after "
            "search_alpaca_docs returns a relevant page ID, or when a page ID "
            "is already known. Read-only; not for API endpoint lookup by "
            "method and path."
        ),
        annotations=_read_only_annotations("Fetch Alpaca Doc"),
    )
    async def fetch_alpaca_doc(id: str) -> dict[str, Any]:
        return await _call_readme_tool(use_client_factory, "fetch", {"id": id})

    @server.tool(
        description=(
            "Search Alpaca API reference endpoints by topic, operation, path "
            "fragment, parameter, or schema term. Use when the exact method "
            "and path are unknown. Read-only; does not execute endpoints; "
            "searches Trading API, Market Data API, and Authentication API "
            "only; excludes Broker API. Use `query`; do not use `pattern`."
        ),
        annotations=_read_only_annotations("Search Alpaca API Specs"),
    )
    async def search_alpaca_api_specs(query: str) -> dict[str, Any]:
        return await _search_allowed_endpoint_specs(use_client_factory, query)

    @server.tool(
        description=(
            "List endpoints for one allowed Alpaca OpenAPI spec. Use when "
            "browsing the available endpoint inventory for Trading API, "
            "Market Data API, or Authentication API before narrowing to a "
            "specific endpoint. Read-only; excludes Broker API; prefer "
            "search_alpaca_api_specs for targeted lookup."
        ),
        annotations=_read_only_annotations("List Alpaca API Endpoints"),
    )
    async def list_alpaca_api_endpoints(title: str = DEFAULT_SPEC_TITLE) -> dict[str, Any]:
        normalized_title = _normalize_spec_title(title)
        if normalized_title is None:
            return _unsupported_spec_title(title)
        return await _call_readme_tool(
            use_client_factory, "list-endpoints", {"title": normalized_title}
        )

    @server.tool(
        description=(
            "Fetch reference docs for one exact Alpaca API endpoint by method "
            "and path. Use when the endpoint is already resolved and details "
            "such as parameters, request shape, responses, or examples are "
            "needed. Read-only; does not execute the endpoint; excludes "
            "Broker API."
        ),
        annotations=_read_only_annotations("Get Alpaca Endpoint Docs"),
    )
    async def get_alpaca_endpoint_docs(
        path: str,
        method: str,
        title: str = DEFAULT_SPEC_TITLE,
    ) -> dict[str, Any]:
        normalized_title = _normalize_spec_title(title)
        if normalized_title is None:
            return _unsupported_spec_title(title)
        return await _call_readme_tool(
            use_client_factory,
            "get-endpoint",
            {"path": path, "method": method.upper(), "title": normalized_title},
        )
