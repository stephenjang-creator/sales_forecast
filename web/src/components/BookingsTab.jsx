import { useState } from "react";
import { C, MONO } from "../tokens.js";

function money(n) {
  n = Number(n || 0);
  return n >= 1e6 ? `$${(n / 1e6).toFixed(2)}M` : `$${Math.round(n / 1000)}k`;
}

const UP = "oklch(0.55 0.14 155)";
const DOWN = "oklch(0.58 0.17 25)";

function Delta({ pct }) {
  if (pct === null || pct === undefined)
    return <span style={{ fontSize: 12, color: C.faint }}>—</span>;
  const up = pct >= 0;
  return (
    <span style={{ fontSize: 13, fontWeight: 600, color: up ? UP : DOWN }}>
      {up ? "▲" : "▼"} {Math.abs(pct).toFixed(1)}%
    </span>
  );
}

function StatCard({ label, value, pct, prior }) {
  return (
    <div
      style={{
        flex: 1,
        minWidth: 180,
        background: "#fff",
        border: `1px solid ${C.border}`,
        borderRadius: 12,
        padding: "15px 17px",
      }}
    >
      <div style={{ fontSize: 11, fontWeight: 500, color: C.muted, marginBottom: 9 }}>{label}</div>
      <div
        style={{
          fontSize: 25,
          fontWeight: 700,
          letterSpacing: "-0.02em",
          color: C.text,
          fontFamily: MONO,
          lineHeight: 1,
        }}
      >
        {value}
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 9 }}>
        <Delta pct={pct} />
        <span style={{ fontSize: 11.5, color: C.faint }}>{prior}</span>
      </div>
    </div>
  );
}

const GRAINS = [
  { key: "month", label: "Monthly" },
  { key: "quarter", label: "Quarterly" },
  { key: "year", label: "Yearly" },
];

function Chart({ series }) {
  const max = Math.max(1, ...series.map((s) => s.booked));
  const current = series.length ? series[series.length - 1].period : null;
  return (
    <div style={{ background: "#fff", border: `1px solid ${C.border}`, borderRadius: 12, padding: "20px 18px 14px" }}>
      <div style={{ display: "flex", alignItems: "flex-end", gap: 10, height: 200, overflowX: "auto", paddingBottom: 4 }}>
        {series.map((s) => {
          const h = Math.max(3, Math.round((s.booked / max) * 168));
          const isCurrent = s.period === current;
          return (
            <div
              key={s.period}
              title={`${s.period}: ${money(s.booked)} · ${s.deals} deals`}
              style={{ flex: "1 0 46px", display: "flex", flexDirection: "column", alignItems: "center", gap: 6 }}
            >
              <div style={{ fontSize: 10.5, fontWeight: 600, color: C.cell, fontFamily: MONO }}>
                {money(s.booked)}
              </div>
              <div
                style={{
                  width: "100%",
                  maxWidth: 54,
                  height: h,
                  borderRadius: "5px 5px 0 0",
                  background: isCurrent ? C.closedBg : "oklch(0.72 0.13 155)",
                  border: isCurrent ? `1px dashed ${C.closedBorder}` : "none",
                }}
              />
              <div style={{ fontSize: 10.5, color: C.muted, fontFamily: MONO, whiteSpace: "nowrap" }}>
                {s.period}
              </div>
            </div>
          );
        })}
      </div>
      <div style={{ fontSize: 11, color: C.faint, marginTop: 10 }}>
        Booked (Closed Won) by period. The most recent period is in progress (dashed).
      </div>
    </div>
  );
}

export default function BookingsTab({ bookings }) {
  const [grain, setGrain] = useState("quarter");
  if (!bookings) return <div style={{ color: C.muted, fontSize: 13 }}>No bookings data.</div>;
  const { ytd, yoy, qoq, mom, series } = bookings;

  return (
    <div>
      <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginBottom: 18 }}>
        <StatCard label="Booked YTD" value={money(ytd.booked)} pct={ytd.pct} prior={`vs ${money(ytd.priorBooked)} last YTD`} />
        <StatCard label={`YoY · ${yoy.period}`} value={money(yoy.booked)} pct={yoy.pct} prior={`vs ${money(yoy.priorBooked)} in ${yoy.priorPeriod}`} />
        <StatCard label={`QoQ · ${qoq.period}`} value={money(qoq.booked)} pct={qoq.pct} prior={`vs ${money(qoq.priorBooked)} in ${qoq.priorPeriod}`} />
        <StatCard label={`MoM · ${mom.period}`} value={money(mom.booked)} pct={mom.pct} prior={`vs ${money(mom.priorBooked)} in ${mom.priorPeriod}`} />
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 14 }}>
        <span style={{ fontSize: 13, fontWeight: 600, color: C.text }}>Bookings trend</span>
        <div style={{ display: "flex", gap: 4, marginLeft: "auto" }}>
          {GRAINS.map((g) => (
            <button
              key={g.key}
              onClick={() => setGrain(g.key)}
              style={{
                height: 28,
                padding: "0 12px",
                borderRadius: 8,
                fontSize: 12,
                fontWeight: 500,
                fontFamily: "inherit",
                cursor: "pointer",
                border: `1px solid ${grain === g.key ? "oklch(0.72 0.13 155)" : C.border}`,
                background: grain === g.key ? C.closedBg : "#fff",
                color: grain === g.key ? C.closedText : C.muted,
              }}
            >
              {g.label}
            </button>
          ))}
        </div>
      </div>

      <Chart series={series[grain]} />
    </div>
  );
}
