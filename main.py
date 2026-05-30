"""Signalroom: FastAPI service that assembles per-ticker signals AND serves the
dashboard from the same origin (so the browser talks only to this server — no
CORS, no proxy, all four signals live).

Run locally:
    pip install -r requirements.txt
    export SEC_USER_AGENT="Signalroom/0.1 (you@example.com)"
    export QUIVER_TOKEN=...   # optional: congressional trades
    export FINNHUB_KEY=...    # optional: live price
    uvicorn main:app --reload --port 8000
    # open http://localhost:8000

Deploy: see README.md (Render one-click via render.yaml, or the Dockerfile).
"""
from __future__ import annotations
import os, time
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

import scoring as sc
import sources as src
from config import WATCHLIST, CACHE_TTL

app = FastAPI(title="Signalroom", version="1.0")

# Same-origin serving means CORS isn't needed for the bundled dashboard.
# Kept permissive so you can point the standalone HTML files at it too; lock
# this down to your own origin(s) for anything beyond a prototype.
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET"], allow_headers=["*"])

_cache: dict[str, tuple[float, dict]] = {}


def build_signal(symbol: str) -> dict:
    meta = WATCHLIST[symbol]
    signals = {
        "congress":  sc.score_congress(src.fetch_congress(symbol)),
        "contracts": sc.score_contracts(src.fetch_contracts(meta["recipient"])),
        "news":      sc.score_news(src.fetch_news(symbol, meta["name"])),
        "social":    sc.score_social(src.fetch_social(symbol, meta["name"])),
        "insider":   sc.score_insider(src.fetch_insider(symbol)),
    }
    comp = sc.composite(signals)
    quote = src.fetch_quote(symbol)
    return {
        "symbol": symbol, "name": meta["name"],
        "price": quote.get("price"), "day": quote.get("day"),
        "ivMove": None,  # wire an options source to fill
        "signals": signals, "composite": comp,
        "direction": sc.direction(comp), "weights": sc.WEIGHTS,
    }


def cached(symbol: str) -> dict:
    hit = _cache.get(symbol)
    if hit and time.time() - hit[0] < CACHE_TTL:
        return hit[1]
    data = build_signal(symbol)
    _cache[symbol] = (time.time(), data)
    return data


@app.get("/health")
def health():
    return {"ok": True, "watchlist": list(WATCHLIST)}


@app.get("/signals")
def all_signals():
    return [cached(s) for s in WATCHLIST]


@app.get("/signals/{symbol}")
def one_signal(symbol: str):
    symbol = symbol.upper()
    if symbol not in WATCHLIST:
        raise HTTPException(404, f"{symbol} not in watchlist")
    return cached(symbol)


# ---- serve the dashboard (mount LAST so it doesn't shadow the API routes) ----
if os.path.isdir("static"):
    @app.get("/")
    def index():
        return FileResponse("static/index.html")
    app.mount("/static", StaticFiles(directory="static"), name="static")
