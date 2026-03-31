"""Shared helpers for FlightClaw - filters, formatting, data persistence."""

import json
import os
from datetime import datetime, timedelta
from itertools import product

from fli.core import (
    build_flight_segments,
    build_time_restrictions,
    parse_airlines as fli_parse_airlines,
    parse_cabin_class,
    parse_max_stops,
    parse_sort_by,
    resolve_airport,
)
from fli.core.parsers import ParseError
from fli.models import (
    FlightSearchFilters,
    LayoverRestrictions,
    PassengerInfo,
    PriceLimit,
    SortBy,
)

from search_utils import fmt_price

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
TRACKED_FILE = os.path.join(DATA_DIR, "tracked.json")


def load_tracked():
    if os.path.exists(TRACKED_FILE):
        with open(TRACKED_FILE, "r") as f:
            return json.load(f)
    return []


def save_tracked(tracked):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(TRACKED_FILE, "w") as f:
        json.dump(tracked, f, indent=2)


def expand_routes(origins_str, destinations_str, date_str, date_to_str=None):
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


def parse_airlines(airlines_str):
    """Parse comma-separated airline codes string into Airline enums."""
    if not airlines_str:
        return None
    codes = [c.strip().upper() for c in airlines_str.split(",")]
    try:
        return fli_parse_airlines(codes)
    except ParseError:
        # Silently skip invalid codes for backwards compat
        from fli.models import Airline
        result = []
        for code in codes:
            try:
                result.append(getattr(Airline, code))
            except AttributeError:
                pass
        return result or None


def _build_departure_window(earliest_departure, latest_departure):
    """Convert individual hour ints to 'HH-HH' window string."""
    if earliest_departure is not None and latest_departure is not None:
        return f"{earliest_departure}-{latest_departure}"
    if earliest_departure is not None:
        return f"{earliest_departure}-23"
    if latest_departure is not None:
        return f"0-{latest_departure}"
    return None


def build_filters(
    orig_code, dest_code, date, return_date=None, cabin="ECONOMY", stops="ANY",
    adults=1, children=0, infants_in_seat=0, infants_on_lap=0,
    airlines=None, max_price=None, max_duration=None,
    earliest_departure=None, latest_departure=None,
    earliest_arrival=None, latest_arrival=None,
    max_layover_duration=None, sort_by=None,
):
    origin = resolve_airport(orig_code)
    destination = resolve_airport(dest_code)

    dep_window = _build_departure_window(earliest_departure, latest_departure)
    arr_window = _build_departure_window(earliest_arrival, latest_arrival)
    time_restrictions = build_time_restrictions(dep_window, arr_window)

    segments, trip_type = build_flight_segments(
        origin=origin,
        destination=destination,
        departure_date=date,
        return_date=return_date,
        time_restrictions=time_restrictions,
    )

    price_limit = PriceLimit(max_price=max_price) if max_price else None
    layover = LayoverRestrictions(max_duration=max_layover_duration) if max_layover_duration else None

    return FlightSearchFilters(
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
        layover_restrictions=layover,
        sort_by=parse_sort_by(sort_by) if sort_by else SortBy.NONE,
    )


def format_duration(minutes):
    h, m = divmod(minutes, 60)
    return f"{h}h {m}m"


def format_flight(flight, currency, index=None):
    prefix = f"Option {index}: " if index else ""
    lines = [f"{prefix}{fmt_price(flight.price, currency)} | {format_duration(flight.duration)} | {flight.stops} stop(s)"]
    for leg in flight.legs:
        lines.append(f"  {leg.airline.name} {leg.flight_number}: {leg.departure_airport.name} {leg.departure_datetime.strftime('%H:%M')} -> {leg.arrival_airport.name} {leg.arrival_datetime.strftime('%H:%M')}")
    return "\n".join(lines)
