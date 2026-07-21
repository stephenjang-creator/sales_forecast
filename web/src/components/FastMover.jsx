import { useState } from "react";
import { MONO } from "../tokens.js";

export default function FastMover({ fastMover, onOpen }) {
  const [hover, setHover] = useState(false);
  if (!fastMover) return null;
  return (
    <div
      onClick={() => onOpen(fastMover)}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        display: "flex",
        alignItems: "stretch",
        gap: 0,
        marginBottom: 24,
        background: "linear-gradient(90deg, oklch(0.97 0.04 155) 0%, #fff 60%)",
        border: `1px solid ${hover ? "oklch(0.78 0.09 155)" : "oklch(0.86 0.06 155)"}`,
        borderRadius: 12,
        overflow: "hidden",
        cursor: "pointer",
      }}
    >
      <div
        style={{
          width: 46,
          flexShrink: 0,
          background: "oklch(0.68 0.13 155)",
          color: "#fff",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontSize: 20,
        }}
      >
        ⚡
      </div>
      <div style={{ padding: "13px 18px", flex: 1, minWidth: 0 }}>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 10,
            flexWrap: "wrap",
            marginBottom: 4,
          }}
        >
          <span
            style={{
              fontSize: 10.5,
              fontWeight: 700,
              letterSpacing: "0.06em",
              textTransform: "uppercase",
              color: "oklch(0.45 0.13 155)",
            }}
          >
            Fast mover — act this week
          </span>
          <span style={{ fontSize: 14, fontWeight: 700, color: "oklch(0.2 0.014 262)" }}>
            {fastMover.account}
          </span>
          <span style={{ fontSize: 12, color: "oklch(0.5 0.012 260)", fontFamily: MONO }}>
            {fastMover.meta}
          </span>
        </div>
        <div style={{ fontSize: 13, lineHeight: 1.5, color: "oklch(0.32 0.012 260)" }}>
          {fastMover.line}
        </div>
        <div
          style={{ fontSize: 12.5, lineHeight: 1.5, color: "oklch(0.5 0.012 260)", marginTop: 3 }}
        >
          {fastMover.note}
        </div>
      </div>
      <div style={{ display: "flex", alignItems: "center", paddingRight: 16, flexShrink: 0 }}>
        <span style={{ fontSize: 12.5, fontWeight: 600, color: "oklch(0.42 0.1 155)" }}>
          Open deal →
        </span>
      </div>
    </div>
  );
}
