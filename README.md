# Signalroom

A backend that aggregates public signals (congressional trades, government
contracts, news sentiment, insider filings) into a per-ticker composite, **and**
serves a dashboard from the same origin. One deploy = one bookmarkable URL with
all four signals live — no CORS, no proxy.

> Not predictions. Not financial advice. The composite is a *signal-strength*
> heuristic; validate with the backtest before trusting anything.

---

## Run locally

```bash
pip install -r requirements.txt
export SEC_USER_AGENT="Signalroom/1.0 (you@example.com)"   # required for SEC
export QUIVER_TOKEN=...    # optional: congress signal
export FINNHUB_KEY=...     # optional: live price
uvicorn main:app --reload --port 8000
# open http://localhost:8000
```

## Deploy to a free URL (Render, ~5 clicks)

1. Push this folder to a new GitHub repo.
2. On [render.com](https://render.com): **New → Blueprint**, pick the repo. It reads `render.yaml`.
3. When prompted, set the env vars:
   - `SEC_USER_AGENT` → `Signalroom/1.0 (your-email)`  ← **required**
   - `QUIVER_TOKEN`, `FINNHUB_KEY` → optional
4. Deploy. Your dashboard is at `https://<your-app>.onrender.com`.

Any container host (Railway, Fly.io) works too via the included `Dockerfile`.

> Free tiers sleep when idle, so the first load after a pause can take ~30s while the server wakes.

## Source status

| Signal     | Source            | Status | Needs |
|------------|-------------------|--------|-------|
| News       | Google News RSS   | ✅ live | nothing |
| Contracts  | USASpending.gov   | ✅ live | nothing (server-side POST) |
| Insider    | SEC EDGAR         | ✅ live | `SEC_USER_AGENT` env var |
| Congress   | QuiverQuant       | ⚪ neutral until token | `QUIVER_TOKEN` |
| Price/IV   | Finnhub           | ⚪ null until key | `FINNHUB_KEY` (IV needs an options feed) |

Once deployed, the dashboard's three former `BACKEND` signals light up because
the browser now talks to your server instead of being blocked by CORS.

## Files
- `main.py` — API + static serving
- `sources.py` — the four fetchers (defensive: any failure → neutral score)
- `scoring.py` — pure scoring logic (matches the backtest)
- `config.py` — watchlist + env config
- `static/index.html` — the dashboard (fetches `/signals` same-origin)

## Hardening before real use
- Restrict CORS `allow_origins` to your own domain in `main.py`.
- Verify the `recipient` names in `config.py` map to the right legal entities on USASpending.
- Run the backtest on this server's output before acting on any signal.
