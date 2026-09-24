#!/usr/bin/env python3
"""
Work out which job board a company actually uses, and prove it returns jobs.

Three strategies, cheapest first:

1. Scan the careers page HTML for an embedded board URL. This is what catches
   tilt.com/careers -> Ashby board "tilthq"; the board slug rarely matches the
   company name.
2. Guess slugs from the company name across the ATS platforms we support.
3. Render the page with Playwright and watch for board API calls, for careers
   pages that are drawn client-side (suna.health does this).

Usage:
    python scripts/uk_ats_resolve.py --name Tilt --domain tilt.com
    python scripts/uk_ats_resolve.py --name Suna --domain suna.health --render
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import main as watcher  # noqa: E402

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

CAREERS_PATHS = [
    "/careers",
    "/careers/",
    "/jobs",
    "/careers/jobs",
    "/company/careers",
    "/about/careers",
    "/join-us",
    "/work-with-us",
    "/company/jobs",
]

# (source type, regex capturing the slug, config field the slug belongs in)
SLUG_PATTERNS: list[tuple[str, str, str]] = [
    (
        "greenhouse",
        r"(?:boards|job-boards)\.greenhouse\.io/(?:embed/job_board\?for=)?([a-z0-9_-]+)",
        "board_token",
    ),
    (
        "greenhouse",
        r"boards-api\.greenhouse\.io/v1/boards/([a-z0-9_-]+)",
        "board_token",
    ),
    (
        "ashby",
        r"(?:jobs\.ashbyhq\.com|api\.ashbyhq\.com/posting-api/job-board)/([a-z0-9_-]+)",
        "board_slug",
    ),
    ("ashby", r"ashby_embed[^\"']{0,40}?[\"']([a-z0-9_-]+)[\"']", "board_slug"),
    ("lever", r"jobs\.lever\.co/([a-z0-9_-]+)", "company_slug"),
    ("lever", r"api\.lever\.co/v0/postings/([a-z0-9_-]+)", "company_slug"),
    ("workable", r"apply\.workable\.com/([a-z0-9_-]+)", "shortcode"),
    ("teamtailor", r"([a-z0-9-]+)\.teamtailor\.com", "tenant"),
    ("pinpoint", r"([a-z0-9-]+)\.pinpointhq\.com", "tenant"),
    ("recruitee", r"([a-z0-9-]+)\.recruitee\.com", "company_slug"),
    (
        "smartrecruiters",
        r"(?:careers|api)\.smartrecruiters\.com/(?:v1/companies/)?([A-Za-z0-9_-]+)",
        "company_id",
    ),
]

WORKDAY_RE = re.compile(
    r"https://([a-z0-9-]+)\.(wd\d+)\.myworkdayjobs\.com/(?:[a-z]{2}-[A-Z]{2}/)?([A-Za-z0-9_]+)",
    re.I,
)

# Generic slugs that mean "this is the company's own careers page", not a board.
BAD_SLUGS = {
    "careers", "career", "jobs", "job", "embed", "boards", "board", "www",
    "api", "en", "us", "uk", "search", "apply", "job_board", "v1", "v0",
}

API_HOST_HINTS = [
    ("greenhouse", "boards-api.greenhouse.io"),
    ("ashby", "api.ashbyhq.com"),
    ("lever", "api.lever.co"),
    ("workable", "apply.workable.com"),
    ("teamtailor", "teamtailor.com"),
    ("pinpoint", "pinpointhq.com"),
    ("recruitee", "recruitee.com"),
    ("smartrecruiters", "api.smartrecruiters.com"),
]


def slug_variants(name: str) -> list[str]:
    """Company name -> plausible board slugs (Tilt also publishes as 'tilthq')."""
    base = re.sub(r"[^a-z0-9]+", "", name.lower())
    hyphen = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    stripped = re.sub(r"(ai|hq|app|io|labs|technologies|technology|group)$", "", base)
    out: list[str] = []
    for cand in (base, hyphen, stripped, f"{base}hq", f"{base}ai", f"{base}app", f"{base}io"):
        if cand and len(cand) > 2 and cand not in out:
            out.append(cand)
    return out


def source_for(stype: str, slug: str, name: str) -> dict[str, Any]:
    field = {
        "greenhouse": "board_token",
        "ashby": "board_slug",
        "lever": "company_slug",
        "workable": "shortcode",
        "smartrecruiters": "company_id",
        "recruitee": "company_slug",
        "teamtailor": "tenant",
        "pinpoint": "tenant",
    }[stype]
    return {"name": name, "type": stype, field: slug}


def fetch_careers_html(domain: str, timeout: int = 20) -> tuple[str, str]:
    """Return (final_url, html) for the first careers path that responds."""
    host = domain.strip()
    if not host.startswith("http"):
        host = f"https://{host}"
    host = host.rstrip("/")
    best = ("", "")
    for path in CAREERS_PATHS:
        try:
            r = requests.get(
                host + path,
                headers={"User-Agent": UA},
                timeout=timeout,
                allow_redirects=True,
            )
        except requests.RequestException:
            continue
        if r.status_code != 200 or not r.text:
            continue
        html = r.text
        if any(re.search(p, html, re.I) for _, p, _ in SLUG_PATTERNS) or WORKDAY_RE.search(html):
            return r.url, html
        if len(html) > len(best[1]):
            best = (r.url, html)
    return best


def candidates_from_html(html: str, name: str) -> list[dict[str, Any]]:
    """Board configs referenced by a careers page, best-looking ones first."""
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for stype, pattern, field in SLUG_PATTERNS:
        for match in re.findall(pattern, html, re.I):
            slug = (match if isinstance(match, str) else match[0]).strip()
            if len(slug) < 3 or slug.lower() in BAD_SLUGS:
                continue
            key = (stype, slug)
            if key in seen:
                continue
            seen.add(key)
            out.append({"name": name, "type": stype, field: slug})
    for tenant, wd, site in WORKDAY_RE.findall(html):
        key = ("workday", f"{tenant}/{site}")
        if key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "name": name,
                "type": "workday",
                "host": f"https://{tenant}.{wd}.myworkdayjobs.com",
                "tenant": tenant,
                "site": site,
                "search_text": "intern",
            }
        )
    return out


def candidates_from_name(name: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for slug in slug_variants(name):
        for stype in ("greenhouse", "ashby", "lever", "workable"):
            out.append(source_for(stype, slug, name))
    return out


def render_candidates(domain: str, name: str, timeout_ms: int = 45000) -> list[dict[str, Any]]:
    """Load the careers page in a browser and watch for board API traffic."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[warn] playwright not installed; skipping render fallback", file=sys.stderr)
        return []

    host = domain if domain.startswith("http") else f"https://{domain}"
    urls: list[str] = []
    html_chunks: list[str] = []

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(user_agent=UA)
            page.on("request", lambda r: urls.append(r.url))
            for path in ("/careers", "/jobs", "/careers/jobs"):
                try:
                    page.goto(host.rstrip("/") + path, wait_until="networkidle", timeout=timeout_ms)
                    page.wait_for_timeout(2500)
                    html_chunks.append(page.content())
                except Exception:
                    continue
            browser.close()
    except Exception as e:
        print(f"[warn] render failed for {domain}: {e}", file=sys.stderr)
        return []

    blob = "\n".join(html_chunks + urls)
    found = candidates_from_html(blob, name)
    if found:
        return found
    # Last resort: an API host showed up but the slug did not parse cleanly.
    for stype, host_hint in API_HOST_HINTS:
        for url in urls:
            if host_hint in url:
                print(f"[info] {name}: saw {stype} traffic at {url[:90]}", file=sys.stderr)
                break
    return []


def verify(candidate: dict[str, Any]) -> dict[str, Any] | None:
    """Fetch a candidate board; keep it only if it has live UK postings."""
    if candidate.get("type") not in watcher.FETCHERS:
        return None
    jobs, err = watcher.fetch_source(candidate)
    if err or not jobs:
        return None
    uk = [j for j in jobs if watcher.job_matches_uk_location(j, j["title"])]
    early = [
        j for j in uk
        if watcher.title_matches(
            j["title"],
            ["intern", "internship", "placement", "graduate", "junior", "student",
             "apprentice", "trainee", "entry level", "new grad"],
        )
    ]
    remote = [
        j for j in jobs
        if re.search(r"remote", " ".join(str(h) for h in j.get("location_hints") or []), re.I)
    ]
    return {
        "source": candidate,
        "jobs": len(jobs),
        "uk_jobs": len(uk),
        "uk_early_career": len(early),
        "remote_jobs": len(remote),
        "sample": [j["title"][:70] for j in (uk or jobs)[:3]],
    }


def resolve(
    name: str,
    domain: str | None = None,
    render: bool = False,
    require_uk: bool = True,
) -> dict[str, Any] | None:
    """
    Resolve a company to a live board.

    A board with UK postings wins outright. A board with postings but no UK
    location (common for London companies advertising "Remote - Europe") comes
    back flagged uk_verified=False so the caller can decide, unless require_uk
    rules it out.
    """
    tried: list[dict[str, Any]] = []
    if domain:
        _, html = fetch_careers_html(domain)
        if html:
            tried += candidates_from_html(html, name)
    tried += candidates_from_name(name)

    seen: set[str] = set()
    fallback: dict[str, Any] | None = None

    def consider(cand: dict[str, Any]) -> dict[str, Any] | None:
        nonlocal fallback
        key = json.dumps(cand, sort_keys=True)
        if key in seen:
            return None
        seen.add(key)
        result = verify(cand)
        if not result:
            return None
        if result["uk_jobs"]:
            return {**result, "uk_verified": True}
        if fallback is None:
            fallback = {**result, "uk_verified": False}
        return None

    for cand in tried:
        hit = consider(cand)
        if hit:
            return hit

    if render and domain:
        for cand in render_candidates(domain, name):
            hit = consider(cand)
            if hit:
                return hit

    return None if require_uk else fallback


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--name", required=True, help="Company name")
    ap.add_argument("--domain", help="Company domain, e.g. tilt.com")
    ap.add_argument("--render", action="store_true", help="Use Playwright fallback")
    ap.add_argument(
        "--any-location",
        action="store_true",
        help="Accept a board even when it has no UK postings right now",
    )
    args = ap.parse_args()

    result = resolve(args.name, args.domain, args.render, require_uk=not args.any_location)
    if not result:
        print(json.dumps({"name": args.name, "resolved": False}, indent=2))
        raise SystemExit(1)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
