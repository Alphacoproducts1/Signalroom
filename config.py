"""Watchlist + source config. Secrets come from environment variables.

What expanded in this version:
- NEWS now pulls from several RSS feeds, not just one.
- SOCIAL signal added (Reddit RSS + StockTwits best-effort).
- Composite weights rebalanced to include social.
"""
import os

WATCHLIST = {
    "LMT":  {"name": "Lockheed Martin",  "recipient": "Lockheed Martin"},
    "NVDA": {"name": "NVIDIA",           "recipient": "NVIDIA"},
    "PLTR": {"name": "Palantir",         "recipient": "Palantir"},
    "LLY":  {"name": "Eli Lilly",        "recipient": "Eli Lilly"},
    "SOFI": {"name": "SoFi Technologies","recipient": "SoFi"},
}

# News RSS feeds. {q} = "Name SYM stock", {sym} = ticker. All keyless.
# Each is fetched server-side, so CORS is a non-issue. Add/remove freely.
NEWS_FEEDS = [
    "https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en",
    "https://feeds.finance.yahoo.com/rss/2.0/headline?s={sym}&region=US&lang=en-US",
    "https://www.nasdaq.com/feed/rssoutbound?symbol={sym}",
]

# Reddit finance subreddits to search for ticker chatter (keyless RSS).
REDDIT_SUBS = "wallstreetbets+stocks+investing+options+StockMarket"

CACHE_TTL = int(os.getenv("CACHE_TTL", "900"))
LOOKBACK_DAYS = int(os.getenv("LOOKBACK_DAYS", "120"))
SEC_USER_AGENT = os.getenv("SEC_USER_AGENT", "Signalroom/1.0 (SET-SEC_USER_AGENT-ENV-VAR)")
# Reddit/StockTwits want a descriptive UA; falls back to the SEC one.
SOCIAL_USER_AGENT = os.getenv("SOCIAL_USER_AGENT") or SEC_USER_AGENT
