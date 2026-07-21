import { ACCENT, C, MONO } from "../tokens.js";
import { TIMEFRAMES } from "../time.js";

// Segmented control (This month / This quarter / Year to date). Scopes booked
// figures only. Active button = white + shadow + dark 600; inactive = muted 500.
function TimeframeControl({ timeframe, onTimeframe }) {
  return (
    <div
      title="Scopes booked (Closed Won) figures — the open pipeline is unaffected"
      style={{
        display: "flex",
        gap: 3,
        padding: 3,
        borderRadius: 9,
        background: "oklch(0.95 0.004 260)",
      }}
    >
      {TIMEFRAMES.map((t) => {
        const active = timeframe === t.key;
        return (
          <button
            key={t.key}
            onClick={() => onTimeframe(t.key)}
            style={{
              height: 30,
              padding: "0 11px",
              borderRadius: 7,
              border: "none",
              fontFamily: "inherit",
              fontSize: 12,
              fontWeight: active ? 600 : 500,
              cursor: "pointer",
              background: active ? "#fff" : "transparent",
              color: active ? C.text : C.muted,
              boxShadow: active ? "0 1px 2px oklch(0.5 0.02 260 / 0.12)" : "none",
            }}
          >
            {t.label}
          </button>
        );
      })}
    </div>
  );
}

export default function Header({ onExport, onShare, timeframe, onTimeframe }) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "flex-start",
        justifyContent: "space-between",
        gap: 24,
        marginBottom: 22,
      }}
    >
      <div>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <div
            style={{
              width: 26,
              height: 26,
              borderRadius: 7,
              background: ACCENT,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              color: "#fff",
              fontWeight: 700,
              fontSize: 14,
              fontFamily: MONO,
            }}
          >
            ◆
          </div>
          <h1
            style={{
              fontSize: 21,
              fontWeight: 700,
              letterSpacing: "-0.02em",
              margin: 0,
              color: C.text,
            }}
          >
            Intelligent Forecast
          </h1>
        </div>
        <p
          style={{
            margin: "7px 0 0 36px",
            fontSize: 13,
            color: C.muted,
            maxWidth: 640,
            lineHeight: 1.5,
          }}
        >
          Deterministic MEDDPICC &amp; pipeline-hygiene rules flag every deal. The model only
          explains and routes — every number is auditable. Data is synthetic.
        </p>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 10, flexShrink: 0 }}>
        <TimeframeControl timeframe={timeframe} onTimeframe={onTimeframe} />
        <button onClick={onExport} style={btn.outline}>
          Export CSV
        </button>
        <button onClick={onShare} style={btn.filled}>
          Share brief
        </button>
      </div>
    </div>
  );
}

const btn = {
  outline: {
    height: 34,
    padding: "0 14px",
    borderRadius: 8,
    border: `1px solid ${C.border}`,
    background: "#fff",
    fontSize: 12.5,
    fontWeight: 500,
    color: "oklch(0.4 0.012 260)",
    cursor: "pointer",
    fontFamily: "inherit",
  },
  filled: {
    height: 34,
    padding: "0 14px",
    borderRadius: 8,
    border: "1px solid transparent",
    background: ACCENT,
    fontSize: 12.5,
    fontWeight: 600,
    color: "#fff",
    cursor: "pointer",
    fontFamily: "inherit",
  },
};
