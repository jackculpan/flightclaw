#!/usr/bin/env python3
# Run with: python3 server.py
"""FlightClaw MCP Server - flight search, tracking, and booking as MCP tools."""

import os
import sys
import urllib.parse
from datetime import datetime, timedelta

# Add scripts dir to path so we can import search_utils
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "scripts"))

from fli.core import (
    build_date_search_segments,
    parse_airlines as fli_parse_airlines,
    parse_cabin_class,
    parse_max_stops,
    resolve_airport,
)
from fli.core.parsers import ParseError
from fli.mcp.server import FliMCP
from fli.models import DateSearchFilters, PassengerInfo, PriceLimit

from helpers import (
    build_filters,
    expand_routes,
    format_duration,
    format_flight,
    parse_airlines,
)
from search_utils import fmt_price, search_with_currency
from tracking import register_tracking_tools

mcp = FliMCP("flightclaw")

BOOKING_BASE_URL = "https://www.google.com/travel/flights/booking?tfs="


@mcp.tool()
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
        sort_by: Sort results by BEST, CHEAPEST, DEPARTURE, ARRIVAL, or DURATION
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


@mcp.tool()
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
    """
    try:
        orig = resolve_airport(origin.strip())
        dest = resolve_airport(destination.strip())
    except ParseError as e:
        return str(e)

    is_round_trip = return_date is not None or trip_duration is not None

    duration = trip_duration
    if return_date and not trip_duration:
        d1 = datetime.strptime(from_date, "%Y-%m-%d").date()
        d2 = datetime.strptime(return_date, "%Y-%m-%d").date()
        duration = (d2 - d1).days

    segments, trip_type = build_date_search_segments(
        origin=orig,
        destination=dest,
        start_date=from_date,
        trip_duration=duration,
        is_round_trip=is_round_trip,
    )

    price_limit = PriceLimit(max_price=max_price) if max_price else None

    from fli.search import SearchDates

    filters = DateSearchFilters(
        trip_type=trip_type,
        passenger_info=PassengerInfo(
            adults=adults, children=children,
            infants_in_seat=infants_in_seat, infants_on_lap=infants_on_lap,
        ),
        flight_segments=segments,
        seat_type=parse_cabin_class(cabin),
        stops=parse_max_stops(stops),
        airlines=parse_airlines(airlines),
        price_limit=price_limit,
        max_duration=max_duration,
        from_date=from_date,
        to_date=to_date,
        duration=duration,
    )

    searcher = SearchDates()
    date_results = searcher.search(filters)

    if not date_results:
        return f"No prices found for {origin} -> {destination} between {from_date} and {to_date}"

    date_results.sort(key=lambda r: r.price)

    output = [f"{origin} -> {destination} cheapest dates ({cabin}):"]
    for r in date_results:
        if isinstance(r.date, tuple) and len(r.date) == 2:
            output.append(f"  {r.date[0].strftime('%Y-%m-%d')} -> {r.date[1].strftime('%Y-%m-%d')}: ${r.price:,.0f}")
        else:
            d = r.date[0] if isinstance(r.date, tuple) else r.date
            output.append(f"  {d.strftime('%Y-%m-%d')}: ${r.price:,.0f}")

    output.append(f"\n{len(date_results)} date(s) found. Cheapest: ${date_results[0].price:,.0f}")
    return "\n".join(output)


@mcp.tool()
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


if __name__ == "__main__":
    mcp.run()
