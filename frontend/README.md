# Risk Copilot dashboard

Next.js 15 + Tailwind + Recharts. Light sage-and-white theme defined in `tailwind.config.ts`.

```bash
npm install
cp .env.example .env.local   # set NEXT_PUBLIC_API_URL to the FastAPI backend
npm run dev                  # http://localhost:3000
```

Without `NEXT_PUBLIC_API_URL`, or while the API is unreachable (the free Render instance
sleeps when idle), every page falls back to deterministic demo data from `lib/demo.ts` and
shows a "Demo data" badge, so the site never breaks in a demo.

Pages: Overview, Risk breakdown, VaR change, Backtests, What-if, Commentary (AI copilot,
next step), Data quality.
