export const usdK = (v: number, digits = 1) => {
  const a = Math.abs(v);
  const s = a >= 1e6 ? `$${(a / 1e6).toFixed(2)}M` : `$${(a / 1e3).toFixed(digits)}k`;
  return v < 0 ? `−${s}` : s;
};
export const signedK = (v: number) => (v >= 0 ? "+" : "") + usdK(v);
export const pct = (v: number, digits = 0) => `${(v * 100).toFixed(digits)}%`;
export const signedPct = (v: number, digits = 1) => (v >= 0 ? "+" : "−") + `${Math.abs(v * 100).toFixed(digits)}%`;
export const confLabel = (c: number) => `${+(c * 100).toFixed(1)}%`;
export const longDate = (iso: string) =>
  new Date(iso + "T00:00:00Z").toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
export const shortDate = (iso: string) =>
  new Date(iso + "T00:00:00Z").toLocaleDateString("en-GB", { day: "numeric", month: "short", timeZone: "UTC" });

export const EFFECT_LABEL: Record<string, string> = {
  position: "Position",
  volatility: "Volatility",
  correlation: "Correlation",
  window_roll: "Window roll",
  market_data: "Market data",
};

export const ASSET_COLOR: Record<string, string> = {
  Equity: "#5E8A66",
  Rates: "#8FB6C9",
  Credit: "#B7A3D1",
  Commodities: "#E8A96B",
  FX: "#D9C27A",
};
