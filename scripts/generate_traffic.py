#!/usr/bin/env python3
"""Generate baseline traffic against the demo API.

Usage:
    python scripts/generate_traffic.py --seconds 60 --rps 5
"""

from __future__ import annotations

import argparse
import asyncio
import random

import httpx

DEMO_API_URL = "http://localhost:8001"


async def generate(seconds: int, rps: int) -> None:
    async with httpx.AsyncClient(timeout=10.0) as client:
        end_time = asyncio.get_event_loop().time() + seconds
        count = 0
        errors = 0
        while asyncio.get_event_loop().time() < end_time:
            try:
                if random.random() < 0.7:
                    await client.get(f"{DEMO_API_URL}/api/orders")
                else:
                    await client.post(
                        f"{DEMO_API_URL}/api/orders",
                        json={"item": "load-test", "quantity": 1},
                    )
                count += 1
            except Exception:  # noqa: BLE001
                errors += 1
            await asyncio.sleep(1.0 / rps)
    print(f"Sent {count} requests ({errors} errors) over {seconds}s")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seconds", type=int, default=60)
    parser.add_argument("--rps", type=int, default=5)
    args = parser.parse_args()
    asyncio.run(generate(args.seconds, args.rps))


if __name__ == "__main__":
    main()
