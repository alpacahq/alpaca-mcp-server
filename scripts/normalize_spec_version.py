"""Clamp the declared OpenAPI version in the bundled specs to one FastMCP accepts.

FastMCP parses specs with openapi-pydantic, whose version field is
``Literal["3.1.1", "3.1.0"]``. Alpaca publishes 3.1.2, which fails validation and
takes the whole server build down with it. 3.1.2 only clarifies wording in the
OpenAPI specification — the document structure is unchanged — so relabelling it
3.1.1 parses correctly.

Only 3.1.x above 3.1.1 is touched. 3.0.x specs parse fine and are left alone.

Delete this script once openapi-pydantic supports 3.1.2.
"""

from __future__ import annotations

import pathlib
import re
import sys

SUPPORTED = {"3.1.0", "3.1.1"}
TARGET = "3.1.1"
SPEC_FILES = ("trading-api.json", "market-data-api.json")
VERSION_RE = re.compile(r'("openapi"\s*:\s*")(3\.1\.\d+)(")')


def normalize(path: pathlib.Path) -> str | None:
    """Rewrite the spec's openapi version if unsupported. Returns the old version."""
    text = path.read_text()
    match = VERSION_RE.search(text)
    if match is None or match.group(2) in SUPPORTED:
        return None

    old = match.group(2)
    path.write_text(VERSION_RE.sub(rf"\g<1>{TARGET}\g<3>", text, count=1))
    return old


def main() -> int:
    specs_dir = pathlib.Path(sys.argv[1])
    for name in SPEC_FILES:
        path = specs_dir / name
        if not path.exists():
            print(f"warning: {name} not found, skipping", file=sys.stderr)
            continue
        old = normalize(path)
        if old:
            print(f"Normalized {name}: openapi {old} -> {TARGET}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
