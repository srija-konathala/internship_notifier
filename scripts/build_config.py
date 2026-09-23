#!/usr/bin/env python3
"""Write config.json for the full target company list."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.json"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from uk_sources import (  # noqa: E402
    DUAL_REGION_SOURCE_NAMES,
    KEYWORD_PROFILES,
    ROLE_PROFILES,
    UK_SOURCES,
)

SOURCES: list[dict] = [
    {
        "name": "Microsoft",
        "type": "pcsx",
        "list_url": "https://apply.careers.microsoft.com/api/pcsx/search",
        "domain": "microsoft.com",
        "query": "intern",
    },
    {
        "name": "Google",
        "type": "google_careers",
        "search_url": "https://www.google.com/about/careers/applications/jobs/results/?q=intern",
        "data_key": "ds:1",
    },
    {
        "name": "Netflix",
        "type": "pcsx",
        "list_url": "https://explore.jobs.netflix.net/api/apply/v2/jobs",
        "domain": "netflix.com",
        "query": "intern",
        "page_size_param": "num",
        "page_size": 10,
    },
    {
        "name": "Amazon",
        "type": "amazon",
        "query": "intern",
    },
    {
        "name": "Oracle",
        "type": "oracle_careers",
        "host": "eeho.fa.us2.oraclecloud.com",
        "site_number": "CX_45001",
        "search_keyword": "intern",
    },
    {
        "name": "NVIDIA",
        "type": "workday",
        "host": "https://nvidia.wd5.myworkdayjobs.com",
        "tenant": "nvidia",
        "site": "NVIDIAExternalCareerSite",
        "search_text": "intern",
    },
    {
        "name": "Salesforce",
        "type": "workday",
        "host": "https://salesforce.wd12.myworkdayjobs.com",
        "tenant": "salesforce",
        "site": "External_Career_Site",
        "search_text": "intern",
    },
    {
        "name": "Adobe",
        "type": "workday",
        "host": "https://adobe.wd5.myworkdayjobs.com",
        "tenant": "adobe",
        "site": "external_experienced",
        "search_text": "intern",
    },
    {
        "name": "Workday",
        "type": "workday",
        "host": "https://workday.wd5.myworkdayjobs.com",
        "tenant": "workday",
        "site": "Workday",
        "search_text": "intern",
    },
    {
        "name": "BlackRock",
        "type": "workday",
        "host": "https://blackrock.wd1.myworkdayjobs.com",
        "tenant": "blackrock",
        "site": "BlackRock_Professional",
        "search_text": "intern",
    },
    {
        "name": "Leidos",
        "type": "workday",
        "host": "https://leidos.wd5.myworkdayjobs.com",
        "tenant": "leidos",
        "site": "External",
        "search_text": "intern",
    },
    {
        "name": "Boston Dynamics",
        "type": "workday",
        "host": "https://bostondynamics.wd1.myworkdayjobs.com",
        "tenant": "bostondynamics",
        "site": "Boston_Dynamics",
        "search_text": "intern",
    },
    {
        "name": "Booz Allen Hamilton",
        "type": "workday",
        "host": "https://bah.wd1.myworkdayjobs.com",
        "tenant": "bah",
        "site": "BAH_Jobs",
        "search_text": "intern",
    },
    {
        "name": "Morgan Stanley",
        "type": "pcsx",
        "list_url": "https://morganstanley.eightfold.ai/api/pcsx/search",
        "domain": "morganstanley.com",
        "query": "intern",
    },
    {
        "name": "Capital One",
        "type": "workday",
        "host": "https://capitalone.wd12.myworkdayjobs.com",
        "tenant": "capitalone",
        "site": "Capital_One",
        "search_text": "intern",
    },
    {"name": "LinkedIn", "type": "greenhouse", "board_token": "linkedin"},
    {"name": "Uber", "type": "greenhouse", "board_token": "uberfreight"},
    {"name": "Lyft", "type": "greenhouse", "board_token": "lyft"},
    {"name": "Twitter / X", "type": "smartrecruiters", "company_id": "x"},
    {"name": "Pinterest", "type": "greenhouse", "board_token": "pinterest"},
    {"name": "Dropbox", "type": "greenhouse", "board_token": "dropbox"},
    {"name": "ServiceNow", "type": "smartrecruiters", "company_id": "servicenow"},
    {"name": "SpaceX", "type": "greenhouse", "board_token": "spacex"},
    {"name": "Waymo", "type": "greenhouse", "board_token": "waymo"},
    {"name": "Zoox", "type": "lever", "company_slug": "zoox"},
    {"name": "Nuro", "type": "greenhouse", "board_token": "nuro"},
    {"name": "Stripe", "type": "greenhouse", "board_token": "stripe"},
    {"name": "Robinhood", "type": "greenhouse", "board_token": "robinhood"},
    {"name": "Affirm", "type": "greenhouse", "board_token": "affirm"},
    {"name": "Chime", "type": "greenhouse", "board_token": "chime"},
    {"name": "Plaid", "type": "ashby", "board_slug": "plaid"},
    {"name": "Brex", "type": "greenhouse", "board_token": "brex"},
    {"name": "Ramp", "type": "ashby", "board_slug": "ramp"},
    {"name": "Jane Street", "type": "greenhouse", "board_token": "janestreet"},
    {"name": "Optiver", "type": "greenhouse", "board_token": "optiverus"},
    {"name": "Virtu Financial", "type": "greenhouse", "board_token": "virtu"},
    {"name": "Anthropic", "type": "greenhouse", "board_token": "anthropic"},
    {"name": "OpenAI", "type": "ashby", "board_slug": "openai"},
    {"name": "Scale AI", "type": "greenhouse", "board_token": "scaleai"},
    {"name": "Cohere", "type": "ashby", "board_slug": "cohere"},
    {"name": "Mistral AI", "type": "lever", "company_slug": "mistral"},
    {"name": "Perplexity AI", "type": "ashby", "board_slug": "perplexity"},
    {"name": "xAI", "type": "greenhouse", "board_token": "xai"},
    {"name": "Codeium / Windsurf", "type": "ashby", "board_slug": "cognition"},
    {"name": "Anduril", "type": "greenhouse", "board_token": "andurilindustries"},
    {"name": "Palantir", "type": "lever", "company_slug": "palantir"},
    {"name": "Notion", "type": "ashby", "board_slug": "notion"},
    {"name": "Linear", "type": "ashby", "board_slug": "linear"},
    {"name": "Vercel", "type": "greenhouse", "board_token": "vercel"},
    {"name": "Airtable", "type": "greenhouse", "board_token": "airtable"},
    {"name": "Figma", "type": "greenhouse", "board_token": "figma"},
    {"name": "Amplitude", "type": "greenhouse", "board_token": "amplitude"},
    {"name": "Datadog", "type": "greenhouse", "board_token": "datadog"},
    {"name": "Snowflake", "type": "ashby", "board_slug": "snowflake"},
    {"name": "Databricks", "type": "greenhouse", "board_token": "databricks"},
    {"name": "Hugging Face", "type": "workable", "shortcode": "huggingface"},
    # --- FAANG satellites / Alphabet ---
    {"name": "Wing", "type": "greenhouse", "board_token": "wing"},
    {"name": "Intrinsic", "type": "greenhouse", "board_token": "intrinsicrobotics"},
    {"name": "Isomorphic Labs", "type": "greenhouse", "board_token": "isomorphiclabs"},
    {"name": "Neuralink", "type": "greenhouse", "board_token": "neuralink"},
    # --- Big Tech ---
    {"name": "Airbnb", "type": "greenhouse", "board_token": "airbnb"},
    {"name": "DoorDash", "type": "greenhouse", "board_token": "doordashusa"},
    {"name": "Instacart", "type": "greenhouse", "board_token": "instacart"},
    {"name": "Snap", "type": "workday", "host": "https://snapchat.wd1.myworkdayjobs.com", "tenant": "snapchat", "site": "Snap", "search_text": "intern"},
    {"name": "Reddit", "type": "greenhouse", "board_token": "reddit"},
    {"name": "Spotify", "type": "lever", "company_slug": "spotify"},
    {"name": "ByteDance / TikTok", "type": "smartrecruiters", "company_id": "bytedance"},
    {"name": "Roku", "type": "greenhouse", "board_token": "roku"},
    {"name": "Asana", "type": "greenhouse", "board_token": "asana"},
    {"name": "Box", "type": "greenhouse", "board_token": "boxinc"},
    {"name": "Twilio", "type": "greenhouse", "board_token": "twilio"},
    {"name": "Zoom", "type": "workday", "host": "https://zoom.wd5.myworkdayjobs.com", "tenant": "zoom", "site": "Zoom", "search_text": "intern"},
    {"name": "PayPal", "type": "workday", "host": "https://paypal.wd1.myworkdayjobs.com", "tenant": "paypal", "site": "jobs", "search_text": "intern"},
    {"name": "eBay", "type": "workday", "host": "https://ebay.wd5.myworkdayjobs.com", "tenant": "ebay", "site": "apply", "search_text": "intern"},
    {"name": "Intel", "type": "workday", "host": "https://intel.wd1.myworkdayjobs.com", "tenant": "intel", "site": "External", "search_text": "intern"},
    {"name": "Zendesk", "type": "workday", "host": "https://zendesk.wd1.myworkdayjobs.com", "tenant": "zendesk", "site": "zendesk", "search_text": "intern"},
    # --- SF Unicorns ---
    {"name": "Coinbase", "type": "greenhouse", "board_token": "coinbase"},
    {"name": "Cloudflare", "type": "greenhouse", "board_token": "cloudflare"},
    {"name": "Gusto", "type": "greenhouse", "board_token": "gusto"},
    {"name": "Carta", "type": "greenhouse", "board_token": "carta"},
    {"name": "Supabase", "type": "ashby", "board_slug": "supabase"},
    {"name": "Replit", "type": "ashby", "board_slug": "replit"},
    {"name": "Verkada", "type": "greenhouse", "board_token": "verkada"},
    {"name": "Samsara", "type": "greenhouse", "board_token": "samsara"},
    {"name": "Intercom", "type": "greenhouse", "board_token": "intercom"},
    {"name": "Lattice", "type": "greenhouse", "board_token": "lattice"},
    {"name": "Mixpanel", "type": "greenhouse", "board_token": "mixpanel"},
    # --- AI Labs ---
    {"name": "Modal", "type": "ashby", "board_slug": "modal"},
    {"name": "Anyscale", "type": "ashby", "board_slug": "anyscale"},
    {"name": "Cursor / Anysphere", "type": "ashby", "board_slug": "cursor"},
    {"name": "Glean", "type": "greenhouse", "board_token": "gleanwork"},
    {"name": "Harvey AI", "type": "ashby", "board_slug": "harvey"},
    # --- Cybersecurity ---
    {"name": "Okta", "type": "greenhouse", "board_token": "okta"},
    {"name": "Zscaler", "type": "greenhouse", "board_token": "zscaler"},
    {"name": "Rubrik", "type": "greenhouse", "board_token": "rubrik"},
    # --- Finance & Quant ---
    {"name": "Jump Trading", "type": "greenhouse", "board_token": "jumptrading"},
    {"name": "Akuna Capital", "type": "greenhouse", "board_token": "akunacapital"},
    {"name": "Point72", "type": "greenhouse", "board_token": "point72"},
    {"name": "Barclays", "type": "workday", "host": "https://barclays.wd3.myworkdayjobs.com", "tenant": "barclays", "site": "External_Career_Site_Barclays", "search_text": "intern"},
    {"name": "Visa", "type": "workday", "host": "https://visa.wd5.myworkdayjobs.com", "tenant": "visa", "site": "Visa", "search_text": "intern"},
    # --- Consulting ---
    {"name": "Oliver Wyman", "type": "lever", "company_slug": "oliverwyman"},
    # --- Defense & Aerospace ---
    {"name": "Raytheon (RTX)", "type": "smartrecruiters", "company_id": "raytheontechnologies"},
    {"name": "Northrop Grumman", "type": "workday", "host": "https://ngc.wd1.myworkdayjobs.com", "tenant": "ngc", "site": "Northrop_Grumman_External_Site", "search_text": "intern"},
    {"name": "Boeing", "type": "workday", "host": "https://boeing.wd1.myworkdayjobs.com", "tenant": "boeing", "site": "EXTERNAL_CAREERS", "search_text": "intern"},
    # --- Gaming ---
    {"name": "Riot Games", "type": "greenhouse", "board_token": "riotgames"},
    {"name": "Epic Games", "type": "greenhouse", "board_token": "epicgames"},
    {"name": "Roblox", "type": "greenhouse", "board_token": "roblox"},
    {
        "name": "Unity Technologies",
        "type": "workday",
        "host": "https://unitytech.wd1.myworkdayjobs.com",
        "tenant": "unitytech",
        "site": "Unity",
        "search_text": "intern",
    },
    {"name": "Take-Two Interactive", "type": "greenhouse", "board_token": "2k"},
    {"name": "Disney (Tech)", "type": "greenhouse", "board_token": "disney"},
    # --- Consumer / NYC startups ---
    {"name": "Squarespace", "type": "greenhouse", "board_token": "squarespace"},
    {"name": "Duolingo", "type": "greenhouse", "board_token": "duolingo"},
    {"name": "Braze", "type": "greenhouse", "board_token": "braze"},
    {"name": "MongoDB", "type": "greenhouse", "board_token": "mongodb"},
    # --- Enterprise / Cloud ---
    {"name": "Confluent", "type": "ashby", "board_slug": "confluent"},
    {"name": "Elastic", "type": "greenhouse", "board_token": "elastic"},
    {"name": "PagerDuty", "type": "greenhouse", "board_token": "pagerduty"},
    # --- Atlanta / Southeast ---
    {"name": "SS&C Technologies", "type": "workday", "host": "https://ssctech.wd1.myworkdayjobs.com", "tenant": "ssctech", "site": "SSCTechnologies", "search_text": "intern"},
    # --- Discovered via careers-page / Workday CXS probes ---
    {"name": "CrowdStrike", "type": "workday", "host": "https://crowdstrike.wd5.myworkdayjobs.com", "tenant": "crowdstrike", "site": "crowdstrikecareers", "search_text": "intern"},
    {"name": "Palo Alto Networks", "type": "workday", "host": "https://paloaltonetworks.wd5.myworkdayjobs.com", "tenant": "paloaltonetworks", "site": "panwexternalcareers", "search_text": "intern"},
    {"name": "Accenture", "type": "workday", "host": "https://accenture.wd103.myworkdayjobs.com", "tenant": "accenture", "site": "AccentureCareers", "search_text": "intern"},
    {"name": "Nike (Tech)", "type": "workday", "host": "https://nike.wd1.myworkdayjobs.com", "tenant": "nike", "site": "nke", "search_text": "intern"},
    {"name": "Mastercard", "type": "workday", "host": "https://mastercard.wd1.myworkdayjobs.com", "tenant": "mastercard", "site": "CorporateCareers", "search_text": "intern"},
    {"name": "AT&T (Tech)", "type": "workday", "host": "https://att.wd1.myworkdayjobs.com", "tenant": "att", "site": "ATTGeneral", "search_text": "intern"},
    {"name": "T-Mobile (Tech)", "type": "workday", "host": "https://tmobile.wd1.myworkdayjobs.com", "tenant": "tmobile", "site": "External", "search_text": "intern"},
    {"name": "Comcast (Tech)", "type": "workday", "host": "https://comcast.wd5.myworkdayjobs.com", "tenant": "comcast", "site": "Comcast_Careers", "search_text": "intern"},
    {"name": "The Home Depot", "type": "workday", "host": "https://homedepot.wd5.myworkdayjobs.com", "tenant": "homedepot", "site": "CareerDepot", "search_text": "intern"},
    {"name": "NCR Voyix", "type": "workday", "host": "https://ncr.wd1.myworkdayjobs.com", "tenant": "ncr", "site": "ext_apac", "search_text": "intern"},
    {"name": "Global Payments", "type": "workday", "host": "https://tsys.wd1.myworkdayjobs.com", "tenant": "tsys", "site": "TSYS", "search_text": "intern"},
    {"name": "Manhattan Associates", "type": "workday", "host": "https://manh.wd5.myworkdayjobs.com", "tenant": "manh", "site": "External", "search_text": "intern"},
    {"name": "Cardlytics", "type": "workday", "host": "https://cardlytics.wd5.myworkdayjobs.com", "tenant": "cardlytics", "site": "CardlyticsExternalCareerSite", "search_text": "intern"},
    {"name": "Elevance Health", "type": "workday", "host": "https://elevancehealth.wd1.myworkdayjobs.com", "tenant": "elevancehealth", "site": "ANT", "search_text": "intern"},
    {"name": "Verily", "type": "workday", "host": "https://verily.wd1.myworkdayjobs.com", "tenant": "verily", "site": "Verily_Careers", "search_text": "intern"},
    {"name": "HRT", "type": "greenhouse", "board_token": "hrttalentcommunity"},
    # --- Detector-verified (round 2) ---
    {
        "name": "Qualcomm",
        "type": "pcsx",
        "list_url": "https://careers.qualcomm.com/api/pcsx/search",
        "domain": "qualcomm.com",
        "query": "intern",
    },
    {
        "name": "Citi",
        "type": "pcsx",
        "list_url": "https://citi.eightfold.ai/api/pcsx/search",
        "domain": "citi.com",
        "query": "intern",
    },
    {"name": "Valve", "type": "valve"},
    {
        "name": "NASA",
        "type": "usajobs",
        "org_keyword": "NASA",
        "search_keyword": "intern",
    },
    # --- Phenom (POST /widgets) ---
    {
        "name": "BCG",
        "type": "phenom",
        "base_url": "https://careers.bcg.com",
        "ref_num": "BCG1US",
        "search_url": "https://careers.bcg.com/global/en/search-results",
        "keywords": "intern",
    },
    {
        "name": "Yelp",
        "type": "phenom",
        "base_url": "https://www.yelp.careers",
        "ref_num": "YELPUS",
        "search_url": "https://www.yelp.careers/us/en/search-results",
        "keywords": "intern",
    },
    {
        "name": "Cisco",
        "type": "phenom",
        "base_url": "https://careers.cisco.com",
        "ref_num": "CISCISGLOBAL",
        "search_url": "https://careers.cisco.com/global/en/search-results",
        "keywords": "intern",
    },
    {
        "name": "Splunk",
        "type": "phenom",
        "base_url": "https://careers.cisco.com",
        "ref_num": "CISCISGLOBAL",
        "search_url": "https://careers.cisco.com/global/en/splunk",
        "keywords": "splunk intern",
    },
    {
        "name": "BAE Systems",
        "type": "phenom",
        "base_url": "https://jobs.baesystems.com",
        "ref_num": "BAE1US",
        "search_url": "https://jobs.baesystems.com/global/en/search-results",
        "keywords": "intern",
    },
    {
        "name": "Warner Bros. Discovery",
        "type": "phenom",
        "base_url": "https://careers.wbd.com",
        "ref_num": "WAMEGLOBAL",
        "search_url": "https://careers.wbd.com/global/en/search-results",
        "keywords": "intern",
    },
    {
        "name": "Fiserv",
        "type": "phenom",
        "base_url": "https://careers.fiserv.com",
        "ref_num": "FFFYJUS",
        "search_url": "https://careers.fiserv.com/us/en/search-results",
        "keywords": "intern",
    },
    {
        "name": "UPS (Tech)",
        "type": "phenom",
        "base_url": "https://www.jobs-ups.com",
        "ref_num": "UPBUPSGLOBAL",
        "search_url": "https://www.jobs-ups.com/us/en/search-results",
        "keywords": "intern",
    },
    # --- Avature RSS ---
    {
        "name": "Deloitte",
        "type": "avature",
        "feed_url": "https://apply.deloitte.com/en_US/careers/SearchJobs/feed/",
        "page_size": 100,
    },
    {
        "name": "Electronic Arts (EA)",
        "type": "avature",
        "feed_url": "https://jobs.ea.com/en_US/careers/SearchJobs/feed/",
        "page_size": 100,
    },
    # --- Bank of America (custom JSON servlet) ---
    {
        "name": "Bank of America",
        "type": "bofa",
        "search": "getAllJobs",
    },
    # --- Playwright (bot-managed) ---
    {
        "name": "Apple",
        "type": "playwright",
        "profile": "apple",
        "page_url": "https://jobs.apple.com/en-us/search?search=intern",
    },
    {
        "name": "Meta",
        "type": "playwright",
        "profile": "meta",
        "page_url": "https://www.metacareers.com/jobs?q=intern",
    },
    {
        "name": "Tesla",
        "type": "playwright",
        "profile": "tesla",
        "page_url": "https://www.tesla.com/careers/search?query=intern",
    },
    # --- SuccessFactors RSS ---
    {
        "name": "EY",
        "type": "successfactors",
        "feed_url": "https://careers.ey.com/services/rss/job/?locale=en_US&keywords=(intern)",
    },
    {
        "name": "SAP",
        "type": "successfactors",
        "feed_url": "https://jobs.sap.com/services/rss/job/?locale=en_US&keywords=(intern)",
    },
    # --- Activision (Phenom) ---
    {
        "name": "Activision Blizzard",
        "type": "phenom",
        "base_url": "https://careers.activisionblizzard.com",
        "ref_num": "ACCOUS",
        "search_url": "https://careers.activisionblizzard.com/global/en/search-results",
        "keywords": "intern",
    },
    # --- iCIMS (Playwright vanity careers pages) ---
    {
        "name": "AMD",
        "type": "playwright",
        "profile": "icims",
        "page_url": "https://careers.amd.com/careers-home/jobs",
    },
    {
        "name": "Intercontinental Exchange (ICE)",
        "type": "playwright",
        "profile": "icims",
        "page_url": "https://careers.ice.com/jobs",
    },
    {
        "name": "Chick-fil-A (Digital)",
        "type": "playwright",
        "profile": "icims",
        "page_url": "https://careers.chick-fil-a.com/corporate/jobs",
    },
    # AmEx omitted: Eightfold PCSX returns 403; Playwright cannot capture job JSON.
    # --- Workday (re-discovered) ---
    {
        "name": "PwC",
        "type": "workday",
        "host": "https://pwc.wd3.myworkdayjobs.com",
        "tenant": "pwc",
        "site": "Global_Experienced_Careers",
        "search_text": "intern",
    },
    {
        "name": "Equifax",
        "type": "workday",
        "host": "https://equifax.wd5.myworkdayjobs.com",
        "tenant": "equifax",
        "site": "External",
        "search_text": "intern",
    },
    {
        "name": "Dell Technologies",
        "type": "oracle_careers",
        "host": "iawmqy.fa.ocs.oraclecloud.com",
        "site_number": "careers",
        "search_keyword": "intern",
        "job_url": "https://iawmqy.fa.ocs.oraclecloud.com/hcmUI/CandidateExperience/en/sites/careers/job/{id}",
    },
    # --- User-requested batch ---
    {"name": "HubSpot", "type": "greenhouse", "board_token": "hubspotjobs"},
    {
        "name": "Goldman Sachs",
        "type": "oracle_careers",
        "host": "hdpc.fa.us2.oraclecloud.com",
        "site_number": "CX_2001",
        "search_keyword": "intern",
        "job_url": "https://hdpc.fa.us2.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_2001/job/{id}",
    },
    {
        "name": "JPMorgan Chase",
        "type": "oracle_careers",
        "host": "jpmc.fa.oraclecloud.com",
        "site_number": "CX_1001",
        "search_keyword": "intern",
        "job_url": "https://jpmc.fa.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1001/job/{id}",
    },
    {
        "name": "Wells Fargo",
        "type": "playwright",
        "profile": "wells",
        "page_url": "https://www.wellsfargojobs.com/en/jobs/?q=intern",
    },
    {
        "name": "Lockheed Martin",
        "type": "playwright",
        "profile": "lockheed",
        "page_url": "https://www.lockheedmartinjobs.com/search-jobs?k=intern",
    },
    {
        "name": "Delta Air Lines",
        "type": "playwright",
        "profile": "avature",
        "page_url": "https://delta.avature.net/en_US/careers/SearchJobs?keywords=intern",
    },
    {
        "name": "Bain & Company",
        "type": "playwright",
        "profile": "bain",
        "page_url": "https://www.bain.com/careers/find-a-role/?q=intern",
    },
    {
        "name": "McKinsey & Company",
        "type": "playwright",
        "profile": "mckinsey",
        "page_url": "https://www.mckinsey.com/careers/search-jobs?q=intern",
    },
    {
        "name": "Shopify",
        "type": "playwright",
        "profile": "shopify",
        "page_url": "https://www.shopify.com/careers/search?query=intern",
    },
    {
        "name": "Rippling",
        "type": "playwright",
        "profile": "rippling",
        "page_url": "https://www.rippling.com/careers/open-roles",
    },
]

def widen_us_sources(sources: list[dict]) -> list[dict]:
    """US-based employers with UK offices should match in both countries."""
    for src in sources:
        if src.get("name") in DUAL_REGION_SOURCE_NAMES:
            src["countries"] = ["US", "GB"]
    return sources


ALL_SOURCES = widen_us_sources(SOURCES) + UK_SOURCES

CONFIG = {
    "poll_interval_seconds": 180,
    # Sources are fetched concurrently; playwright ones stay serial.
    "fetch_workers": 10,
    # A newly added source records its existing postings silently instead of
    # alerting on its whole backlog.
    "prime_new_sources": True,
    "title_keywords": ["intern", "internship", "student"],
    # Optional AND-filter: if non-empty, a posting must ALSO match one of
    # these (on top of title_keywords) to be notified. Leave empty to keep
    # every internship/student posting. See README "Customizing the keyword
    # filter" for role-specific examples (e.g. engineering-only).
    # Set to software/SWE-only for this personal deployment.
    "title_require_any": [
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
    ],
    # Per-source "keyword_profile" / "role_profile" select these; sources
    # without one fall back to title_keywords + title_require_any above.
    "keyword_profiles": KEYWORD_PROFILES,
    "role_profiles": ROLE_PROFILES,
    "location_filter": {"countries": ["US", "GB"]},
    "sources": ALL_SOURCES,
}


def main() -> None:
    CONFIG_PATH.write_text(json.dumps(CONFIG, indent=2) + "\n", encoding="utf-8")
    print(
        f"Wrote {len(ALL_SOURCES)} sources to {CONFIG_PATH} "
        f"({len(SOURCES)} existing + {len(UK_SOURCES)} UK)"
    )


if __name__ == "__main__":
    main()
