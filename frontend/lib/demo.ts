// Deterministic sample data used when the API is unreachable (e.g. before the first
// real run, or while the free-tier API is waking up). Shapes match the API exactly;
// every page shows a "Demo data" badge while these are on screen.

import type {
  Attribution,
  BacktestRow,
  ChatEvent,
  Commentary,
  CommentaryDates,
  Contributors,
  DataQuality,
  Limits,
  Meta,
  Portfolio,
  RiskHistory,
  RiskSummary,
  WhatIfRequest,
  WhatIfResult,
} from "./types";

export const DEMO_AS_OF = "2026-10-29";
const PREV = "2026-10-28";

const MODELS = [
  { key: "hs_250", method: "historical", label: "Historical simulation, 250d", window: 250, f: 1.08, chg: 0.12 },
  { key: "hs_500", method: "historical", label: "Historical simulation, 500d", window: 500, f: 1.0, chg: 0.181 },
  { key: "hs_aw_500", method: "historical", label: "Age-weighted HS (lambda 0.98), 500d", window: 500, f: 1.15, chg: 0.2 },
  { key: "fhs_500", method: "historical", label: "Filtered HS (GARCH 1,1), 500d", window: 500, f: 1.12, chg: 0.22 },
  { key: "pn_sample_500", method: "parametric", label: "Parametric normal, sample covariance", window: 500, f: 0.86, chg: 0.03 },
  { key: "pn_ewma", method: "parametric", label: "Parametric normal, EWMA (lambda 0.94)", window: 500, f: 0.93, chg: 0.15 },
  { key: "pt_ewma", method: "parametric", label: "Parametric Student-t, EWMA", window: 500, f: 1.01, chg: 0.16 },
  { key: "mc_ewma", method: "monte_carlo", label: "Monte Carlo, EWMA covariance", window: 500, f: 0.94, chg: 0.15 },
  { key: "svar", method: "stressed", label: "Stressed VaR (historical, 2020 stress window)", window: 250, f: 1.72, chg: 0 },
];
const BASE_VAR = 168_400;

function scale(model: string, conf: number) {
  const m = MODELS.find((x) => x.key === model) ?? MODELS[1];
  return m.f * (conf >= 0.99 ? 1 : 0.72);
}

function rng(seed: number) {
  return () => {
    seed |= 0;
    seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export const demoMeta = (): Meta => ({
  latest_as_of: DEMO_AS_OF,
  first_as_of: "2017-01-03",
  primary_model: "hs_500",
  primary_confidence: 0.99,
  models: MODELS.map(({ key, method, label, window }) => ({ key, method, label, window })),
});

const POSITIONS: [string, string, string, number][] = [
  ["SPY", "S&P 500 ETF", "Equity", 1_500_000],
  ["QQQ", "Nasdaq-100 ETF", "Equity", 1_000_000],
  ["NVDA", "Nvidia", "Equity", 750_000],
  ["AAPL", "Apple", "Equity", 500_000],
  ["XLF", "US financials ETF", "Equity", 500_000],
  ["EFA", "Developed ex-US equity ETF", "Equity", 700_000],
  ["INDA", "India equity ETF", "Equity", 600_000],
  ["TLT", "20+ year Treasury ETF", "Rates", 900_000],
  ["IEF", "7-10 year Treasury ETF", "Rates", 800_000],
  ["LQD", "Investment-grade corporate bond ETF", "Credit", 700_000],
  ["HYG", "High-yield bond ETF", "Credit", 500_000],
  ["GLD", "Gold ETF", "Commodities", 650_000],
  ["USO", "Oil ETF", "Commodities", 300_000],
  ["EURUSD=X", "Long EUR cash", "FX", 400_000],
  ["INR=X", "Long INR cash", "FX", 300_000],
];
// Component VaR (hs_500, 99%) in USD; sums to BASE_VAR.
const COMPONENT: Record<string, number> = {
  SPY: 32_000, QQQ: 30_500, NVDA: 38_600, AAPL: 11_400, XLF: 8_600, EFA: 7_400, INDA: 5_700,
  TLT: 7_900, IEF: 1_700, LQD: 3_600, HYG: 2_700, GLD: 6_000, USO: 8_200, "EURUSD=X": 2_500, "INR=X": 1_600,
};

export const demoPortfolio = (): Portfolio => ({
  as_of: DEMO_AS_OF,
  positions_as_of: "2026-10-20",
  total_usd: POSITIONS.reduce((a, p) => a + p[3], 0),
  positions: POSITIONS.map(([ticker, name, asset_class, notional_usd]) => ({ ticker, name, asset_class, notional_usd })),
});

export const demoSummary = (): RiskSummary => ({
  as_of: DEMO_AS_OF,
  previous_as_of: PREV,
  code_version: "demo",
  figures: MODELS.flatMap((m) =>
    [0.99, 0.975].map((c) => {
      const v = BASE_VAR * scale(m.key, c);
      const prev = v / (1 + m.chg);
      const es = v * (c >= 0.99 ? 1.276 : 1.42);
      return {
        model: m.key, method: m.method, label: m.label, confidence: c,
        var_usd: v, es_usd: es, var_10d_usd: v * Math.sqrt(10), es_10d_usd: es * Math.sqrt(10),
        prev_var_usd: prev, change_usd: v - prev, change_pct: v / prev - 1,
      };
    }),
  ),
});

export const demoHistory = (model: string, conf: number): RiskHistory => {
  const r = rng(11);
  const s = scale(model, conf);
  const n = 250;
  const end = new Date(DEMO_AS_OF + "T00:00:00Z");
  const days: string[] = [];
  for (const d = new Date(end); days.length < n; d.setUTCDate(d.getUTCDate() - 1)) {
    const wd = d.getUTCDay();
    if (wd !== 0 && wd !== 6) days.unshift(d.toISOString().slice(0, 10));
  }
  const points = days.map((date, i) => {
    const v = (128_000 + 16_000 * Math.sin(i / 23) + (i > 240 ? (i - 240) * 3_500 : 0)) * s;
    const z = (r() + r() + r() + r() - 2) * 1.7;
    let pnl: number | null = z * 34_000 * (1 + 0.3 * Math.sin(i / 17));
    if (i === 97) pnl = -v * 1.07;
    if (i === 211) pnl = -v * 1.03;
    if (i === n - 1) pnl = null;
    return { date, var_usd: v, es_usd: v * 1.276, pnl_usd: pnl, exception: pnl === null ? null : -pnl > v };
  });
  points[n - 1].var_usd = BASE_VAR * s;
  points[n - 2].var_usd = (BASE_VAR * s) / 1.181;
  return { model, confidence: conf, points };
};

export const demoContributors = (model: string, conf: number, level: "position" | "asset_class"): Contributors => {
  const s = scale(model, conf);
  const total = BASE_VAR * s;
  const rows = POSITIONS.map(([t, , ac, n]) => ({ key: t, ac, exposure_usd: n, component_var: COMPONENT[t] * s }));
  let items;
  if (level === "position") {
    items = rows.map((x) => ({ key: x.key, exposure_usd: x.exposure_usd, component_var: x.component_var, marginal_var: x.component_var / x.exposure_usd, share: x.component_var / total }));
  } else {
    const by = new Map<string, { e: number; c: number }>();
    rows.forEach((x) => {
      const g = by.get(x.ac) ?? { e: 0, c: 0 };
      by.set(x.ac, { e: g.e + x.exposure_usd, c: g.c + x.component_var });
    });
    items = [...by].map(([key, g]) => ({ key, exposure_usd: g.e, component_var: g.c, marginal_var: g.c / g.e, share: g.c / total }));
  }
  items.sort((a, b) => b.component_var - a.component_var);
  return { as_of: DEMO_AS_OF, model, confidence: conf, level, total_var_usd: total, items };
};

export const demoAttribution = (model: string, conf: number): Attribution => {
  const s = scale(model, conf);
  const m = MODELS.find((x) => x.key === model) ?? MODELS[1];
  const v = BASE_VAR * s;
  const prev = v / (1 + m.chg);
  const d = v - prev;
  const pos = Math.min(9_800 * s, d);
  const changes = { NVDA: { from: 500_000, to: 750_000 } };
  let effects: Attribution["effects"];
  if (m.method === "historical" && !m.key.includes("aw") && !m.key.includes("fhs")) {
    effects = [
      { effect: "position", amount_usd: pos, detail: { changes } },
      {
        effect: "window_roll",
        amount_usd: d - pos,
        detail: {
          dropped: [{ date: "2024-10-31", pnl: -12_400, in_tail: false }],
          added: [{ date: DEMO_AS_OF, pnl: -171_900, in_tail: true }],
        },
      },
    ];
  } else if (m.method === "parametric" && m.key !== "pt_ewma") {
    effects = [
      { effect: "position", amount_usd: pos, detail: { changes } },
      { effect: "volatility", amount_usd: (d - pos) * 1.19, detail: { daily_vol: { QQQ: { from: 0.0118, to: 0.0157 }, NVDA: { from: 0.0241, to: 0.0322 } } } },
      { effect: "correlation", amount_usd: (d - pos) * -0.19, detail: {} },
    ];
  } else {
    effects = [
      { effect: "position", amount_usd: pos, detail: { changes } },
      { effect: "market_data", amount_usd: d - pos, detail: {} },
    ];
  }
  return { as_of: DEMO_AS_OF, model, confidence: conf, previous_var_usd: prev, var_usd: v, effects };
};

const chi2sf1 = (x: number) => {
  // P(chi2_1 > x) = erfc(sqrt(x/2)); Abramowitz-Stegun erfc approximation.
  const z = Math.sqrt(x / 2);
  const t = 1 / (1 + 0.5 * z);
  const y = t * Math.exp(-z * z - 1.26551223 + t * (1.00002368 + t * (0.37409196 + t * (0.09678418 + t * (-0.18628806 + t * (0.27886807 + t * (-1.13520398 + t * (1.48851587 + t * (-0.82215223 + t * 0.17087277)))))))));
  return Math.min(1, Math.max(0, y));
};
const xlogy = (a: number, b: number) => (a === 0 ? 0 : a * Math.log(b));
function kupiec(T: number, x: number, p: number) {
  const ph = x / T;
  const lr = Math.max(0, -2 * (xlogy(T - x, 1 - p) + xlogy(x, p) - xlogy(T - x, 1 - ph) - xlogy(x, ph)));
  return { lr, p: chi2sf1(lr) };
}
const EXC: Record<string, [number, number, number, number]> = {
  // rolling 99, full 99, rolling 97.5, full 97.5
  hs_250: [3, 31, 7, 66], hs_500: [2, 27, 6, 63], hs_aw_500: [2, 25, 5, 58], fhs_500: [2, 24, 6, 60],
  pn_sample_500: [6, 39, 9, 74], pn_ewma: [4, 33, 7, 65], pt_ewma: [3, 26, 7, 64], mc_ewma: [4, 34, 8, 66], svar: [0, 6, 1, 19],
};
export const demoBacktests = (): BacktestRow[] =>
  Object.entries(EXC).flatMap(([model, [r99, f99, r975, f975]]) =>
    (
      [
        [0.99, "rolling_250", 250, r99],
        [0.99, "full", 2450, f99],
        [0.975, "rolling_250", 250, r975],
        [0.975, "full", 2450, f975],
      ] as const
    ).map(([confidence, scope, T, x]) => {
      const p = 1 - confidence;
      const k = kupiec(T, x, p);
      const ind = model === "pn_sample_500" ? 4.9 : 0.3 + (x % 3) * 0.4;
      const cc = k.lr + ind;
      const zone = x <= T * p + 1.65 * Math.sqrt(T * p * (1 - p)) ? "green" : x <= T * p + 3.7 * Math.sqrt(T * p * (1 - p)) ? "yellow" : "red";
      return {
        model, confidence, scope, window_end: DEMO_AS_OF, T, exceptions: x, expected: T * p,
        lr_pof: k.lr, p_pof: k.p, lr_ind: ind, p_ind: chi2sf1(ind), lr_cc: cc, p_cc: Math.exp(-cc / 2), zone,
      } as BacktestRow;
    }),
  );

const LIMITS: [string, number, number][] = [
  ["Portfolio", 168_400, 200_000],
  ["Equity", 151_000, 175_000],
  ["Rates", 22_800, 40_000],
  ["Commodities", 19_400, 30_000],
  ["Credit", 11_200, 20_000],
  ["FX", 6_100, 15_000],
];
const limitItem = (scope: string, value: number, limit: number) => {
  const u = value / limit;
  return { scope, limit_usd: limit, value_usd: value, utilisation: u, warn_pct: 0.8, status: (u >= 1 ? "breach" : u >= 0.8 ? "warning" : "ok") as "ok" | "warning" | "breach" };
};
export const demoLimits = (): Limits => ({
  as_of: DEMO_AS_OF,
  model: "hs_500",
  items: LIMITS.map(([s, v, l]) => limitItem(s, v, l)),
});

export const demoDataQuality = (): DataQuality => ({
  as_of: DEMO_AS_OF,
  blocking: false,
  issues: [
    { id: 1, date: DEMO_AS_OF, ticker: "INR=X", check: "fill", severity: "info", detail: "forward-filled (market holiday or missing print)", resolved: false },
  ],
  latest_price_dates: Object.fromEntries(POSITIONS.map(([t]) => [t, t === "INR=X" ? PREV : DEMO_AS_OF])),
});

/** Linear (marginal VaR) approximation, good for small changes; the real API reprices fully. */
export const demoWhatIf = (req: WhatIfRequest): WhatIfResult => {
  const before = Object.fromEntries(POSITIONS.map(([t, , , n]) => [t, n]));
  const after: Record<string, number> = { ...before, ...(req.set_exposure ?? {}) };
  for (const [t, dv] of Object.entries(req.change_exposure ?? {})) after[t] = (after[t] ?? 0) + dv;
  const acOf = Object.fromEntries(POSITIONS.map(([t, , ac]) => [t, ac]));
  const dVar = (s: number, filter?: string) =>
    POSITIONS.reduce((a, [t, , ac, n]) => (filter && ac !== filter ? a : a + (COMPONENT[t] / n) * s * ((after[t] ?? 0) - n)), 0);
  const figures = (req.models ?? ["hs_500", "pn_ewma", "mc_ewma"]).flatMap((m) =>
    [0.99, 0.975].map((c) => {
      const s = scale(m, c);
      const vb = BASE_VAR * s;
      const va = Math.max(0, vb + dVar(s));
      return { model: m, confidence: c, var_before: vb, var_after: va, es_before: vb * 1.276, es_after: va * 1.276 };
    }),
  );
  const lb = demoLimits().items;
  const la = lb.map((l) => {
    const d = l.scope === "Portfolio" ? dVar(1) : dVar(1, l.scope) * (l.value_usd / (POSITIONS.filter((p) => acOf[p[0]] === l.scope).reduce((a, p) => a + COMPONENT[p[0]], 0) || 1));
    return limitItem(l.scope, Math.max(0, l.value_usd + d), l.limit_usd);
  });
  return { as_of: DEMO_AS_OF, exposures_before: before, exposures_after: after, figures, limits_before: lb, limits_after: la };
};

const k1 = (v: number) => `${v < 0 ? "-" : ""}$${(Math.abs(v) / 1000).toFixed(1)}k`;
const sk1 = (v: number) => (v >= 0 ? "+" : "-") + k1(Math.abs(v));

/** Builds the sample note from the same demo figures as the other pages, the way the
 *  backend renders the model's JSON, so every number on it can be traced. */
export const demoCommentaryMd = (): string => {
  const s = demoSummary().figures.find((f) => f.model === "hs_500" && f.confidence === 0.99)!;
  const a = demoAttribution("hs_500", 0.99);
  const lim = demoLimits().items;
  const pos = a.effects.find((e) => e.effect === "position")!.amount_usd;
  const roll = a.effects.find((e) => e.effect === "window_roll")!.amount_usd;
  const eq = lim.find((l) => l.scope === "Equity")!;
  const pf = lim.find((l) => l.scope === "Portfolio")!;
  const bt = demoBacktests().find((b) => b.model === "hs_500" && b.confidence === 0.99 && b.scope === "rolling_250")!;
  const chg = (s.change_pct ?? 0) * 100;
  return [
    `## Daily risk commentary, ${DEMO_AS_OF}`,
    "",
    `**Portfolio 1-day 99% historical VaR rose ${chg.toFixed(1)}% to ${k1(s.var_usd)}, driven mainly by a large loss scenario entering the 500-day window (${sk1(roll)}) and the larger NVDA position (${sk1(pos)}).**`,
    "",
    "### VaR summary",
    "",
    "| Metric | Value | Change |",
    "|---|---:|---:|",
    `| HS 500d VaR 99% 1d | ${k1(s.var_usd)} | +${chg.toFixed(1)}% |`,
    `| HS 500d ES 99% 1d | ${k1(s.es_usd)} | n/a |`,
    "",
    "### What drove the change",
    "",
    `- **Window roll** (${sk1(roll)}): today's scenario, a ${k1(171_900)} loss on current positions, entered the window and sits in the VaR tail; the scenario that dropped out was a ${k1(12_400)} loss.`,
    `- **Position** (${sk1(pos)}): NVDA exposure rose from $500.0k to $750.0k under the simulated trade.`,
    "",
    "### Limits",
    "",
    "| Scope | Utilisation | Status |",
    "|---|---:|---|",
    `| Portfolio | ${(pf.utilisation * 100).toFixed(1)}% | ${pf.status} |`,
    `| Equity | ${(eq.utilisation * 100).toFixed(1)}% | ${eq.status} |`,
    "",
    "### Backtesting",
    "",
    `${bt.exceptions} exceptions in the last ${bt.T} days against ${bt.expected.toFixed(1)} expected; the model stays in the ${bt.zone} zone.`,
    "",
    "### Market context",
    "",
    "Daily volatility rose in QQQ and NVDA; see the parametric attribution for the volatility effect.",
    "",
    "### Data caveats",
    "",
    "- INR=X was forward-filled for a market holiday.",
    "",
    "_Sources: get_risk_summary, get_var_attribution, get_scenario_rolloff, get_limit_status, get_backtest_status, get_data_quality_issues_",
    "",
  ].join("\n");
};

export const demoCommentary = (): Commentary => ({
  as_of: DEMO_AS_OF,
  status: "draft",
  draft_md: demoCommentaryMd(),
  final_md: null,
  validator_report: { ok: true, attempts: 1, errors: [], model: "claude-opus-5-5", trace_id: null, draft: null },
  approved_by: null,
  approved_at: null,
});

export const demoCommentaryDates = (): CommentaryDates => ({
  items: [
    { as_of: DEMO_AS_OF, status: "draft" },
    { as_of: PREV, status: "approved" },
    { as_of: "2026-10-27", status: "approved" },
    { as_of: "2026-10-26", status: "needs_review" },
  ],
});

/** Scripted copilot answers for the demo, built from the demo figures. */
export const demoChat = (question: string): ChatEvent[] => {
  const q = question.toLowerCase();
  const s = demoSummary().figures.find((f) => f.model === "hs_500" && f.confidence === 0.99)!;
  const tool = (name: string, input: Record<string, unknown> = {}): ChatEvent[] => [
    { type: "tool_call", id: name, name, input },
    { type: "tool_result", id: name, name, ok: true, preview: "" },
  ];
  if (q.includes("what if") || q.includes("cut") || q.includes("half")) {
    const w = demoWhatIf({ change_exposure: { NVDA: -375_000 } });
    const f = w.figures.find((x) => x.model === "hs_500" && x.confidence === 0.99)!;
    const eq = w.limits_after.find((l) => l.scope === "Equity")!;
    return [
      ...tool("run_what_if", { change_exposure: { NVDA: -375_000 } }),
      { type: "text", text: `Halving NVDA (−$375.0k) would take 1-day 99% HS VaR from ${k1(f.var_before)} to ${k1(f.var_after)}, and Equity limit use to ${(eq.utilisation * 100).toFixed(1)}% (${eq.status}). This is hypothetical; positions are unchanged.\n\nSources: run_what_if` },
    ];
  }
  if (q.includes("limit") || q.includes("breach")) {
    const l = demoLimits().items;
    const rows = l.map((x) => `| ${x.scope} | ${(x.utilisation * 100).toFixed(1)}% | ${x.status} |`).join("\n");
    const warn = l.filter((x) => x.status === "warning").map((x) => x.scope);
    const breach = l.filter((x) => x.status === "breach").map((x) => x.scope);
    const lead = `${breach.length ? `${breach.join(" and ")} in breach.` : "No limit is in breach."} ${warn.length ? `${warn.join(" and ")} ${warn.length > 1 ? "are" : "is"} in warning (80% or more of the limit).` : ""}`;
    return [...tool("get_limit_status"), { type: "text", text: `${lead}\n\n| Scope | Use | Status |\n|---|---:|---|\n${rows}\n\nSources: get_limit_status` }];
  }
  if (q.includes("backtest") || q.includes("exception")) {
    const b = demoBacktests().find((x) => x.model === "hs_500" && x.confidence === 0.99 && x.scope === "rolling_250")!;
    return [...tool("get_backtest_status"), { type: "text", text: `HS 500d VaR at 99% had ${b.exceptions} exceptions in the last ${b.T} days, against ${b.expected.toFixed(1)} expected, so it is in the ${b.zone} zone.\n\nSources: get_backtest_status` }];
  }
  const a = demoAttribution("hs_500", 0.99);
  return [
    ...tool("get_risk_summary"),
    ...tool("get_var_attribution", { model: "hs_500" }),
    {
      type: "text",
      text: `1-day 99% HS VaR is ${k1(s.var_usd)}, up ${((s.change_pct ?? 0) * 100).toFixed(1)}% on the day. ${a.effects
        .map((e) => `${e.effect.replace("_", " ")} ${sk1(e.amount_usd)}`)
        .join(", ")}.\n\nSources: get_risk_summary, get_var_attribution`,
    },
  ];
};
