#!/usr/bin/env python3
"""
Poll configured job boards, remember seen postings in SQLite, notify via Telegram.
"""

from __future__ import annotations

import argparse
import codecs
import json
import os
import re
import sqlite3
import sys
import time
import uuid
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from html import escape as html_escape
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

import requests
from dotenv import load_dotenv

# Load `.env` from this folder when you run locally (never commit `.env`).
load_dotenv(Path(__file__).resolve().parent / ".env")

STATE_DB = os.environ.get("STATE_DB_PATH", "./state.db")
CONFIG_PATH = os.environ.get("CONFIG_PATH", "./config.json")
# Sources discovered by scripts/discover_uk_startups.py live in their own file so
# that regenerating config.json from scripts/build_config.py never drops them.
AUTO_CONFIG_PATH = os.environ.get("AUTO_CONFIG_PATH", "./config.uk.auto.json")


UA_BROWSER = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


class SourceSkipped(Exception):
    """Source cannot run right now (e.g. missing optional API key) — not an error."""


def merge_auto_sources(config: dict[str, Any], auto_path: str) -> dict[str, Any]:
    if not Path(auto_path).is_file():
        return config
    try:
        with open(auto_path, encoding="utf-8") as f:
            auto = json.load(f)
    except json.JSONDecodeError as e:
        print(f"[warn] {auto_path} is not valid JSON ({e}); ignoring it.")
        return config

    sources = config.setdefault("sources", [])
    existing = {source_key(s) for s in sources}
    added = 0
    for src in auto.get("sources") or []:
        if source_key(src) in existing:
            continue
        existing.add(source_key(src))
        sources.append(src)
        added += 1
    if added:
        print(f"Merged {added} auto-discovered source(s) from {auto_path}")
    return config


def load_config(path: str) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        config = json.load(f)
    return merge_auto_sources(config, AUTO_CONFIG_PATH)


def get_env(name: str) -> str:
    v = os.environ.get(name, "").strip()
    if not v:
        print(f"Missing required environment variable: {name}", file=sys.stderr)
        sys.exit(1)
    return v


def init_db(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS seen_jobs (
            source_key TEXT NOT NULL,
            job_id TEXT NOT NULL,
            title TEXT,
            url TEXT,
            first_seen REAL NOT NULL,
            PRIMARY KEY (source_key, job_id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS source_state (
            source_key TEXT PRIMARY KEY,
            primed_at REAL NOT NULL
        )
        """
    )
    conn.commit()


def source_is_new(conn: sqlite3.Connection, source_key: str) -> bool:
    """
    True when a source has never been polled. Sources added before source_state
    existed are recognised by their recorded postings, so they are not re-primed.
    """
    row = conn.execute(
        "SELECT 1 FROM source_state WHERE source_key = ? LIMIT 1",
        (source_key,),
    ).fetchone()
    if row is not None:
        return False
    row = conn.execute(
        "SELECT 1 FROM seen_jobs WHERE source_key = ? LIMIT 1",
        (source_key,),
    ).fetchone()
    return row is None


def mark_source_primed(conn: sqlite3.Connection, source_key: str) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO source_state (source_key, primed_at) VALUES (?, ?)",
        (source_key, time.time()),
    )
    conn.commit()


def already_seen(conn: sqlite3.Connection, source_key: str, job_id: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM seen_jobs WHERE source_key = ? AND job_id = ?",
        (source_key, job_id),
    ).fetchone()
    return row is not None


def mark_seen(
    conn: sqlite3.Connection,
    source_key: str,
    job_id: str,
    title: str,
    url: str,
) -> None:
    conn.execute(
        """
        INSERT OR IGNORE INTO seen_jobs (source_key, job_id, title, url, first_seen)
        VALUES (?, ?, ?, ?, ?)
        """,
        (source_key, job_id, title, url, time.time()),
    )
    conn.commit()


def title_matches(title: str, keywords: list[str]) -> bool:
    t = title.lower()
    for k in keywords:
        kl = k.lower()
        if kl == "intern":
            if re.search(r"\bintern\b", t):
                return True
        elif kl in t:
            return True
    return False


def source_keywords(config: dict[str, Any], src: dict[str, Any]) -> list[str]:
    """Stage keywords for a source: per-source list, named profile, or global."""
    if src.get("title_keywords"):
        return list(src["title_keywords"])
    profile = src.get("keyword_profile")
    if profile:
        profiles = config.get("keyword_profiles") or {}
        if profile in profiles:
            return list(profiles[profile])
        print(f"[warn] unknown keyword_profile {profile!r}; using global keywords")
    return list(config.get("title_keywords") or ["intern", "internship"])


def source_role_filter(
    config: dict[str, Any], src: dict[str, Any]
) -> tuple[list[str], bool, list[str]]:
    """Return (require_any, allow_vague, exclude_any) for a source."""
    profiles = config.get("role_profiles") or {}
    name = src.get("role_profile") or "default"
    profile = profiles.get(name)
    if profile is None:
        if name != "default":
            print(f"[warn] unknown role_profile {name!r}; using default")
        profile = profiles.get("default") or {}
    require_any = list(
        src.get("title_require_any")
        or profile.get("require_any")
        or config.get("title_require_any")
        or []
    )
    allow_vague = bool(profile.get("allow_vague"))
    exclude_any = list(profile.get("exclude_any") or config.get("title_exclude_any") or [])
    return require_any, allow_vague, exclude_any


def title_passes(
    title: str,
    keywords: list[str],
    require_any: list[str],
    allow_vague: bool,
    exclude_any: list[str],
) -> bool:
    """Early-career keyword gate, then the function gate unless vague titles are allowed."""
    if not title_matches(title, keywords):
        return False
    if exclude_any and title_matches(title, exclude_any):
        return False
    if require_any and not allow_vague and not title_matches(title, require_any):
        return False
    return True


# US state / DC codes for "City, ST" style locations (Greenhouse, Lever, etc.).
US_STATE_CODES: set[str] = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "DC", "FL", "GA", "HI", "ID",
    "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO",
    "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA",
    "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY", "PR",
}

# Canadian provinces — trailing ", ON" is not a US location.
CA_PROVINCE_CODES: set[str] = {
    "ON", "QC", "BC", "AB", "SK", "MB", "NL", "NS", "NB", "PE", "YT", "NT", "NU",
}

_US_POSITIVE_RE = re.compile(
    r"united states(\s+of\s+america)?|(^|[,;|])\s*us\s*($|[,;|])|\busa\b|\bu\.s\.a\.?\b|"
    r"\bu\.s\.(?![a-z])|\(\s*us\s*\)|\(\s*usa\s*\)|\b(?:us|usa)\s+remote\b|\bremote[^\n,]{0,24}\b(?:us|usa)\b",
    re.I,
)

_NON_US_REGION_RE = re.compile(
    r"\b(?:india|china|canada|ireland|israel|australia|germany|france|japan|"
    r"singapore|mexico|brazil|spain|italy|netherlands|switzerland|sweden|poland|"
    r"belgium|hungary|romania|croatia|serbia|ukraine|russia|philippines|indonesia|"
    r"malaysia|thailand|vietnam|portugal|austria|finland|norway|denmark|greece|"
    r"taiwan|colombia|chile|argentina|peru|south\s+africa|new\s+zealand|hong\s+kong|"
    r"south\s+korea|korea|united\s+kingdom|uk|"
    r"bengaluru|bangalore|hyderabad|pune|mumbai|delhi|chennai|kolkata|noida|"
    r"gurgaon|dubai|tel\s+aviv|zurich|stockholm|amsterdam|munich|frankfurt|"
    r"paris|berlin|tokyo|sydney|melbourne|shanghai|beijing|shenzhen|moscow|"
    r"warsaw|dublin|lisbon|madrid|barcelona|rome|milan|vienna|prague|budapest|"
    r"manila|jakarta|bangkok|ho\s+chi\s+minh|hanoi|kuala\s+lumpur|"
    r"montreal|toronto|vancouver|ottawa|calgary|edmonton|waterloo|"
    r"são\s+paulo|sao\s+paulo|mexico\s+city|buenos\s+aires|bogotá|bogota|"
    r"johannesburg|cape\s+town)\b",
    re.I,
)

_US_STATE_INLINE_RE = re.compile(
    r",\s*(" + "|".join(sorted(US_STATE_CODES)) + r")\b",
    re.I,
)

# Unambiguous UK markers: a hint containing one of these is UK regardless of
# whatever else it mentions.
_UK_STRONG_RE = re.compile(
    r"united\s+kingdom|great\s+britain|\bengland\b|\bscotland\b|\bwales\b|"
    r"northern\s+ireland|greater\s+london|(^|[,;|(\s])u\.?k\.?($|[,;|)\s])|"
    r"\bgbr?\b|\bu\.k\.|\buk\s+remote\b|\bremote[^\n,]{0,24}\buk\b",
    re.I,
)

# UK cities that also exist elsewhere (Cambridge MA, London ON, Birmingham AL),
# so they only count when the same hint has no competing country signal.
_UK_CITY_RE = re.compile(
    r"\b(?:london|cambridge|oxford|manchester|edinburgh|glasgow|bristol|leeds|"
    r"birmingham|belfast|cardiff|liverpool|sheffield|newcastle|nottingham|"
    r"brighton|reading|southampton|portsmouth|coventry|leicester|york|bath|"
    r"milton\s+keynes|cheltenham|swindon|aberdeen|dundee|exeter|norwich|"
    r"canary\s+wharf|shoreditch|farringdon|chippenham|basingstoke|guildford|"
    r"slough|watford|hounslow|croydon|warrington|harwell|didcot)\b",
    re.I,
)

_NON_UK_REGION_RE = re.compile(
    r"\b(?:united\s+states|usa|u\.s\.a\.?|canada|ontario|india|china|ireland|"
    r"israel|australia|germany|france|japan|singapore|mexico|brazil|spain|italy|"
    r"netherlands|switzerland|sweden|poland|belgium|hungary|romania|serbia|"
    r"ukraine|russia|philippines|indonesia|malaysia|thailand|vietnam|portugal|"
    r"austria|finland|norway|denmark|greece|taiwan|colombia|chile|argentina|"
    r"peru|south\s+africa|new\s+zealand|hong\s+kong|south\s+korea|korea|uae|"
    r"new\s+hampshire|massachusetts|alabama|new\s+jersey|"
    r"new\s+york|san\s+francisco|seattle|austin|chicago|boston|denver|atlanta|"
    r"toronto|montreal|vancouver|bengaluru|bangalore|hyderabad|mumbai|dublin|"
    r"paris|berlin|munich|amsterdam|zurich|stockholm|madrid|barcelona|milan|"
    r"tokyo|sydney|melbourne|singapore|tel\s+aviv|dubai|warsaw|lisbon)\b",
    re.I,
)

US_MAJOR_METROS: tuple[str, ...] = (
    "san francisco",
    "new york city",
    "new york",
    "los angeles",
    "chicago",
    "seattle",
    "austin",
    "boston",
    "denver",
    "atlanta",
    "miami",
    "philadelphia",
    "washington",
    "houston",
    "phoenix",
    "dallas",
    "detroit",
    "minneapolis",
    "portland",
    "cupertino",
    "mountain view",
    "palo alto",
    "redmond",
    "sunnyvale",
    "menlo park",
    "san diego",
    "san jose",
    "charlotte",
    "nashville",
    "pittsburgh",
    "salt lake",
)


_COUNTRY_ALIASES = {
    "US": "US", "USA": "US", "U.S.": "US", "UNITED STATES": "US",
    "UK": "GB", "GB": "GB", "GBR": "GB", "UNITED KINGDOM": "GB", "BRITAIN": "GB",
}


def normalize_countries(values: Any) -> set[str]:
    """Map assorted country spellings onto the codes the matchers understand."""
    out: set[str] = set()
    for v in values or []:
        code = _COUNTRY_ALIASES.get(str(v).strip().upper())
        if code:
            out.add(code)
    return out


def configured_countries(config: dict[str, Any]) -> set[str]:
    lf = config.get("location_filter") or {}
    return normalize_countries(lf.get("countries"))


def source_countries(src: dict[str, Any], default: set[str]) -> set[str]:
    """Per-source override, e.g. a London-only board tagged {"countries": ["GB"]}."""
    if src.get("skip_location_filter"):
        return set()
    if src.get("countries"):
        return normalize_countries(src["countries"])
    return default


def job_matches_countries(
    job: dict[str, Any], title: str, countries: set[str]
) -> bool:
    if not countries:
        return True
    if "US" in countries and job_matches_us_location(job, title):
        return True
    if "GB" in countries and job_matches_uk_location(job, title):
        return True
    return False


def _hint_is_uk(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    if _UK_STRONG_RE.search(t):
        return True
    if _NON_UK_REGION_RE.search(t):
        return False
    m = re.search(r",\s*([A-Za-z]{2})\s*$", t)
    if m and m.group(1).upper() in (US_STATE_CODES | CA_PROVINCE_CODES):
        return False
    return bool(_UK_CITY_RE.search(t))


def job_matches_uk_location(job: dict[str, Any], title: str) -> bool:
    """Heuristic: job has a UK location signal. False positives are possible."""
    cc = (job.get("country_code") or "").strip().lower()
    if cc:
        return cc in ("gb", "uk", "gbr", "united kingdom")

    gloc = (job.get("google_country") or "").strip().upper()
    if gloc:
        return gloc in ("GB", "UK", "UNITED KINGDOM")

    hints = [str(h).strip() for h in (job.get("location_hints") or []) if str(h).strip()]
    for h in hints:
        if _hint_is_uk(h):
            return True
    return _hint_is_uk(title)


def job_matches_us_location(job: dict[str, Any], title: str) -> bool:
    """Heuristic: job has a US location signal. False positives/negatives are possible."""
    cc = (job.get("country_code") or "").strip().lower()
    if cc:
        return cc in ("us", "usa")

    gloc = (job.get("google_country") or "").strip().upper()
    if gloc:
        return gloc == "US"

    hints = [str(h).strip() for h in (job.get("location_hints") or []) if str(h).strip()]
    blob = " | ".join(hints + [title]).lower()

    if _US_POSITIVE_RE.search(blob):
        return True

    for h in hints:
        ht = h.strip()
        if re.match(r"^US\s*,", ht, re.I):
            return True
        if re.search(r",\s*US\s*$", ht, re.I):
            return True

    for h in hints:
        m = re.search(r",\s*([A-Za-z]{2})\s*$", h.strip())
        if not m:
            continue
        code = m.group(1).upper()
        if code in CA_PROVINCE_CODES:
            continue
        if code in US_STATE_CODES:
            return True

    has_neg = bool(_NON_US_REGION_RE.search(blob))
    if not has_neg:
        for m in _US_STATE_INLINE_RE.finditer(blob):
            code = m.group(1).upper()
            if code in CA_PROVINCE_CODES:
                continue
            if code in US_STATE_CODES:
                return True
        metro_hits = sum(1 for m in US_MAJOR_METROS if m in blob)
        if metro_hits >= 2:
            return True

    return False


def _unicode_unescape(s: str) -> str:
    try:
        return codecs.decode(s, "unicode_escape")
    except UnicodeDecodeError:
        return s


def fetch_google_careers(src: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Parse job rows embedded in Google careers HTML (AF_initDataCallback / ds:1 blob).
    Matches the public search results page; no official JSON API.
    """
    search_url = (
        src.get("search_url")
        or "https://www.google.com/about/careers/applications/jobs/results/?q=intern"
    ).strip()
    data_key = (src.get("data_key") or "ds:1").strip()
    r = requests.get(
        search_url,
        timeout=45,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    r.raise_for_status()
    t = r.text
    key_marker = f"key: '{data_key}'"
    if key_marker not in t:
        raise RuntimeError(
            f"Google careers page missing data key {data_key!r}; page layout may have changed."
        )
    pat = re.compile(
        r'\["(\d{10,})","((?:\\.|[^"\\])*)","(https://www\.google\.com/about/careers[^"]+)"'
    )
    out: list[dict[str, Any]] = []
    for jid, title, url in pat.findall(t):
        title = _unicode_unescape(title).strip()
        link = _unicode_unescape(url).strip()
        if not jid:
            continue
        q = parse_qs(urlparse(unquote(link)).query)
        gl = (q.get("loc") or [""])[0].upper()
        hints: list[str] = [gl] if gl else []
        out.append(
            {
                "id": jid,
                "title": title,
                "url": link,
                "location_hints": hints,
                "google_country": gl,
            }
        )
    return out


def fetch_greenhouse(board_token: str) -> list[dict[str, Any]]:
    url = f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs"
    r = requests.get(url, timeout=45)
    r.raise_for_status()
    data = r.json()
    jobs = data.get("jobs") or []
    out: list[dict[str, Any]] = []
    for j in jobs:
        jid = str(j.get("id") or "")
        title = (j.get("title") or "").strip()
        link = (j.get("absolute_url") or "").strip()
        if not jid:
            continue
        hints: list[str] = []
        loc = j.get("location")
        if isinstance(loc, dict):
            name = (loc.get("name") or "").strip()
            if name:
                hints.append(name)
        for o in j.get("offices") or []:
            if not isinstance(o, dict):
                continue
            ol = o.get("location")
            if isinstance(ol, dict):
                on = (ol.get("name") or "").strip()
                if on:
                    hints.append(on)
            else:
                on2 = (o.get("name") or "").strip()
                if on2:
                    hints.append(on2)
        out.append({"id": jid, "title": title, "url": link, "location_hints": hints})
    return out


def fetch_lever(company_slug: str) -> list[dict[str, Any]]:
    r = requests.get(
        f"https://api.lever.co/v0/postings/{company_slug}",
        params={"mode": "json"},
        timeout=45,
    )
    r.raise_for_status()
    data = r.json()
    if not isinstance(data, list):
        return []
    out: list[dict[str, Any]] = []
    for j in data:
        jid = str(j.get("id") or "")
        title = (j.get("text") or "").strip()
        link = (j.get("hostedUrl") or j.get("applyUrl") or "").strip()
        if not jid:
            continue
        cats = j.get("categories") or {}
        hints: list[str] = []
        if isinstance(cats, dict):
            loc = (cats.get("location") or "").strip()
            if loc:
                hints.append(loc)
            for al in cats.get("allLocations") or []:
                s = str(al).strip()
                if s:
                    hints.append(s)
        out.append({"id": jid, "title": title, "url": link, "location_hints": hints})
    return out


def fetch_ashby(board_slug: str) -> list[dict[str, Any]]:
    r = requests.get(
        f"https://api.ashbyhq.com/posting-api/job-board/{board_slug}",
        timeout=45,
    )
    r.raise_for_status()
    jobs = (r.json() or {}).get("jobs") or []
    out: list[dict[str, Any]] = []
    for j in jobs:
        jid = str(j.get("id") or "")
        title = (j.get("title") or "").strip()
        link = (j.get("jobUrl") or j.get("applyUrl") or "").strip()
        if not jid:
            continue
        hints: list[str] = []
        loc = (j.get("location") or "").strip()
        if loc:
            hints.append(loc)
        for sl in j.get("secondaryLocations") or []:
            s = str(sl).strip()
            if s:
                hints.append(s)
        out.append({"id": jid, "title": title, "url": link, "location_hints": hints})
    return out


def fetch_smartrecruiters(company_id: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    offset = 0
    page_size = 100
    total: int | None = None

    while True:
        r = requests.get(
            f"https://api.smartrecruiters.com/v1/companies/{company_id}/postings",
            params={"limit": page_size, "offset": offset},
            timeout=45,
        )
        r.raise_for_status()
        data = r.json() or {}
        if total is None:
            total = int(data.get("totalFound") or 0)
        postings = data.get("content") or []
        if not postings:
            break

        for p in postings:
            jid = str(p.get("id") or p.get("uuid") or "")
            title = (p.get("name") or "").strip()
            company = (p.get("company") or {}).get("identifier") or company_id
            uuid = (p.get("uuid") or "").strip()
            if uuid:
                link = f"https://jobs.smartrecruiters.com/{company}/{uuid}"
            else:
                link = (p.get("ref") or "").strip()
            if not jid:
                continue
            loc = p.get("location") or {}
            hints: list[str] = []
            cc = ""
            if isinstance(loc, dict):
                cc = (loc.get("country") or "").strip().lower()
                for key in ("fullLocation", "city", "region", "country"):
                    v = loc.get(key)
                    if isinstance(v, str) and v.strip():
                        hints.append(v.strip())
            row: dict[str, Any] = {
                "id": jid,
                "title": title,
                "url": link,
                "location_hints": hints,
            }
            if cc:
                row["country_code"] = cc
            out.append(row)

        offset += len(postings)
        if total and offset >= total:
            break
        if len(postings) < page_size:
            break

    return out


def fetch_recruitee(src: dict[str, Any]) -> list[dict[str, Any]]:
    slug = (src.get("company_slug") or src.get("board_slug") or "").strip()
    if not slug:
        raise ValueError("recruitee source requires company_slug")
    r = requests.get(f"https://{slug}.recruitee.com/api/offers/", timeout=45)
    r.raise_for_status()
    offers = (r.json() or {}).get("offers") or []
    out: list[dict[str, Any]] = []
    for o in offers:
        jid = str(o.get("id") or o.get("slug") or "")
        title = (o.get("title") or "").strip()
        link = (o.get("careers_url") or o.get("url") or "").strip()
        if not link and o.get("slug"):
            link = f"https://{slug}.recruitee.com/o/{o['slug']}"
        if not jid or not title:
            continue
        hints: list[str] = []
        for key in ("city", "state", "country", "location"):
            v = (o.get(key) or "").strip()
            if v:
                hints.append(v)
        cc = (o.get("country_code") or "").strip().lower()
        row: dict[str, Any] = {"id": jid, "title": title, "url": link, "location_hints": hints}
        if cc:
            row["country_code"] = cc
        out.append(row)
    return out


_PHENOM_REF_RE = re.compile(r'"refNum"\s*:\s*"([^"]+)"')


def fetch_phenom(src: dict[str, Any]) -> list[dict[str, Any]]:
    base_url = (src.get("base_url") or "").strip().rstrip("/")
    search_url = (src.get("search_url") or f"{base_url}/search-results").strip()
    ref_num = (src.get("ref_num") or "").strip()
    keywords = (src.get("keywords") or "intern").strip()
    page_size = int(src.get("page_size") or 50)
    if not base_url:
        raise ValueError("phenom source requires base_url")

    if not ref_num:
        warm = requests.get(
            search_url,
            timeout=45,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
        )
        warm.raise_for_status()
        m = _PHENOM_REF_RE.search(warm.text or "")
        if not m:
            raise RuntimeError(f"phenom: could not find refNum on {search_url}")
        ref_num = m.group(1)

    out: list[dict[str, Any]] = []
    offset = 0
    total_hits: int | None = None
    while True:
        payload = {
            "lang": "en_global",
            "deviceType": "desktop",
            "country": "global",
            "pageName": "search-results",
            "size": page_size,
            "from": offset,
            "jobs": True,
            "counts": True,
            "all_fields": ["category", "country", "city", "type"],
            "clearAll": False,
            "jdsource": "facets",
            "isSliderEnable": False,
            "pageId": "page20",
            "siteType": "external",
            "keywords": keywords,
            "global": True,
            "selected_fields": {},
            "sort": {"order": "desc", "field": "postedDate"},
            "locationData": {},
            "refNum": ref_num,
            "ddoKey": "refineSearch",
        }
        r = requests.post(
            f"{base_url}/widgets",
            json=payload,
            timeout=45,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Referer": search_url,
            },
        )
        r.raise_for_status()
        refine = (r.json() or {}).get("refineSearch") or {}
        if total_hits is None:
            total_hits = int(refine.get("totalHits") or refine.get("totalCount") or 0)
        data = refine.get("data") or {}
        jobs = data.get("jobs") or []
        if not jobs:
            break
        for j in jobs:
            jid = str(j.get("jobId") or j.get("reqId") or j.get("jobSeqNo") or "")
            title = (j.get("title") or "").strip()
            link = (j.get("applyUrl") or "").strip()
            if not jid or not title:
                continue
            hints: list[str] = []
            for key in ("location", "cityStateCountry", "multi_location"):
                val = j.get(key)
                if isinstance(val, str) and val.strip():
                    hints.append(val.strip())
                elif isinstance(val, list):
                    hints.extend(str(x).strip() for x in val if str(x).strip())
            cc = (j.get("country") or "").strip().lower()
            row: dict[str, Any] = {"id": jid, "title": title, "url": link, "location_hints": hints}
            if cc in ("us", "usa", "united states"):
                row["country_code"] = "us"
            out.append(row)
        offset += len(jobs)
        if total_hits and offset >= total_hits:
            break
        if len(jobs) < page_size:
            break
    return out


def fetch_successfactors(src: dict[str, Any]) -> list[dict[str, Any]]:
    feed_url = (src.get("feed_url") or "").strip()
    if not feed_url:
        raise ValueError("successfactors source requires feed_url")
    r = requests.get(feed_url, timeout=45, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    _sf_id_re = re.compile(r"/(\d{6,})(?:/|\?|$)")
    for item in ET.fromstring(r.text).findall("./channel/item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        m = _sf_id_re.search(link)
        jid = m.group(1) if m else (item.findtext("guid") or link or "").strip()
        if not title or not link or jid in seen:
            continue
        seen.add(jid)
        out.append({"id": jid, "title": title, "url": link, "location_hints": []})
    return out


def fetch_avature(src: dict[str, Any]) -> list[dict[str, Any]]:
    feed_url = (src.get("feed_url") or "").strip()
    if not feed_url:
        raise ValueError("avature source requires feed_url")
    page_size = int(src.get("page_size") or 100)
    max_pages = int(src.get("max_pages") or 10)
    out: list[dict[str, Any]] = []
    for page in range(max_pages):
        sep = "&" if "?" in feed_url else "?"
        url = f"{feed_url}{sep}jobRecordsPerPage={page_size}&jobOffset={page * page_size}"
        r = requests.get(url, timeout=45, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        root = ET.fromstring(r.text)
        items = root.findall("./channel/item")
        if not items:
            break
        for item in items:
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            guid = (item.findtext("guid") or link or "").strip()
            jid = guid.rsplit("/", 1)[-1] if guid else link
            if not title or not link:
                continue
            out.append({"id": jid, "title": title, "url": link, "location_hints": []})
        if len(items) < page_size:
            break
    return out


def fetch_bofa(src: dict[str, Any]) -> list[dict[str, Any]]:
    search = (src.get("search") or "getAllJobs").strip()
    page_size = int(src.get("page_size") or 100)
    max_pages = int(src.get("max_pages") or 20)
    out: list[dict[str, Any]] = []
    for page in range(max_pages):
        start = page * page_size
        r = requests.get(
            "https://careers.bankofamerica.com/services/jobssearchservlet",
            params={"start": start, "rows": page_size, "search": search},
            timeout=45,
            headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"},
        )
        r.raise_for_status()
        data = r.json() or {}
        jobs = data.get("jobsList") or []
        if not jobs:
            break
        for j in jobs:
            jid = str(j.get("jobRequisitionId") or "")
            title = (j.get("postingTitle") or "").strip()
            path = (j.get("jcrURL") or "").strip()
            link = f"https://careers.bankofamerica.com{path}" if path.startswith("/") else path
            if not jid or not title:
                continue
            hints = [
                x
                for x in (
                    j.get("primaryLocation"),
                    j.get("location"),
                    j.get("city"),
                    j.get("state"),
                    j.get("country"),
                )
                if isinstance(x, str) and x.strip()
            ]
            cc = (j.get("country") or "").strip().lower()
            row: dict[str, Any] = {"id": jid, "title": title, "url": link, "location_hints": hints}
            if cc == "united states":
                row["country_code"] = "us"
            out.append(row)
        total = int(data.get("totalMatches") or 0)
        if start + len(jobs) >= total:
            break
    return out


def fetch_playwright(src: dict[str, Any]) -> list[dict[str, Any]]:
    profile = (src.get("profile") or "").strip()
    if not profile:
        raise ValueError("playwright source requires profile")
    scripts_dir = Path(__file__).resolve().parent / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    from playwright_fetch import fetch_playwright_profile

    return fetch_playwright_profile(profile, src)


_VALVE_JOB_RE = re.compile(
    r'<a href="([^"]+job_id=\d+)"[^>]*>\s*<h5 class="job_title">\s*([^<]+?)\s*</h5>',
    re.I | re.S,
)


def fetch_valve(src: dict[str, Any]) -> list[dict[str, Any]]:
    url = (src.get("jobs_url") or "https://www.valvesoftware.com/en/jobs").strip()
    r = requests.get(
        url,
        timeout=45,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
            ),
        },
    )
    r.raise_for_status()
    out: list[dict[str, Any]] = []
    for link, title in _VALVE_JOB_RE.findall(r.text or ""):
        title = re.sub(r"\s+", " ", title).strip()
        m = re.search(r"job_id=(\d+)", link)
        jid = m.group(1) if m else link
        if not title:
            continue
        if link.startswith("/"):
            link = f"https://www.valvesoftware.com{link}"
        out.append({"id": jid, "title": title, "url": link, "location_hints": ["Bellevue, WA"]})
    return out


def fetch_usajobs(src: dict[str, Any]) -> list[dict[str, Any]]:
    """
    USAJOBS public API — free key from https://developer.usajobs.gov/
    Set USAJOBS_API_KEY and USAJOBS_USER_AGENT (your email) in .env
    """
    api_key = os.environ.get("USAJOBS_API_KEY", "").strip()
    user_agent = os.environ.get("USAJOBS_USER_AGENT", "").strip()
    if not api_key or not user_agent:
        raise RuntimeError(
            "USAJOBS_API_KEY and USAJOBS_USER_AGENT (email) required in .env — "
            "see https://developer.usajobs.gov/"
        )
    org = (src.get("org_keyword") or "NASA").strip()
    query = (src.get("search_keyword") or "intern").strip()
    keyword = f"{org} {query}".strip()
    out: list[dict[str, Any]] = []
    page = 1
    while page <= 5:
        r = requests.get(
            "https://data.usajobs.gov/api/search",
            params={
                "Keyword": keyword,
                "LocationName": "United States",
                "Page": page,
                "ResultsPerPage": 100,
            },
            headers={
                "Host": "data.usajobs.gov",
                "User-Agent": user_agent,
                "Authorization-Key": api_key,
            },
            timeout=45,
        )
        r.raise_for_status()
        data = r.json() or {}
        items = (
            (data.get("SearchResult") or {}).get("SearchResultItems") or []
        )
        if not items:
            break
        for item in items:
            md = (item.get("MatchedObjectDescriptor") or {})
            jid = str(md.get("PositionID") or md.get("MatchedObjectId") or "")
            title = (md.get("PositionTitle") or "").strip()
            link = (md.get("PositionURI") or "").strip()
            if not jid or not title:
                continue
            locs = md.get("PositionLocation") or []
            hints: list[str] = []
            for loc in locs:
                if isinstance(loc, dict):
                    name = (loc.get("LocationName") or "").strip()
                    if name:
                        hints.append(name)
            cc = ""
            if locs and isinstance(locs[0], dict):
                cc = (locs[0].get("CountryCode") or "").strip().lower()
            row: dict[str, Any] = {
                "id": jid,
                "title": title,
                "url": link,
                "location_hints": hints,
            }
            if cc:
                row["country_code"] = cc
            out.append(row)
        if len(items) < 100:
            break
        page += 1
    return out


def fetch_amazon(src: dict[str, Any]) -> list[dict[str, Any]]:
    query = (src.get("query") or "intern").strip()
    out: list[dict[str, Any]] = []
    offset = 0
    page_size = 100
    total: int | None = None

    while True:
        r = requests.get(
            "https://amazon.jobs/en/search.json",
            params={
                "base_query": query,
                "offset": offset,
                "result_limit": page_size,
            },
            timeout=45,
        )
        r.raise_for_status()
        data = r.json() or {}
        if total is None:
            total = int(data.get("hits") or 0)
        jobs = data.get("jobs") or []
        if not jobs:
            break

        for j in jobs:
            jid = str(j.get("id") or j.get("job_id") or "")
            title = (j.get("title") or "").strip()
            path = (j.get("job_path") or "").strip()
            if path.startswith("/"):
                link = f"https://amazon.jobs{path}"
            else:
                link = path
            if not jid:
                continue
            loc = (j.get("location") or "").strip()
            hints = [loc] if loc else []
            cc = ""
            if loc:
                first = loc.split(",")[0].strip().upper()
                if len(first) == 2 and first.isalpha():
                    cc = first.lower()
            row: dict[str, Any] = {"id": jid, "title": title, "url": link, "location_hints": hints}
            if cc:
                row["country_code"] = cc
            out.append(row)

        offset += len(jobs)
        if total and offset >= total:
            break
        if len(jobs) < page_size:
            break

    return out


def fetch_workday(src: dict[str, Any]) -> list[dict[str, Any]]:
    host = (src.get("host") or "").strip().rstrip("/")
    tenant = (src.get("tenant") or "").strip()
    site = (src.get("site") or "").strip()
    locale = (src.get("locale") or "en-US").strip()
    search_text = (src.get("search_text") or "intern").strip()
    # Workday pages 20 at a time, so broad queries (e.g. Airbus "placement")
    # cost dozens of round trips; cap them to keep one source from dominating.
    max_results = int(src.get("max_results") or 600)
    out: list[dict[str, Any]] = []
    offset = 0
    page_size = 20
    total: int | None = None

    while True:
        r = requests.post(
            f"{host}/wday/cxs/{tenant}/{site}/jobs",
            json={
                "appliedFacets": {},
                "limit": page_size,
                "offset": offset,
                "searchText": search_text,
            },
            timeout=45,
        )
        r.raise_for_status()
        data = r.json() or {}
        if total is None:
            total = int(data.get("total") or 0)
        postings = data.get("jobPostings") or []
        if not postings:
            break

        for p in postings:
            path = (p.get("externalPath") or "").strip()
            bullets = p.get("bulletFields") or []
            jid = str(bullets[0] if bullets else path or p.get("title") or "")
            title = (p.get("title") or "").strip()
            if path:
                link = f"{host}/{locale}/{site}{path}"
            else:
                link = ""
            if not jid:
                continue
            loc_txt = (p.get("locationsText") or "").strip()
            hints = [loc_txt] if loc_txt else []
            out.append({"id": jid, "title": title, "url": link, "location_hints": hints})

        offset += len(postings)
        if total and offset >= total:
            break
        if len(postings) < page_size:
            break
        if len(out) >= max_results:
            break

    return out


def fetch_pcsx(src: dict[str, Any]) -> list[dict[str, Any]]:
    list_url = (src.get("list_url") or "").strip()
    domain = (src.get("domain") or "").strip()
    query = (src.get("query") or "intern").strip()
    start_param = (src.get("start_param") or "start").strip()
    page_size_param = (src.get("page_size_param") or "count").strip()
    page_size = int(src.get("page_size") or 10)
    out: list[dict[str, Any]] = []
    start = 0
    total: int | None = None
    origin = "/".join(list_url.split("/")[:3])

    while True:
        params: dict[str, Any] = {
            "domain": domain,
            "query": query,
            start_param: start,
            page_size_param: page_size,
        }
        if page_size_param == "count":
            params["sort_by"] = "relevance"

        r = requests.get(list_url, params=params, timeout=45)
        r.raise_for_status()
        payload = r.json() or {}
        data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
        if total is None:
            total = int(data.get("count") or payload.get("count") or 0)
        positions = data.get("positions") or []
        if not positions:
            break

        for p in positions:
            jid = str(p.get("id") or "")
            title = (p.get("name") or "").strip()
            link = (p.get("canonicalPositionUrl") or "").strip()
            if not link:
                path = (p.get("positionUrl") or "").strip()
                if path.startswith("/"):
                    link = f"{origin}{path}"
                else:
                    link = path
            if not jid:
                continue
            hints: list[str] = []
            for key in ("standardizedLocations", "locations"):
                for x in p.get(key) or []:
                    s = str(x).strip()
                    if s:
                        hints.append(s)
            out.append({"id": jid, "title": title, "url": link, "location_hints": hints})

        start += len(positions)
        if total and start >= total:
            break
        if len(positions) < page_size:
            break

    return out


_VIEW_LINK_RE = re.compile(r"\[View\]\((https://apply\.workable\.com/[^)]+)\)")


def fetch_workable(src: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Workable-hosted careers: public markdown feed per shortcode.
    See https://apply.workable.com/{shortcode}/jobs.md (Accept: text/markdown).
    """
    shortcode = (src.get("shortcode") or "").strip()
    if not shortcode:
        raise ValueError("workable source requires non-empty shortcode")
    url = f"https://apply.workable.com/{shortcode}/jobs.md"
    r = requests.get(
        url,
        timeout=45,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "text/markdown,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    r.raise_for_status()
    ctype = (r.headers.get("content-type") or "").lower()
    text = r.text or ""
    if "markdown" not in ctype and not text.lstrip().startswith("#"):
        raise RuntimeError(
            f"Workable {shortcode!r}: expected markdown feed from {url!r}, "
            f"got content-type {ctype!r} ({len(text)} bytes)."
        )

    out: list[dict[str, Any]] = []
    for m in _VIEW_LINK_RE.finditer(text):
        raw_url = m.group(1).strip()
        line_start = text.rfind("\n", 0, m.start()) + 1
        line_end = text.find("\n", m.end())
        line = text[line_start : line_end if line_end != -1 else len(text)]
        parts = [p.strip() for p in line.strip().strip("|").split("|")]
        title = parts[0] if parts else ""
        loc = parts[2] if len(parts) > 2 else ""
        hints = [loc] if loc else []
        link = raw_url.removesuffix(".md")
        id_m = re.search(r"/jobs/view/([^/.?#]+)", raw_url, re.I)
        jid = (id_m.group(1) if id_m else "") or raw_url
        if not title or not jid:
            continue
        out.append({"id": jid, "title": title, "url": link, "location_hints": hints})

    return out


def fetch_oracle_careers(src: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Oracle Cloud HCM careers (careers.oracle.com).
    Uses the public recruitingCEJobRequisitions REST API.
    """
    host = (src.get("host") or "eeho.fa.us2.oraclecloud.com").strip().rstrip("/")
    site_number = (src.get("site_number") or "CX_45001").strip()
    keyword = (src.get("search_keyword") or "intern").strip()
    job_url_tmpl = (
        src.get("job_url")
        or "https://careers.oracle.com/en/sites/jobsearch/job/{id}"
    ).strip()
    page_size = int(src.get("page_size") or 100)
    out: list[dict[str, Any]] = []
    offset = 0
    list_url = f"https://{host}/hcmRestApi/resources/latest/recruitingCEJobRequisitions"

    while True:
        params = {
            "onlyData": "true",
            "expand": (
                "requisitionList.workLocation,"
                "requisitionList.otherWorkLocations,"
                "requisitionList.secondaryLocations"
            ),
            "finder": f"findReqs;siteNumber={site_number},keyword={keyword}",
            "limit": page_size,
            "offset": offset,
        }
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json",
            "ora-irc-cx-userid": str(uuid.uuid4()),
            "ora-irc-language": "en",
            "content-type": "application/vnd.oracle.adf.resourceitem+json;charset=utf-8",
        }
        r = requests.get(list_url, params=params, headers=headers, timeout=45)
        r.raise_for_status()
        payload = r.json() or {}
        postings = (payload.get("items") or [{}])[0].get("requisitionList") or []
        if not postings:
            break

        for p in postings:
            jid = str(p.get("Id") or "")
            title = (p.get("Title") or "").strip()
            if not jid or not title:
                continue
            link = job_url_tmpl.format(id=jid)
            hints: list[str] = []
            primary_loc = (p.get("PrimaryLocation") or "").strip()
            if primary_loc:
                hints.append(primary_loc)
            for key in ("secondaryLocations", "otherWorkLocations", "workLocation"):
                for loc in p.get(key) or []:
                    if isinstance(loc, dict):
                        for field in ("Name", "TownOrCity", "CountryCode"):
                            val = (loc.get(field) or "").strip()
                            if val:
                                hints.append(val)
                    elif isinstance(loc, str) and loc.strip():
                        hints.append(loc.strip())
            cc = (p.get("PrimaryLocationCountry") or "").strip().lower()
            row: dict[str, Any] = {
                "id": jid,
                "title": title,
                "url": link,
                "location_hints": hints,
            }
            if cc:
                row["country_code"] = cc
            out.append(row)

        if not payload.get("hasMore"):
            break
        offset += len(postings)
        if len(postings) < page_size:
            break

    return out


def fetch_pinpoint(src: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Pinpoint ATS (popular with UK employers): public postings feed per tenant.
    See https://{tenant}.pinpointhq.com/postings.json
    """
    tenant = (src.get("tenant") or src.get("company_slug") or "").strip()
    feed_url = (src.get("feed_url") or "").strip()
    if not feed_url:
        if not tenant:
            raise ValueError("pinpoint source requires tenant or feed_url")
        feed_url = f"https://{tenant}.pinpointhq.com/postings.json"
    r = requests.get(feed_url, timeout=45, headers={"User-Agent": UA_BROWSER})
    r.raise_for_status()
    out: list[dict[str, Any]] = []
    for p in (r.json() or {}).get("data") or []:
        jid = str(p.get("id") or "")
        title = (p.get("title") or "").strip()
        link = (p.get("url") or "").strip()
        if not jid or not title:
            continue
        hints: list[str] = []
        loc = p.get("location")
        if isinstance(loc, dict):
            for key in ("name", "city", "province", "country"):
                v = loc.get(key)
                if isinstance(v, str) and v.strip():
                    hints.append(v.strip())
        wt = (p.get("workplace_type_text") or "").strip()
        if wt:
            hints.append(wt)
        out.append({"id": jid, "title": title, "url": link, "location_hints": hints})
    return out


_TT_NS = "{https://teamtailor.com/locations}"


def fetch_teamtailor(src: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Teamtailor careers sites expose a public RSS feed per tenant.
    See https://{tenant}.teamtailor.com/jobs.rss
    """
    tenant = (src.get("tenant") or src.get("company_slug") or "").strip()
    feed_url = (src.get("feed_url") or "").strip()
    if not feed_url:
        if not tenant:
            raise ValueError("teamtailor source requires tenant or feed_url")
        feed_url = f"https://{tenant}.teamtailor.com/jobs.rss"
    r = requests.get(feed_url, timeout=45, headers={"User-Agent": UA_BROWSER})
    r.raise_for_status()
    out: list[dict[str, Any]] = []
    for item in ET.fromstring(r.text).findall("./channel/item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        jid = (item.findtext("guid") or link or "").strip()
        if not title or not jid:
            continue
        hints: list[str] = []
        locations = item.find(f"{_TT_NS}locations")
        if locations is not None:
            # <tt:locations><tt:location><tt:city>/<tt:country>...</></>
            for node in locations.iter():
                if node.tag in (f"{_TT_NS}locations", f"{_TT_NS}location"):
                    continue
                if node.tag in (f"{_TT_NS}name", f"{_TT_NS}city", f"{_TT_NS}country"):
                    text = (node.text or "").strip()
                    if text and text not in hints:
                        hints.append(text)
        remote = (item.findtext("remoteStatus") or "").strip()
        if remote:
            hints.append(remote)
        out.append({"id": jid, "title": title, "url": link, "location_hints": hints})
    return out


def fetch_adzuna(src: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Adzuna aggregator — the widest UK net we have. Free credentials from
    https://developer.adzuna.com/ ; the source skips itself when unset.
    """
    app_id = os.environ.get("ADZUNA_APP_ID", "").strip()
    app_key = os.environ.get("ADZUNA_APP_KEY", "").strip()
    if not app_id or not app_key:
        raise SourceSkipped(
            "ADZUNA_APP_ID / ADZUNA_APP_KEY not set — see https://developer.adzuna.com/"
        )
    country = (src.get("country") or "gb").strip().lower()
    what = (src.get("what") or "internship").strip()
    where = (src.get("where") or "london").strip()
    distance = int(src.get("distance") or 20)
    page_size = min(int(src.get("page_size") or 50), 50)
    max_pages = int(src.get("max_pages") or 3)
    category = (src.get("category") or "").strip()

    out: list[dict[str, Any]] = []
    for page in range(1, max_pages + 1):
        params: dict[str, Any] = {
            "app_id": app_id,
            "app_key": app_key,
            "what": what,
            "results_per_page": page_size,
            "content-type": "application/json",
        }
        if where:
            params["where"] = where
            params["distance"] = distance
        if category:
            params["category"] = category
        if src.get("max_days_old"):
            params["max_days_old"] = int(src["max_days_old"])
        r = requests.get(
            f"https://api.adzuna.com/v1/api/jobs/{country}/search/{page}",
            params=params,
            timeout=45,
            headers={"User-Agent": UA_BROWSER, "Accept": "application/json"},
        )
        r.raise_for_status()
        results = (r.json() or {}).get("results") or []
        if not results:
            break
        for j in results:
            jid = str(j.get("id") or "")
            title = re.sub(r"<[^>]+>", "", j.get("title") or "").strip()
            link = (j.get("redirect_url") or "").strip()
            if not jid or not title:
                continue
            hints: list[str] = []
            loc = j.get("location")
            if isinstance(loc, dict):
                display = (loc.get("display_name") or "").strip()
                if display:
                    hints.append(display)
                hints.extend(str(a).strip() for a in loc.get("area") or [] if str(a).strip())
            company = ((j.get("company") or {}).get("display_name") or "").strip()
            row: dict[str, Any] = {
                "id": jid,
                "title": f"{title} — {company}" if company else title,
                "url": link,
                "location_hints": hints,
            }
            if country == "gb":
                row["country_code"] = "gb"
            elif country == "us":
                row["country_code"] = "us"
            out.append(row)
        if len(results) < page_size:
            break
    return out


def fetch_reed(src: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Reed.co.uk API — UK-only board. Free key from
    https://www.reed.co.uk/developers ; the source skips itself when unset.
    """
    api_key = os.environ.get("REED_API_KEY", "").strip()
    if not api_key:
        raise SourceSkipped(
            "REED_API_KEY not set — see https://www.reed.co.uk/developers"
        )
    keywords = (src.get("keywords") or "internship").strip()
    location = (src.get("location") or "London").strip()
    distance = int(src.get("distance") or 15)
    page_size = min(int(src.get("page_size") or 100), 100)
    max_pages = int(src.get("max_pages") or 3)

    out: list[dict[str, Any]] = []
    skip = 0
    for _ in range(max_pages):
        params: dict[str, Any] = {
            "keywords": keywords,
            "resultsToTake": page_size,
            "resultsToSkip": skip,
        }
        if location:
            params["locationName"] = location
            params["distanceFromLocation"] = distance
        r = requests.get(
            "https://www.reed.co.uk/api/1.0/search",
            params=params,
            auth=(api_key, ""),
            timeout=45,
            headers={"User-Agent": UA_BROWSER, "Accept": "application/json"},
        )
        r.raise_for_status()
        data = r.json() or {}
        results = data.get("results") or []
        if not results:
            break
        for j in results:
            jid = str(j.get("jobId") or "")
            title = (j.get("jobTitle") or "").strip()
            link = (j.get("jobUrl") or "").strip()
            if not jid or not title:
                continue
            employer = (j.get("employerName") or "").strip()
            hints = [x for x in [(j.get("locationName") or "").strip()] if x]
            out.append(
                {
                    "id": jid,
                    "title": f"{title} — {employer}" if employer else title,
                    "url": link,
                    "location_hints": hints,
                    "country_code": "gb",
                }
            )
        skip += len(results)
        if skip >= int(data.get("totalResults") or 0) or len(results) < page_size:
            break
    return out


def fetch_microsoft(src: dict[str, Any]) -> list[dict[str, Any]]:
    merged = {
        "list_url": "https://apply.careers.microsoft.com/api/pcsx/search",
        "domain": src.get("domain") or "microsoft.com",
        "query": src.get("query") or "intern",
        "page_size_param": "count",
        "page_size": 10,
        "start_param": "start",
    }
    return fetch_pcsx(merged)


def source_key(src: dict[str, Any]) -> str:
    stype = src.get("type") or "unknown"
    if stype == "greenhouse":
        return f"{stype}:{src.get('board_token') or src.get('name') or 'unknown'}"
    if stype == "lever":
        return f"{stype}:{src.get('company_slug') or src.get('name') or 'unknown'}"
    if stype == "ashby":
        return f"{stype}:{src.get('board_slug') or src.get('name') or 'unknown'}"
    if stype == "smartrecruiters":
        return f"{stype}:{src.get('company_id') or src.get('name') or 'unknown'}"
    if stype == "amazon":
        return f"{stype}:{src.get('query') or 'intern'}"
    if stype == "workday":
        return (
            f"{stype}:{src.get('tenant') or 'unknown'}:"
            f"{src.get('site') or 'unknown'}:{src.get('search_text') or 'intern'}"
        )
    if stype in {"microsoft", "pcsx"}:
        return (
            f"pcsx:{src.get('domain') or 'unknown'}:"
            f"{src.get('query') or 'intern'}:{src.get('list_url') or 'microsoft'}"
        )
    if stype == "workable":
        return f"workable:{src.get('shortcode') or src.get('name') or 'unknown'}"
    if stype == "recruitee":
        return f"recruitee:{src.get('company_slug') or src.get('board_slug') or src.get('name') or 'unknown'}"
    if stype == "oracle_careers":
        return (
            f"oracle_careers:{src.get('host') or 'eeho.fa.us2.oraclecloud.com'}:"
            f"{src.get('site_number') or 'CX_45001'}:"
            f"{src.get('search_keyword') or 'intern'}"
        )
    if stype == "google_careers":
        return (
            f"google_careers:{src.get('data_key') or 'ds:1'}:"
            f"{src.get('search_url') or 'default'}"
        )
    if stype == "valve":
        return f"valve:{src.get('jobs_url') or 'default'}"
    if stype == "usajobs":
        return (
            f"usajobs:{src.get('org_keyword') or 'NASA'}:"
            f"{src.get('search_keyword') or 'intern'}"
        )
    if stype == "phenom":
        return (
            f"phenom:{src.get('ref_num') or src.get('base_url') or 'unknown'}:"
            f"{src.get('keywords') or 'intern'}"
        )
    if stype == "avature":
        return f"avature:{src.get('feed_url') or src.get('name') or 'unknown'}"
    if stype == "successfactors":
        return f"successfactors:{src.get('feed_url') or src.get('name') or 'unknown'}"
    if stype == "bofa":
        return f"bofa:{src.get('search') or 'getAllJobs'}"
    if stype == "playwright":
        return f"playwright:{src.get('profile') or 'unknown'}:{src.get('page_url') or 'unknown'}"
    if stype == "pinpoint":
        return f"pinpoint:{src.get('tenant') or src.get('feed_url') or src.get('name') or 'unknown'}"
    if stype == "teamtailor":
        return f"teamtailor:{src.get('tenant') or src.get('feed_url') or src.get('name') or 'unknown'}"
    if stype == "adzuna":
        return (
            f"adzuna:{src.get('country') or 'gb'}:{src.get('what') or 'internship'}:"
            f"{src.get('where') or 'london'}"
        )
    if stype == "reed":
        return (
            f"reed:{src.get('keywords') or 'internship'}:"
            f"{src.get('location') or 'London'}"
        )
    return f"{stype}:{src.get('name') or 'unknown'}"


FETCHERS = {
    "greenhouse": lambda src: fetch_greenhouse(src["board_token"]),
    "lever": lambda src: fetch_lever(src["company_slug"]),
    "ashby": lambda src: fetch_ashby(src["board_slug"]),
    "smartrecruiters": lambda src: fetch_smartrecruiters(src["company_id"]),
    "amazon": fetch_amazon,
    "workday": fetch_workday,
    "pcsx": fetch_pcsx,
    "microsoft": fetch_microsoft,
    "google_careers": fetch_google_careers,
    "workable": fetch_workable,
    "oracle_careers": fetch_oracle_careers,
    "recruitee": fetch_recruitee,
    "valve": fetch_valve,
    "usajobs": fetch_usajobs,
    "phenom": fetch_phenom,
    "successfactors": fetch_successfactors,
    "avature": fetch_avature,
    "bofa": fetch_bofa,
    "playwright": fetch_playwright,
    "pinpoint": fetch_pinpoint,
    "teamtailor": fetch_teamtailor,
    "adzuna": fetch_adzuna,
    "reed": fetch_reed,
}


def telegram_send_html(token: str, chat_id: str, text: str) -> None:
    r = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": False,
        },
        timeout=30,
    )
    if not r.ok:
        raise RuntimeError(f"Telegram API error {r.status_code}: {r.text}")


def escape_html(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


JTRACK_MARKER = "JTRACK::"
JTRACK_PREFIX = "Internship tracker data — do not unpin or delete\n"


def slugify_company(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _tg_api(token: str, method: str, payload: dict[str, Any]) -> dict[str, Any]:
    r = requests.post(
        f"https://api.telegram.org/bot{token}/{method}",
        json=payload,
        timeout=30,
    )
    body = r.json()
    if not body.get("ok"):
        raise RuntimeError(f"Telegram {method}: {body}")
    return body["result"]


def _decode_tracker(text: str) -> dict[str, Any] | None:
    idx = text.find(JTRACK_MARKER)
    if idx == -1:
        return None
    try:
        return json.loads(text[idx + len(JTRACK_MARKER) :])
    except json.JSONDecodeError:
        return None


def _encode_tracker(data: dict[str, Any]) -> str:
    return JTRACK_PREFIX + JTRACK_MARKER + json.dumps(data, separators=(",", ":"))


def _load_pinned_tracker(token: str, chat_id: str) -> tuple[dict[str, Any], int | None]:
    chat = _tg_api(token, "getChat", {"chat_id": chat_id})
    pm = chat.get("pinned_message") or {}
    text = pm.get("text") or ""
    msg_id = pm.get("message_id")
    decoded = _decode_tracker(text)
    if decoded is None:
        return {"applied": {}, "deadlines": [], "notified": {}, "updatedAt": 0}, msg_id
    decoded.setdefault("applied", {})
    decoded.setdefault("deadlines", [])
    decoded.setdefault("notified", {})
    return decoded, msg_id


def _save_pinned_tracker(
    token: str, chat_id: str, data: dict[str, Any], msg_id: int | None
) -> int | None:
    text = _encode_tracker(data)
    if msg_id:
        try:
            _tg_api(
                token,
                "editMessageText",
                {"chat_id": chat_id, "message_id": msg_id, "text": text},
            )
            return msg_id
        except RuntimeError as e:
            if "exactly the same" not in str(e).lower():
                msg_id = None
    msg = _tg_api(
        token,
        "sendMessage",
        {"chat_id": chat_id, "text": text, "disable_notification": True},
    )
    new_id = msg["message_id"]
    _tg_api(
        token,
        "pinChatMessage",
        {"chat_id": chat_id, "message_id": new_id, "disable_notification": True},
    )
    return new_id


def mark_company_notified(token: str, chat_id: str, company_name: str) -> None:
    """Record a new job alert in the pinned webapp sync message."""
    slug = slugify_company(company_name)
    if not slug:
        return
    try:
        data, msg_id = _load_pinned_tracker(token, chat_id)
        notified = data.setdefault("notified", {})
        notified[slug] = int(time.time() * 1000)
        data["updatedAt"] = notified[slug]
        _save_pinned_tracker(token, chat_id, data, msg_id)
    except Exception as e:
        print(f"[warn] Could not update tracker highlight for {company_name}: {e}")


def fetch_source(src: dict[str, Any]) -> tuple[list[dict[str, Any]], str | None]:
    """Run one source's fetcher. Returns (jobs, error_message)."""
    stype = src.get("type")
    try:
        return FETCHERS[stype](src), None
    except SourceSkipped as e:
        return [], f"skip:{e}"
    except Exception as e:
        return [], f"error:{e}"


def fetch_all_sources(
    sources: list[dict[str, Any]], workers: int
) -> list[tuple[dict[str, Any], list[dict[str, Any]], str | None]]:
    """
    Fetch every source, HTTP ones in parallel. Playwright sources stay serial:
    each one launches a browser, so running them concurrently is a memory risk
    on the free CI runner.
    """
    results: dict[int, tuple[list[dict[str, Any]], str | None]] = {}
    parallel: list[tuple[int, dict[str, Any]]] = []
    serial: list[tuple[int, dict[str, Any]]] = []

    for i, src in enumerate(sources):
        (serial if src.get("type") == "playwright" else parallel).append((i, src))

    if parallel:
        with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
            futures = {pool.submit(fetch_source, src): i for i, src in parallel}
            for fut in as_completed(futures):
                results[futures[fut]] = fut.result()

    for i, src in serial:
        results[i] = fetch_source(src)

    return [(src, *results[i]) for i, src in enumerate(sources)]


def job_region_tag(job: dict[str, Any], title: str) -> str:
    if job_matches_uk_location(job, title):
        return "UK"
    if job_matches_us_location(job, title):
        return "US"
    return ""


def job_location_text(job: dict[str, Any]) -> str:
    for hint in job.get("location_hints") or []:
        text = str(hint).strip()
        if text:
            return text[:80]
    return ""


def send_priming_summary(token: str, chat_id: str, primed: list[tuple[str, int]]) -> None:
    """One message for freshly added sources instead of an alert per backlog job."""
    lines = [
        f"<b>Now watching {len(primed)} new source(s)</b>",
        "Existing postings recorded silently; new ones will alert.",
        "",
    ]
    lines += [f"{escape_html(name)} — {count} open match(es)" for name, count in primed]
    chunk: list[str] = []
    size = 0
    for line in lines:
        if size + len(line) > 3500:
            telegram_send_html(token, chat_id, "\n".join(chunk))
            chunk, size = [], 0
        chunk.append(line)
        size += len(line) + 1
    if chunk:
        telegram_send_html(token, chat_id, "\n".join(chunk))


def poll_once(config: dict[str, Any]) -> int:
    token = get_env("TELEGRAM_BOT_TOKEN")
    chat_id = get_env("TELEGRAM_CHAT_ID")
    default_countries = configured_countries(config)
    prime_new = config.get("prime_new_sources", True)
    workers = int(config.get("fetch_workers") or 10)

    conn = sqlite3.connect(STATE_DB)
    init_db(conn)

    sources = [s for s in (config.get("sources") or []) if s.get("type") in FETCHERS]
    for src in config.get("sources") or []:
        if src.get("type") not in FETCHERS:
            print(f"Skip unknown source type: {src.get('type')} ({src.get('name')})")

    new_count = 0
    primed: list[tuple[str, int]] = []

    for src, jobs, err in fetch_all_sources(sources, workers):
        name = src.get("name") or "unknown"
        if err:
            kind, _, detail = err.partition(":")
            print(f"[{kind}] {name}: {detail}")
            continue

        sk = source_key(src)
        countries = source_countries(src, default_countries)
        keywords = source_keywords(config, src)
        require_any, allow_vague, exclude_any = source_role_filter(config, src)
        priming = prime_new and source_is_new(conn, sk)
        primed_count = 0

        for job in jobs:
            jid = job["id"]
            title = job["title"]
            url = job["url"]
            if not title_passes(title, keywords, require_any, allow_vague, exclude_any):
                continue
            if not job_matches_countries(job, title, countries):
                continue
            if already_seen(conn, sk, jid):
                continue
            mark_seen(conn, sk, jid, title, url)

            if priming:
                primed_count += 1
                continue

            new_count += 1
            tag = job_region_tag(job, title)
            header = "<b>New internship match</b>" + (f" [{tag}]" if tag else "")
            location = job_location_text(job)
            subject = escape_html(name)
            if location:
                subject += f" — {escape_html(location)}"
            safe_title = escape_html(title)
            if url:
                safe_href = html_escape(url, quote=True)
                line = f'<a href="{safe_href}">{safe_title}</a>'
            else:
                line = safe_title
            telegram_send_html(token, chat_id, f"{header}\n{subject}\n{line}")
            mark_company_notified(token, chat_id, name)
            print(f"Notified: {name} — {title}")

        mark_source_primed(conn, sk)
        if priming:
            primed.append((name, primed_count))
            print(f"Primed new source: {name} ({primed_count} open matches)")

    if primed:
        try:
            send_priming_summary(token, chat_id, primed)
        except Exception as e:
            print(f"[warn] could not send priming summary: {e}")

    conn.close()
    return new_count


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single poll and exit (good for cron / scheduled jobs).",
    )
    args = parser.parse_args()

    if not Path(CONFIG_PATH).is_file():
        print(f"Config not found: {CONFIG_PATH}", file=sys.stderr)
        sys.exit(1)

    config = load_config(CONFIG_PATH)
    interval = int(config.get("poll_interval_seconds") or 120)

    if args.once:
        n = poll_once(config)
        print(f"Done. New postings notified: {n}")
        return

    print(f"Looping every {interval}s. SQLite: {STATE_DB}")
    while True:
        try:
            poll_once(config)
        except KeyboardInterrupt:
            raise
        except Exception as e:
            print(f"[fatal loop error] {e}")
        time.sleep(interval)


if __name__ == "__main__":
    main()
