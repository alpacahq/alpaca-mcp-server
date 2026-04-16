# Agent Instructions

## Architecture Overview

This MCP server auto-generates tools from bundled OpenAPI specs (`src/alpaca_mcp_server/specs/`) using FastMCP's `from_openapi()`. Tool names and descriptions are customized in `names.py`. Complex endpoints (orders, historical data) use hand-written overrides in `overrides.py` and `market_data_overrides.py`. Toolset filtering is defined in `toolsets.py`.

The test suite has three layers:
- `tests/test_integrity.py` — Spec ↔ toolset ↔ names consistency (no network)
- `tests/test_server_construction.py` — Server builds correctly, exposes 62 tools (no network)
- `tests/test_paper_integration.py` — Real API calls against Alpaca paper (needs credentials)

CI is defined in `.github/workflows/ci.yml` with two jobs: `test-core` (runs on every PR) and `test-integration` (runs when `ALPACA_API_KEY` / `ALPACA_SECRET_KEY` secrets are available).

---

# Syncing OpenAPI Specs

When asked to "sync the MCP server" or "update specs", follow this process:

## Step 1: Download latest specs

Run the sync script:

```bash
./scripts/sync-specs.sh
```

## Step 2: Diff the specs

Check what changed:

```bash
git diff src/alpaca_mcp_server/specs/
```

Classify every change into one of three categories:

### A. Modified existing endpoints

Parameter or schema changes to endpoints already in the allowlist (`toolsets.py`).
**Action:** No code changes needed — the spec update is sufficient.

### B. New endpoints

Endpoints with operationIds not present in any toolset.
**Action:** Evaluate each:

1. **Is this endpoint useful for LLM interactions?** (e.g., CRUD for a core trading resource = yes; internal/admin endpoints = no)
2. **If yes:** Add the operationId to the appropriate toolset in `toolsets.py`. Add a `ToolOverride` entry to the `TOOLS` dict in `names.py` with a `snake_case` name and a curated description (see existing entries for the pattern).
3. **If the endpoint is complex** (many conditional params, multiple use cases in one schema like `POST /v2/orders`): Write an override function in `overrides.py`, add the operationId to `OVERRIDE_OPERATION_IDS` in `toolsets.py`, and do NOT add it to any toolset's operations.
4. **If not useful:** Note in the commit message that the endpoint was evaluated and excluded.

### C. Removed or renamed endpoints

OperationIds in `toolsets.py` that no longer exist in the specs.
**Action:** Flag as a breaking change. Remove the stale operationId from `toolsets.py` and the corresponding `ToolOverride` entry from `TOOLS` in `names.py`.

## Step 3: Validate

Run the integrity test suite. It checks that every operationId in `toolsets.py` exists in the specs, has a `ToolOverride` in `names.py`, and that all tool names are unique:

```bash
python -m pytest tests/test_integrity.py -v
```

All 7 tests must pass before proceeding. The tests are self-updating — they read `toolsets.py`, `names.py`, and the spec JSONs at runtime, so they never need manual changes.

## Step 4: Update README.md

If tools were added, removed, or renamed, update the **Available Tools** section in `README.md` to match. The section uses `<details>` blocks grouped by category. Each tool is listed as:

```
* `tool_name` — Short description
```

Use the tool name and description from the `ToolOverride` entry you added in `names.py`. Place the tool in the correct category block (Account & Portfolio, Trading, Positions, etc.). If a new toolset was created, add a new `<details>` block for it.

## Step 5: Extend Tests

If new tools were added (either auto-generated or overrides), add integration test coverage in `tests/test_paper_integration.py`:

1. Follow the existing patterns in the file — each test is an `async def test_...` function marked with `@pytest.mark.integration`.
2. Tests call tools via `server.call_tool(tool_name, arguments)` and parse results with the `_to_dict` / `_parse` helpers at the top of the file.
3. Assert the response contains expected keys or structure. Keep assertions loose enough to tolerate live data variability (e.g., check a key exists rather than asserting an exact value).
4. If a test requires placing orders or creating resources, clean up after itself (cancel orders, delete watchlists, etc.).
5. Run the full suite locally to verify:

```bash
# Core tests (fast, no credentials)
pytest tests/test_integrity.py tests/test_server_construction.py -v

# Integration tests (requires paper API keys)
ALPACA_API_KEY=... ALPACA_SECRET_KEY=... pytest tests/ -m integration -v
```

All tests must pass before proceeding. The CI pipeline (`.github/workflows/ci.yml`) runs core tests on every PR and integration tests when secrets are available.

## Step 6: Commit

Write a descriptive commit message listing:
- What changed in the API specs
- Which new endpoints were added to toolsets (and which toolset)
- Which new endpoints were excluded (and why)
- Any breaking changes (removed/renamed endpoints)
- Whether README was updated
- Whether new tests were added
