#!/usr/bin/env python3
"""Add a flight route to the price tracking list."""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from itertools import product

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
    parser.add_argument("origin", help="Origin airport IATA code(s), comma-separated (e.g. LHR or LHR,MAN)")
    parser.add_argument("destination", help="Destination airport IATA code(s), comma-separated (e.g. JFK or JFK,EWR)")
    parser.add_argument("date", help="Departure date (YYYY-MM-DD)")
    parser.add_argument("--date-to", help="End of date range (YYYY-MM-DD). Tracks each day from date to date-to inclusive.")
    parser.add_argument("--return-date", help="Return date (YYYY-MM-DD)")
    parser.add_argument("--cabin", default="ECONOMY", choices=SEAT_MAP.keys())
    parser.add_argument("--stops", default="ANY", choices=STOPS_MAP.keys())
    parser.add_argument("--target-price", type=float, help="Alert when price drops below this")
    return parser.parse_args()


def expand_routes(origins_str, destinations_str, date_str, date_to_str=None):
    origins = [o.strip().upper() for o in origins_str.split(",")]
    destinations = [d.strip().upper() for d in destinations_str.split(",")]
    start = datetime.strptime(date_str, "%Y-%m-%d").date()
    if date_to_str:
        end = datetime.strptime(date_to_str, "%Y-%m-%d").date()
    else:
        end = start
    dates = []
    current = start
    while current <= end:
        dates.append(current.strftime("%Y-%m-%d"))
        current += timedelta(days=1)
    return list(product(origins, destinations, dates))


def main():
    args = parse_args()
    combos = expand_routes(args.origin, args.destination, args.date, args.date_to)
    tracked = load_tracked()
    added = 0
    skipped = 0

    for orig_code, dest_code, date in combos:
        route_id = f"{orig_code}-{dest_code}-{date}"
        if args.return_date:
            route_id += f"-RT-{args.return_date}"

        if any(t["id"] == route_id for t in tracked):
            print(f"Already tracking {route_id}")
            skipped += 1
            continue

        try:
            origin = Airport[orig_code]
            destination = Airport[dest_code]
        except KeyError as e:
            print(f"Unknown airport code: {e}", file=sys.stderr)
            continue

        segments = [FlightSegment(departure_airport=[[origin, 0]], arrival_airport=[[destination, 0]], travel_date=date)]

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

        print(f"Searching {orig_code} -> {dest_code} on {date}...")
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
            "date": date,
            "return_date": args.return_date,
            "cabin": args.cabin,
            "stops": args.stops,
            "target_price": args.target_price,
            "currency": currency,
            "added_at": now,
            "price_history": [price_entry],
        }

        tracked.append(entry)
        added += 1

        if price_entry["best_price"]:
            print(f"  {fmt_price(price_entry['best_price'], currency)} ({price_entry['airline']})")

    save_tracked(tracked)

    print(f"\nNow tracking {added} new route(s).", end="")
    if skipped:
        print(f" ({skipped} already tracked)", end="")
    print()
    if args.target_price:
        currency = currency if 'currency' in dir() else "USD"
        print(f"Target price: {fmt_price(args.target_price, currency)}")


if __name__ == "__main__":
    main()
