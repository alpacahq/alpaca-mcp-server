#!/bin/bash
set -e
SPECS_DIR="$(dirname "$0")/../src/alpaca_mcp_server/specs"
curl -sL https://docs.alpaca.markets/openapi/trading-api.json -o "$SPECS_DIR/trading-api.json"
curl -sL https://docs.alpaca.markets/openapi/market-data-api.json -o "$SPECS_DIR/market-data-api.json"
echo "Specs updated. Run 'git diff' to see changes."
