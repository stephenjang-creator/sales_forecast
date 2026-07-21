import { ACCENT, C, KPI_TONE, MONO } from "../tokens.js";

export default function Summary({ narrative, kpis }) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "stretch",
        gap: 14,
        marginBottom: 24,
        flexWrap: "wrap",
      }}
    >
      <div
        style={{
          flex: 1,
          minWidth: 340,
          background: "#fff",
          border: `1px solid ${C.border}`,
          borderLeft: `3px solid ${ACCENT}`,
          borderRadius: 12,
          padding: "16px 18px",
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
        }}
      >
        <div
          style={{
            fontSize: 10.5,
            fontWeight: 600,
            letterSpacing: "0.05em",
            textTransform: "uppercase",
            color: ACCENT,
            marginBottom: 7,
          }}
        >
          AI summary
        </div>
        <p
          style={{
            margin: 0,
            fontSize: 15.5,
            lineHeight: 1.5,
            color: "oklch(0.28 0.014 262)",
            fontWeight: 500,
          }}
        >
          {narrative}
        </p>
      </div>
      {kpis.map((k) => (
        <div
          key={k.label}
          style={{
            width: 178,
            background: "#fff",
            border: `1px solid ${C.border}`,
            borderRadius: 12,
            padding: "15px 16px",
          }}
        >
          <div style={{ fontSize: 11, fontWeight: 500, color: C.muted, marginBottom: 8 }}>
            {k.label}
          </div>
          <div
            style={{
              fontSize: 26,
              fontWeight: 700,
              letterSpacing: "-0.02em",
              color: C.text,
              fontFamily: MONO,
              lineHeight: 1,
            }}
          >
            {k.value}
          </div>
          <div style={{ fontSize: 11.5, color: KPI_TONE[k.tone] || C.muted, marginTop: 7 }}>
            {k.sub}
          </div>
        </div>
      ))}
    </div>
  );
}
