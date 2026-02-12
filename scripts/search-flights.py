#!/usr/bin/env python3
"""Search Google Flights for a route and date."""

import argparse
import sys
from datetime import datetime, timedelta
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


def parse_args():
    parser = argparse.ArgumentParser(description="Search Google Flights")
    parser.add_argument("origin", help="Origin airport IATA code(s), comma-separated (e.g. LHR or LHR,MAN)")
    parser.add_argument("destination", help="Destination airport IATA code(s), comma-separated (e.g. JFK or JFK,EWR)")
    parser.add_argument("date", help="Departure date (YYYY-MM-DD)")
    parser.add_argument("--date-to", help="End of date range (YYYY-MM-DD). Searches each day from date to date-to inclusive.")
    parser.add_argument("--return-date", help="Return date for round trips (YYYY-MM-DD)")
    parser.add_argument("--cabin", default="ECONOMY", choices=SEAT_MAP.keys(), help="Cabin class")
    parser.add_argument("--stops", default="ANY", choices=STOPS_MAP.keys(), help="Max stops")
    parser.add_argument("--results", type=int, default=5, help="Number of results")
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


def format_duration(minutes):
    h, m = divmod(minutes, 60)
    return f"{h}h {m}m"


def format_results(results, currency, is_round_trip=False):
    if not results:
        print("No flights found.")
        return

    for i, result in enumerate(results, 1):
        if is_round_trip and isinstance(result, tuple):
            outbound, ret = result
            print(f"\n{'='*60}")
            print(f"Option {i}: {fmt_price(outbound.price + ret.price, currency)} total")
            print(f"  Outbound: {fmt_price(outbound.price, currency)} | {format_duration(outbound.duration)} | {outbound.stops} stop(s)")
            for leg in outbound.legs:
                print(f"    {leg.airline.name} {leg.flight_number}: {leg.departure_airport.name} {leg.departure_datetime.strftime('%H:%M')} -> {leg.arrival_airport.name} {leg.arrival_datetime.strftime('%H:%M')}")
            print(f"  Return: {fmt_price(ret.price, currency)} | {format_duration(ret.duration)} | {ret.stops} stop(s)")
            for leg in ret.legs:
                print(f"    {leg.airline.name} {leg.flight_number}: {leg.departure_airport.name} {leg.departure_datetime.strftime('%H:%M')} -> {leg.arrival_airport.name} {leg.arrival_datetime.strftime('%H:%M')}")
        else:
            flight = result[0] if isinstance(result, tuple) else result
            print(f"\n{'='*60}")
            print(f"Option {i}: {fmt_price(flight.price, currency)} | {format_duration(flight.duration)} | {flight.stops} stop(s)")
            for leg in flight.legs:
                print(f"  {leg.airline.name} {leg.flight_number}: {leg.departure_airport.name} {leg.departure_datetime.strftime('%H:%M')} -> {leg.arrival_airport.name} {leg.arrival_datetime.strftime('%H:%M')}")


def main():
    args = parse_args()
    combos = expand_routes(args.origin, args.destination, args.date, args.date_to)
    total_results = 0

    for orig_code, dest_code, date in combos:
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

        print(f"\nSearching {orig_code} -> {dest_code} on {date}...")
        results, currency = search_with_currency(filters, top_n=args.results)

        if results:
            print(f"Prices in {currency}")
            format_results(results, currency, is_round_trip=bool(args.return_date))
            print(f"\n{len(results)} result(s) found.")
            total_results += len(results)
        else:
            print("No flights found.")

    if len(combos) > 1:
        print(f"\n{'='*60}")
        print(f"Searched {len(combos)} route/date combination(s). {total_results} total result(s).")


if __name__ == "__main__":
    main()
