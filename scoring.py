"""Pure signal-scoring logic. No external dependencies, fully unit-testable.

Each raw source maps to a score in [-100, 100]; the composite is a weighted
blend. NOTE: signal-strength heuristic, NOT a probability of profit. Backtest.
"""
from __future__ import annotations
from datetime import datetime, timezone

# Rebalanced to include the new 'social' signal. Must sum to ~1.0 and match
# the keys the dashboard renders.
WEIGHTS = {"congress": 0.25, "contracts": 0.20, "news": 0.20, "insider": 0.15, "social": 0.20}


def clamp(x, lo=-100.0, hi=100.0):
    return max(lo, min(hi, x))


def _days_ago(iso_date):
    if not iso_date:
        return 999.0
    try:
        d = datetime.fromisoformat(str(iso_date).replace("Z", "+00:00"))
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return max(0.0, (datetime.now(timezone.utc) - d).total_seconds() / 86400.0)
    except Exception:
        return 999.0


def score_congress(trades):
    if not trades:
        return {"score": 0, "detail": "No disclosed congressional trades"}
    net = 0.0; buys = sells = 0
    for t in trades:
        recency = max(0.2, 1.0 - _days_ago(t.get("filed_date")) / 60.0)
        sign = 1 if t.get("transaction") == "buy" else -1
        buys += sign > 0; sells += sign < 0
        net += sign * recency * 20.0
    return {"score": round(clamp(net)), "detail": f"{buys} buy / {sells} sell disclosure(s) (≤45d lag)"}


def score_contracts(awards):
    if not awards:
        return {"score": 0, "detail": "No relevant federal awards in window"}
    import math
    total = sum(a.get("amount", 0) or 0 for a in awards)
    score = clamp(min(80, 18 * math.log10(max(total, 1) / 1e6 + 1)), -100, 80)
    return {"score": round(score), "detail": f"${total/1e6:,.0f}M across {len(awards)} award(s)"}


def score_news(items):
    if not items:
        return {"score": 0, "detail": "No recent headlines"}
    avg = sum(i.get("sentiment", 0.0) for i in items) / len(items)
    score = clamp(avg * 60.0)
    mood = "positive" if score > 8 else "negative" if score < -8 else "mixed"
    srcs = sorted({i.get("source", "rss") for i in items})
    return {"score": round(score), "detail": f"{len(items)} headlines from {len(srcs)} feeds, {mood} (avg {avg:+.2f})"}


def score_social(posts):
    """posts: [{sentiment: -1..1, source: 'reddit'|'stocktwits'}].
    Averages sentiment; lightly rewards higher chatter volume (conviction).
    """
    if not posts:
        return {"score": 0, "detail": "No social chatter found"}
    avg = sum(p.get("sentiment", 0.0) for p in posts) / len(posts)
    vol_factor = min(1.2, 0.6 + len(posts) / 50.0)  # 0.6..1.2
    score = clamp(avg * 55.0 * vol_factor)
    srcs = sorted({p.get("source", "social") for p in posts})
    mood = "bullish" if score > 8 else "bearish" if score < -8 else "mixed"
    return {"score": round(score), "detail": f"{len(posts)} posts ({', '.join(srcs)}), {mood} (avg {avg:+.2f})"}


def score_insider(filings):
    if not filings:
        return {"score": 0, "detail": "No notable Form 4 activity"}
    net = 0.0; buys = sells = 0
    for f in filings:
        code = (f.get("code") or "").upper()
        if code == "P":
            net += 25; buys += 1
        elif code == "S":
            net -= 18; sells += 1
    return {"score": round(clamp(net)), "detail": f"{buys} purchase / {sells} sale Form 4 filing(s)"}


def composite(signals):
    return round(sum(signals[k]["score"] * WEIGHTS[k] for k in WEIGHTS if k in signals), 1)


def direction(comp):
    return "LEANS BULLISH" if comp > 12 else "LEANS BEARISH" if comp < -12 else "NO CLEAR SIGNAL"
