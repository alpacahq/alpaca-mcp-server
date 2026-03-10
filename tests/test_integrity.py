"""
Data integrity checks across toolsets, names, and OpenAPI specs.

Catches drift after spec updates: stale operationIds, missing ToolOverride
entries, and duplicate tool names.
"""

from __future__ import annotations

import json
from pathlib import Path

from alpaca_mcp_server.names import TOOLS, TOOL_NAMES, TOOL_DESCRIPTIONS
from alpaca_mcp_server.toolsets import OVERRIDE_OPERATION_IDS, TOOLSETS

SPECS_DIR = Path(__file__).resolve().parent.parent / "src" / "alpaca_mcp_server" / "specs"


def _load_operation_ids(spec_name: str) -> set[str]:
    """Extract all operationIds from a bundled OpenAPI spec."""
    spec = json.loads((SPECS_DIR / f"{spec_name}.json").read_text())
    ids: set[str] = set()
    for methods in spec["paths"].values():
        for details in methods.values():
            if isinstance(details, dict) and "operationId" in details:
                ids.add(details["operationId"])
    return ids


TRADING_OPS = _load_operation_ids("trading-api")
MARKET_DATA_OPS = _load_operation_ids("market-data-api")

SPEC_OPS = {
    "trading": TRADING_OPS,
    "market-data": MARKET_DATA_OPS,
}


def test_all_toolset_operation_ids_exist_in_specs():
    """Every operationId referenced in TOOLSETS must exist in its spec."""
    missing: list[str] = []
    for ts_name, ts_config in TOOLSETS.items():
        spec_ops = SPEC_OPS[ts_config["spec"]]
        for op_id in ts_config["operations"]:
            if op_id not in spec_ops:
                missing.append(f"{ts_name}/{op_id} not in {ts_config['spec']} spec")
    assert not missing, f"Stale operationIds:\n" + "\n".join(missing)


def test_override_operation_ids_exist_in_spec():
    """Every OVERRIDE_OPERATION_ID must exist in the trading spec."""
    missing = OVERRIDE_OPERATION_IDS - TRADING_OPS
    assert not missing, f"Override operationIds not in trading spec: {missing}"


def test_all_non_override_operations_have_tool_overrides():
    """Every auto-generated operationId must have a ToolOverride in names.py."""
    all_ops: set[str] = set()
    for ts_config in TOOLSETS.values():
        all_ops.update(ts_config["operations"])

    need_override = all_ops - OVERRIDE_OPERATION_IDS
    missing = need_override - set(TOOLS.keys())
    assert not missing, (
        f"operationIds in toolsets.py without ToolOverride in names.py:\n"
        + "\n".join(sorted(missing))
    )


def test_no_orphan_tool_overrides():
    """Every ToolOverride key should be referenced by a toolset or an override."""
    all_ops: set[str] = set()
    for ts_config in TOOLSETS.values():
        all_ops.update(ts_config["operations"])
    all_ops.update(OVERRIDE_OPERATION_IDS)

    orphans = set(TOOLS.keys()) - all_ops
    assert not orphans, (
        f"ToolOverride entries in names.py not referenced by any toolset:\n"
        + "\n".join(sorted(orphans))
    )


def test_tool_names_are_unique():
    """No two operationIds should map to the same MCP tool name."""
    seen: dict[str, str] = {}
    dupes: list[str] = []
    for op_id, override in TOOLS.items():
        if override.name in seen:
            dupes.append(f"{override.name!r} used by both {seen[override.name]} and {op_id}")
        seen[override.name] = op_id
    assert not dupes, f"Duplicate tool names:\n" + "\n".join(dupes)


def test_all_descriptions_non_empty():
    """Every ToolOverride must have a non-empty description."""
    empty = [op_id for op_id, t in TOOLS.items() if not t.description.strip()]
    assert not empty, f"Empty descriptions: {empty}"


def test_derived_lookups_match_tools():
    """TOOL_NAMES and TOOL_DESCRIPTIONS must stay in sync with TOOLS."""
    assert set(TOOL_NAMES.keys()) == set(TOOLS.keys())
    assert set(TOOL_DESCRIPTIONS.keys()) == set(TOOLS.keys())
    for op_id, t in TOOLS.items():
        assert TOOL_NAMES[op_id] == t.name
        assert TOOL_DESCRIPTIONS[op_id] == t.description
