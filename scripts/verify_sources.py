#!/usr/bin/env python3
"""
Re-check that configured sources still respond and still carry postings.

Boards go stale: slugs get renamed, companies migrate ATS, tenants disappear.
Run this before trusting a long config.

Usage:
    python scripts/verify_sources.py                 # everything
    python scripts/verify_sources.py --region uk     # GB-tagged sources only
    python scripts/verify_sources.py --region uk --failing-only
"""

from __future__ import annotations

import argparse
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import main as watcher  # noqa: E402


def check(src: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    jobs, err = watcher.fetch_source(src)
    row: dict[str, Any] = {"name": src.get("name"), "type": src.get("type"), "error": err}
    if err:
        return row
    countries = watcher.source_countries(src, watcher.configured_countries(config))
    keywords = watcher.source_keywords(config, src)
    require_any, allow_vague, exclude_any = watcher.source_role_filter(config, src)
    row["jobs"] = len(jobs)
    row["uk_jobs"] = sum(1 for j in jobs if watcher.job_matches_uk_location(j, j["title"]))
    row["matches"] = sum(
        1
        for j in jobs
        if watcher.title_passes(j["title"], keywords, require_any, allow_vague, exclude_any)
        and watcher.job_matches_countries(j, j["title"], countries)
    )
    return row


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--region", choices=["uk", "us", "all"], default="all")
    ap.add_argument("--failing-only", action="store_true")
    ap.add_argument("--workers", type=int, default=10)
    ap.add_argument("--config", default=str(ROOT / "config.json"))
    args = ap.parse_args()

    config = watcher.load_config(args.config)
    sources = [s for s in config.get("sources") or [] if s.get("type") in watcher.FETCHERS]
    if args.region == "uk":
        sources = [s for s in sources if "GB" in (s.get("countries") or []) or s.get("skip_location_filter")]
    elif args.region == "us":
        sources = [s for s in sources if "US" in (s.get("countries") or [])]

    print(f"Checking {len(sources)} source(s)...\n")
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        rows = list(pool.map(lambda s: check(s, config), sources))

    failures = 0
    skipped = 0
    for row in sorted(rows, key=lambda r: (r.get("error") is None, r.get("name") or "")):
        error = row.get("error") or ""
        if error.startswith("skip:"):
            # Optional source without its API key; not a broken board.
            skipped += 1
            print(f"SKIP  {row['name']:34} {row['type']:16} {error[5:75]}")
        elif error:
            failures += 1
            print(f"FAIL  {row['name']:34} {row['type']:16} {error[6:76]}")
        elif not row.get("jobs"):
            failures += 1
            print(f"EMPTY {row['name']:34} {row['type']:16} board returned no postings")
        elif not args.failing_only:
            print(
                f"ok    {row['name']:34} {row['type']:16} "
                f"jobs={row['jobs']:5} uk={row['uk_jobs']:4} matches={row['matches']:3}"
            )

    healthy = len(rows) - failures - skipped
    print(f"\n{healthy}/{len(rows) - skipped} healthy" + (f", {skipped} skipped" if skipped else ""))
    raise SystemExit(1 if failures else 0)


if __name__ == "__main__":
    main()
