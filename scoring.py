"""Pure signal-scoring logic. No external dependencies, fully unit-testable.

Every raw source is mapped to a score in [-100, 100]. The composite is a
weighted blend matching the dashboard. NOTE: this is a *signal-strength*
heuristic, not a probability of profit. Validate with backtests before trusting.
"""
from __future__ import annotations
from datetime import datetime, timezone

# Must match the frontend weights exactly.
WEIGHTS = {"congress": 0.30, "contracts": 0.25, "news": 0.25, "insider": 0.20}


def clamp(x: float, lo: float = -100.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


def _days_ago(iso_date: str | None) -> float:
    if not iso_date:
        return 999.0
    try:
        d = datetime.fromisoformat(iso_date.replace("Z", "+00:00"))
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return max(0.0, (datetime.now(timezone.utc) - d).total_seconds() / 86400.0)
    except Exception:
        return 999.0


def score_congress(trades: list[dict]) -> dict:
    """trades: [{transaction: 'buy'|'sell', amount: float, filed_date: iso}]
    Disclosures lag up to 45 days, so we decay older filings.
    """
    if not trades:
        return {"score": 0, "detail": "No disclosed congressional trades"}
    net = 0.0
    buys = sells = 0
    for t in trades:
        recency = max(0.2, 1.0 - _days_ago(t.get("filed_date")) / 60.0)  # 0.2..1.0
        sign = 1 if t.get("transaction") == "buy" else -1
        if sign > 0:
            buys += 1
        else:
            sells += 1
        net += sign * recency * 20.0
    detail = f"{buys} buy / {sells} sell disclosure(s) in window (≤45d lag)"
    return {"score": round(clamp(net)), "detail": detail}


def score_contracts(awards: list[dict]) -> dict:
    """awards: [{amount: float, date: iso}] from USASpending.
    Federal awards are a mild positive revenue signal; capped, never strongly negative.
    """
    if not awards:
        return {"score": 0, "detail": "No relevant federal awards in window"}
    total = sum(a.get("amount", 0) or 0 for a in awards)
    # log-ish scaling: $100M -> ~40, $1B -> ~65, $5B+ -> ~80
    import math
    score = clamp(min(80, 18 * math.log10(max(total, 1) / 1e6 + 1)), -100, 80)
    detail = f"${total/1e6:,.0f}M across {len(awards)} award(s)"
    return {"score": round(score), "detail": detail}


def score_news(items: list[dict]) -> dict:
    """items: [{sentiment: float in [-1,1]}]. Average -> scaled to [-60, 60]."""
    if not items:
        return {"score": 0, "detail": "No recent headlines"}
    avg = sum(i.get("sentiment", 0.0) for i in items) / len(items)
    score = clamp(avg * 60.0)
    mood = "positive" if score > 8 else "negative" if score < -8 else "mixed"
    detail = f"{len(items)} headlines, {mood} (avg {avg:+.2f})"
    return {"score": round(score), "detail": detail}


def score_insider(filings: list[dict]) -> dict:
    """filings: [{code: 'P'|'S'|..., value: float, date: iso}] from SEC Form 4.
    P = open-market purchase (bullish), S = sale (bearish). 10b5-1 sales discounted.
    """
    if not filings:
        return {"score": 0, "detail": "No notable Form 4 activity"}
    net = 0.0
    buys = sells = 0
    for f in filings:
        code = (f.get("code") or "").upper()
        if code == "P":
            net += 25
            buys += 1
        elif code == "S":
            net -= 18  # sales are weaker signal (comp, planned plans, etc.)
            sells += 1
    detail = f"{buys} purchase / {sells} sale Form 4 filing(s)"
    return {"score": round(clamp(net)), "detail": detail}


def composite(signals: dict) -> float:
    return round(sum(signals[k]["score"] * WEIGHTS[k] for k in WEIGHTS), 1)


def direction(comp: float) -> str:
    return "LEANS BULLISH" if comp > 12 else "LEANS BEARISH" if comp < -12 else "NO CLEAR SIGNAL"
