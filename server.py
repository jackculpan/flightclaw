#!/usr/bin/env python3
# Run with: python3 server.py
"""FlightClaw MCP Server - expose flight search and tracking as MCP tools."""

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from itertools import product

from mcp.server.fastmcp import FastMCP

# Add scripts dir to path so we can import search_utils
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "scripts"))

from fli.models import (
    Airport,
    DateSearchFilters,
    FlightSearchFilters,
    FlightSegment,
    LayoverRestrictions,
    MaxStops,
    PassengerInfo,
    PriceLimit,
    SeatType,
    SortBy,
    TimeRestrictions,
    TripType,
)
from fli.models.google_flights.base import Airline
from fli.search import SearchDates
from search_utils import fmt_price, search_with_currency

mcp = FastMCP("flightclaw")

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
TRACKED_FILE = os.path.join(DATA_DIR, "tracked.json")

SEAT_MAP = {
    "ECONOMY": SeatType.ECONOMY,
    "PREMIUM_ECONOMY": SeatType.PREMIUM_ECONOMY,
    "BUSINESS": SeatType.BUSINESS,
    "FIRST": SeatType.FIRST,
}

STOPS_MAP = {
    "ANY": MaxStops.ANY,
    "NON_STOP": MaxStops.NON_STOP,
    "ONE_STOP": MaxStops.ONE_STOP_OR_FEWER,
    "TWO_STOPS": MaxStops.TWO_OR_FEWER_STOPS,
}

SORT_MAP = {
    "BEST": SortBy.TOP_FLIGHTS,
    "CHEAPEST": SortBy.CHEAPEST,
    "DEPARTURE": SortBy.DEPARTURE_TIME,
    "ARRIVAL": SortBy.ARRIVAL_TIME,
    "DURATION": SortBy.DURATION,
}


def _load_tracked():
    if os.path.exists(TRACKED_FILE):
        with open(TRACKED_FILE, "r") as f:
            return json.load(f)
    return []


def _save_tracked(tracked):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(TRACKED_FILE, "w") as f:
        json.dump(tracked, f, indent=2)


def _expand_routes(origins_str, destinations_str, date_str, date_to_str=None):
    origins = [o.strip().upper() for o in origins_str.split(",")]
    destinations = [d.strip().upper() for d in destinations_str.split(",")]
    start = datetime.strptime(date_str, "%Y-%m-%d").date()
    end = datetime.strptime(date_to_str, "%Y-%m-%d").date() if date_to_str else start
    dates = []
    current = start
    while current <= end:
        dates.append(current.strftime("%Y-%m-%d"))
        current += timedelta(days=1)
    return list(product(origins, destinations, dates))


def _parse_airlines(airlines_str):
    """Parse comma-separated airline codes into Airline enums."""
    if not airlines_str:
        return None
    codes = [c.strip().upper() for c in airlines_str.split(",")]
    result = []
    for code in codes:
        try:
            result.append(Airline[code])
        except KeyError:
            pass
    return result or None


def _build_time_restrictions(
    earliest_departure=None, latest_departure=None,
    earliest_arrival=None, latest_arrival=None,
):
    """Build TimeRestrictions if any time params are set."""
    if any(v is not None for v in [earliest_departure, latest_departure, earliest_arrival, latest_arrival]):
        return TimeRestrictions(
            earliest_departure=earliest_departure,
            latest_departure=latest_departure,
            earliest_arrival=earliest_arrival,
            latest_arrival=latest_arrival,
        )
    return None


def _build_filters(
    orig_code, dest_code, date, return_date=None, cabin="ECONOMY", stops="ANY",
    adults=1, children=0, infants_in_seat=0, infants_on_lap=0,
    airlines=None, max_price=None, max_duration=None,
    earliest_departure=None, latest_departure=None,
    earliest_arrival=None, latest_arrival=None,
    max_layover_duration=None, sort_by=None,
):
    origin = Airport[orig_code]
    destination = Airport[dest_code]

    time_restrictions = _build_time_restrictions(
        earliest_departure, latest_departure, earliest_arrival, latest_arrival,
    )

    segments = [FlightSegment(
        departure_airport=[[origin, 0]],
        arrival_airport=[[destination, 0]],
        travel_date=date,
        time_restrictions=time_restrictions,
    )]
    trip_type = TripType.ONE_WAY
    if return_date:
        segments.append(FlightSegment(
            departure_airport=[[destination, 0]],
            arrival_airport=[[origin, 0]],
            travel_date=return_date,
            time_restrictions=time_restrictions,
        ))
        trip_type = TripType.ROUND_TRIP

    price_limit = PriceLimit(max_price=max_price) if max_price else None
    layover = LayoverRestrictions(max_duration=max_layover_duration) if max_layover_duration else None

    return FlightSearchFilters(
        trip_type=trip_type,
        passenger_info=PassengerInfo(
            adults=adults, children=children,
            infants_in_seat=infants_in_seat, infants_on_lap=infants_on_lap,
        ),
        flight_segments=segments,
        seat_type=SEAT_MAP.get(cabin, SeatType.ECONOMY),
        stops=STOPS_MAP.get(stops, MaxStops.ANY),
        airlines=_parse_airlines(airlines),
        price_limit=price_limit,
        max_duration=max_duration,
        layover_restrictions=layover,
        sort_by=SORT_MAP.get(sort_by, SortBy.NONE),
    )


def _format_duration(minutes):
    h, m = divmod(minutes, 60)
    return f"{h}h {m}m"


def _format_flight(flight, currency, index=None):
    prefix = f"Option {index}: " if index else ""
    lines = [f"{prefix}{fmt_price(flight.price, currency)} | {_format_duration(flight.duration)} | {flight.stops} stop(s)"]
    for leg in flight.legs:
        lines.append(f"  {leg.airline.name} {leg.flight_number}: {leg.departure_airport.name} {leg.departure_datetime.strftime('%H:%M')} -> {leg.arrival_airport.name} {leg.arrival_datetime.strftime('%H:%M')}")
    return "\n".join(lines)


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
    """Search Google Flights for prices on a route.

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
    combos = _expand_routes(origin, destination, date, date_to)
    output = []
    total = 0

    for orig_code, dest_code, d in combos:
        try:
            filters = _build_filters(
                orig_code, dest_code, d, return_date, cabin, stops,
                adults, children, infants_in_seat, infants_on_lap,
                airlines, max_price, max_duration,
                earliest_departure, latest_departure,
                earliest_arrival, latest_arrival,
                max_layover_duration, sort_by,
            )
        except KeyError as e:
            output.append(f"Unknown airport code: {e}")
            continue

        search_results, currency = search_with_currency(filters, top_n=results)

        if not search_results:
            output.append(f"{orig_code} -> {dest_code} on {d}: No flights found")
            continue

        output.append(f"\n{orig_code} -> {dest_code} on {d} ({currency}):")
        is_round_trip = bool(return_date)

        for i, result in enumerate(search_results[:results], 1):
            if is_round_trip and isinstance(result, tuple):
                outbound, ret = result
                output.append(f"\nOption {i}: {fmt_price(outbound.price + ret.price, currency)} total")
                output.append(f"  Outbound: {_format_flight(outbound, currency)}")
                output.append(f"  Return: {_format_flight(ret, currency)}")
            else:
                flight = result[0] if isinstance(result, tuple) else result
                output.append(_format_flight(flight, currency, index=i))
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
        orig = Airport[origin.strip().upper()]
        dest = Airport[destination.strip().upper()]
    except KeyError as e:
        return f"Unknown airport code: {e}"

    is_round_trip = return_date is not None or trip_duration is not None
    trip_type = TripType.ROUND_TRIP if is_round_trip else TripType.ONE_WAY

    # For round trip with fixed return_date, calculate duration
    duration = trip_duration
    if return_date and not trip_duration:
        d1 = datetime.strptime(from_date, "%Y-%m-%d").date()
        d2 = datetime.strptime(return_date, "%Y-%m-%d").date()
        duration = (d2 - d1).days

    segments = [FlightSegment(
        departure_airport=[[orig, 0]],
        arrival_airport=[[dest, 0]],
        travel_date=from_date,
    )]
    if is_round_trip:
        ret_date = return_date or (datetime.strptime(from_date, "%Y-%m-%d") + timedelta(days=duration)).strftime("%Y-%m-%d")
        segments.append(FlightSegment(
            departure_airport=[[dest, 0]],
            arrival_airport=[[orig, 0]],
            travel_date=ret_date,
        ))

    price_limit = PriceLimit(max_price=max_price) if max_price else None

    filters = DateSearchFilters(
        trip_type=trip_type,
        passenger_info=PassengerInfo(
            adults=adults, children=children,
            infants_in_seat=infants_in_seat, infants_on_lap=infants_on_lap,
        ),
        flight_segments=segments,
        seat_type=SEAT_MAP.get(cabin, SeatType.ECONOMY),
        stops=STOPS_MAP.get(stops, MaxStops.ANY),
        airlines=_parse_airlines(airlines),
        price_limit=price_limit,
        max_duration=max_duration,
        from_date=from_date,
        to_date=to_date,
        duration=duration,
    )

    searcher = SearchDates()
    results = searcher.search(filters)

    if not results:
        return f"No prices found for {origin} -> {destination} between {from_date} and {to_date}"

    # Sort by price
    results.sort(key=lambda r: r.price)

    output = [f"{origin} -> {destination} cheapest dates ({cabin}):"]
    for r in results:
        if isinstance(r.date, tuple) and len(r.date) == 2:
            output.append(f"  {r.date[0].strftime('%Y-%m-%d')} -> {r.date[1].strftime('%Y-%m-%d')}: ${r.price:,.0f}")
        else:
            d = r.date[0] if isinstance(r.date, tuple) else r.date
            output.append(f"  {d.strftime('%Y-%m-%d')}: ${r.price:,.0f}")

    output.append(f"\n{len(results)} date(s) found. Cheapest: ${results[0].price:,.0f}")
    return "\n".join(output)


@mcp.tool()
def track_flight(
    origin: str,
    destination: str,
    date: str,
    date_to: str | None = None,
    return_date: str | None = None,
    cabin: str = "ECONOMY",
    stops: str = "ANY",
    target_price: float | None = None,
    adults: int = 1,
    children: int = 0,
    infants_in_seat: int = 0,
    infants_on_lap: int = 0,
    airlines: str | None = None,
    max_price: int | None = None,
    max_duration: int | None = None,
) -> str:
    """Add a flight route to price tracking. Records current price and monitors for drops.

    Args:
        origin: Origin IATA code(s), comma-separated (e.g. LHR or LHR,MAN)
        destination: Destination IATA code(s), comma-separated (e.g. JFK or JFK,EWR)
        date: Departure date (YYYY-MM-DD)
        date_to: End of date range (YYYY-MM-DD), tracks each day inclusive
        return_date: Return date for round trips (YYYY-MM-DD)
        cabin: ECONOMY, PREMIUM_ECONOMY, BUSINESS, or FIRST
        stops: ANY, NON_STOP, ONE_STOP, or TWO_STOPS
        target_price: Alert when price drops below this amount
        adults: Number of adult passengers (default 1)
        children: Number of child passengers (default 0)
        infants_in_seat: Number of infants in seat (default 0)
        infants_on_lap: Number of infants on lap (default 0)
        airlines: Filter to specific airlines, comma-separated IATA codes (e.g. BA,AA,DL)
        max_price: Maximum price in USD
        max_duration: Maximum total flight duration in minutes
    """
    combos = _expand_routes(origin, destination, date, date_to)
    tracked = _load_tracked()
    output = []
    added = 0
    skipped = 0

    for orig_code, dest_code, d in combos:
        route_id = f"{orig_code}-{dest_code}-{d}"
        if return_date:
            route_id += f"-RT-{return_date}"

        if any(t["id"] == route_id for t in tracked):
            output.append(f"Already tracking {route_id}")
            skipped += 1
            continue

        try:
            filters = _build_filters(
                orig_code, dest_code, d, return_date, cabin, stops,
                adults, children, infants_in_seat, infants_on_lap,
                airlines, max_price, max_duration,
            )
        except KeyError as e:
            output.append(f"Unknown airport code: {e}")
            continue

        results, currency = search_with_currency(filters, top_n=1)

        now = datetime.now(timezone.utc).isoformat()
        price_entry = {"timestamp": now, "best_price": None, "airline": None}

        if results:
            flight = results[0]
            if isinstance(flight, tuple):
                flight = flight[0]
            price_entry["best_price"] = round(flight.price, 2)
            if flight.legs:
                price_entry["airline"] = flight.legs[0].airline.name

        entry = {
            "id": route_id,
            "origin": orig_code,
            "destination": dest_code,
            "date": d,
            "return_date": return_date,
            "cabin": cabin,
            "stops": stops,
            "target_price": target_price,
            "currency": currency,
            "added_at": now,
            "price_history": [price_entry],
        }

        tracked.append(entry)
        added += 1

        if price_entry["best_price"]:
            output.append(f"Tracking {route_id}: {fmt_price(price_entry['best_price'], currency)} ({price_entry['airline']})")
        else:
            output.append(f"Tracking {route_id}: no price found")

    _save_tracked(tracked)

    summary = f"\n{added} new route(s) tracked."
    if skipped:
        summary += f" {skipped} already tracked."
    if target_price:
        output.append(f"Target price: {fmt_price(target_price, currency)}")
    output.append(summary)
    return "\n".join(output)


@mcp.tool()
def check_prices(threshold: float = 10.0) -> str:
    """Check all tracked flights for price changes and generate alerts.

    Args:
        threshold: Percentage drop to trigger alert (default 10)
    """
    tracked = _load_tracked()
    if not tracked:
        return "No flights being tracked. Use track_flight to add routes."

    now = datetime.now(timezone.utc).isoformat()
    output = []
    alerts = []

    for entry in tracked:
        route = f"{entry['origin']} -> {entry['destination']} on {entry['date']}"
        currency = entry.get("currency", "USD")

        try:
            filters = _build_filters(
                entry["origin"], entry["destination"], entry["date"],
                entry.get("return_date"), entry.get("cabin", "ECONOMY"), entry.get("stops", "ANY"),
            )
            results, detected_currency = search_with_currency(filters, top_n=1)
            currency = detected_currency or currency
        except Exception as e:
            output.append(f"{route}: Error - {e}")
            continue

        if not results:
            output.append(f"{route}: No results found")
            continue

        flight = results[0]
        if isinstance(flight, tuple):
            flight = flight[0]
        price = round(flight.price, 2)
        airline = flight.legs[0].airline.name if flight.legs else None

        entry["price_history"].append({"timestamp": now, "best_price": price, "airline": airline})
        entry["currency"] = currency

        prev_prices = [p["best_price"] for p in entry["price_history"][:-1] if p["best_price"]]
        if prev_prices:
            last_price = prev_prices[-1]
            change = price - last_price
            pct = (change / last_price) * 100

            if change < 0:
                output.append(f"{route}: {fmt_price(price, currency)} ({airline}) - DOWN {fmt_price(abs(change), currency)} ({abs(pct):.1f}%)")
                if abs(pct) >= threshold:
                    alerts.append(f"PRICE DROP: {route} is now {fmt_price(price, currency)} (was {fmt_price(last_price, currency)}, down {abs(pct):.1f}%)")
            elif change > 0:
                output.append(f"{route}: {fmt_price(price, currency)} ({airline}) - up {fmt_price(change, currency)} ({pct:.1f}%)")
            else:
                output.append(f"{route}: {fmt_price(price, currency)} ({airline}) - no change")
        else:
            output.append(f"{route}: {fmt_price(price, currency)} ({airline}) - first price recorded")

        if entry.get("target_price") and price <= entry["target_price"]:
            alerts.append(f"TARGET REACHED: {route} is {fmt_price(price, currency)} (target: {fmt_price(entry['target_price'], currency)})")

    _save_tracked(tracked)

    if alerts:
        output.append("\nALERTS:")
        output.extend(f"  {a}" for a in alerts)

    return "\n".join(output)


@mcp.tool()
def list_tracked() -> str:
    """List all tracked flights with current prices and history summary."""
    tracked = _load_tracked()
    if not tracked:
        return "No flights being tracked. Use track_flight to add routes."

    output = []
    for entry in tracked:
        route = f"{entry['origin']} -> {entry['destination']}"
        cabin = entry.get("cabin", "ECONOMY")
        currency = entry.get("currency", "USD")
        line = f"{route} | {entry['date']} | {cabin} | {currency}"
        if entry.get("return_date"):
            line += f" | Return: {entry['return_date']}"
        if entry.get("target_price"):
            line += f" | Target: {fmt_price(entry['target_price'], currency)}"

        history = entry.get("price_history", [])
        if history:
            first_price = next((p["best_price"] for p in history if p["best_price"]), None)
            last = history[-1]
            current_price = last.get("best_price")

            if current_price and first_price:
                change = current_price - first_price
                pct = (change / first_price) * 100
                direction = "down" if change < 0 else "up"
                line += f"\n  Current: {fmt_price(current_price, currency)} ({last.get('airline', '?')}) | Original: {fmt_price(first_price, currency)} | {direction} {fmt_price(abs(change), currency)} ({abs(pct):.1f}%)"
            elif current_price:
                line += f"\n  Current: {fmt_price(current_price, currency)} ({last.get('airline', '?')})"

            line += f"\n  Checks: {len(history)} | Since: {entry.get('added_at', '?')[:10]}"
        else:
            line += "\n  No price data yet"

        output.append(line)

    output.append(f"\n{len(tracked)} flight(s) tracked.")
    return "\n".join(output)


@mcp.tool()
def remove_tracked(route_id: str) -> str:
    """Remove a flight from the tracking list.

    Args:
        route_id: The route ID to remove (e.g. LHR-JFK-2025-07-01). Use list_tracked to see IDs.
    """
    tracked = _load_tracked()
    before = len(tracked)
    tracked = [t for t in tracked if t["id"] != route_id]

    if len(tracked) == before:
        return f"Route {route_id} not found. Use list_tracked to see tracked routes."

    _save_tracked(tracked)
    return f"Removed {route_id}. {len(tracked)} route(s) remaining."


if __name__ == "__main__":
    mcp.run()
