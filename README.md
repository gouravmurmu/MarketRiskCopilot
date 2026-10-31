# Market Risk Copilot

A daily market risk platform for a sample ~$10M multi-asset portfolio. It computes 1-day
VaR and Expected Shortfall several ways, backtests every model, checks limits, and uses a
Claude-powered copilot to explain the day's move and draft the risk commentary.

Deterministic models produce every number. The AI only explains them, and a validator plus
human sign-off sit between its draft and the final report.

**Live demo:** [market-risk-copilot-gules.vercel.app](https://market-risk-copilot-gules.vercel.app)
(the free API sleeps when idle, so the first load can take about 30 seconds).

> Educational project using only public data. Not investment advice. Not affiliated with
> any employer.

## Status

| Step | Scope | State |
| --- | --- | --- |
| 1 | Data pipeline, risk engine, backtests, limits, daily batch | Done |
| 2 | FastAPI backend and Next.js dashboard | Done |
| 3 | AI copilot: daily commentary, validator, sign-off, chat | Done |
| 4 | Deployment, monitoring, showcase | Done |

## Portfolio

15 liquid instruments across five asset classes, held as USD exposures:
equities (SPY, QQQ, NVDA, AAPL, XLF, EFA, INDA), rates (TLT, IEF), credit (LQD, HYG),
commodities (GLD, USO) and FX (long EUR, long INR). See `backend/riskcopilot/reference.py`.

## Models

All at 99% and 97.5%, 1-day, with 10-day by square-root-of-time (assumes i.i.d. returns).

| Key | Model |
| --- | --- |
| `hs_250`, `hs_500` | Historical simulation, 250 and 500 days |
| `hs_aw_500` | Age-weighted historical simulation (lambda 0.98) |
| `fhs_500` | Filtered historical simulation, GARCH(1,1) per instrument |
| `pn_sample_500` | Parametric normal, equally weighted covariance |
| `pn_ewma` | Parametric normal, RiskMetrics EWMA (lambda 0.94) |
| `pt_ewma` | Parametric Student-t, degrees of freedom fitted to portfolio P&L |
| `mc_ewma` | Monte Carlo, 20,000 correlated paths, fixed seed |
| `svar` | Stressed VaR, historical over Feb 2020 to Jan 2021 |

Each run also stores:

- **Component and marginal VaR** by position and asset class (Euler allocation; components
  sum exactly to total VaR).
- **Daily VaR change attribution** into position, volatility, correlation and window-roll
  effects, which always reconcile to the day-over-day change.
- **Backtests**: Kupiec POF, Christoffersen independence, conditional coverage and the Basel
  traffic light, over a rolling 250 days and the full history.
- **Limit checks** on standalone 1-day 99% VaR (500-day historical): warning at 80%
  utilisation, breach at 100%.

## Daily pipeline

`python -m riskcopilot.jobs.eod` runs ingest, data checks, engine, attribution, limits and
backtests. Data checks (missing, stale, 6-sigma jumps, coverage, forward fills) run first, and
a critical issue on the as-of date stops the run before any risk number is produced. Every step
is idempotent, so reruns replace a day's results. The first run backfills from 2015.

It runs on GitHub Actions at 00:23 UTC Tuesday to Saturday (`.github/workflows/eod.yml`).

## AI copilot

Built on the Claude API (`claude-opus-5-5`, adaptive thinking) in `backend/riskcopilot/agent/`.
The model never calculates a number: it reads ten read-only tools over the engine outputs
(`get_risk_summary`, `get_var_attribution`, `get_top_contributors`, `get_market_moves`,
`get_macro_context`, `get_limit_status`, `get_backtest_status`, `get_scenario_rolloff`,
`get_data_quality_issues`, `run_what_if`). `run_what_if` works on a copy of the positions.

**Daily commentary** (`python -m riskcopilot.agent.daily`, runs after the EOD job):

1. Code calls the tools in a fixed order, so the input is identical every run.
2. Claude returns JSON in a fixed schema (structured outputs); code renders it to markdown.
3. A numeric validator matches every figure, including those in the prose ($172.4k, 18.1%),
   to a tool output, checks every warning or breach is reported with the rule engine's status,
   and rejects tickers outside the portfolio.
4. Validator errors go back to the model, at most twice; then the draft is marked
   "needs review".
5. An analyst edits and approves it on the Commentary page. Approved notes are never redrafted.

**Chat**: a tool-use loop (at most 8 tool calls per question) that streams the answer and
the tools it called to a side panel on every page. A daily question cap protects the API budget.

Every tool call and model call is logged to `agent_traces` with an output hash, tokens,
latency and the model that served it. Requests opt into server-side fallbacks, so a declined
request is retried on Anthropic's recommended fallback model.

`python -m riskcopilot.agent.eval` scores the commentary on ten golden dates (COVID crash,
2022 CPI shock, SVB, the 2024 yen unwind, the simulated trades): validator pass rate, first-try
rate, direction of the headline, limits coverage and top-driver coverage. It runs from the
"Copilot eval" workflow.

## API

FastAPI, read-only over the risk tables (`uvicorn riskcopilot.api.main:app`, docs at `/docs`):

| Endpoint | Returns |
| --- | --- |
| `GET /meta` | Models, primary model, available dates |
| `GET /portfolio?as_of=` | Positions and notionals |
| `GET /risk/summary?as_of=` | VaR and ES for every model, with day-over-day change |
| `GET /risk/history?model=&confidence=&from=&to=` | VaR/ES series with next-day P&L and exceptions |
| `GET /risk/contributors?as_of=&model=&level=` | Component and marginal VaR |
| `GET /risk/attribution?as_of=&model=` | Waterfall effects with detail |
| `GET /backtest?model=&confidence=&scope=` | Kupiec, Christoffersen, traffic light |
| `GET /limits?as_of=` | Utilisation and status |
| `GET /data-quality?as_of=` | Issues and latest price dates |
| `POST /whatif` | VaR, ES and limits after hypothetical exposure changes |
| `POST /jobs/eod` | Triggers the batch (bearer `EOD_TOKEN`) |
| `GET /commentary?as_of=` | Daily note, status and validator report |
| `GET /commentary/dates` | Recent notes and their status |
| `POST /commentary/generate` | Drafts the note in the background (bearer `EOD_TOKEN`) |
| `POST /commentary/approve` | Stores the edited note and approver (optional `APPROVE_TOKEN`) |
| `POST /chat` | Copilot answer as server-sent events |

`docker compose up` starts Postgres and the API locally.

## Dashboard

Next.js in `frontend/` (see its README): overview with VaR/ES tiles, P&L vs VaR chart, limit
bars and the "why did VaR move?" waterfall; risk breakdown by position; VaR change detail;
backtest table for every model; a what-if page with sliders that reprices through the API;
commentary review and sign-off; data quality; and the copilot side panel. It falls back to labelled demo data when the API is unreachable.

## Deployment

| Piece | Where | Notes |
| --- | --- | --- |
| Database | Supabase Postgres (us-east-1) | Reached through the session pooler (IPv4) |
| Daily batch + commentary | GitHub Actions, 00:23 UTC Tue to Sat | Backfills ten years (about 2,470 business days) in 8 minutes on first run |
| API | Render, Docker (`backend/Dockerfile`) | Runs migrations on start; CI builds the same image |
| Dashboard | Vercel (`frontend/`) | `NEXT_PUBLIC_API_URL` points at the API |

Secrets live only in GitHub Actions and Render settings: `DATABASE_URL`, `ANTHROPIC_API_KEY`,
optional `FRED_API_KEY`, `EOD_TOKEN` and `APPROVE_TOKEN`. The API's `CORS_ORIGINS` must include
the dashboard URL.

## Local development

```bash
cd backend
uv sync
uv run pytest            # engine, data, job, API and copilot tests (Claude is mocked)
uv run alembic upgrade head
uv run python -m riskcopilot.jobs.eod
```

Settings come from environment variables; see `backend/.env.example`. Without
`DATABASE_URL` a local SQLite file is used.

## Stack

Python 3.12, NumPy, pandas, SciPy, arch, SQLAlchemy 2 and Alembic on Postgres (Neon).
FastAPI, the Anthropic Python SDK, Next.js 15 + Tailwind + Recharts.
