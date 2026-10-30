// Mirrors backend/riskcopilot/api/schemas.py. All risk figures are positive USD losses.

export type ModelInfo = { key: string; method: string; label: string; window: number };
export type Meta = {
  latest_as_of: string | null;
  first_as_of: string | null;
  primary_model: string;
  primary_confidence: number;
  models: ModelInfo[];
};
export type Position = { ticker: string; name: string; asset_class: string; notional_usd: number };
export type Portfolio = { as_of: string; positions_as_of: string | null; total_usd: number; positions: Position[] };
export type RiskFigure = {
  model: string;
  method: string;
  label: string;
  confidence: number;
  var_usd: number;
  es_usd: number;
  var_10d_usd: number;
  es_10d_usd: number;
  prev_var_usd: number | null;
  change_usd: number | null;
  change_pct: number | null;
};
export type RiskSummary = { as_of: string; previous_as_of: string | null; code_version: string | null; figures: RiskFigure[] };
export type HistoryPoint = { date: string; var_usd: number; es_usd: number; pnl_usd: number | null; exception: boolean | null };
export type RiskHistory = { model: string; confidence: number; points: HistoryPoint[] };
export type Contribution = { key: string; exposure_usd: number; component_var: number; marginal_var: number; share: number };
export type Contributors = {
  as_of: string;
  model: string;
  confidence: number;
  level: "position" | "asset_class";
  total_var_usd: number;
  items: Contribution[];
};
export type Scenario = { date: string; pnl: number; in_tail: boolean };
export type Effect = {
  effect: "position" | "volatility" | "correlation" | "window_roll" | "market_data";
  amount_usd: number;
  detail: {
    changes?: Record<string, { from: number; to: number }>;
    daily_vol?: Record<string, { from: number; to: number }>;
    dropped?: Scenario[];
    added?: Scenario[];
  };
};
export type Attribution = {
  as_of: string;
  model: string;
  confidence: number;
  previous_var_usd: number | null;
  var_usd: number;
  effects: Effect[];
};
export type BacktestRow = {
  model: string;
  confidence: number;
  scope: "rolling_250" | "full";
  window_end: string;
  T: number;
  exceptions: number;
  expected: number;
  lr_pof: number;
  p_pof: number;
  lr_ind: number;
  p_ind: number;
  lr_cc: number;
  p_cc: number;
  zone: "green" | "yellow" | "red";
};
export type LimitItem = {
  scope: string;
  limit_usd: number;
  value_usd: number;
  utilisation: number;
  status: "ok" | "warning" | "breach";
  warn_pct: number;
};
export type Limits = { as_of: string; model: string; items: LimitItem[] };
export type Issue = {
  id: number;
  date: string;
  ticker: string | null;
  check: string;
  severity: "info" | "warning" | "critical";
  detail: string;
  resolved: boolean;
};
export type DataQuality = { as_of: string; blocking: boolean; issues: Issue[]; latest_price_dates: Record<string, string> };
export type WhatIfRequest = {
  as_of?: string;
  set_exposure?: Record<string, number>;
  change_exposure?: Record<string, number>;
  models?: string[];
};
export type WhatIfFigure = { model: string; confidence: number; var_before: number; var_after: number; es_before: number; es_after: number };
export type WhatIfResult = {
  as_of: string;
  exposures_before: Record<string, number>;
  exposures_after: Record<string, number>;
  figures: WhatIfFigure[];
  limits_before: LimitItem[];
  limits_after: LimitItem[];
};
