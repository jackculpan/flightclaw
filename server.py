#!/usr/bin/env python3
# Run with: python3 server.py
"""FlightClaw MCP Server - flight search, tracking, and booking as MCP tools."""

import os
import sys
import urllib.parse
from datetime import datetime, timedelta

# Add scripts dir to path so we can import search_utils
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "scripts"))

from fli.core.parsers import ParseError
from fli.mcp.server import FliMCP

from helpers import (
    build_date_filters,
    build_filters,
    expand_routes,
    format_duration,
    format_flight,
)
from search_utils import fmt_price, search_with_currency
from tracking import register_tracking_tools

mcp = FliMCP("flightclaw")

BOOKING_BASE_URL = "https://www.google.com/travel/flights/booking?tfs="


@mcp.tool(annotations={"readOnlyHint": True, "idempotentHint": True})
def search_flights(
    origin: str,
    destination: str,
    date: str,
    date_to: str | None = None,
    return_date: str | None = None,
    cabin: str = "ECONOMY",
    stops: str = "ANY",
    results: int = 5,
    adults: int = 1,
    children: int = 0,
    infants_in_seat: int = 0,
    infants_on_lap: int = 0,
    airlines: str | None = None,
    max_price: int | None = None,
    max_duration: int | None = None,
    earliest_departure: int | None = None,
    latest_departure: int | None = None,
    earliest_arrival: int | None = None,
    latest_arrival: int | None = None,
    max_layover_duration: int | None = None,
    sort_by: str | None = None,
    exclude_basic_economy: bool = False,
    emissions: str = "ALL",
    checked_bags: int = 0,
    carry_on: bool = False,
    show_all_results: bool = True,
) -> str:
    """Search Google Flights for prices on a route. Returns booking links for each result.

    Args:
        origin: Origin IATA code(s), comma-separated (e.g. LHR or LHR,MAN)
        destination: Destination IATA code(s), comma-separated (e.g. JFK or JFK,EWR)
        date: Departure date (YYYY-MM-DD)
        date_to: End of date range (YYYY-MM-DD), searches each day inclusive
        return_date: Return date for round trips (YYYY-MM-DD)
        cabin: ECONOMY, PREMIUM_ECONOMY, BUSINESS, or FIRST
        stops: ANY, NON_STOP, ONE_STOP, or TWO_STOPS
        results: Number of results per search (default 5)
        adults: Number of adult passengers (default 1)
        children: Number of child passengers (default 0)
        infants_in_seat: Number of infants in seat (default 0)
        infants_on_lap: Number of infants on lap (default 0)
        airlines: Filter to specific airlines, comma-separated IATA codes (e.g. BA,AA,DL)
        max_price: Maximum price in USD
        max_duration: Maximum total flight duration in minutes
        earliest_departure: Earliest departure hour 0-23 (e.g. 8 for 8am)
        latest_departure: Latest departure hour 1-23 (e.g. 20 for 8pm)
        earliest_arrival: Earliest arrival hour 0-23
        latest_arrival: Latest arrival hour 1-23
        max_layover_duration: Maximum layover time in minutes
        sort_by: Sort by TOP_FLIGHTS, BEST, CHEAPEST, DEPARTURE_TIME, ARRIVAL_TIME, DURATION, or EMISSIONS
        exclude_basic_economy: Exclude basic economy fares from results (default false)
        emissions: Filter by emissions: ALL or LESS (default ALL)
        checked_bags: Include checked bag fees in price, 0-2 bags (default 0)
        carry_on: Include carry-on bag fee in price (default false)
        show_all_results: Return all results instead of curated top ~30 (default true)
    """
    combos = expand_routes(origin, destination, date, date_to)
    output = []
    total = 0

    for orig_code, dest_code, d in combos:
        try:
            filters = build_filters(
                orig_code, dest_code, d, return_date, cabin, stops,
                adults, children, infants_in_seat, infants_on_lap,
                airlines, max_price, max_duration,
                earliest_departure, latest_departure,
                earliest_arrival, latest_arrival,
                max_layover_duration, sort_by,
                exclude_basic_economy=exclude_basic_economy,
                emissions=emissions,
                checked_bags=checked_bags,
                carry_on=carry_on,
                show_all_results=show_all_results,
            )
        except (KeyError, ParseError) as e:
            output.append(f"Invalid parameter: {e}")
            continue

        search_results, currency = search_with_currency(filters, top_n=results)

        if not search_results:
            output.append(f"{orig_code} -> {dest_code} on {d}: No flights found")
            continue

        output.append(f"\n{orig_code} -> {dest_code} on {d} ({currency}):")
        is_round_trip = bool(return_date)

        for i, (result, token) in enumerate(search_results[:results], 1):
            if is_round_trip and isinstance(result, tuple):
                outbound, ret = result
                output.append(f"\nOption {i}: {fmt_price(outbound.price + ret.price, currency)} total")
                output.append(f"  Outbound: {format_flight(outbound, currency)}")
                output.append(f"  Return: {format_flight(ret, currency)}")
            else:
                flight = result[0] if isinstance(result, tuple) else result
                output.append(format_flight(flight, currency, index=i))

            if token:
                encoded_token = urllib.parse.quote(token, safe="")
                output.append(f"  Book: {BOOKING_BASE_URL}{encoded_token}")
            total += 1

    if len(combos) > 1:
        output.append(f"\nSearched {len(combos)} route/date combination(s). {total} total result(s).")

    return "\n".join(output)


@mcp.tool(annotations={"readOnlyHint": True, "idempotentHint": True})
def search_dates(
    origin: str,
    destination: str,
    from_date: str,
    to_date: str,
    return_date: str | None = None,
    trip_duration: int | None = None,
    cabin: str = "ECONOMY",
    stops: str = "ANY",
    adults: int = 1,
    children: int = 0,
    infants_in_seat: int = 0,
    infants_on_lap: int = 0,
    airlines: str | None = None,
    max_price: int | None = None,
    max_duration: int | None = None,
    earliest_departure: int | None = None,
    latest_departure: int | None = None,
    earliest_arrival: int | None = None,
    latest_arrival: int | None = None,
    emissions: str = "ALL",
    checked_bags: int = 0,
    carry_on: bool = False,
) -> str:
    """Find the cheapest dates to fly across a date range (calendar view).

    Args:
        origin: Origin IATA code (e.g. LHR)
        destination: Destination IATA code (e.g. JFK)
        from_date: Start of date range (YYYY-MM-DD)
        to_date: End of date range (YYYY-MM-DD)
        return_date: Return date for round trips (YYYY-MM-DD). Use trip_duration instead for flexible returns.
        trip_duration: Number of days between outbound and return (e.g. 7 for a week). Makes this a round-trip search.
        cabin: ECONOMY, PREMIUM_ECONOMY, BUSINESS, or FIRST
        stops: ANY, NON_STOP, ONE_STOP, or TWO_STOPS
        adults: Number of adult passengers (default 1)
        children: Number of child passengers (default 0)
        infants_in_seat: Number of infants in seat (default 0)
        infants_on_lap: Number of infants on lap (default 0)
        airlines: Filter to specific airlines, comma-separated IATA codes (e.g. BA,AA,DL)
        max_price: Maximum price in USD
        max_duration: Maximum total flight duration in minutes
        earliest_departure: Earliest departure hour 0-23 (e.g. 8 for 8am)
        latest_departure: Latest departure hour 1-23 (e.g. 20 for 8pm)
        earliest_arrival: Earliest arrival hour 0-23
        latest_arrival: Latest arrival hour 1-23
        emissions: Filter by emissions: ALL or LESS (default ALL)
        checked_bags: Include checked bag fees in price, 0-2 bags (default 0)
        carry_on: Include carry-on bag fee in price (default false)
    """
    is_round_trip = return_date is not None or trip_duration is not None

    duration = trip_duration
    if return_date and not trip_duration:
        d1 = datetime.strptime(from_date, "%Y-%m-%d").date()
        d2 = datetime.strptime(return_date, "%Y-%m-%d").date()
        duration = (d2 - d1).days

    try:
        filters = build_date_filters(
            origin.strip().upper(), destination.strip().upper(),
            from_date, to_date,
            duration=duration, is_round_trip=is_round_trip,
            cabin=cabin, stops=stops,
            adults=adults, children=children,
            infants_in_seat=infants_in_seat, infants_on_lap=infants_on_lap,
            airlines=airlines, max_price=max_price, max_duration=max_duration,
            earliest_departure=earliest_departure, latest_departure=latest_departure,
            earliest_arrival=earliest_arrival, latest_arrival=latest_arrival,
            emissions=emissions, checked_bags=checked_bags, carry_on=carry_on,
        )
    except (KeyError, ParseError) as e:
        return f"Invalid parameter: {e}"

    from fli.search import SearchDates

    searcher = SearchDates()
    date_results = searcher.search(filters)

    if not date_results:
        return f"No prices found for {origin} -> {destination} between {from_date} and {to_date}"

    date_results.sort(key=lambda r: r.price)

    # Use currency from first result if available
    currency = getattr(date_results[0], "currency", None) or "USD"

    output = [f"{origin} -> {destination} cheapest dates ({cabin}, {currency}):"]
    for r in date_results:
        cur = getattr(r, "currency", None) or currency
        if isinstance(r.date, tuple) and len(r.date) == 2:
            output.append(f"  {r.date[0].strftime('%Y-%m-%d')} -> {r.date[1].strftime('%Y-%m-%d')}: {fmt_price(r.price, cur)}")
        else:
            d = r.date[0] if isinstance(r.date, tuple) else r.date
            output.append(f"  {d.strftime('%Y-%m-%d')}: {fmt_price(r.price, cur)}")

    output.append(f"\n{len(date_results)} date(s) found. Cheapest: {fmt_price(date_results[0].price, currency)}")
    return "\n".join(output)


@mcp.tool(annotations={"readOnlyHint": True, "idempotentHint": True})
def book_flight(
    booking_token: str,
    passenger_first_name: str | None = None,
    passenger_last_name: str | None = None,
    passenger_email: str | None = None,
    passenger_phone: str | None = None,
) -> str:
    """Open a Google Flights booking page for a specific flight. Use after search_flights.

    The booking_token comes from the "Book:" URL in search results (the part after fli=).
    After calling this tool, use Chrome browser automation to navigate to the URL and
    complete the booking.

    Args:
        booking_token: The booking token from search results (from the Book URL)
        passenger_first_name: Passenger's first name (optional, for form filling)
        passenger_last_name: Passenger's last name (optional, for form filling)
        passenger_email: Contact email (optional, for form filling)
        passenger_phone: Contact phone number (optional, for form filling)
    """
    encoded_token = urllib.parse.quote(booking_token, safe="")
    booking_url = f"{BOOKING_BASE_URL}{encoded_token}"

    lines = [f"Booking URL: {booking_url}", ""]
    lines.append("To complete this booking, use Chrome automation to:")
    lines.append("1. Navigate to the booking URL above")
    lines.append("2. Select a booking option from the available airlines/OTAs")

    if any([passenger_first_name, passenger_last_name, passenger_email, passenger_phone]):
        lines.append("3. Fill in passenger details:")
        if passenger_first_name:
            lines.append(f"   - First name: {passenger_first_name}")
        if passenger_last_name:
            lines.append(f"   - Last name: {passenger_last_name}")
        if passenger_email:
            lines.append(f"   - Email: {passenger_email}")
        if passenger_phone:
            lines.append(f"   - Phone: {passenger_phone}")
        lines.append("4. Proceed to payment page and confirm with user before paying")
    else:
        lines.append("3. Proceed through booking flow to payment")
        lines.append("4. Confirm with user before completing payment")

    return "\n".join(lines)


# Register tracking tools on our mcp instance
register_tracking_tools(mcp)

# Register Duffel tools if API wrapper is configured
from duffel_api import is_configured as duffel_configured
if duffel_configured():
    from duffel_tools import register_duffel_tools
    register_duffel_tools(mcp)


from passenger_profiles import register_passenger_tools
register_passenger_tools(mcp)


# =============================================================================
# Prompts
# =============================================================================

from mcp.types import PromptArgument, PromptMessage, TextContent

mcp.add_prompt(
    name="search-route",
    description="Search for flights on a specific route and date.",
    arguments=[
        PromptArgument(name="origin", description="Departure airport IATA code", required=True),
        PromptArgument(name="destination", description="Arrival airport IATA code", required=True),
        PromptArgument(name="date", description="Departure date (YYYY-MM-DD)", required=True),
        PromptArgument(name="return_date", description="Return date (YYYY-MM-DD)", required=False),
    ],
    build_messages=lambda args: [
        PromptMessage(
            role="user",
            content=TextContent(
                type="text",
                text=(
                    f"Search for flights from {args.get('origin', 'LHR')} to {args.get('destination', 'JFK')} "
                    f"on {args.get('date', 'tomorrow')}"
                    + (f" returning {args['return_date']}" if args.get("return_date") else "")
                    + ". Show the cheapest options with booking links."
                ),
            ),
        ),
    ],
)

mcp.add_prompt(
    name="find-cheapest-dates",
    description="Find the cheapest dates to fly on a route within a date range.",
    arguments=[
        PromptArgument(name="origin", description="Departure airport IATA code", required=True),
        PromptArgument(name="destination", description="Arrival airport IATA code", required=True),
        PromptArgument(name="from_date", description="Start of date range (YYYY-MM-DD)", required=True),
        PromptArgument(name="to_date", description="End of date range (YYYY-MM-DD)", required=True),
        PromptArgument(name="trip_duration", description="Trip length in days for round trips", required=False),
    ],
    build_messages=lambda args: [
        PromptMessage(
            role="user",
            content=TextContent(
                type="text",
                text=(
                    f"Find the cheapest dates to fly from {args.get('origin', 'LHR')} to {args.get('destination', 'JFK')} "
                    f"between {args.get('from_date')} and {args.get('to_date')}"
                    + (f" with a trip duration of {args['trip_duration']} days" if args.get("trip_duration") else "")
                    + ". Sort by price and highlight the best deals."
                ),
            ),
        ),
    ],
)

mcp.add_prompt(
    name="track-and-alert",
    description="Set up price tracking on a route with a target price alert.",
    arguments=[
        PromptArgument(name="origin", description="Departure airport IATA code", required=True),
        PromptArgument(name="destination", description="Arrival airport IATA code", required=True),
        PromptArgument(name="date", description="Departure date (YYYY-MM-DD)", required=True),
        PromptArgument(name="target_price", description="Target price to alert on", required=False),
    ],
    build_messages=lambda args: [
        PromptMessage(
            role="user",
            content=TextContent(
                type="text",
                text=(
                    f"Track the price of flights from {args.get('origin', 'LHR')} to {args.get('destination', 'JFK')} "
                    f"on {args.get('date')}"
                    + (f" and alert me when the price drops below {args['target_price']}" if args.get("target_price") else "")
                    + ". Show the current price after setting up tracking."
                ),
            ),
        ),
    ],
)


# =============================================================================
# Resources
# =============================================================================

import json
from helpers import load_tracked

@mcp.resource(
    "resource://flightclaw/tracked-flights",
    name="Tracked Flights",
    description="All currently tracked flights with price history.",
    mime_type="application/json",
)
def tracked_flights_resource() -> str:
    tracked = load_tracked()
    return json.dumps(tracked, indent=2)


@mcp.resource(
    "resource://flightclaw/price-alerts",
    name="Price Alerts",
    description="Flights that have hit their target price or dropped significantly.",
    mime_type="application/json",
)
def price_alerts_resource() -> str:
    tracked = load_tracked()
    alerts = []
    for entry in tracked:
        history = entry.get("price_history", [])
        if not history:
            continue
        current = history[-1].get("best_price")
        if current is None:
            continue
        target = entry.get("target_price")
        if target and current <= target:
            alerts.append({
                "type": "target_reached",
                "route": f"{entry['origin']} -> {entry['destination']}",
                "date": entry["date"],
                "current_price": current,
                "target_price": target,
                "currency": entry.get("currency", "USD"),
            })
        prices = [p["best_price"] for p in history if p.get("best_price")]
        if len(prices) >= 2:
            prev = prices[-2]
            change_pct = ((current - prev) / prev) * 100
            if change_pct <= -10:
                alerts.append({
                    "type": "price_drop",
                    "route": f"{entry['origin']} -> {entry['destination']}",
                    "date": entry["date"],
                    "current_price": current,
                    "previous_price": prev,
                    "change_pct": round(change_pct, 1),
                    "currency": entry.get("currency", "USD"),
                })
    return json.dumps(alerts, indent=2)


if __name__ == "__main__":
    import sys

    if "--http" in sys.argv:
        host = os.environ.get("HOST", "127.0.0.1")
        port = int(os.environ.get("PORT", "8000"))
        mcp.run(transport="http", host=host, port=port)
    else:
        mcp.run()
