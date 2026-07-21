import { useState } from "react";
import { ACCENT, C, SHADOW } from "../tokens.js";

const SUGGESTIONS = [
  "Which deals should I chase first?",
  "Why is exposure so concentrated?",
  "How do I rescue our biggest at-risk deal?",
  "How much Commit is at risk this quarter?",
];

export default function AgentBar({ query, setQuery, result, loading, onAsk, onClear }) {
  const [hoverChip, setHoverChip] = useState(-1);
  return (
    <div
      style={{
        background: "#fff",
        border: `1px solid ${C.border}`,
        borderRadius: 14,
        padding: 6,
        boxShadow: SHADOW.card,
        marginBottom: 22,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "8px 10px" }}>
        <div
          style={{
            width: 30,
            height: 30,
            flexShrink: 0,
            borderRadius: 8,
            background: C.accentTint,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            color: ACCENT,
            fontSize: 15,
          }}
        >
          ✦
        </div>
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && onAsk(query)}
          placeholder="Ask anything about the forecast — I'll route it to the right agent…"
          style={{
            flex: 1,
            border: "none",
            outline: "none",
            fontSize: 15,
            fontFamily: "inherit",
            background: "transparent",
            color: "oklch(0.24 0.012 260)",
          }}
        />
        <button
          onClick={() => onAsk(query)}
          disabled={loading}
          style={{
            height: 32,
            minWidth: 78,
            padding: "0 16px",
            borderRadius: 8,
            border: "none",
            background: ACCENT,
            color: "#fff",
            fontSize: 13,
            fontWeight: 600,
            cursor: loading ? "default" : "pointer",
            opacity: loading ? 0.85 : 1,
            fontFamily: "inherit",
            flexShrink: 0,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            gap: 7,
          }}
        >
          {loading ? (
            <>
              <span
                aria-hidden="true"
                style={{
                  width: 13,
                  height: 13,
                  borderRadius: "50%",
                  border: "2px solid rgba(255,255,255,0.4)",
                  borderTopColor: "#fff",
                  animation: "spin 0.6s linear infinite",
                }}
              />
              Thinking
            </>
          ) : (
            "Ask"
          )}
        </button>
      </div>

      {result && (
        <div
          style={{
            margin: "2px 8px 8px",
            padding: "14px 16px",
            borderRadius: 10,
            background: C.accentTintSoft,
            border: "1px solid oklch(0.92 0.02 264)",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
            <span
              style={{
                fontSize: 10.5,
                fontWeight: 600,
                letterSpacing: "0.04em",
                textTransform: "uppercase",
                color: ACCENT,
                background: C.accentPill,
                padding: "3px 9px",
                borderRadius: 20,
              }}
            >
              → {result.agent}
            </span>
            <span style={{ fontSize: 11.5, color: C.faint }}>routed automatically</span>
            <button
              onClick={onClear}
              style={{
                marginLeft: "auto",
                border: "none",
                background: "transparent",
                color: C.faint,
                cursor: "pointer",
                fontSize: 15,
                lineHeight: 1,
              }}
            >
              ×
            </button>
          </div>
          <p style={{ margin: 0, fontSize: 14, lineHeight: 1.55, color: "oklch(0.3 0.012 260)" }}>
            {result.text}
          </p>
        </div>
      )}

      <div style={{ display: "flex", flexWrap: "wrap", gap: 6, padding: "4px 10px 10px" }}>
        {SUGGESTIONS.map((s, i) => (
          <button
            key={s}
            onClick={() => onAsk(s)}
            onMouseEnter={() => setHoverChip(i)}
            onMouseLeave={() => setHoverChip(-1)}
            style={{
              border: `1px solid ${hoverChip === i ? "oklch(0.82 0.02 264)" : "oklch(0.92 0.006 260)"}`,
              background: "oklch(0.99 0.002 260)",
              color: hoverChip === i ? ACCENT : "oklch(0.45 0.012 260)",
              fontSize: 12,
              fontFamily: "inherit",
              padding: "5px 11px",
              borderRadius: 20,
              cursor: "pointer",
              transition: "all .12s",
            }}
          >
            {s}
          </button>
        ))}
      </div>
    </div>
  );
}
