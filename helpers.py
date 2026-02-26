"""Shared helpers for FlightClaw - filters, formatting, data persistence."""

import json
import os
from datetime import datetime, timedelta
from itertools import product

from fli.models import (
    Airport,
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
from search_utils import fmt_price

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


def build_time_restrictions(
    earliest_departure=None, latest_departure=None,
    earliest_arrival=None, latest_arrival=None,
):
    if any(v is not None for v in [earliest_departure, latest_departure, earliest_arrival, latest_arrival]):
        return TimeRestrictions(
            earliest_departure=earliest_departure,
            latest_departure=latest_departure,
            earliest_arrival=earliest_arrival,
            latest_arrival=latest_arrival,
        )
    return None


def build_filters(
    orig_code, dest_code, date, return_date=None, cabin="ECONOMY", stops="ANY",
    adults=1, children=0, infants_in_seat=0, infants_on_lap=0,
    airlines=None, max_price=None, max_duration=None,
    earliest_departure=None, latest_departure=None,
    earliest_arrival=None, latest_arrival=None,
    max_layover_duration=None, sort_by=None,
):
    origin = Airport[orig_code]
    destination = Airport[dest_code]

    time_restrictions = build_time_restrictions(
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
        airlines=parse_airlines(airlines),
        price_limit=price_limit,
        max_duration=max_duration,
        layover_restrictions=layover,
        sort_by=SORT_MAP.get(sort_by, SortBy.NONE),
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
