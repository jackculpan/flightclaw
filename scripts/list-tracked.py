#!/usr/bin/env python3
"""List all tracked flights with price history."""

import json
import os
import sys

from search_utils import fmt_price

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
TRACKED_FILE = os.path.join(DATA_DIR, "tracked.json")


def main():
    if not os.path.exists(TRACKED_FILE):
        print("No flights being tracked. Use track-flight.py to add routes.")
        sys.exit(0)

    with open(TRACKED_FILE, "r") as f:
        tracked = json.load(f)

    if not tracked:
        print("No flights being tracked. Use track-flight.py to add routes.")
        sys.exit(0)

    for entry in tracked:
        route = f"{entry['origin']} -> {entry['destination']}"
        cabin = entry.get("cabin", "ECONOMY")
        currency = entry.get("currency", "USD")
        print(f"\n{'='*60}")
        print(f"{route} | {entry['date']} | {cabin} | {currency}")
        if entry.get("return_date"):
            print(f"  Return: {entry['return_date']}")
        if entry.get("target_price"):
            print(f"  Target: {fmt_price(entry['target_price'], currency)}")

        history = entry.get("price_history", [])
        if not history:
            print("  No price data yet")
            continue

        first_price = next((p["best_price"] for p in history if p["best_price"]), None)
        last = history[-1]
        current_price = last.get("best_price")

        if current_price and first_price:
            change = current_price - first_price
            pct = (change / first_price) * 100
            direction = "down" if change < 0 else "up"
            print(f"  Current: {fmt_price(current_price, currency)} ({last.get('airline', '?')})")
            print(f"  Original: {fmt_price(first_price, currency)} | {direction} {fmt_price(abs(change), currency)} ({abs(pct):.1f}%)")
        elif current_price:
            print(f"  Current: {fmt_price(current_price, currency)} ({last.get('airline', '?')})")

        print(f"  Checks: {len(history)} | Since: {entry.get('added_at', '?')[:10]}")

    print(f"\n{len(tracked)} flight(s) tracked.")


if __name__ == "__main__":
    main()
