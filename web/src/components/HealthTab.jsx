import { C, MONO } from "../tokens.js";

const RULE_GRID = "minmax(220px,2fr) 1fr 1fr 90px 90px 90px";

export default function HealthTab({ scorecard }) {
  const { metrics, perRule } = scorecard;
  const num = (v, color) => ({
    textAlign: "right",
    fontFamily: MONO,
    fontSize: 13,
    color: color || "oklch(0.45 0.012 260)",
  });
  return (
    <div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 14, marginBottom: 22 }}>
        {metrics.map((m) => (
          <div key={m.label} style={{ background: "#fff", border: `1px solid ${C.border}`, borderRadius: 12, padding: "16px 18px" }}>
            <div style={{ fontSize: 11, fontWeight: 500, color: C.muted, marginBottom: 9 }}>{m.label}</div>
            <div style={{ fontSize: 30, fontWeight: 700, letterSpacing: "-0.02em", color: C.text, fontFamily: MONO, lineHeight: 1 }}>
              {m.value}
            </div>
          </div>
        ))}
      </div>
      <p style={{ fontSize: 12.5, color: C.muted, margin: "0 0 12px 2px" }}>
        Per-rule: when a rule fires, does the deal truly carry that anomaly (precision), and of the
        deals that do, how many did it catch (recall)?
      </p>
      <div style={{ background: "#fff", border: `1px solid ${C.border}`, borderRadius: 12, overflow: "hidden" }}>
        <div
          style={{
            display: "grid",
            gridTemplateColumns: RULE_GRID,
            padding: "10px 18px",
            background: C.headerBg,
            borderBottom: `1px solid ${C.borderSoft}`,
            fontSize: 10.5,
            fontWeight: 600,
            letterSpacing: "0.04em",
            textTransform: "uppercase",
            color: C.muted,
          }}
        >
          <div>rule_id</div>
          <div style={{ textAlign: "right" }}>precision</div>
          <div style={{ textAlign: "right" }}>recall</div>
          <div style={{ textAlign: "right" }}>fired</div>
          <div style={{ textAlign: "right" }}>labeled</div>
          <div style={{ textAlign: "right" }}>correct</div>
        </div>
        {perRule.map((r) => (
          <div
            key={r.id}
            style={{
              display: "grid",
              gridTemplateColumns: RULE_GRID,
              padding: "12px 18px",
              borderBottom: `1px solid ${C.hairline}`,
              alignItems: "center",
            }}
          >
            <div style={{ fontSize: 13, fontFamily: MONO, color: "oklch(0.3 0.012 260)" }}>{r.id}</div>
            <div style={num(r.precision, parseFloat(r.precision) < 0.6 ? C.warning : "oklch(0.3 0.012 260)")}>
              {r.precision}
            </div>
            <div style={num(r.recall, "oklch(0.3 0.012 260)")}>{r.recall}</div>
            <div style={num(r.fired)}>{r.fired}</div>
            <div style={num(r.labeled)}>{r.labeled}</div>
            <div style={num(r.correct)}>{r.correct}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
