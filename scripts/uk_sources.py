#!/usr/bin/env python3
"""
UK / London sources and the matching profiles they use.

Every board below was probed live and confirmed to (a) respond and (b) carry at
least one UK posting at the time it was added. Re-check with:

    python scripts/verify_sources.py --region uk
"""

from __future__ import annotations

# Early-career vocabulary. UK employers rarely say "intern": the summer
# equivalents are placements, industrial placements and summer analyst schemes.
UK_EARLY_CAREER_KEYWORDS = [
    "intern",
    "internship",
    "placement",
    "industrial placement",
    "year in industry",
    "summer analyst",
    "summer associate",
    "spring week",
    "spring insight",
    "insight programme",
    "insight program",
    "graduate scheme",
    "graduate programme",
    "graduate program",
    "student",
    "campus",
    "apprentice",
    "penultimate year",
]

# Startups hire early-career people under looser titles, so this adds the
# junior/entry-level vocabulary on top.
STARTUP_EARLY_CAREER_KEYWORDS = UK_EARLY_CAREER_KEYWORDS + [
    "junior",
    "new grad",
    "entry level",
    "entry-level",
    "trainee",
    "associate",
    "first job",
]

SOFTWARE_TERMS = [
    "software",
    "swe",
    "developer",
    "programmer",
    "backend",
    "back end",
    "frontend",
    "front end",
    "full stack",
    "fullstack",
    "computer science",
    "web developer",
    "mobile developer",
    "ios developer",
    "android developer",
]

# Large UK employers post placements across every function; keep the technical
# ones without opening the gate to vague titles.
UK_TECHNICAL_TERMS = SOFTWARE_TERMS + [
    "engineer",
    "engineering",
    "technology",
    "technical",
    "data",
    "machine learning",
    "artificial intelligence",
    " ai ",
    "quantitative",
    "quant",
    "research",
    "analyst",
    "analytics",
    "cyber",
    "security",
    "digital",
    "it ",
    "informatics",
    "robotics",
    "systems",
    "cloud",
    "platform",
]

# Startups: the user explicitly wants product/growth/ops and vaguely titled
# roles here, so allow_vague carries the match and this list is a hint only.
STARTUP_TERMS = SOFTWARE_TERMS + [
    "engineer",
    "engineering",
    "product",
    "growth",
    "data",
    "analyst",
    "operations",
    "ops",
    "business",
    "strategy",
    "design",
    "marketing",
    "founder",
    "chief of staff",
    "generalist",
    "research",
]

# Noise that slips through when vague titles are allowed. Seniority markers go
# first: "associate" is a useful early-career signal on its own, but not in
# "Tax Senior Associate" or "Senior Rider Onboarding Associate".
STARTUP_EXCLUDE = [
    "senior",
    "staff ",
    "principal",
    "head of",
    "director",
    "vp,",
    "vp ",
    "chief",
    "lead ",
    " lead",
    "experienced",
    "expert",
    "nurse",
    "nursing",
    "clinical",
    "phlebotom",
    "caregiver",
    "care assistant",
    "driver",
    "warehouse operative",
    "cleaner",
    "barista",
    "chef",
    "security guard",
]

KEYWORD_PROFILES = {
    "uk_early_career": UK_EARLY_CAREER_KEYWORDS,
    "startup_early_career": STARTUP_EARLY_CAREER_KEYWORDS,
}

ROLE_PROFILES = {
    "default": {"require_any": SOFTWARE_TERMS},
    "uk_technical": {"require_any": UK_TECHNICAL_TERMS},
    "startup": {
        "require_any": STARTUP_TERMS,
        "allow_vague": True,
        "exclude_any": STARTUP_EXCLUDE,
    },
}


def _startup(name: str, **fields) -> dict:
    """London/UK startup or scaleup board: loose titles, UK-only locations."""
    return {
        "name": name,
        "countries": ["GB"],
        "role_profile": "startup",
        "keyword_profile": "startup_early_career",
        **fields,
    }


def _employer(name: str, **fields) -> dict:
    """Large UK employer: technical roles only, UK-only locations."""
    return {
        "name": name,
        "countries": ["GB"],
        "role_profile": "uk_technical",
        "keyword_profile": "uk_early_career",
        **fields,
    }


def _gh(token: str) -> dict:
    return {"type": "greenhouse", "board_token": token}


def _ashby(slug: str) -> dict:
    return {"type": "ashby", "board_slug": slug}


UK_SOURCES: list[dict] = [
    # --- London startups and scaleups -------------------------------------
    _startup("Monzo", **_gh("monzo")),
    _startup("Deliveroo", **_gh("deliveroo")),
    _startup("GoCardless", **_gh("gocardless")),
    _startup("Tide", **_gh("tide")),
    _startup("SumUp", **_gh("sumup")),
    _startup("Ebury", **_gh("ebury")),
    _startup("TrueLayer", **_gh("truelayer")),
    _startup("Form3", **_gh("form3")),
    _startup("ComplyAdvantage", **_gh("complyadvantage")),
    _startup("Global Relay", **_gh("globalrelay")),
    _startup("Wayve", **_gh("wayve")),
    _startup("Graphcore", **_gh("graphcore")),
    _startup("Riverlane", **_gh("riverlane")),
    _startup("Dexory", **_gh("dexory")),
    _startup("CarbonChain", **_gh("carbonchain")),
    _startup("Nothing", **_gh("nothing")),
    _startup("Canonical", **_gh("canonical")),
    _startup("Auto Trader", **_gh("autotrader")),
    _startup("Ocado Group", **_gh("ocadogroup")),
    _startup("OVO Energy", **_gh("ovoenergy")),
    _startup("ElevenLabs", **_ashby("elevenlabs")),
    _startup("Synthesia", **_ashby("synthesia")),
    _startup("Tilt", **_ashby("tilthq")),
    _startup("Legora", **_ashby("legora")),
    _startup("Lovable", **_ashby("lovable")),
    _startup("Granola", **_ashby("granola")),
    _startup("Multiverse", **_ashby("multiverse")),
    _startup("Quantexa", **_ashby("quantexa")),
    _startup("Zego", **_ashby("zego")),
    _startup("Marshmallow", **_ashby("marshmallow")),
    _startup("Ravio", **_ashby("ravio")),
    _startup("OakNorth", **_ashby("oaknorth")),
    _startup("hyperexponential", **_ashby("hyperexponential")),
    _startup("Sylvera", **_ashby("sylvera")),
    _startup("Wonderful", **_ashby("wonderful")),
    _startup("Tractable", **_ashby("tractable")),
    _startup("Unlikely AI", **_ashby("unlikelyai")),
    _startup("n8n", **_ashby("n8n")),
    _startup("Sierra", **_ashby("sierra")),
    _startup("Goodlord", type="pinpoint", tenant="goodlord"),
    _startup("Frontier Developments", type="pinpoint", tenant="frontierdevelopments"),
    _startup("Tails.com", type="pinpoint", tenant="tails"),
    _startup("On the Beach", type="teamtailor", tenant="onthebeach"),
    _startup("Paysend", type="teamtailor", tenant="paysend"),
    # --- UK quant / trading / finance -------------------------------------
    _employer("Man Group", **_gh("mangroup")),
    _employer("Qube Research & Technologies", **_gh("quberesearchandtechnologies")),
    _employer("Squarepoint Capital", **_gh("squarepointcapital")),
    _employer("IMC Trading", **_gh("imc")),
    _employer("GSA Capital", **_gh("gsacapital")),
    _employer("Winton", **_gh("winton")),
    _employer("Engineers Gate", **_gh("engineersgate")),
    _employer("WPP", **_gh("wpp")),
    _employer(
        "LSEG",
        type="workday",
        host="https://lseg.wd3.myworkdayjobs.com",
        tenant="lseg",
        site="Careers",
        search_text="intern",
    ),
    _employer(
        "Lloyds Banking Group",
        type="workday",
        host="https://lbg.wd3.myworkdayjobs.com",
        tenant="lbg",
        site="lbg_Careers",
        search_text="intern",
    ),
    # --- UK industry, pharma, defence (placement-year heavy) --------------
    _employer(
        "Airbus",
        type="workday",
        host="https://ag.wd3.myworkdayjobs.com",
        tenant="ag",
        site="Airbus",
        search_text="placement",
        max_results=400,
    ),
    _employer(
        "Darktrace",
        type="workday",
        host="https://darktrace.wd3.myworkdayjobs.com",
        tenant="darktrace",
        site="DarktaceExternal",
        search_text="intern",
    ),
    _employer(
        "GSK",
        type="phenom",
        base_url="https://jobs.gsk.com",
        ref_num="GHVGPAGB",
        search_url="https://jobs.gsk.com/en-gb/search-results",
        keywords="placement",
    ),
    _employer(
        "AstraZeneca",
        type="pcsx",
        list_url="https://astrazeneca.eightfold.ai/api/pcsx/search",
        domain="astrazeneca.com",
        query="placement",
    ),
    # SuccessFactors RSS carries no location data, and QinetiQ only hires in
    # the UK, so skip the location gate rather than drop everything.
    _employer(
        "QinetiQ",
        type="successfactors",
        feed_url="https://careers.qinetiq.com/services/rss/job/?locale=en_GB&keywords=(intern)",
        skip_location_filter=True,
    ),
    # --- UK-wide aggregators (need free API keys; skipped when unset) -----
    _employer(
        "Adzuna — London internships",
        type="adzuna",
        what="internship",
        where="london",
        max_days_old=30,
    ),
    _employer(
        "Adzuna — UK industrial placements",
        type="adzuna",
        what="industrial placement",
        where="",
        max_days_old=30,
    ),
    _employer(
        "Adzuna — London graduate software",
        type="adzuna",
        what="graduate software engineer",
        where="london",
        max_days_old=30,
    ),
    _employer(
        "Reed — London internships",
        type="reed",
        keywords="internship",
        location="London",
    ),
    _employer(
        "Reed — UK industrial placements",
        type="reed",
        keywords="industrial placement",
        location="",
    ),
]

# Existing US sources whose UK offices also hire interns; these get widened to
# both countries rather than duplicated.
DUAL_REGION_SOURCE_NAMES = {
    "Palantir",
    "Stripe",
    "Figma",
    "Optiver",
    "Jane Street",
    "Jump Trading",
    "Point72",
    "Epic Games",
    "Scale AI",
    "Isomorphic Labs",
    "Cohere",
    "HRT",
    "Barclays",
    "Citi",
    "Morgan Stanley",
    "Goldman Sachs",
    "JPMorgan Chase",
    "BlackRock",
    "Bloomberg",
    "Google",
    "Amazon",
    "Microsoft",
    "Apple",
    "Meta",
    "Datadog",
    "Databricks",
    "Snowflake",
    "MongoDB",
    "Cloudflare",
    "OpenAI",
    "Anthropic",
    "Hugging Face",
    "Spotify",
    "ByteDance / TikTok",
    "Deloitte",
    "PwC",
    "EY",
    "Accenture",
    "BCG",
    "McKinsey & Company",
    "Bain & Company",
    "BAE Systems",
    "Cisco",
    "SAP",
    "Oracle",
    "Arm",
}
