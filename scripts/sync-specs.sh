#!/bin/bash
set -e
SPECS_DIR="$(dirname "$0")/../src/alpaca_mcp_server/specs"
curl -sL https://docs.alpaca.markets/openapi/trading-api.json -o "$SPECS_DIR/trading-api.json"
curl -sL https://docs.alpaca.markets/openapi/market-data-api.json -o "$SPECS_DIR/market-data-api.json"

# Alpaca publishes OpenAPI 3.1.2. FastMCP parses specs with openapi-pydantic,
# which accepts only 3.1.0 and 3.1.1 and rejects anything else outright, so the
# server builds zero tools. 3.1.2 only clarifies wording in the OpenAPI
# specification and leaves the document structure unchanged, so it parses
# correctly as 3.1.1. Remove once openapi-pydantic supports 3.1.2.
perl -pi -e 's/"openapi":"3\.1\.[2-9]"/"openapi":"3.1.1"/' \
  "$SPECS_DIR/trading-api.json" "$SPECS_DIR/market-data-api.json"

echo "Specs updated. Run 'git diff' to see changes."
