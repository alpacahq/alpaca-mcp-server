# CLAUDE.md — Alpaca MCP Server

## Build & Test

```bash
uv run --extra dev pytest tests/ --ignore=tests/test_paper_integration.py -v
```

Integration tests (`test_paper_integration.py`) require `ALPACA_API_KEY` and `ALPACA_SECRET_KEY` env vars pointed at a paper account.

## Architecture

- **OpenAPI-driven tools** are generated automatically by `FastMCP.from_openapi()` from specs in `src/alpaca_mcp_server/specs/`.
- **Hand-crafted overrides** in `src/alpaca_mcp_server/overrides.py` replace endpoints too complex for auto-generation (e.g., `POST /v2/orders`).
- `toolsets.py` controls which operationIds are exposed; `OVERRIDE_OPERATION_IDS` prevents auto-generation of endpoints that have hand-crafted replacements.
- Tool names and descriptions are customised in `names.py`.

## Key trading rules for LLM callers

### Closing positions — use `close_position`, not `place_stock_order`

To close or reduce any existing position (long **or** short), always use the `close_position` tool (mapped to `DELETE /v2/positions/{symbol}`). It automatically determines the correct side and intent.

**Do NOT** use `place_stock_order` to cover a short or sell a long — it does not carry position intent and can flip a short position into a long (or vice versa), doubling exposure instead of flattening it.

```
# Correct — covers a short OR sells a long:
close_position(symbol="NCLH")           # full close
close_position(symbol="NCLH", qty=100)  # partial close

# WRONG — may flip a short to a long:
place_stock_order(symbol="NCLH", side="buy", qty=200, type="market")
```

### Bracket / OTO / OCO orders — nested serialization

The Alpaca API requires `take_profit` and `stop_loss` as nested JSON objects. The `place_stock_order` tool handles this automatically — pass the flat parameter names and they are serialized into the required format:

| Tool parameter          | API JSON path              |
|------------------------|----------------------------|
| `take_profit_price`     | `take_profit.limit_price`  |
| `stop_loss_price`       | `stop_loss.stop_price`     |
| `stop_loss_limit_price` | `stop_loss.limit_price`    |

`order_class` is auto-set to `"bracket"` when bracket params are provided.
