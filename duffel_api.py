"""Thin HTTP client for the flightclaw-api wrapper (private Duffel proxy)."""

import json
import os
import urllib.error
import urllib.parse
import urllib.request


def _get_config():
    base_url = os.environ.get("FLIGHTCLAW_API_URL", "").rstrip("/")
    api_key = os.environ.get("FLIGHTCLAW_API_KEY", "")
    if not base_url or not api_key:
        raise RuntimeError(
            "FLIGHTCLAW_API_URL and FLIGHTCLAW_API_KEY must be set. "
            "These point to your private flightclaw-api Worker."
        )
    return base_url, api_key


def _request(method, path, body=None, params=None):
    """Make an authenticated request to flightclaw-api."""
    base_url, api_key = _get_config()
    url = f"{base_url}{path}"

    if params:
        qs = "&".join(f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items())
        url = f"{url}?{qs}"

    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "flightclaw/1.0",
        },
    )

    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        error_body = e.read().decode()
        try:
            err = json.loads(error_body)
            msg = err.get("error", error_body)
        except json.JSONDecodeError:
            msg = error_body
        raise RuntimeError(f"API error ({e.code}): {msg}")


def is_configured():
    """Check if the API wrapper is configured."""
    return bool(
        os.environ.get("FLIGHTCLAW_API_URL")
        and os.environ.get("FLIGHTCLAW_API_KEY")
    )


def search(origin, destination, date, return_date=None, cabin="ECONOMY",
           adults=1, children=0, infants=0, max_connections=1):
    body = {
        "origin": origin, "destination": destination, "date": date,
        "cabin": cabin, "adults": adults, "children": children,
        "infants": infants, "max_connections": max_connections,
    }
    if return_date:
        body["return_date"] = return_date
    return _request("POST", "/search", body)


def search_multi(slices, cabin="ECONOMY", adults=1, children=0, infants=0, max_connections=1):
    """Multi-city search. slices is a list of {origin, destination, date} dicts."""
    body = {
        "slices": slices, "cabin": cabin, "adults": adults,
        "children": children, "infants": infants, "max_connections": max_connections,
    }
    return _request("POST", "/search/multi", body)


def get_offer(offer_id):
    return _request("GET", "/offer", params={"offer_id": offer_id})


def get_seat_map(offer_id):
    return _request("GET", "/seat-map", params={"offer_id": offer_id})


def book(offer_id, passengers, payment_type="balance", services=None):
    body = {
        "offer_id": offer_id,
        "passengers": passengers,
        "payment_type": payment_type,
    }
    if services:
        body["services"] = services
    return _request("POST", "/book", body)


def hold(offer_id, passengers, services=None):
    body = {
        "offer_id": offer_id,
        "passengers": passengers,
    }
    if services:
        body["services"] = services
    return _request("POST", "/hold", body)


def pay(order_id, amount, currency, payment_type="balance"):
    return _request("POST", "/pay", {
        "order_id": order_id,
        "amount": amount,
        "currency": currency,
        "payment_type": payment_type,
    })


def get_order(order_id):
    return _request("GET", "/order", params={"order_id": order_id})


def request_change(order_id, slices_to_remove, slices_to_add):
    return _request("POST", "/change/request", {
        "order_id": order_id,
        "slices_to_remove": slices_to_remove,
        "slices_to_add": slices_to_add,
    })


def get_change_request(change_request_id):
    return _request("GET", "/change/request",
                     params={"change_request_id": change_request_id})


def create_change(change_offer_id):
    return _request("POST", "/change/create",
                     {"change_offer_id": change_offer_id})


def confirm_change(change_id, amount, currency, payment_type="balance"):
    return _request("POST", "/change/confirm", {
        "change_id": change_id,
        "amount": amount,
        "currency": currency,
        "payment_type": payment_type,
    })


def cancel(order_id):
    return _request("POST", "/cancel", {"order_id": order_id})


def confirm_cancel(cancellation_id):
    return _request("POST", "/cancel/confirm",
                     {"cancellation_id": cancellation_id})


def create_checkout(offer_id, passengers, amount, currency,
                    flight_summary="", services=None):
    body = {
        "offer_id": offer_id,
        "passengers": passengers,
        "amount": amount,
        "currency": currency,
        "flight_summary": flight_summary,
    }
    if services:
        body["services"] = services
    return _request("POST", "/checkout/create", body)


def get_webhook_alerts(order_id=None):
    params = {}
    if order_id:
        params["order_id"] = order_id
    return _request("GET", "/webhooks/alerts", params=params)
