// Timeframe helpers for the header segmented control. The timeframe scopes
// BOOKED (Closed Won) figures only; the open flagged pipeline is unaffected.
export const TIMEFRAMES = [
  { key: "month", label: "This month", short: "this month" },
  { key: "quarter", label: "This quarter", short: "this quarter" },
  { key: "ytd", label: "Year to date", short: "YTD" },
];

export const tfLabel = (tf) => TIMEFRAMES.find((t) => t.key === tf)?.label ?? "";
export const tfShort = (tf) => TIMEFRAMES.find((t) => t.key === tf)?.short ?? "";

const quarterOf = (m) => Math.floor((m - 1) / 3) + 1;

// Is a booked date (ISO) inside the timeframe, measured against the data's
// "as of" date? Real calendar boundaries (month / quarter / year-to-date).
export function inTimeframe(iso, tf, asOf) {
  if (!iso || !asOf) return true;
  const ay = +asOf.slice(0, 4);
  const am = +asOf.slice(5, 7);
  const y = +iso.slice(0, 4);
  const m = +iso.slice(5, 7);
  if (tf === "month") return y === ay && m === am;
  if (tf === "quarter") return y === ay && quarterOf(m) === quarterOf(am);
  if (tf === "ytd") return y === ay && iso <= asOf;
  return true;
}
