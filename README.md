# Market Risk Copilot

A daily market risk platform for a sample ~$10M multi-asset portfolio. It computes 1-day
VaR and Expected Shortfall several ways, backtests every model, checks limits, and (coming
next) uses an LLM copilot to explain the day's move and draft the risk commentary.

Deterministic models produce every number. The AI only explains them, and a validator plus
human sign-off sit between its draft and the final report.

> Educational project using only public data. Not investment advice. Not affiliated with
> any employer.

## Status

| Step | Scope | State |
| --- | --- | --- |
| 1 | Data pipeline, risk engine, backtests, limits, daily batch | In review |
| 2 | FastAPI backend and Next.js dashboard | Planned |
| 3 | AI copilot: daily commentary, validator, sign-off, chat | Planned |
| 4 | Deployment, monitoring, showcase | Planned |

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

It runs on GitHub Actions at 00:00 UTC Tuesday to Saturday (`.github/workflows/eod.yml`).

## Local development

```bash
cd backend
uv sync
uv run pytest            # engine, data-quality and end-to-end job tests
uv run alembic upgrade head
uv run python -m riskcopilot.jobs.eod
```

Settings come from environment variables; see `backend/.env.example`. Without
`DATABASE_URL` a local SQLite file is used.

## Stack

Python 3.12, NumPy, pandas, SciPy, arch, SQLAlchemy 2 and Alembic on Postgres (Supabase).
Coming next: FastAPI, Next.js + Tailwind + Recharts, the Claude API, Langfuse.
