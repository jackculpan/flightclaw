#!/usr/bin/env python3
"""Check all tracked flights for price changes. Designed for cron/scheduled use."""

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
from fli.models.airline import Airline
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
    if not os.path.exists(TRACKED_FILE):
        return []
    with open(TRACKED_FILE, "r") as f:
        return json.load(f)


def save_tracked(tracked):
    with open(TRACKED_FILE, "w") as f:
        json.dump(tracked, f, indent=2)


def parse_args():
    parser = argparse.ArgumentParser(description="Check tracked flight prices")
    parser.add_argument("--threshold", type=float, default=10, help="Percentage drop to alert on (default: 10)")
    return parser.parse_args()


def check_route(entry):
    origin = Airport[entry["origin"]]
    destination = Airport[entry["destination"]]

    segments = [FlightSegment(departure_airport=[[origin, 0]], arrival_airport=[[destination, 0]], travel_date=entry["date"])]
    trip_type = TripType.ONE_WAY

    if entry.get("return_date"):
        segments.append(FlightSegment(departure_airport=[[destination, 0]], arrival_airport=[[origin, 0]], travel_date=entry["return_date"]))
        trip_type = TripType.ROUND_TRIP

    # Build airline filter if preferred_airline is specified
    airlines = None
    preferred_airline = entry.get("preferred_airline")
    if preferred_airline:
        try:
            airlines = [Airline[preferred_airline]]
        except KeyError:
            print(f"  Warning: unknown airline code '{preferred_airline}', ignoring filter", file=sys.stderr)

    filters = FlightSearchFilters(
        trip_type=trip_type,
        passenger_info=PassengerInfo(adults=1),
        flight_segments=segments,
        seat_type=SEAT_MAP.get(entry.get("cabin", "ECONOMY"), SeatType.ECONOMY),
        stops=STOPS_MAP.get(entry.get("stops", "ANY"), MaxStops.ANY),
        airlines=airlines,
    )

    exclude_basic = entry.get("exclude_basic", False)
    results, currency = search_with_currency(filters, top_n=10, exclude_basic_economy=exclude_basic)
    if not results:
        return None, None, None, currency

    target_out = entry.get("outbound_flight_number")
    target_ret = entry.get("return_flight_number")

    # Optional time-window filters (format: "HH:MM" 24h, e.g. "08:00")
    depart_after = entry.get("depart_after")
    depart_before = entry.get("depart_before")
    return_after = entry.get("return_after")
    return_before = entry.get("return_before")

    flights = []
    for r in results:
        outbound = r[0] if isinstance(r, tuple) else r
        ret = r[1] if isinstance(r, tuple) else None
        if not outbound.legs:
            continue
        leg = outbound.legs[0]
        ret_leg = ret.legs[0] if ret and ret.legs else None

        # Filter by specific flight numbers if set
        if target_out and leg.flight_number != target_out:
            continue
        if target_ret and ret_leg and ret_leg.flight_number != target_ret:
            continue

        # Filter by time windows if no specific flight numbers
        if not target_out and depart_after and leg.departure_datetime:
            h, m = map(int, depart_after.split(":"))
            if leg.departure_datetime.hour * 60 + leg.departure_datetime.minute < h * 60 + m:
                continue
        if not target_out and depart_before and leg.departure_datetime:
            h, m = map(int, depart_before.split(":"))
            if leg.departure_datetime.hour * 60 + leg.departure_datetime.minute > h * 60 + m:
                continue
        if not target_ret and return_after and ret_leg and ret_leg.departure_datetime:
            h, m = map(int, return_after.split(":"))
            if ret_leg.departure_datetime.hour * 60 + ret_leg.departure_datetime.minute < h * 60 + m:
                continue
        if not target_ret and return_before and ret_leg and ret_leg.departure_datetime:
            h, m = map(int, return_before.split(":"))
            if ret_leg.departure_datetime.hour * 60 + ret_leg.departure_datetime.minute > h * 60 + m:
                continue

        # For round-trip results, use ret.price (the price of the specific
        # outbound+return combination from the second API call) instead of
        # outbound.price (which is the cheapest round-trip for that outbound,
        # potentially with a different return flight). This matters when
        # filtering for a specific return flight number that isn't the cheapest
        # return option — outbound.price would understate the actual cost.
        price = round(ret.price if ret is not None else outbound.price, 2)
        flights.append({
            "price": price,
            "airline": leg.airline.name,
            "flight_number": leg.flight_number,
            "departs": leg.departure_datetime.strftime("%I:%M %p") if leg.departure_datetime else "?",
            "arrives": leg.arrival_datetime.strftime("%I:%M %p") if leg.arrival_datetime else "?",
            "return_flight_number": ret_leg.flight_number if ret_leg else None,
            "return_departs": ret_leg.departure_datetime.strftime("%I:%M %p") if ret_leg and ret_leg.departure_datetime else None,
            "return_arrives": ret_leg.arrival_datetime.strftime("%I:%M %p") if ret_leg and ret_leg.arrival_datetime else None,
        })

    if not flights:
        not_found_msg = f"DL{target_out}" if target_out else "any flight"
        if target_ret:
            not_found_msg += f" / DL{target_ret}"
        print(f"  ⚠️  No results for {not_found_msg} — flight may not be operating or sold out")
        return None, None, None, currency

    best = min(flights, key=lambda f: f["price"])
    return best["price"], best["airline"], flights, currency


def main():
    args = parse_args()
    tracked = load_tracked()

    if not tracked:
        print("No flights being tracked. Use track-flight.py to add routes.")
        sys.exit(0)

    now = datetime.now(timezone.utc).isoformat()
    alerts = []

    for entry in tracked:
        route = entry.get("label") or f"{entry['origin']} -> {entry['destination']} on {entry['date']}"
        currency = entry.get("currency", "USD")
        print(f"Checking {route}...")

        try:
            price, airline, all_flights, detected_currency = check_route(entry)
            currency = detected_currency or currency
        except Exception as e:
            print(f"  Error: {e}", file=sys.stderr)
            continue

        if price is None:
            print(f"  No results found")
            continue

        entry["price_history"].append({
            "timestamp": now,
            "best_price": price,
            "airline": airline,
        })
        entry["currency"] = currency

        # Print all flight options, deduped by outbound flight (show best price per outbound)
        if all_flights:
            has_return = any(f.get("return_flight_number") for f in all_flights)
            # Group by outbound flight number, keep lowest price per outbound
            seen = {}
            for f in all_flights:
                key = f["flight_number"]
                if key not in seen or f["price"] < seen[key]["price"]:
                    seen[key] = f
            for f in sorted(seen.values(), key=lambda x: (x["price"], x["departs"])):
                marker = "★" if f["price"] == price else " "
                fn = f"DL{f['flight_number']}" if f["airline"] == "Delta Air Lines" else f"{f['airline']} {f['flight_number']}"
                if has_return and f.get("return_flight_number"):
                    ret_fn = f"DL{f['return_flight_number']}"
                    print(f"  {marker} {fmt_price(f['price'], currency):>8}  {fn} {f['departs']}→{f['arrives']}  /  ret {ret_fn} {f['return_departs']}→{f['return_arrives']}")
                else:
                    print(f"  {marker} {fmt_price(f['price'], currency):>8}  {fn} {f['departs']}→{f['arrives']}")

        prev_prices = [p["best_price"] for p in entry["price_history"][:-1] if p["best_price"]]
        if prev_prices:
            last_price = prev_prices[-1]
            change = price - last_price
            pct = (change / last_price) * 100

            if change < 0:
                print(f"  → Best: {fmt_price(price, currency)} - DOWN {fmt_price(abs(change), currency)} ({abs(pct):.1f}%)")
                if abs(pct) >= args.threshold:
                    alerts.append(f"PRICE DROP: {route} is now {fmt_price(price, currency)} (was {fmt_price(last_price, currency)}, down {abs(pct):.1f}%)")
            elif change > 0:
                print(f"  → Best: {fmt_price(price, currency)} - up {fmt_price(change, currency)} ({pct:.1f}%)")
            else:
                print(f"  → Best: {fmt_price(price, currency)} - no change")
        else:
            print(f"  → Best: {fmt_price(price, currency)} - first price recorded")

        if entry.get("target_price") and price <= entry["target_price"]:
            alerts.append(f"TARGET REACHED: {route} is {fmt_price(price, currency)} (target: {fmt_price(entry['target_price'], currency)})")

    save_tracked(tracked)

    if alerts:
        print(f"\n{'='*60}")
        print("ALERTS:")
        for alert in alerts:
            print(f"  {alert}")


if __name__ == "__main__":
    main()
