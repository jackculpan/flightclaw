#!/bin/bash
set -e

echo "Installing flightclaw dependencies..."
# Pin fli to a released version for reproducible installs. flights 0.9.0 provides
# the date-search / emissions / bags / basic-economy APIs this server imports.
# fastmcp backs the FastMCP fallback in server.py (fli dropped the FliMCP base class).
pip install "flights==0.9.0" "mcp[cli]" fastmcp
mkdir -p "$(dirname "$0")/data"
echo "Done. flightclaw is ready to use."
