#!/usr/bin/env python3
"""Reset the demo lab to a clean state.

Usage:
    python scripts/reset_demo.py
"""

from __future__ import annotations

import os
import urllib.request
import json

API_URL = os.environ.get("OPENSRE_API_URL", "http://localhost:8000")
ADMIN_KEY = os.environ.get("DEMO_ADMIN_KEY", "change-me-admin-key")


def main() -> None:
    req = urllib.request.Request(
        f"{API_URL}/api/v1/demo/reset",
        method="POST",
        headers={"X-API-Key": ADMIN_KEY},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            print(resp.read().decode())
    except Exception as exc:  # noqa: BLE001
        print(f"Reset failed: {exc}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
