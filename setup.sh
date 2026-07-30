#!/bin/bash
set -e

echo "Installing flightclaw dependencies..."
# Pin fli to a released version for reproducible installs. flights 0.9.0 provides
# the date-search / emissions / bags / basic-economy APIs this server imports.
# fastmcp backs the FastMCP fallback in server.py (fli dropped the FliMCP base class).
#
# mcp is capped below 2.0: that release renamed McpError -> MCPError, which fastmcp
# still imports under the old name. fastmcp asks only for mcp>=1.24.0, so an
# uncapped install silently resolves to 2.x and the server dies on import.
#
# pydantic-settings is listed explicitly for the benefit of existing fastmcp 2.14.x
# environments: that version imports it without declaring it, and relied on it
# arriving transitively via mcp[cli]. fastmcp 3.x declares it properly (via
# fastmcp-slim), so this is a no-op on a fresh install.
pip install "flights==0.9.0" "mcp[cli]>=1.24,<2" fastmcp pydantic-settings
mkdir -p "$(dirname "$0")/data"
echo "Done. flightclaw is ready to use."
