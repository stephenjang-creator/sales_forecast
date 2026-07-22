import { useState } from "react";
import { ACCENT, C, SHADOW } from "../tokens.js";

const SUGGESTIONS = [
  "Which deals should I chase first?",
  "Why is exposure so concentrated?",
  "How do I rescue our biggest at-risk deal?",
  "How much Commit is at risk this quarter?",
];

export default function AgentBar({
  query,
  setQuery,
  result,
  loading,
  onAsk,
  onClear,
  apiKey = "",
  setApiKey = () => {},
  serverHasKey = false,
}) {
  const [hoverChip, setHoverChip] = useState(-1);
  const [keyOpen, setKeyOpen] = useState(false);
  const [draft, setDraft] = useState("");

  const usingKey = !!apiKey.trim();
  const fullMode = usingKey || serverHasKey;
  const sourceLabel =
    result?.source === "llm" ? "answered by AI" : result ? "deterministic answer" : "";

  const openKey = () => {
    setDraft(apiKey);
    setKeyOpen(true);
  };
  const saveKey = () => {
    setApiKey(draft.trim());
    setKeyOpen(false);
  };
  const clearKey = () => {
    setApiKey("");
    setDraft("");
    setKeyOpen(false);
  };

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
            <span style={{ fontSize: 11.5, color: C.faint }}>routed automatically · {sourceLabel}</span>
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
          {result.note && (
            <p style={{ margin: "8px 0 0", fontSize: 12, color: C.warning }}>{result.note}</p>
          )}
        </div>
      )}

      <div style={{ display: "flex", flexWrap: "wrap", gap: 6, padding: "4px 10px 8px" }}>
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

      {/* Mode footer: demo (deterministic) vs full AI (server key or bring-your-own). */}
      <div
        style={{
          borderTop: `1px solid ${C.hairline}`,
          padding: "9px 12px",
          display: "flex",
          alignItems: "center",
          gap: 10,
          flexWrap: "wrap",
        }}
      >
        <span
          aria-hidden="true"
          style={{
            width: 8,
            height: 8,
            borderRadius: "50%",
            background: fullMode ? C.positive : "oklch(0.75 0.01 260)",
            flexShrink: 0,
          }}
        />
        <span style={{ fontSize: 12, color: fullMode ? C.positive : C.muted, fontWeight: 500 }}>
          {usingKey
            ? "Full AI mode · your Anthropic key (not saved)"
            : serverHasKey
              ? "Full AI mode · LLM answers enabled"
              : "Demo mode · deterministic answers"}
        </span>

        {!keyOpen && (
          <div style={{ marginLeft: "auto", display: "flex", gap: 12 }}>
            {usingKey ? (
              <>
                <FooterLink onClick={openKey}>Change key</FooterLink>
                <FooterLink onClick={clearKey}>Clear</FooterLink>
              </>
            ) : (
              <FooterLink onClick={openKey}>
                {serverHasKey ? "Use your own key" : "Use your Anthropic key for full AI answers"}
              </FooterLink>
            )}
          </div>
        )}
      </div>

      {keyOpen && (
        <div style={{ padding: "0 12px 12px", display: "flex", flexDirection: "column", gap: 8 }}>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <input
              type="password"
              value={draft}
              autoComplete="off"
              spellCheck={false}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && saveKey()}
              placeholder="sk-ant-…  (your Anthropic API key)"
              style={{
                flex: 1,
                minWidth: 240,
                height: 34,
                padding: "0 12px",
                borderRadius: 8,
                border: `1px solid ${C.border}`,
                outline: "none",
                fontSize: 13,
                fontFamily: "inherit",
                color: "oklch(0.24 0.012 260)",
              }}
            />
            <button onClick={saveKey} style={btn(ACCENT, "#fff")}>
              Enable
            </button>
            <button onClick={() => setKeyOpen(false)} style={btn("#fff", "oklch(0.4 0.012 260)", true)}>
              Cancel
            </button>
          </div>
          <p style={{ margin: 0, fontSize: 11.5, lineHeight: 1.5, color: C.faint }}>
            🔒 Kept in your browser for this session only. It's sent over HTTPS with each
            question, used once to answer, and <strong>never stored or logged</strong> on the
            server. Refreshing the page clears it. Get a key at{" "}
            <span style={{ fontFamily: "monospace" }}>console.anthropic.com</span>.
          </p>
        </div>
      )}
    </div>
  );
}

function FooterLink({ onClick, children }) {
  return (
    <button
      onClick={onClick}
      style={{
        border: "none",
        background: "transparent",
        color: ACCENT,
        cursor: "pointer",
        fontSize: 12,
        fontWeight: 600,
        fontFamily: "inherit",
        padding: 0,
      }}
    >
      {children}
    </button>
  );
}

function btn(bg, fg, bordered) {
  return {
    height: 34,
    padding: "0 14px",
    borderRadius: 8,
    border: bordered ? `1px solid ${C.border}` : "none",
    background: bg,
    color: fg,
    fontSize: 13,
    fontWeight: 600,
    cursor: "pointer",
    fontFamily: "inherit",
    flexShrink: 0,
  };
}
