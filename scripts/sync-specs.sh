#!/bin/bash
set -e
SPECS_DIR="$(dirname "$0")/../src/alpaca_mcp_server/specs"
curl -sL https://docs.alpaca.markets/openapi/trading-api.json -o "$SPECS_DIR/trading-api.json"
curl -sL https://docs.alpaca.markets/openapi/market-data-api.json -o "$SPECS_DIR/market-data-api.json"

# Alpaca publishes OpenAPI 3.1.2. FastMCP parses specs with openapi-pydantic,
# which accepts only 3.1.0 and 3.1.1 and rejects anything else outright, so the
# server fails to build. 3.1.2 is a clarifying patch release of the OpenAPI
# spec with no structural changes, so declaring 3.1.1 parses correctly.
# Remove this once openapi-pydantic supports 3.1.2.
python3 "$(dirname "$0")/normalize_spec_version.py" "$SPECS_DIR"

echo "Specs updated. Run 'git diff' to see changes."
