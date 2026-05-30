"""Watchlist + per-ticker hints. Secrets/config come from environment variables
so you set them in your host's dashboard, never in code.
"""
import os

# symbol -> {name, recipient (USASpending search string)}
WATCHLIST = {
    "LMT":  {"name": "Lockheed Martin",  "recipient": "Lockheed Martin"},
    "NVDA": {"name": "NVIDIA",           "recipient": "NVIDIA"},
    "PLTR": {"name": "Palantir",         "recipient": "Palantir"},
    "LLY":  {"name": "Eli Lilly",        "recipient": "Eli Lilly"},
    "SOFI": {"name": "SoFi Technologies","recipient": "SoFi"},
}

CACHE_TTL = int(os.getenv("CACHE_TTL", "900"))      # seconds
LOOKBACK_DAYS = int(os.getenv("LOOKBACK_DAYS", "120"))

# SEC mandates a descriptive User-Agent with real contact info. Set this env var
# on your host or SEC will block the requests.
SEC_USER_AGENT = os.getenv("SEC_USER_AGENT", "Signalroom/0.1 (SET-SEC_USER_AGENT-ENV-VAR)")
