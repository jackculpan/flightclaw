"""Duffel response formatters, order persistence, and helpers for FlightClaw."""

import json
import os

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
ORDERS_FILE = os.path.join(DATA_DIR, "duffel_orders.json")


def load_orders():
    if os.path.exists(ORDERS_FILE):
        with open(ORDERS_FILE, "r") as f:
            return json.load(f)
    return []


def save_orders(orders):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(ORDERS_FILE, "w") as f:
        json.dump(orders, f, indent=2)


def upsert_order(order_data):
    orders = load_orders()
    for i, o in enumerate(orders):
        if o["id"] == order_data["id"]:
            orders[i] = order_data
            save_orders(orders)
            return
    orders.append(order_data)
    save_orders(orders)


def fmt_segment(seg):
    carrier = seg.get("marketing_carrier", {}).get("iata_code", "?")
    fnum = seg.get("marketing_carrier_flight_number", "")
    orig = seg.get("origin", {}).get("iata_code", "?")
    dest = seg.get("destination", {}).get("iata_code", "?")
    dep = seg.get("departing_at", "")[:16].replace("T", " ")
    arr = seg.get("arriving_at", "")[:16].replace("T", " ")
    return f"    {carrier}{fnum}: {orig} {dep} -> {dest} {arr}"


def fmt_offer(offer, index=None):
    prefix = f"Option {index}: " if index else ""
    owner = offer.get("owner", {}).get("name", "?")
    lines = [f"{prefix}{offer.get('total_currency')} {offer.get('total_amount')} | {owner}"]

    for s in offer.get("slices", []):
        orig = s.get("origin", {}).get("iata_code", "?")
        dest = s.get("destination", {}).get("iata_code", "?")
        dur = s.get("duration", "?")
        lines.append(f"  {orig} -> {dest} ({dur})")
        for seg in s.get("segments", []):
            lines.append(fmt_segment(seg))

    cond = offer.get("conditions", {})
    chg = cond.get("change_before_departure")
    if chg:
        if chg.get("allowed"):
            pen = f" (penalty: {chg['penalty_currency']} {chg['penalty_amount']})" if chg.get("penalty_amount") else ""
            lines.append(f"  Changeable: Yes{pen}")
        else:
            lines.append("  Changeable: No")

    ref = cond.get("refund_before_departure")
    if ref:
        if ref.get("allowed"):
            pen = f" (penalty: {ref['penalty_currency']} {ref['penalty_amount']})" if ref.get("penalty_amount") else ""
            lines.append(f"  Refundable: Yes{pen}")
        else:
            lines.append("  Refundable: No")

    lines.append(f"  Offer ID: {offer.get('id')}")
    expires = offer.get("expires_at", "")[:16].replace("T", " ")
    lines.append(f"  Expires: {expires}")
    return "\n".join(lines)


def fmt_order(order):
    lines = [
        f"Order: {order.get('id')}",
        f"Booking ref: {order.get('booking_reference')}",
        f"Airline: {order.get('owner', {}).get('name', '?')}",
        f"Total: {order.get('total_currency')} {order.get('total_amount')}",
    ]
    pax = ", ".join(
        f"{p.get('given_name')} {p.get('family_name')}"
        for p in order.get("passengers", [])
    )
    lines.append(f"Passengers: {pax}")

    for s in order.get("slices", []):
        orig = s.get("origin", {}).get("iata_code", "?")
        dest = s.get("destination", {}).get("iata_code", "?")
        changeable = "changeable" if s.get("changeable") else "not changeable"
        lines.append(f"  {orig} -> {dest} ({changeable})")
        for seg in s.get("segments", []):
            lines.append(fmt_segment(seg))

    if order.get("cancelled_at"):
        lines.append(f"  CANCELLED at {order['cancelled_at']}")
    return "\n".join(lines)


def fmt_change_offer(co, index=None):
    prefix = f"Option {index}: " if index else ""
    cost = float(co.get("change_total_amount", "0"))
    currency = co.get("change_total_currency") or co.get("new_total_currency", "?")
    penalty = ""
    if co.get("penalty_amount"):
        penalty = f" (penalty: {co['penalty_currency']} {co['penalty_amount']})"

    if cost > 0:
        cost_str = f"Additional cost: {currency} {co['change_total_amount']}{penalty}"
    elif cost < 0:
        cost_str = f"Refund: {currency} {abs(cost):.2f}{penalty}"
    else:
        cost_str = f"No additional cost{penalty}"

    lines = [f"{prefix}{cost_str}"]
    lines.append(f"  New total: {co.get('new_total_currency')} {co.get('new_total_amount')}")

    for s in co.get("slices", {}).get("add", []):
        orig = s.get("origin", {}).get("iata_code", "?")
        dest = s.get("destination", {}).get("iata_code", "?")
        dur = s.get("duration", "?")
        lines.append(f"  NEW: {orig} -> {dest} ({dur})")
        for seg in s.get("segments", []):
            lines.append(fmt_segment(seg))

    lines.append(f"  Change offer ID: {co.get('id')}")
    expires = co.get("expires_at", "")[:16].replace("T", " ")
    lines.append(f"  Expires: {expires}")
    return "\n".join(lines)


def resolve_passengers(passengers_str):
    """Resolve passenger string to list of dicts.
    Accepts JSON array or comma-separated profile names.
    Returns (list, None) on success or (None, error_str) on failure.
    """
    try:
        return json.loads(passengers_str), None
    except (json.JSONDecodeError, ValueError):
        pass

    from passenger_profiles import load_passengers
    profiles = load_passengers()
    profile_map = {p["name"]: p for p in profiles}
    names = [n.strip().lower() for n in passengers_str.split(",")]
    pax = []
    for name in names:
        if name not in profile_map:
            return None, f"Unknown profile '{name}'. Use list_passengers."
        p = profile_map[name]
        pax.append({
            "given_name": p["given_name"],
            "family_name": p["family_name"],
            "born_on": p["born_on"],
            "gender": p["gender"],
            "title": p["title"],
            "email": p["email"],
            "phone_number": p["phone_number"],
        })
    return pax, None
