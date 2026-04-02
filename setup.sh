#!/bin/bash
set -e

echo "Installing flightclaw dependencies..."
pip install "flights>=0.8.0" "mcp[cli]"
mkdir -p "$(dirname "$0")/data"
echo "Done. flightclaw is ready to use."
