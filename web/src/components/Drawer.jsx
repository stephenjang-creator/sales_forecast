import { ACCENT, C, MONO, SHADOW, tierColors, tierOf } from "../tokens.js";

export default function Drawer({ deal, onClose, onAsk }) {
  const open = !!deal;
  const tc = deal ? tierColors(deal.risk) : {};
  const facts = deal
    ? [
        { k: "Region", v: deal.region },
        { k: "Segment", v: deal.segment },
        { k: "Industry", v: deal.industry },
        { k: "Stage", v: deal.stage },
        { k: "Opportunity owner", v: deal.owner },
        { k: "Sales manager", v: deal.manager },
        { k: "Close date", v: deal.closeDate || "—" },
        { k: "Next meeting", v: deal.nextMeeting || "None booked" },
      ]
    : [];

  return (
    <>
      <div
        onClick={onClose}
        style={{
          position: "fixed",
          inset: 0,
          zIndex: 55,
          background: open ? "oklch(0.3 0.02 260 / 0.28)" : "oklch(0.3 0.02 260 / 0)",
          pointerEvents: open ? "auto" : "none",
          transition: "background .28s",
        }}
      />
      <div
        style={{
          position: "fixed",
          top: 0,
          right: 0,
          height: "100vh",
          width: "min(460px, 92vw)",
          zIndex: 60,
          transform: open ? "translateX(0)" : "translateX(100%)",
          transition: "transform .28s cubic-bezier(.4,0,.2,1)",
          background: "#fff",
          borderLeft: `1px solid ${C.border}`,
          boxShadow: SHADOW.drawer,
          overflowY: "auto",
        }}
      >
        {deal && (
          <div style={{ padding: "22px 24px 32px" }}>
            <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 12, marginBottom: 18 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 11 }}>
                <div
                  style={{
                    minWidth: 34,
                    height: 32,
                    padding: "0 9px",
                    borderRadius: 8,
                    background: tc.chipBg,
                    color: tc.chipFg,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    fontWeight: 700,
                    fontSize: 16,
                    fontFamily: MONO,
                  }}
                >
                  {deal.risk}
                </div>
                <div>
                  <div style={{ fontSize: 17, fontWeight: 700, letterSpacing: "-0.01em", color: "oklch(0.2 0.014 262)" }}>
                    {deal.account}
                  </div>
                  <div style={{ fontSize: 11.5, color: "oklch(0.58 0.01 260)", fontFamily: MONO, marginTop: 2 }}>
                    {deal.id} · {deal.region} · {tierOf(deal.risk)} risk
                  </div>
                </div>
              </div>
              <button
                onClick={onClose}
                style={{ width: 30, height: 30, flexShrink: 0, border: `1px solid ${C.border}`, background: "#fff", borderRadius: 8, cursor: "pointer", fontSize: 16, lineHeight: 1, color: C.muted }}
              >
                ×
              </button>
            </div>

            <div style={{ display: "flex", gap: 8, marginBottom: 22 }}>
              <TopTile label="Forecasted ARR" value={deal.amountStr} mono />
              <div style={{ flex: 1, background: "oklch(0.975 0.003 260)", border: `1px solid ${C.borderSoft}`, borderRadius: 10, padding: "11px 13px" }}>
                <div style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: "0.04em", color: "oklch(0.58 0.01 260)", marginBottom: 6 }}>
                  Forecast category
                </div>
                <ForecastBadge fc={deal.fc} />
              </div>
            </div>

            <SectionLabel>Flagged issues &amp; recommended steps</SectionLabel>
            <div style={{ display: "flex", flexDirection: "column", gap: 12, marginBottom: 24 }}>
              {deal.rules.map((r) => (
                <div key={r.id} style={{ border: `1px solid ${C.border}`, borderRadius: 10, overflow: "hidden" }}>
                  <div style={{ padding: "11px 13px", background: C.headerBg }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                      <div style={{ width: 7, height: 7, borderRadius: "50%", background: tc.band, flexShrink: 0 }} />
                      <div style={{ fontSize: 13, fontWeight: 600, color: "oklch(0.26 0.012 260)" }}>{r.label}</div>
                    </div>
                    <div style={{ fontSize: 12, lineHeight: 1.45, color: "oklch(0.48 0.012 260)", fontFamily: MONO, paddingLeft: 15 }}>
                      {r.reason}
                    </div>
                  </div>
                  <div style={{ padding: "10px 13px 10px 28px", borderTop: `1px solid ${C.borderSoft}` }}>
                    <div style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: "0.04em", color: ACCENT, fontWeight: 600, marginBottom: 3 }}>
                      Recommended step
                    </div>
                    <div style={{ fontSize: 12.5, lineHeight: 1.45, color: "oklch(0.32 0.014 262)" }}>{r.action}</div>
                  </div>
                </div>
              ))}
            </div>

            <SectionLabel>Deal facts</SectionLabel>
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "1fr 1fr",
                gap: 1,
                background: C.borderSoft,
                border: `1px solid ${C.borderSoft}`,
                borderRadius: 10,
                overflow: "hidden",
                marginBottom: 24,
              }}
            >
              {facts.map((f) => (
                <div key={f.k} style={{ background: "#fff", padding: "10px 13px" }}>
                  <div style={{ fontSize: 10.5, color: "oklch(0.58 0.01 260)", marginBottom: 3 }}>{f.k}</div>
                  <div style={{ fontSize: 13, fontWeight: 500, color: "oklch(0.28 0.012 260)" }}>{f.v}</div>
                </div>
              ))}
            </div>

            <div style={{ display: "flex", gap: 8 }}>
              <button
                onClick={() => onAsk(deal)}
                style={{ flex: 1, height: 38, border: "none", borderRadius: 9, background: ACCENT, color: "#fff", fontSize: 13, fontWeight: 600, cursor: "pointer", fontFamily: "inherit" }}
              >
                Ask Deal Rescue Planner
              </button>
              <button
                onClick={onClose}
                style={{ height: 38, padding: "0 16px", border: `1px solid ${C.border}`, borderRadius: 9, background: "#fff", color: "oklch(0.4 0.012 260)", fontSize: 13, fontWeight: 500, cursor: "pointer", fontFamily: "inherit" }}
              >
                Close
              </button>
            </div>
          </div>
        )}
      </div>
    </>
  );
}

function SectionLabel({ children }) {
  return (
    <div style={{ fontSize: 11, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.04em", color: C.muted, marginBottom: 12 }}>
      {children}
    </div>
  );
}

function TopTile({ label, value, mono }) {
  return (
    <div style={{ flex: 1, background: "oklch(0.975 0.003 260)", border: `1px solid ${C.borderSoft}`, borderRadius: 10, padding: "11px 13px" }}>
      <div style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: "0.04em", color: "oklch(0.58 0.01 260)", marginBottom: 4 }}>
        {label}
      </div>
      <div style={{ fontSize: 19, fontWeight: 700, fontFamily: mono ? MONO : "inherit", color: C.text }}>{value}</div>
    </div>
  );
}

function ForecastBadge({ fc }) {
  const commit = fc === "Commit";
  return (
    <span
      style={{
        fontSize: 11,
        fontWeight: 600,
        padding: "3px 9px",
        borderRadius: 6,
        background: commit ? "oklch(0.3 0.014 262)" : "oklch(0.95 0.004 260)",
        color: commit ? "#fff" : "oklch(0.45 0.012 260)",
        border: commit ? "none" : `1px solid ${C.border}`,
      }}
    >
      {fc}
    </span>
  );
}
