"""Duffel MCP tools for FlightClaw - search, booking, and order management."""

import json

import duffel_api
from duffel_fmt import (
    fmt_change_offer,
    fmt_offer,
    fmt_order,
    load_orders,
    resolve_passengers,
    upsert_order,
)


def register_duffel_tools(mcp):
    """Register all Duffel tools on the MCP server."""

    @mcp.tool()
    def duffel_search_flights(
        origin: str,
        destination: str,
        date: str,
        return_date: str | None = None,
        cabin: str = "ECONOMY",
        adults: int = 1,
        children: int = 0,
        infants: int = 0,
        results: int = 5,
        max_connections: int = 1,
    ) -> str:
        """Search bookable flights via Duffel with real-time fares and conditions.

        Args:
            origin: Origin IATA code (e.g. LHR)
            destination: Destination IATA code (e.g. JFK)
            date: Departure date (YYYY-MM-DD)
            return_date: Return date for round trips (YYYY-MM-DD)
            cabin: ECONOMY, PREMIUM_ECONOMY, BUSINESS, or FIRST
            adults: Adults (default 1)
            children: Children (default 0)
            infants: Infants (default 0)
            results: Max results (default 5)
            max_connections: Max connections per slice (default 1)
        """
        try:
            data = duffel_api.search(
                origin.strip().upper(), destination.strip().upper(),
                date, return_date, cabin, adults, children, infants,
                max_connections,
            )
        except Exception as e:
            return f"Search error: {e}"

        offers = data.get("offers", [])
        if not offers:
            return f"No flights found for {origin} -> {destination} on {date}"

        offers.sort(key=lambda o: float(o.get("total_amount", "999999")))
        show = offers[:results]

        route = f"{origin} -> {destination}"
        if return_date:
            route += f" (return {return_date})"

        output = [f"Duffel search: {route} on {date} ({cabin})", ""]
        for i, offer in enumerate(show, 1):
            output.append(fmt_offer(offer, index=i))
            output.append("")

        output.append(f"{len(offers)} offer(s) found. Showing top {len(show)}.")
        output.append("Use duffel_book_flight with an offer ID to book.")
        return "\n".join(output)

    @mcp.tool()
    def duffel_search_multi_city(
        slices: str,
        cabin: str = "ECONOMY",
        adults: int = 1,
        children: int = 0,
        infants: int = 0,
        results: int = 5,
        max_connections: int = 1,
    ) -> str:
        """Search multi-city flights via Duffel.

        Args:
            slices: JSON array, e.g. [{"origin":"LHR","destination":"JFK","date":"2026-07-01"},
                {"origin":"JFK","destination":"LAX","date":"2026-07-05"}]
            cabin: ECONOMY, PREMIUM_ECONOMY, BUSINESS, or FIRST
            adults: Adults (default 1)
            children: Children (default 0)
            infants: Infants (default 0)
            results: Max results (default 5)
            max_connections: Max connections per slice (default 1)
        """
        try:
            slice_list = json.loads(slices)
        except json.JSONDecodeError as e:
            return f"Invalid slices JSON: {e}"

        if not isinstance(slice_list, list) or len(slice_list) < 2:
            return "Slices must be a JSON array with at least 2 segments."

        for s in slice_list:
            if not all(k in s for k in ("origin", "destination", "date")):
                return "Each slice must have origin, destination, and date."

        try:
            data = duffel_api.search_multi(
                slice_list, cabin, adults, children, infants, max_connections,
            )
        except Exception as e:
            return f"Search error: {e}"

        offers = data.get("offers", [])
        if not offers:
            route = " -> ".join(
                f"{s['origin']}-{s['destination']}" for s in slice_list
            )
            return f"No multi-city flights found for {route}"

        offers.sort(key=lambda o: float(o.get("total_amount", "999999")))
        show = offers[:results]

        route = " -> ".join(
            f"{s['origin']}-{s['destination']}" for s in slice_list
        )
        output = [f"Multi-city search: {route} ({cabin})", ""]
        for i, offer in enumerate(show, 1):
            output.append(fmt_offer(offer, index=i))
            output.append("")

        output.append(f"{len(offers)} offer(s) found. Showing top {len(show)}.")
        output.append("Use duffel_book_flight with an offer ID to book.")
        return "\n".join(output)

    @mcp.tool()
    def duffel_get_offer(offer_id: str) -> str:
        """Get offer details including conditions and available extras.

        Args:
            offer_id: Duffel offer ID from search results
        """
        try:
            offer = duffel_api.get_offer(offer_id)
        except Exception as e:
            return f"Error: {e}"

        lines = [fmt_offer(offer)]

        services = offer.get("available_services") or []
        if services:
            lines.append("\nAvailable extras:")
            for svc in services:
                stype = svc.get("type", "?")
                price = f"{offer.get('total_currency')} {svc.get('total_amount')}"
                meta = svc.get("metadata", {})
                desc = meta.get("type", stype)
                if meta.get("maximum_weight_kg"):
                    desc += f" ({meta['maximum_weight_kg']}kg)"
                lines.append(f"  {desc}: {price} (max qty: {svc.get('maximum_quantity', 1)}) | ID: {svc['id']}")
            lines.append("\nPass service IDs to duffel_book_flight via services parameter.")

        return "\n".join(lines)

    @mcp.tool()
    def duffel_get_seat_map(offer_id: str) -> str:
        """Get seat map with available seats and prices.

        Args:
            offer_id: Duffel offer ID from search results
        """
        try:
            seat_maps = duffel_api.get_seat_map(offer_id)
        except Exception as e:
            return f"Error: {e}"

        if not seat_maps:
            return "No seat map available for this offer."

        output = []
        for sm in seat_maps:
            segment = sm.get("segment_id", "?")
            output.append(f"Segment: {segment}")
            cabins = sm.get("cabins", [])
            for cabin_info in cabins:
                cabin_class = cabin_info.get("cabin_class", "?")
                output.append(f"  Cabin: {cabin_class}")
                rows = cabin_info.get("rows", [])
                for row in rows:
                    sections = row.get("sections", [])
                    for section in sections:
                        seats = section.get("elements", [])
                        for seat in seats:
                            if seat.get("type") != "seat":
                                continue
                            designator = seat.get("designator", "?")
                            available = seat.get("available_services", [])
                            if not available:
                                continue
                            svc = available[0]
                            price = f"{svc.get('total_currency', '?')} {svc.get('total_amount', '?')}"
                            disclosures = ", ".join(seat.get("disclosures", []))
                            extra = f" ({disclosures})" if disclosures else ""
                            output.append(f"    {designator}: {price}{extra} | ID: {svc.get('id', '?')}")
            output.append("")

        output.append("Pass seat service IDs to duffel_book_flight via services parameter.")
        return "\n".join(output)

    @mcp.tool()
    def duffel_book_flight(
        offer_id: str,
        passengers: str,
        payment_type: str = "balance",
        services: str | None = None,
    ) -> str:
        """Book a flight. Accepts profile names or JSON passenger array.

        Args:
            offer_id: Offer ID from search results
            passengers: Comma-separated profile names (e.g. "jack,jane") or
                JSON array with given_name, family_name, born_on, gender, title, email, phone_number
            payment_type: "balance" or "arc_bsp_cash"
            services: Optional JSON array e.g. [{"id":"ase_xxx","quantity":1}]
        """
        pax, err = resolve_passengers(passengers)
        if err:
            return err

        # Auto-assign offer passenger IDs if missing
        if pax and not pax[0].get("id"):
            try:
                offer = duffel_api.get_offer(offer_id)
                offer_pax = offer.get("passengers", [])
                for i, p in enumerate(pax):
                    if i < len(offer_pax):
                        p["id"] = offer_pax[i]["id"]
            except Exception:
                pass  # Let Duffel return the error if IDs are wrong

        svc_list = None
        if services:
            try:
                svc_list = json.loads(services)
            except json.JSONDecodeError as e:
                return f"Invalid services JSON: {e}"

        try:
            order = duffel_api.book(offer_id, pax, payment_type, svc_list)
        except Exception as e:
            return f"Booking failed: {e}"

        upsert_order(order)
        return "Flight booked!\n\n" + fmt_order(order)

    @mcp.tool()
    def duffel_list_orders() -> str:
        """List all Duffel orders stored locally."""
        orders = load_orders()
        if not orders:
            return "No Duffel orders. Use duffel_book_flight to create one."
        output = [fmt_order(o) for o in orders]
        output.append(f"\n{len(orders)} order(s).")
        return "\n\n".join(output)

    @mcp.tool()
    def duffel_get_order(order_id: str) -> str:
        """Get live order status from Duffel.

        Args:
            order_id: Duffel order ID (e.g. ord_xxx)"""
        try:
            order = duffel_api.get_order(order_id)
        except Exception as e:
            return f"Error: {e}"
        upsert_order(order)
        return fmt_order(order)

    @mcp.tool()
    def duffel_request_change(
        order_id: str,
        new_date: str,
        slice_index: int = 0,
        new_origin: str | None = None,
        new_destination: str | None = None,
        cabin: str | None = None,
    ) -> str:
        """Request a flight change. Returns options with fees.

        Args:
            order_id: Duffel order ID
            new_date: New departure date (YYYY-MM-DD)
            slice_index: 0=outbound, 1=return
            new_origin: New origin IATA (optional)
            new_destination: New destination IATA (optional)
            cabin: ECONOMY, PREMIUM_ECONOMY, BUSINESS, or FIRST (optional)
        """
        try:
            order = duffel_api.get_order(order_id)
        except Exception as e:
            return f"Error: {e}"

        slices = order.get("slices", [])
        if slice_index >= len(slices):
            return f"Invalid slice_index {slice_index}. Order has {len(slices)} slice(s)."

        target = slices[slice_index]
        if not target.get("changeable"):
            orig = target.get("origin", {}).get("iata_code", "?")
            dest = target.get("destination", {}).get("iata_code", "?")
            return f"Slice {slice_index} ({orig} -> {dest}) is not changeable."

        origin = new_origin or target["origin"]["iata_code"]
        destination = new_destination or target["destination"]["iata_code"]

        cabin_map = {"ECONOMY": "economy", "PREMIUM_ECONOMY": "premium_economy",
                     "BUSINESS": "business", "FIRST": "first"}
        if cabin and cabin not in cabin_map:
            return f"Unknown cabin '{cabin}'. Use ECONOMY, PREMIUM_ECONOMY, BUSINESS, or FIRST."
        cabin_class = cabin_map.get(cabin) if cabin else None
        if not cabin_class:
            segs = target.get("segments", [])
            if segs and segs[0].get("passengers"):
                cabin_class = segs[0]["passengers"][0].get("cabin_class", "economy")
            else:
                cabin_class = "economy"

        try:
            result = duffel_api.request_change(
                order_id,
                [{"slice_id": target["id"]}],
                [{"origin": origin.upper(), "destination": destination.upper(),
                  "departure_date": new_date, "cabin_class": cabin_class}],
            )
        except Exception as e:
            return f"Change request failed: {e}"

        offers = result.get("order_change_offers", [])
        if not offers:
            return f"No change options for {origin} -> {destination} on {new_date}."

        output = [f"Change options for order {order_id}:", ""]
        for i, co in enumerate(offers, 1):
            output.append(fmt_change_offer(co, index=i))
            output.append("")

        output.append(f"{len(offers)} option(s). Use duffel_confirm_change with a change_offer_id.")
        return "\n".join(output)

    @mcp.tool()
    def duffel_confirm_change(
        change_offer_id: str,
        payment_type: str = "balance",
    ) -> str:
        """Confirm a flight change from duffel_request_change.

        Args:
            change_offer_id: Change offer ID
            payment_type: "balance" or "arc_bsp_cash" """
        try:
            change = duffel_api.create_change(change_offer_id)
        except Exception as e:
            return f"Change failed: {e}"

        amount = float(change.get("change_total_amount", "0"))
        currency = change.get("change_total_currency", "GBP")

        try:
            duffel_api.confirm_change(
                change["id"], change.get("change_total_amount", "0"), currency, payment_type,
            )
        except Exception as e:
            return f"Confirm failed: {e}"

        lines = ["Flight changed!", f"Order {change.get('order_id')} updated."]
        if amount > 0:
            lines.append(f"Charged: {currency} {amount:.2f}")
        elif amount < 0:
            lines.append(f"Refund: {currency} {abs(amount):.2f}")
        lines.append("\nUse duffel_get_order to see updated details.")
        return "\n".join(lines)

    @mcp.tool()
    def duffel_cancel_order(order_id: str) -> str:
        """Request cancellation quote. Shows refund before confirming.

        Args:
            order_id: Duffel order ID"""
        try:
            cancellation = duffel_api.cancel(order_id)
        except Exception as e:
            return f"Cancel failed: {e}"

        lines = [
            f"Cancel quote for {order_id}:",
            f"  Refund: {cancellation.get('refund_currency')} {cancellation.get('refund_amount')}",
            f"  Refund to: {cancellation.get('refund_to')}",
            "",
            f"Confirm with duffel_confirm_cancel(cancellation_id=\"{cancellation.get('id')}\")",
        ]
        return "\n".join(lines)

    @mcp.tool()
    def duffel_confirm_cancel(cancellation_id: str) -> str:
        """Confirm cancellation. Irreversible.

        Args:
            cancellation_id: From duffel_cancel_order"""
        try:
            result = duffel_api.confirm_cancel(cancellation_id)
        except Exception as e:
            return f"Confirm failed: {e}"

        return (
            f"Order {result.get('order_id')} cancelled. "
            f"Refund: {result.get('refund_currency')} {result.get('refund_amount')}"
        )

    @mcp.tool()
    def duffel_create_checkout(
        offer_id: str,
        passengers: str,
        services: str | None = None,
    ) -> str:
        """Create a checkout page for card payment. Returns URL for user to pay.

        Args:
            offer_id: Offer ID from search results
            passengers: Profile names (e.g. "jack,jane") or JSON passenger array
            services: Optional JSON array e.g. [{"id":"ase_xxx","quantity":1}]
        """
        pax, err = resolve_passengers(passengers)
        if err:
            return err

        svc_list = None
        if services:
            try:
                svc_list = json.loads(services)
            except json.JSONDecodeError as e:
                return f"Invalid services JSON: {e}"

        # Get offer to know amount/currency and assign passenger IDs
        try:
            offer = duffel_api.get_offer(offer_id)
        except Exception as e:
            return f"Error: {e}"

        if pax and not pax[0].get("id"):
            offer_pax = offer.get("passengers", [])
            for i, p in enumerate(pax):
                if i < len(offer_pax):
                    p["id"] = offer_pax[i]["id"]

        summary = fmt_offer(offer)

        try:
            result = duffel_api.create_checkout(
                offer_id, pax,
                offer.get("total_amount"), offer.get("total_currency"),
                summary, svc_list,
            )
        except Exception as e:
            return f"Checkout creation failed: {e}"

        import os
        base = os.environ.get("FLIGHTCLAW_API_URL", "").rstrip("/")
        checkout_path = result.get("checkout_url", "")
        url = f"{base}{checkout_path}"
        fee = result.get("fee", 0)
        return (
            f"Checkout page created.\n\nURL: {url}\n"
            f"Fee included: {offer.get('total_currency')} {fee:.2f}\n\n"
            f"Send this URL to the passenger to complete card payment."
        )

    @mcp.tool()
    def duffel_check_alerts(order_id: str | None = None) -> str:
        """Check for airline-initiated changes or updates on orders.

        Args:
            order_id: Order ID to check (optional, omit for all recent)
        """
        try:
            result = duffel_api.get_webhook_alerts(order_id)
        except Exception as e:
            return f"Error: {e}"

        alerts = result.get("alerts", [])
        events = result.get("events", [])
        items = alerts or events

        if not items:
            return "No alerts." if not order_id else f"No alerts for {order_id}."
        lines = []
        for item in items:
            lines.append(f"  {item.get('type', item.get('summary', '?'))} ({item.get('created_at', '?')})")
        return f"{len(items)} alert(s):\n" + "\n".join(lines)
