"""
Optional pre-trade gate: an independent invinoveritas /review verdict on
destructive tool calls (place_stock_order, place_crypto_order,
place_option_order, cancel_order_by_id, cancel_all_orders, close_position,
close_all_positions, replace_order_by_id, ...).

Not a rule engine — a signed, independently-recomputable judgment call issued
by a party structurally separate from the agent placing the order. Gates on
the same MCP `destructiveHint` annotation this server already uses for its own
tool metadata (see server.tool(annotations=...) calls in overrides.py), so it
composes with any current or future destructive tool without a hardcoded
name list.

Design mirrors the same discipline as invinoveritas's other integrations
(AutoGen GovernedWorkbench, mcp-context-forge InvinoveritasReviewPlugin):
  - FAIL-OPEN on any /review-side problem (network error, timeout, malformed
    response, missing key) -- the order proceeds as if ungated rather than
    silently hanging or blocking the gateway on our service having a bad
    moment. Every destructive call's result carries an `invinoveritas_review`
    marker in `meta` regardless of outcome ("unavailable" on fail-open,
    "approve"/"approve_with_concerns" on a passed review) -- so a client or
    audit consumer can always tell an unreviewed destructive call apart from
    a reviewed one, not just infer it from the absence of an error.
  - GATES on a real `reject` verdict by default (block_on_reject=True in the
    constructor). Pass block_on_reject=False for an advisory/observe-only
    rollout that never blocks, only annotates (the marker on `meta` still
    reports "reject" in that mode, it just doesn't raise).
  - Never overrides an approve/approve_with_concerns verdict.

Data sent externally: on every destructive call, the full tool argument
dictionary (e.g. for place_stock_order -- symbol, side, qty/notional, type,
time_in_force, limit/stop/trail prices, client_order_id, order_class, and any
bracket/multi-leg fields present) is sent to the invinoveritas /review
endpoint as part of the review artifact, over HTTPS with your IVV_API_KEY as
bearer auth. No account credentials, API keys, or account/portfolio state are
sent -- only the arguments of the specific call being reviewed.

Usage (opt-in, disabled unless explicitly wired -- see README):

    from .invinoveritas_review import InvinoveritasReviewMiddleware
    main.add_middleware(InvinoveritasReviewMiddleware())
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Optional

import httpx
from fastmcp.exceptions import ToolError
from fastmcp.server.middleware import Middleware, MiddlewareContext
from fastmcp.tools.tool import ToolResult

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://api.babyblueviper.com"
DEFAULT_TIMEOUT_S = 15.0
_VALID_VERDICTS = ("approve", "approve_with_concerns", "reject")


class InvinoveritasReviewMiddleware(Middleware):
    """Gates destructive tool calls on an independent invinoveritas /review verdict.

    Register free, instant, no payment: POST https://api.babyblueviper.com/register
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = DEFAULT_BASE_URL,
        block_on_reject: bool = True,
        sign: bool = False,
        artifact_type: str = "financial_transaction",
        timeout_s: float = DEFAULT_TIMEOUT_S,
    ) -> None:
        self._api_key = api_key or os.environ.get("IVV_API_KEY")
        self._base_url = base_url
        self._block_on_reject = block_on_reject
        self._sign = sign
        self._artifact_type = artifact_type
        self._timeout_s = timeout_s
        if not self._api_key:
            logger.warning(
                "InvinoveritasReviewMiddleware: no IVV_API_KEY set (constructor arg or env "
                "var) -- every destructive tool call will proceed UNGATED. Register free at "
                "%s/register",
                self._base_url,
            )

    async def on_call_tool(self, context: MiddlewareContext, call_next) -> ToolResult:
        tool_name = context.message.name

        if not await self._is_destructive(context, tool_name):
            return await call_next(context)

        verdict = await self._review(tool_name, context.message.arguments)
        marker = verdict.get("verdict") if verdict is not None else "unavailable"

        if verdict is not None and verdict.get("verdict") == "reject" and self._block_on_reject:
            logger.warning(
                "InvinoveritasReviewMiddleware BLOCK %r (confidence=%s)",
                tool_name, verdict.get("confidence"),
            )
            raise ToolError(
                f"Tool call to {tool_name!r} BLOCKED by an independent invinoveritas /review "
                f"verdict (reject, confidence={verdict.get('confidence')}). "
                f"{verdict.get('summary', '')} "
                f"Verify this verdict yourself, no trust required: "
                f"POST {self._base_url}/verify-proof"
            )

        result = await call_next(context)
        return ToolResult(
            content=result.content,
            structured_content=result.structured_content,
            meta={**(result.meta or {}), "invinoveritas_review": marker},
            is_error=result.is_error,
        )

    # ---- internals ----

    async def _is_destructive(self, context: MiddlewareContext, tool_name: str) -> bool:
        fastmcp_ctx = context.fastmcp_context
        if fastmcp_ctx is None:
            return False
        try:
            tool = await fastmcp_ctx.fastmcp.get_tool(tool_name)
        except Exception:  # noqa: BLE001 -- unknown tool, nothing to gate
            return False
        return bool(tool.annotations and tool.annotations.destructiveHint)

    async def _review(self, tool_name: str, arguments: dict[str, Any] | None) -> Optional[dict[str, Any]]:
        """Returns the /review response dict, or None on any failure/misconfiguration
        (fail-open -- the caller treats None exactly like an approve)."""
        if not self._api_key:
            return None

        artifact = json.dumps({"tool_name": tool_name, "arguments": dict(arguments or {})}, default=str)
        try:
            async with httpx.AsyncClient(timeout=self._timeout_s) as client:
                resp = await client.post(
                    f"{self._base_url}/review",
                    headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"},
                    json={
                        "artifact": artifact,
                        "artifact_type": self._artifact_type,
                        "context": f"Alpaca MCP tool call: {tool_name}",
                        "sign": self._sign,
                    },
                )
            resp.raise_for_status()
            data = resp.json()
            if data.get("verdict") not in _VALID_VERDICTS:
                logger.warning(
                    "InvinoveritasReviewMiddleware: malformed /review response for %r, failing open: %r",
                    tool_name, data,
                )
                return None
            logger.info(
                "InvinoveritasReviewMiddleware: %r -> %s (confidence=%s)",
                tool_name, data.get("verdict"), data.get("confidence"),
            )
            return data
        except Exception as e:  # noqa: BLE001 -- fail-open on ANY error, by design
            logger.warning(
                "InvinoveritasReviewMiddleware: /review call failed for %r (%s), failing open",
                tool_name, e,
            )
            return None
