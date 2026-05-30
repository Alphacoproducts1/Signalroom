"""Data-source adapters. Each returns the normalized shape that scoring.py expects.
Each is wrapped so a network/parse failure returns an empty list (-> neutral score),
never an exception that breaks the whole response.

Keyless out of the box:  USASpending, SEC EDGAR, Google News RSS.
Needs a token:           congressional trades (QuiverQuant).
Optional:                quote/price (Finnhub) if FINNHUB_KEY is set.
"""
from __future__ import annotations
import os, re, datetime as dt
import requests
from config import SEC_USER_AGENT, LOOKBACK_DAYS

TIMEOUT = 12
_now = lambda: dt.datetime.now(dt.timezone.utc)
_since = lambda: (_now() - dt.timedelta(days=LOOKBACK_DAYS)).date().isoformat()


def _safe(fn):
    """Decorator: log and swallow errors, returning []."""
    def wrap(*a, **k):
        try:
            return fn(*a, **k)
        except Exception as e:  # noqa
            print(f"[{fn.__name__}] failed: {e}")
            return []
    return wrap


# ---------------------------------------------------------------- USASpending
@_safe
def fetch_contracts(recipient: str) -> list[dict]:
    url = "https://api.usaspending.gov/api/v2/search/spending_by_award/"
    body = {
        "filters": {
            "recipient_search_text": [recipient],
            "award_type_codes": ["A", "B", "C", "D"],  # contracts
            "time_period": [{"start_date": _since(), "end_date": _now().date().isoformat()}],
        },
        "fields": ["Award Amount", "Recipient Name", "Action Date", "Award ID"],
        "sort": "Award Amount", "order": "desc", "limit": 50,
    }
    r = requests.post(url, json=body, timeout=TIMEOUT)
    r.raise_for_status()
    out = []
    for a in r.json().get("results", []):
        out.append({"amount": a.get("Award Amount") or 0, "date": a.get("Action Date")})
    return out


# ----------------------------------------------------------------- SEC EDGAR
_CIK_CACHE: dict[str, str] = {}

def _cik_for(symbol: str) -> str | None:
    if not _CIK_CACHE:
        r = requests.get("https://www.sec.gov/files/company_tickers.json",
                         headers={"User-Agent": SEC_USER_AGENT}, timeout=TIMEOUT)
        r.raise_for_status()
        for row in r.json().values():
            _CIK_CACHE[row["ticker"].upper()] = str(row["cik_str"]).zfill(10)
    return _CIK_CACHE.get(symbol.upper())


@_safe
def fetch_insider(symbol: str) -> list[dict]:
    cik = _cik_for(symbol)
    if not cik:
        return []
    h = {"User-Agent": SEC_USER_AGENT}
    sub = requests.get(f"https://data.sec.gov/submissions/CIK{cik}.json", headers=h, timeout=TIMEOUT)
    sub.raise_for_status()
    recent = sub.json().get("filings", {}).get("recent", {})
    forms = recent.get("form", []); dates = recent.get("filingDate", [])
    accns = recent.get("accessionNumber", []); docs = recent.get("primaryDocument", [])
    cutoff = (_now() - dt.timedelta(days=LOOKBACK_DAYS)).date().isoformat()
    out = []
    cik_int = str(int(cik))
    checked = 0
    for form, date, accn, doc in zip(forms, dates, accns, docs):
        if form != "4" or date < cutoff or checked >= 8:
            continue
        checked += 1
        accn_nodash = accn.replace("-", "")
        xml_url = f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{accn_nodash}/{doc}"
        try:
            x = requests.get(xml_url, headers=h, timeout=TIMEOUT).text
            for code in re.findall(r"<transactionCode>([A-Z])</transactionCode>", x):
                out.append({"code": code, "date": date})
        except Exception:
            continue
    return out


# --------------------------------------------------------- Congress (token)
@_safe
def fetch_congress(symbol: str) -> list[dict]:
    token = os.getenv("QUIVER_TOKEN")
    if not token:
        print("[fetch_congress] no QUIVER_TOKEN set -> neutral")
        return []
    url = f"https://api.quiverquant.com/beta/historical/congresstrading/{symbol}"
    r = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=TIMEOUT)
    r.raise_for_status()
    cutoff = (_now() - dt.timedelta(days=LOOKBACK_DAYS)).date().isoformat()
    out = []
    for t in r.json():
        filed = (t.get("ReportDate") or t.get("Filed") or "")[:10]
        if filed and filed < cutoff:
            continue
        txn = "buy" if "purchase" in str(t.get("Transaction", "")).lower() else "sell"
        out.append({"transaction": txn, "amount": 0, "filed_date": filed})
    return out


# ---------------------------------------------------- News (RSS, keyless)
_POS = {"surge","beat","beats","record","upgrade","growth","strong","win","wins","approval","gains","jumps","soars","raises","outperform"}
_NEG = {"miss","misses","downgrade","lawsuit","probe","recall","cut","cuts","falls","plunges","drops","weak","warning","investigation","decline","slump"}

def _lexical_sentiment(text: str) -> float:
    words = re.findall(r"[a-z]+", text.lower())
    p = sum(w in _POS for w in words); n = sum(w in _NEG for w in words)
    if p + n == 0:
        return 0.0
    return max(-1.0, min(1.0, (p - n) / (p + n)))


@_safe
def fetch_news(symbol: str, name: str) -> list[dict]:
    import feedparser
    q = requests.utils.quote(f"{name} {symbol} stock")
    feed = feedparser.parse(f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en")
    out = []
    for e in feed.entries[:15]:
        out.append({"title": e.get("title", ""), "sentiment": _lexical_sentiment(e.get("title", ""))})
    return out


# ------------------------------------------------ Optional price (Finnhub)
@_safe
def fetch_quote(symbol: str) -> dict:
    key = os.getenv("FINNHUB_KEY")
    if not key:
        return {}
    r = requests.get("https://finnhub.io/api/v1/quote",
                     params={"symbol": symbol, "token": key}, timeout=TIMEOUT)
    r.raise_for_status()
    d = r.json()
    return {"price": d.get("c"), "day": round(d.get("dp") or 0, 2)}
