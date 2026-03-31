"""Passenger profile storage for FlightClaw - save and reuse passenger details."""

import json
import os

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
PASSENGERS_FILE = os.path.join(DATA_DIR, "passengers.json")


def load_passengers():
    if os.path.exists(PASSENGERS_FILE):
        with open(PASSENGERS_FILE, "r") as f:
            return json.load(f)
    return []


def save_passengers(passengers):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(PASSENGERS_FILE, "w") as f:
        json.dump(passengers, f, indent=2)


def register_passenger_tools(mcp):
    """Register passenger profile tools on the given MCP server instance."""

    @mcp.tool()
    def save_passenger(
        name: str,
        given_name: str,
        family_name: str,
        born_on: str,
        gender: str,
        title: str,
        email: str,
        phone_number: str,
        passport_number: str | None = None,
        passport_expiry: str | None = None,
        passport_nationality: str | None = None,
        loyalty_programmes: list | None = None,
    ) -> str:
        """Save or update a passenger profile for easy booking.

        Args:
            name: Short key for lookup (e.g. 'jack')
            given_name: First/given name as on passport
            family_name: Last/family name as on passport
            born_on: Date of birth (YYYY-MM-DD)
            gender: 'm' or 'f'
            title: 'mr', 'mrs', 'ms', 'miss', 'dr'
            email: Contact email address
            phone_number: Phone number with country code (e.g. +447700000000)
            passport_number: Passport number (optional)
            passport_expiry: Passport expiry date YYYY-MM-DD (optional)
            passport_nationality: Passport nationality ISO code (optional)
            loyalty_programmes: List of {airline_iata_code, account_number} (optional)
        """
        passengers = load_passengers()
        profile = {
            "name": name.lower().strip(),
            "given_name": given_name,
            "family_name": family_name,
            "born_on": born_on,
            "gender": gender.lower().strip(),
            "title": title.lower().strip(),
            "email": email,
            "phone_number": phone_number,
            "passport_number": passport_number,
            "passport_expiry": passport_expiry,
            "passport_nationality": passport_nationality,
            "loyalty_programmes": loyalty_programmes or [],
        }

        existing = next((i for i, p in enumerate(passengers) if p["name"] == profile["name"]), None)
        if existing is not None:
            passengers[existing] = profile
            save_passengers(passengers)
            return f"Updated passenger profile '{profile['name']}'."
        else:
            passengers.append(profile)
            save_passengers(passengers)
            return f"Saved new passenger profile '{profile['name']}'."

    @mcp.tool()
    def list_passengers() -> str:
        """List all saved passenger profiles."""
        passengers = load_passengers()
        if not passengers:
            return "No passenger profiles saved. Use save_passenger to add one."

        lines = []
        for p in passengers:
            line = f"{p['name']}: {p['given_name']} {p['family_name']} ({p['email']})"
            if p.get("loyalty_programmes"):
                programmes = ", ".join(
                    f"{lp['airline_iata_code']}: {lp['account_number']}"
                    for lp in p["loyalty_programmes"]
                )
                line += f" | Loyalty: {programmes}"
            lines.append(line)

        lines.append(f"\n{len(passengers)} passenger(s) saved.")
        return "\n".join(lines)

    @mcp.tool()
    def get_passenger(name: str) -> str:
        """Get a passenger profile by name. Returns JSON for use with duffel_book_flight.

        Args:
            name: The short name key of the passenger (e.g. 'jack')
        """
        passengers = load_passengers()
        key = name.lower().strip()
        profile = next((p for p in passengers if p["name"] == key), None)

        if not profile:
            return f"No passenger profile found for '{key}'. Use list_passengers to see saved profiles."

        return json.dumps(profile, indent=2)

    @mcp.tool()
    def delete_passenger(name: str) -> str:
        """Delete a saved passenger profile.

        Args:
            name: The short name key of the passenger to delete (e.g. 'jack')
        """
        passengers = load_passengers()
        key = name.lower().strip()
        before = len(passengers)
        passengers = [p for p in passengers if p["name"] != key]

        if len(passengers) == before:
            return f"No passenger profile found for '{key}'. Use list_passengers to see saved profiles."

        save_passengers(passengers)
        return f"Deleted passenger profile '{key}'. {len(passengers)} profile(s) remaining."
