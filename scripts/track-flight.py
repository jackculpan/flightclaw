#!/usr/bin/env python3
"""Add a flight route to the price tracking list."""

import argparse
import json
import os
import sys
from datetime import datetime, timezone

from fli.models import (
    Airport,
    FlightSearchFilters,
    FlightSegment,
    MaxStops,
    PassengerInfo,
    SeatType,
    TripType,
)
from search_utils import fmt_price, search_with_currency

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

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
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


def parse_args():
    parser = argparse.ArgumentParser(description="Track a flight route")
    parser.add_argument("origin", help="Origin airport IATA code")
    parser.add_argument("destination", help="Destination airport IATA code")
    parser.add_argument("date", help="Departure date (YYYY-MM-DD)")
    parser.add_argument("--return-date", help="Return date (YYYY-MM-DD)")
    parser.add_argument("--cabin", default="ECONOMY", choices=SEAT_MAP.keys())
    parser.add_argument("--stops", default="ANY", choices=STOPS_MAP.keys())
    parser.add_argument("--target-price", type=float, help="Alert when price drops below this")
    return parser.parse_args()


def main():
    args = parse_args()

    try:
        origin = Airport[args.origin.upper()]
        destination = Airport[args.destination.upper()]
    except KeyError as e:
        print(f"Unknown airport code: {e}", file=sys.stderr)
        sys.exit(1)

    route_id = f"{args.origin.upper()}-{args.destination.upper()}-{args.date}"
    if args.return_date:
        route_id += f"-RT-{args.return_date}"

    tracked = load_tracked()
    if any(t["id"] == route_id for t in tracked):
        print(f"Already tracking {route_id}")
        sys.exit(0)

    segments = [FlightSegment(departure_airport=[[origin, 0]], arrival_airport=[[destination, 0]], travel_date=args.date)]

    trip_type = TripType.ONE_WAY
    if args.return_date:
        segments.append(FlightSegment(departure_airport=[[destination, 0]], arrival_airport=[[origin, 0]], travel_date=args.return_date))
        trip_type = TripType.ROUND_TRIP

    filters = FlightSearchFilters(
        trip_type=trip_type,
        passenger_info=PassengerInfo(adults=1),
        flight_segments=segments,
        seat_type=SEAT_MAP[args.cabin],
        stops=STOPS_MAP[args.stops],
    )

    print(f"Searching {args.origin.upper()} -> {args.destination.upper()} on {args.date}...")
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
        "origin": args.origin.upper(),
        "destination": args.destination.upper(),
        "date": args.date,
        "return_date": args.return_date,
        "cabin": args.cabin,
        "stops": args.stops,
        "target_price": args.target_price,
        "currency": currency,
        "added_at": now,
        "price_history": [price_entry],
    }

    tracked.append(entry)
    save_tracked(tracked)

    print(f"Now tracking: {args.origin.upper()} -> {args.destination.upper()} on {args.date}")
    if price_entry["best_price"]:
        print(f"Current best price: {fmt_price(price_entry['best_price'], currency)} ({price_entry['airline']})")
    if args.target_price:
        print(f"Target price: {fmt_price(args.target_price, currency)}")


if __name__ == "__main__":
    main()
