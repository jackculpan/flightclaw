#!/bin/bash
set -e

echo "Installing flightclaw dependencies..."
pip install flights "mcp[cli]"
mkdir -p "$(dirname "$0")/data"
echo "Done. flightclaw is ready to use."
