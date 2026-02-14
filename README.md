# flightclaw

Track flight prices from Google Flights. Search routes, monitor prices over time, and get alerts when prices drop.

## MCP Server

FlightClaw runs as a local [MCP](https://modelcontextprotocol.io) server, giving any MCP-compatible client (Claude Code, Claude Desktop, etc.) access to flight search and tracking tools.

### Setup

```bash
# Install dependencies
pip install flights "mcp[cli]"

# Add to Claude Code
claude mcp add flightclaw -- python3 /path/to/flightclaw/server.py
```

Or in Claude Desktop, add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "flightclaw": {
      "command": "python3",
      "args": ["/path/to/flightclaw/server.py"]
    }
  }
}
```

### Tools

| Tool | Description |
|------|-------------|
| `search_flights` | Search Google Flights for prices on a route |
| `track_flight` | Add a route to price tracking with optional target price |
| `check_prices` | Check all tracked flights for price changes and alerts |
| `list_tracked` | List all tracked flights with price history |
| `remove_tracked` | Remove a route from tracking |

All tools support comma-separated airport codes (e.g. `LHR,MAN`) and date ranges via `date_to` for batch searching.

### Example prompts

- "Search flights from LHR to JFK on 2025-08-01 in business class"
- "Track LHR to SFO on 2025-07-01 with a target price of $400"
- "Check my tracked flights for price drops"
- "List all my tracked flights"

## CLI Scripts

The original CLI scripts are still available in `scripts/`:

```bash
# Search flights
python scripts/search-flights.py LHR JFK 2025-07-01 --cabin BUSINESS

# Multiple airports and date ranges
python scripts/search-flights.py LHR,MAN JFK,EWR 2025-07-01 --date-to 2025-07-05

# Track a route
python scripts/track-flight.py LHR JFK 2025-07-01 --target-price 400

# Check for price drops (good for cron)
python scripts/check-prices.py --threshold 5

# List tracked flights
python scripts/list-tracked.py
```

## How it works

- Queries Google Flights via the `fli` library
- Prices returned in user's local currency (auto-detected from IP)
- Price history persists in `data/tracked.json`
- Supports round trips (`return_date`), cabin classes, stop filters
- Multi-airport and date-range searches expand into all combinations

## Install (OpenClaw)

```bash
npx skills add jackculpan/flightclaw
```
