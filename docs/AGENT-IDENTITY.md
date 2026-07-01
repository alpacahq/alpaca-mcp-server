# Agent Identity and Per-Tool Authorization

This guide covers how to verify which agent is acting and restrict what
tools it can call when multiple agents or third-party tools connect to
your Alpaca MCP server.

## When this matters

- Multiple agents share the same Alpaca API credentials
- A third-party tool or wrapper connects to your MCP server
- You want to attribute trades to specific agent software for debugging or operational visibility
- You want to restrict some agents to read-only access (market data only, no order placement)

## Pattern: authorization proxy

Place a reverse proxy between agents and the Alpaca MCP server. The proxy
verifies agent credentials and enforces a per-tool permission policy before
forwarding requests. The MCP server does not need code changes.

```
Agent → Authorization Proxy (verify + enforce) → alpaca-mcp-server
```

The proxy should:
1. Verify the agent's identity (signed attestation, API key, certificate, etc.)
2. Check the requested tool against a permission policy
3. Reject unauthorized or replayed requests
4. Log the decision for troubleshooting and accountability

## Example tool permission tiers

The Alpaca MCP server exposes 65+ tools with different risk levels. As an
illustrative starting point, you might group them like this:

| Tier | Example tools | Rationale |
|------|--------------|-----------|
| Read-only | `get_account_info`, `get_all_positions`, `get_orders`, `get_stock_snapshot`, `get_portfolio_history` | No side effects |
| Write | `cancel_order_by_id`, `close_position`, `update_account_config` | Modifies state but does not create new exposure |
| Trade (equities) | `place_stock_order` | Creates financial exposure |
| Trade (high-risk) | `place_option_order`, `place_crypto_order`, `close_all_positions`, `cancel_all_orders` | Higher-risk or bulk operations |

> **This is illustrative, not exhaustive.** Check the tool definitions in
> `src/tools/` for the current tool list and review each tool's risk level
> before building your policy. Tools may be added or renamed between versions.

An agent authorized for "Read-only" should not be able to call
`place_stock_order` or `close_all_positions`. The proxy enforces this before
the request reaches the MCP server.

## Implementation options

Several approaches can implement this pattern:

- **API gateway with tool-name routing** (e.g., nginx + Lua, Envoy, Kong):
  inspect the JSON-RPC `params.name` field and enforce allow/deny rules
  per agent identity.
- **MCP-aware auth proxy** (e.g., [@bolyra/gateway](https://github.com/bolyra/bolyra/tree/main/integrations/gateway)):
  a reverse proxy purpose-built for MCP servers with per-tool policy
  enforcement and decision logging.
- **Custom middleware**: wrap the MCP server's HTTP transport with
  authentication and authorization checks.

The choice depends on your deployment topology and trust model.

## What the proxy should log

For each `tools/call` request, the proxy should record:
- Agent identity (however you identify agents)
- Tool name requested
- Decision (allowed or denied)
- Timestamp
- Reason for denial (if applicable)

This creates a record that answers "which software placed this trade?"
or "which agent closed all positions?"

## Relationship to existing security

| Layer | Protects | How |
|-------|----------|-----|
| API key scoping | What operations the key allows | Alpaca restricted API keys |
| Agent authorization | Which agent can call which tools | Authorization proxy (this guide) |

Both layers are independent. API key scoping restricts at the Alpaca API
level. Agent authorization restricts at the MCP tool level before requests
reach the API.
