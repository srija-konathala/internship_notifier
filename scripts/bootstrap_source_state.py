#!/usr/bin/env python3
"""
Mark sources as already-watched so priming does not swallow their alerts.

Priming (see main.poll_once) silences a source's existing postings the first
time it is polled. That is right for a board we just added, and wrong for a
board that has been watched for months but has simply never matched anything —
before source_state existed, "no rows in seen_jobs" was indistinguishable from
"brand new".

Run this once against the config as it was *before* new sources were added:

    git show <old-commit>:config.json > /tmp/old-config.json
    python scripts/bootstrap_source_state.py --config /tmp/old-config.json

Sources in the current config that are not in the old one stay unprimed, so
they get the silent first poll they should.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import main as watcher  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", default=str(ROOT / "config.json"))
    ap.add_argument("--db", default=str(ROOT / "state.db"))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    with open(args.config, encoding="utf-8") as f:
        config = json.load(f)
    sources = config.get("sources") or []

    conn = sqlite3.connect(args.db)
    watcher.init_db(conn)
    already = {
        row[0] for row in conn.execute("SELECT source_key FROM source_state").fetchall()
    }

    marked = 0
    now = time.time()
    for src in sources:
        key = watcher.source_key(src)
        if key in already:
            continue
        if not args.dry_run:
            conn.execute(
                "INSERT OR IGNORE INTO source_state (source_key, primed_at) VALUES (?, ?)",
                (key, now),
            )
        marked += 1

    if not args.dry_run:
        conn.commit()
    total = conn.execute("SELECT COUNT(*) FROM source_state").fetchone()[0]
    conn.close()

    verb = "would mark" if args.dry_run else "marked"
    print(f"{verb} {marked} source(s) as already watched; source_state now holds {total}")


if __name__ == "__main__":
    main()
