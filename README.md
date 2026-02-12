# flightclaw

An [OpenClaw](https://github.com/jackculpan/openclaw) skill that tracks flight prices from Google Flights. Search routes, monitor prices over time, and get alerts when prices drop.

## Install

```bash
npx skills add jackculpan/flightclaw
```

Or manually:

```bash
bash skills/flightclaw/setup.sh
```

## Usage

### Search flights
```bash
python skills/flightclaw/scripts/search-flights.py LHR JFK 2025-07-01
python skills/flightclaw/scripts/search-flights.py LHR SFO 2025-06-01 --cabin BUSINESS --stops NON_STOP
python skills/flightclaw/scripts/search-flights.py LHR JFK 2025-07-01 --return-date 2025-07-08

# Multiple airports (searches all combinations)
python skills/flightclaw/scripts/search-flights.py LHR,MAN JFK,EWR 2025-07-01

# Date range
python skills/flightclaw/scripts/search-flights.py LHR JFK 2025-07-01 --date-to 2025-07-05

# Both
python skills/flightclaw/scripts/search-flights.py LHR,MAN JFK,EWR 2025-07-01 --date-to 2025-07-03
```

### Track a route
```bash
python skills/flightclaw/scripts/track-flight.py LHR JFK 2025-07-01 --target-price 400

# Track multiple airports and date ranges at once
python skills/flightclaw/scripts/track-flight.py LHR,MAN JFK,EWR 2025-07-01 --date-to 2025-07-03 --target-price 400
```

### Check for price drops
```bash
python skills/flightclaw/scripts/check-prices.py
python skills/flightclaw/scripts/check-prices.py --threshold 5
```

Set this up on a cron to get regular price alerts via your connected chat channel (Telegram, Discord, Slack).

### List tracked flights
```bash
python skills/flightclaw/scripts/list-tracked.py
```

## How it works

- `search-flights.py` queries Google Flights via the `fli` library and returns prices, airlines, times. Supports comma-separated airports and `--date-to` for date ranges
- `track-flight.py` adds routes to `data/tracked.json` and records initial prices. Same multi-airport/date-range support
- `check-prices.py` re-checks all tracked routes and compares to previous prices. Outputs alerts for significant drops or when target prices are reached
- Prices are returned in the user's local currency based on IP location, auto-detected from the Google Flights API
- Price history persists in `data/tracked.json` and is backed up via R2
