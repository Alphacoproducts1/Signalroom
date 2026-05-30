"""Data-source adapters. Each returns the shape scoring.py expects, and each is
wrapped so a network/parse failure returns [] (-> neutral score), never an
exception that breaks the whole response.

Keyless server-side:  USASpending, SEC EDGAR, multi-feed news RSS,
                       Reddit RSS, StockTwits (best-effort).
Needs a token:         congressional trades (QuiverQuant).
Optional:              price (Finnhub) if FINNHUB_KEY is set.
"""
from __future__ import annotations
import os, re, datetime as dt
import requests
from config import (SEC_USER_AGENT, SOCIAL_USER_AGENT, LOOKBACK_DAYS,
                    NEWS_FEEDS, REDDIT_SUBS)

TIMEOUT = 12
_now = lambda: dt.datetime.now(dt.timezone.utc)
_since = lambda: (_now() - dt.timedelta(days=LOOKBACK_DAYS)).date().isoformat()


def _safe(fn):
    def wrap(*a, **k):
        try:
            return fn(*a, **k)
        except Exception as e:
            print(f"[{fn.__name__}] failed: {e}")
            return []
    return wrap


# ---- shared lexical sentiment (rough; swap for VADER/FinBERT for quality) ----
_POS = set("surge surges beat beats record upgrade upgraded growth strong soar soars win wins approval approved gains jumps rallies rally raises boost boosts outperform bullish buy long calls moon".split())
_NEG = set("miss misses downgrade downgraded lawsuit probe recall cut cuts fall falls plunge plunges drop drops weak warning warns investigation decline slump slumps loss losses bearish sell short puts dump halt".split())

def _sent(text):
    w = re.findall(r"[a-z]+", (text or "").lower())
    p = sum(x in _POS for x in w); n = sum(x in _NEG for x in w)
    return 0.0 if p + n == 0 else max(-1.0, min(1.0, (p - n) / (p + n)))


# -------------------------------------------------------------- USASpending
@_safe
def fetch_contracts(recipient):
    url = "https://api.usaspending.gov/api/v2/search/spending_by_award/"
    body = {"filters": {"recipient_search_text": [recipient],
            "award_type_codes": ["A", "B", "C", "D"],
            "time_period": [{"start_date": _since(), "end_date": _now().date().isoformat()}]},
            "fields": ["Award Amount", "Recipient Name", "Action Date", "Award ID"],
            "sort": "Award Amount", "order": "desc", "limit": 50}
    r = requests.post(url, json=body, timeout=TIMEOUT); r.raise_for_status()
    return [{"amount": a.get("Award Amount") or 0, "date": a.get("Action Date")}
            for a in r.json().get("results", [])]


# --------------------------------------------------------------- SEC EDGAR
_CIK = {}
def _cik_for(symbol):
    if not _CIK:
        r = requests.get("https://www.sec.gov/files/company_tickers.json",
                         headers={"User-Agent": SEC_USER_AGENT}, timeout=TIMEOUT)
        r.raise_for_status()
        for row in r.json().values():
            _CIK[row["ticker"].upper()] = str(row["cik_str"]).zfill(10)
    return _CIK.get(symbol.upper())

@_safe
def fetch_insider(symbol):
    cik = _cik_for(symbol)
    if not cik: return []
    h = {"User-Agent": SEC_USER_AGENT}
    sub = requests.get(f"https://data.sec.gov/submissions/CIK{cik}.json", headers=h, timeout=TIMEOUT)
    sub.raise_for_status()
    rec = sub.json().get("filings", {}).get("recent", {})
    forms, dates = rec.get("form", []), rec.get("filingDate", [])
    accns, docs = rec.get("accessionNumber", []), rec.get("primaryDocument", [])
    cutoff = (_now() - dt.timedelta(days=LOOKBACK_DAYS)).date().isoformat()
    out = []; cik_int = str(int(cik)); checked = 0
    for form, date, accn, doc in zip(forms, dates, accns, docs):
        if form != "4" or date < cutoff or checked >= 8: continue
        checked += 1
        xml_url = f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{accn.replace('-','')}/{doc}"
        try:
            x = requests.get(xml_url, headers=h, timeout=TIMEOUT).text
            for code in re.findall(r"<transactionCode>([A-Z])</transactionCode>", x):
                out.append({"code": code, "date": date})
        except Exception:
            continue
    return out


# ----------------------------------------------------- Congress (token)
@_safe
def fetch_congress(symbol):
    token = os.getenv("QUIVER_TOKEN")
    if not token:
        print("[fetch_congress] no QUIVER_TOKEN -> neutral"); return []
    r = requests.get(f"https://api.quiverquant.com/beta/historical/congresstrading/{symbol}",
                     headers={"Authorization": f"Bearer {token}"}, timeout=TIMEOUT)
    r.raise_for_status()
    cutoff = (_now() - dt.timedelta(days=LOOKBACK_DAYS)).date().isoformat()
    out = []
    for t in r.json():
        filed = (t.get("ReportDate") or t.get("Filed") or "")[:10]
        if filed and filed < cutoff: continue
        txn = "buy" if "purchase" in str(t.get("Transaction", "")).lower() else "sell"
        out.append({"transaction": txn, "amount": 0, "filed_date": filed})
    return out


# ------------------------------------------ News (multi-feed RSS, keyless)
@_safe
def fetch_news(symbol, name):
    import feedparser
    seen = set(); out = []
    for tmpl in NEWS_FEEDS:
        url = tmpl.format(q=requests.utils.quote(f"{name} {symbol} stock"), sym=symbol)
        src = re.sub(r"^https?://(www\.)?([^/]+).*", r"\2", url).split(".")[0]
        try:
            feed = feedparser.parse(url)
            for e in feed.entries[:12]:
                title = (e.get("title") or "").strip()
                key = title.lower()[:80]
                if not title or key in seen: continue
                seen.add(key)
                out.append({"title": title, "source": src, "sentiment": _sent(title)})
        except Exception as ex:
            print(f"[fetch_news:{src}] {ex}")
    return out


# ------------------------------------- Social (Reddit RSS + StockTwits)
@_safe
def fetch_social(symbol, name):
    import feedparser
    out = []
    # Reddit: search finance subreddits for the ticker (keyless RSS)
    try:
        rurl = (f"https://www.reddit.com/r/{REDDIT_SUBS}/search.rss"
                f"?q={requests.utils.quote(symbol)}&restrict_sr=on&sort=new&limit=25")
        rt = requests.get(rurl, headers={"User-Agent": SOCIAL_USER_AGENT}, timeout=TIMEOUT)
        if rt.ok:
            for e in feedparser.parse(rt.text).entries[:20]:
                title = (e.get("title") or "")
                out.append({"source": "reddit", "sentiment": _sent(title)})
    except Exception as ex:
        print(f"[fetch_social:reddit] {ex}")
    # StockTwits: public symbol stream; users often tag Bullish/Bearish
    try:
        st = requests.get(f"https://api.stocktwits.com/api/2/streams/symbol/{symbol}.json",
                          headers={"User-Agent": SOCIAL_USER_AGENT}, timeout=TIMEOUT)
        if st.ok:
            for m in st.json().get("messages", [])[:30]:
                basic = (((m.get("entities") or {}).get("sentiment") or {}).get("basic"))
                s = 1.0 if basic == "Bullish" else -1.0 if basic == "Bearish" else _sent(m.get("body", ""))
                out.append({"source": "stocktwits", "sentiment": s})
    except Exception as ex:
        print(f"[fetch_social:stocktwits] {ex}")
    return out


# ------------------------------------------------ Optional price (Finnhub)
@_safe
def fetch_quote(symbol):
    key = os.getenv("FINNHUB_KEY")
    if not key: return {}
    r = requests.get("https://finnhub.io/api/v1/quote",
                     params={"symbol": symbol, "token": key}, timeout=TIMEOUT)
    r.raise_for_status(); d = r.json()
    return {"price": d.get("c"), "day": round(d.get("dp") or 0, 2)}
