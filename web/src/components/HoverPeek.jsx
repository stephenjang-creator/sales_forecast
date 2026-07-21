import { ACCENT, C, MONO, SHADOW, tierColors, tierOf } from "../tokens.js";

// Anchored to the row rect: default to the right of the row, flip left on
// overflow, clamp vertically. Computed by the parent; here we just position.
export function peekPosition(rect) {
  const W = 372;
  const GAP = 14;
  let left = rect.right + GAP;
  if (left + W > window.innerWidth - 12) left = rect.left - W - GAP;
  if (left < 12) left = 12;
  let top = Math.min(rect.top, window.innerHeight - 360);
  top = Math.max(12, top);
  return { top, left };
}

export default function HoverPeek({ deal, pos }) {
  if (!deal) return null;
  const tc = tierColors(deal.risk);
  return (
    <div
      style={{
        position: "fixed",
        top: pos.top,
        left: pos.left,
        width: 372,
        zIndex: 50,
        background: "#fff",
        border: "1px solid oklch(0.88 0.006 260)",
        borderRadius: 14,
        padding: "16px 18px",
        boxShadow: SHADOW.popover,
        pointerEvents: "none",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 9, marginBottom: 12 }}>
        <Chip tc={tc} risk={deal.risk} />
        <div>
          <div style={{ fontSize: 14, fontWeight: 700, color: "oklch(0.2 0.014 262)" }}>{deal.account}</div>
          <div style={{ fontSize: 11, color: "oklch(0.58 0.01 260)", fontFamily: MONO }}>
            {deal.id} · {deal.region} · {tierOf(deal.risk)} risk
          </div>
        </div>
      </div>
      <div style={{ display: "flex", gap: 8, marginBottom: 13 }}>
        <Tile label="ARR at risk" value={deal.amountStr} mono />
        <Tile label="Forecast" value={deal.fc} />
      </div>
      <div style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: "0.04em", color: "oklch(0.58 0.01 260)", marginBottom: 7 }}>
        Flagged issues
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 8, marginBottom: 13 }}>
        {deal.rules.map((r) => (
          <div key={r.id} style={{ display: "flex", gap: 8, alignItems: "flex-start" }}>
            <div style={{ width: 6, height: 6, borderRadius: "50%", background: tc.band, marginTop: 6, flexShrink: 0 }} />
            <div>
              <div style={{ fontSize: 12.5, fontWeight: 600, color: "oklch(0.28 0.012 260)" }}>{r.label}</div>
              <div style={{ fontSize: 12, lineHeight: 1.45, color: "oklch(0.48 0.012 260)", fontFamily: MONO }}>
                {r.reason}
              </div>
            </div>
          </div>
        ))}
      </div>
      <div style={{ background: C.accentTint, border: "1px solid oklch(0.92 0.025 264)", borderRadius: 8, padding: "9px 11px" }}>
        <div style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: "0.04em", color: ACCENT, marginBottom: 4, fontWeight: 600 }}>
          Recommended next step
        </div>
        <div style={{ fontSize: 12.5, lineHeight: 1.45, color: "oklch(0.3 0.014 262)" }}>
          {deal.rules[0]?.action}
        </div>
      </div>
    </div>
  );
}

function Chip({ tc, risk }) {
  return (
    <div
      style={{
        minWidth: 30,
        height: 28,
        padding: "0 8px",
        borderRadius: 7,
        background: tc.chipBg,
        color: tc.chipFg,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        fontWeight: 700,
        fontSize: 14,
        fontFamily: MONO,
      }}
    >
      {risk}
    </div>
  );
}

function Tile({ label, value, mono }) {
  return (
    <div style={{ flex: 1, background: "oklch(0.97 0.003 260)", borderRadius: 8, padding: "8px 10px" }}>
      <div style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: "0.04em", color: "oklch(0.58 0.01 260)", marginBottom: 3 }}>
        {label}
      </div>
      <div style={{ fontSize: 15, fontWeight: 700, fontFamily: mono ? MONO : "inherit", color: "oklch(0.24 0.014 262)" }}>
        {value}
      </div>
    </div>
  );
}
