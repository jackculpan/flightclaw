"""FlightClaw tracking tools - track, check, list, and remove flight routes."""

from datetime import datetime, timezone

from fli.core.parsers import ParseError

from helpers import (
    build_filters,
    expand_routes,
    load_tracked,
    save_tracked,
)
from search_utils import fmt_price, search_with_currency


def register_tracking_tools(mcp):
    """Register all tracking tools on the given MCP server instance."""

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
        combos = expand_routes(origin, destination, date, date_to)
        tracked = load_tracked()
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
                filters = build_filters(
                    orig_code, dest_code, d, return_date, cabin, stops,
                    adults, children, infants_in_seat, infants_on_lap,
                    airlines, max_price, max_duration,
                )
            except (KeyError, ParseError) as e:
                output.append(f"Invalid parameter: {e}")
                continue

            results, currency = search_with_currency(filters, top_n=1)

            now = datetime.now(timezone.utc).isoformat()
            price_entry = {"timestamp": now, "best_price": None, "airline": None}

            if results:
                flight, _token = results[0]
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

        save_tracked(tracked)

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
        tracked = load_tracked()
        if not tracked:
            return "No flights being tracked. Use track_flight to add routes."

        now = datetime.now(timezone.utc).isoformat()
        output = []
        alerts = []

        for entry in tracked:
            route = f"{entry['origin']} -> {entry['destination']} on {entry['date']}"
            currency = entry.get("currency", "USD")

            try:
                filters = build_filters(
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

            flight, _token = results[0]
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

        save_tracked(tracked)

        if alerts:
            output.append("\nALERTS:")
            output.extend(f"  {a}" for a in alerts)

        return "\n".join(output)

    @mcp.tool()
    def list_tracked() -> str:
        """List all tracked flights with current prices and history summary."""
        tracked = load_tracked()
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
        tracked = load_tracked()
        before = len(tracked)
        tracked = [t for t in tracked if t["id"] != route_id]

        if len(tracked) == before:
            return f"Route {route_id} not found. Use list_tracked to see tracked routes."

        save_tracked(tracked)
        return f"Removed {route_id}. {len(tracked)} route(s) remaining."
