"""Search wrapper that extracts currency from Google Flights API response."""

import base64
import json
import re
from copy import deepcopy

from fli.models import FlightSearchFilters
from fli.models.google_flights.base import TripType
from fli.search import SearchFlights
from fli.search.client import get_client

BASE_URL = "https://www.google.com/_/FlightsFrontendUi/data/travel.frontend.flights.FlightsFrontendService/GetShoppingResults"

CURRENCY_SYMBOLS = {
    "USD": "$", "GBP": "\u00a3", "EUR": "\u20ac", "THB": "\u0e3f",
    "JPY": "\u00a5", "CNY": "\u00a5", "KRW": "\u20a9", "INR": "\u20b9",
    "AUD": "A$", "CAD": "C$", "SGD": "S$", "HKD": "HK$", "NZD": "NZ$",
    "TWD": "NT$", "MYR": "RM", "PHP": "\u20b1", "IDR": "Rp", "VND": "\u20ab",
    "BRL": "R$", "MXN": "MX$", "CHF": "CHF", "SEK": "kr", "NOK": "kr",
    "DKK": "kr", "PLN": "z\u0142", "CZK": "K\u010d", "HUF": "Ft",
    "TRY": "\u20ba", "ZAR": "R", "AED": "AED", "SAR": "SAR", "QAR": "QAR",
    "KWD": "KD", "BHD": "BD", "OMR": "OMR", "ILS": "\u20aa",
}


def _extract_currency(token_b64):
    """Extract 3-letter currency code from base64 booking token."""
    try:
        decoded = base64.b64decode(token_b64)
        match = re.search(rb"\x1a\x03([A-Z]{3})", decoded)
        if match:
            return match.group(1).decode("ascii")
    except Exception:
        pass
    return None


def currency_symbol(code):
    """Get currency symbol for a currency code."""
    return CURRENCY_SYMBOLS.get(code, code)


def fmt_price(price, code):
    """Format a price with currency symbol."""
    return f"{currency_symbol(code)}{price:,.0f}"


def _raw_search(filters):
    """Make raw API call and return parsed response data."""
    client = get_client()
    encoded = filters.encode()
    response = client.post(
        url=BASE_URL,
        data=f"f.req={encoded}",
        impersonate="chrome",
        allow_redirects=True,
    )
    response.raise_for_status()
    parsed = json.loads(response.text.lstrip(")]}'"))[0][2]
    if not parsed:
        return None
    return json.loads(parsed)


def search_with_currency(filters: FlightSearchFilters, top_n: int = 5):
    """Search flights and detect currency from the raw API response.

    Returns (results, currency_code) where currency_code is e.g. 'THB', 'USD', 'GBP'.
    Makes a single API call.
    """
    data = _raw_search(filters)
    if data is None:
        return None, "USD"

    # Extract currency from first flight's booking token
    currency = None
    flights_data = []
    for i in [2, 3]:
        if i < len(data) and isinstance(data[i], list):
            for item in data[i][0]:
                flights_data.append(item)
                if currency is None and len(item[1]) > 1 and isinstance(item[1][1], str):
                    currency = _extract_currency(item[1][1])

    # Parse flights using fli's parser
    results = [SearchFlights._parse_flights_data(flight) for flight in flights_data]

    if filters.trip_type == TripType.ONE_WAY or filters.flight_segments[0].selected_flight is not None:
        return results, currency or "USD"

    # Round-trip: get return flights
    flight_pairs = []
    searcher = SearchFlights()
    for selected_flight in results[:top_n]:
        selected_filters = deepcopy(filters)
        selected_filters.flight_segments[0].selected_flight = selected_flight
        return_flights = searcher.search(selected_filters, top_n=top_n)
        if return_flights is not None:
            flight_pairs.extend(
                (selected_flight, ret) for ret in return_flights
            )

    return flight_pairs, currency or "USD"
