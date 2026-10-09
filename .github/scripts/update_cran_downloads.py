#!/usr/bin/env python3
"""Fetch daily CRAN download counts for my packages and write data/cran-downloads.json.

This asks the same CRAN download-log service that packageRank::cranDownloads()
uses (https://cranlogs.r-pkg.org). The end of each range is the keyword
"last-day", so it moves forward by itself every day: yesterday, or the day
before if the logs for yesterday are not in yet.

Add a package by adding one line to PACKAGES (name -> first day to plot).
Uses only the Python standard library.
"""
import datetime as dt
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

API = os.environ.get("CRANLOGS_API", "https://cranlogs.r-pkg.org").rstrip("/")

# package -> first day to plot (the `from` values in the R script)
PACKAGES = {
    "HACSim": "2019-05-09",
    "VLF": "2013-11-19",
    "RulesTools": "2025-01-28",
}

OUT = Path(__file__).resolve().parents[2] / "data" / "cran-downloads.json"


def fetch(package, start):
    url = f"{API}/downloads/daily/{start}:last-day/{package}"
    last_error = None
    for attempt in range(1, 5):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "cran-downloads-site-updater"})
            with urllib.request.urlopen(req, timeout=60) as resp:
                payload = json.load(resp)
            if not isinstance(payload, list) or not payload or "downloads" not in payload[0]:
                raise ValueError(f"unexpected response for {package}: {str(payload)[:200]}")
            return payload[0]["downloads"]
        except (urllib.error.URLError, TimeoutError, ValueError, json.JSONDecodeError) as err:
            last_error = err
            print(f"{package}: attempt {attempt} failed: {err}", file=sys.stderr)
            time.sleep(5 * attempt)
    raise SystemExit(f"{package}: giving up after repeated failures ({last_error})")


def main():
    series = {}
    for package, start in PACKAGES.items():
        rows = fetch(package, start)
        by_day = {r["day"]: int(r["downloads"]) for r in rows}
        if not by_day:
            raise SystemExit(f"{package}: the API returned no days")
        series[package] = (start, by_day)

    # The newest day with data, which the API may report later than "last-day" says.
    # Use the latest day that every package has, so all plots end on the same date.
    through = min(max(by_day) for _, by_day in series.values())
    through_date = dt.date.fromisoformat(through)

    packages = {}
    for package, (start, by_day) in series.items():
        first = dt.date.fromisoformat(start)
        if first > through_date:
            raise SystemExit(f"{package}: start {start} is after the last day with data ({through})")
        counts = []
        day = first
        while day <= through_date:
            counts.append(by_day.get(day.isoformat(), 0))  # the API zero-fills, but be safe
            day += dt.timedelta(days=1)
        packages[package] = {"from": start, "counts": counts}

    # Never replace a newer snapshot with an older one.
    if OUT.exists():
        try:
            previous = json.loads(OUT.read_text(encoding="utf-8")).get("through", "")
        except (OSError, json.JSONDecodeError):
            previous = ""
        if previous and previous > through:
            raise SystemExit(f"Existing data runs to {previous}, newer than {through}; not overwriting")

    doc = {
        "generated": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "through": through,
        "source": "https://cranlogs.r-pkg.org",
        "packages": packages,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, separators=(",", ":")) + "\n", encoding="utf-8")
    totals = ", ".join(f"{p}: {sum(v['counts']):,}" for p, v in packages.items())
    print(f"Wrote {OUT} (through {through}). Totals: {totals}")


if __name__ == "__main__":
    main()
