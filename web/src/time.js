// Timeframe helpers for the header segmented control. The timeframe scopes the
// whole forecast by close date: booked (Closed Won) figures by their booking
// date, and open pipeline by its projected close date -- so you can project
// bookings + forecast for the period.
export const TIMEFRAMES = [
  { key: "month", label: "This month", short: "this month" },
  { key: "quarter", label: "This quarter", short: "this quarter" },
  { key: "year", label: "This year", short: "this year" },
];

export const tfLabel = (tf) => TIMEFRAMES.find((t) => t.key === tf)?.label ?? "";
export const tfShort = (tf) => TIMEFRAMES.find((t) => t.key === tf)?.short ?? "";

const quarterOf = (m) => Math.floor((m - 1) / 3) + 1;

// Is a close/booking date (ISO) inside the timeframe's calendar period, measured
// against the data's "as of" date? A period spans both sides of today: booked
// deals (past) and open deals projected to close later in the same period.
export function inTimeframe(iso, tf, asOf) {
  if (!iso || !asOf) return true;
  const ay = +asOf.slice(0, 4);
  const am = +asOf.slice(5, 7);
  const y = +iso.slice(0, 4);
  const m = +iso.slice(5, 7);
  if (tf === "month") return y === ay && m === am;
  if (tf === "quarter") return y === ay && quarterOf(m) === quarterOf(am);
  if (tf === "year") return y === ay;
  return true;
}

// Aggregate the server's per-month pipeline buckets into a single projection for
// the timeframe: booked (won so far), open pipeline projected to close, the
// risk-adjusted projection (booked + weighted open), and flagged-at-risk ARR.
export function sumPipeline(byMonth, tf, asOf) {
  const acc = { booked: 0, open: 0, projected: 0, atRisk: 0, openDeals: 0 };
  for (const b of byMonth || []) {
    if (!inTimeframe(`${b.period}-01`, tf, asOf)) continue;
    acc.booked += b.won_arr;
    acc.open += b.open_arr;
    acc.projected += b.won_arr + b.risk_adjusted_open_arr;
    acc.atRisk += b.flagged_open_arr;
    acc.openDeals += b.open_deals;
  }
  return acc;
}
