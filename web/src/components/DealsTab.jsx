import { useRef } from "react";
import { ACCENT, C, MONO, tierColors, tierOf } from "../tokens.js";

const GRID = "74px minmax(170px,1.5fr) 136px 118px 116px 100px 112px";
const TIERS = ["Critical", "High", "Medium", "Low"];
const SEGMENTS = ["Enterprise", "Mid-Market", "SMB"];

function Pill({ label, active, onClick }) {
  return (
    <button
      onClick={onClick}
      style={{
        height: 28,
        padding: "0 12px",
        borderRadius: 20,
        fontSize: 12,
        fontWeight: 500,
        fontFamily: "inherit",
        cursor: "pointer",
        transition: "all .12s",
        border: `1px solid ${active ? ACCENT : C.border}`,
        background: active ? ACCENT : "#fff",
        color: active ? "#fff" : "oklch(0.45 0.012 260)",
      }}
    >
      {label}
    </button>
  );
}

function FilterGroup({ label, values, active, toggle }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
      <span
        style={{
          fontSize: 11,
          fontWeight: 600,
          letterSpacing: "0.03em",
          textTransform: "uppercase",
          color: C.muted,
        }}
      >
        {label}
      </span>
      {values.map((v) => (
        <Pill key={v} label={v} active={active.includes(v)} onClick={() => toggle(v)} />
      ))}
    </div>
  );
}

function Divider() {
  return <div style={{ width: 1, height: 22, background: C.border }} />;
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

function DealRow({ deal, onOpen, onHover, onLeave }) {
  const ref = useRef(null);
  const tc = tierColors(deal.risk);
  const enter = () => ref.current && onHover(deal, ref.current.getBoundingClientRect());
  return (
    <div
      ref={ref}
      onClick={() => onOpen(deal)}
      style={{
        display: "grid",
        gridTemplateColumns: GRID,
        alignItems: "center",
        padding: "11px 16px",
        borderBottom: `1px solid ${C.hairline}`,
        cursor: "pointer",
        transition: "background .1s",
      }}
      onMouseOver={(e) => (e.currentTarget.style.background = "oklch(0.99 0.002 260)")}
      onMouseOut={(e) => (e.currentTarget.style.background = "transparent")}
    >
      <div
        onMouseEnter={enter}
        onMouseLeave={onLeave}
        style={{ display: "inline-flex", alignItems: "center", gap: 9, cursor: "help", width: "fit-content" }}
      >
        <div style={{ width: 4, height: 28, borderRadius: 3, background: tc.band }} />
        <div
          style={{
            minWidth: 30,
            height: 26,
            padding: "0 7px",
            borderRadius: 7,
            background: tc.chipBg,
            color: tc.chipFg,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontWeight: 700,
            fontSize: 13,
            fontFamily: MONO,
          }}
        >
          {deal.risk}
        </div>
      </div>
      <div style={{ minWidth: 0 }}>
        <div
          onMouseEnter={enter}
          onMouseLeave={onLeave}
          style={{ display: "inline-block", cursor: "help" }}
        >
          <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
            <span
              style={{
                fontSize: 13.5,
                fontWeight: 600,
                color: C.text2,
                whiteSpace: "nowrap",
                overflow: "hidden",
                textOverflow: "ellipsis",
              }}
            >
              {deal.account}
            </span>
            <span style={{ fontSize: 12, fontWeight: 500, color: "oklch(0.5 0.012 260)", fontFamily: MONO, flexShrink: 0 }}>
              {deal.mrrStr}
            </span>
          </div>
          <div style={{ fontSize: 11, color: C.faint, fontFamily: MONO, marginTop: 1 }}>
            {deal.id} · {tierOf(deal.risk)}
          </div>
        </div>
      </div>
      <Cell text={deal.owner} />
      <Cell text={deal.manager} />
      <div style={{ fontSize: 12.5, color: C.cell }}>{deal.stage}</div>
      <div>
        <ForecastBadge fc={deal.fc} />
      </div>
      <div style={{ textAlign: "right", fontSize: 13.5, fontWeight: 600, color: "oklch(0.26 0.014 262)", fontFamily: MONO }}>
        {deal.amountStr}
      </div>
    </div>
  );
}

function Cell({ text }) {
  return (
    <div
      style={{
        fontSize: 12.5,
        color: C.cell,
        whiteSpace: "nowrap",
        overflow: "hidden",
        textOverflow: "ellipsis",
        paddingRight: 10,
      }}
    >
      {text}
    </div>
  );
}

function HeaderRow() {
  const cell = {
    fontSize: 10.5,
    fontWeight: 600,
    letterSpacing: "0.04em",
    textTransform: "uppercase",
    color: C.muted,
  };
  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: GRID,
        alignItems: "center",
        padding: "9px 16px",
        background: C.headerBg,
        borderBottom: `1px solid ${C.borderSoft}`,
      }}
    >
      <div style={cell}>Risk</div>
      <div style={cell}>Account</div>
      <div style={cell}>Opportunity owner</div>
      <div style={cell}>Sales manager</div>
      <div style={cell}>Stage</div>
      <div style={cell}>Forecast</div>
      <div style={{ ...cell, textAlign: "right" }}>ARR</div>
    </div>
  );
}

function money(n) {
  return n >= 1e6 ? `$${(n / 1e6).toFixed(2)}M` : `$${Math.round(n / 1000)}k`;
}

export default function DealsTab({ deals, regionOrder, filters, setFilters, onOpen, onHover, onLeave }) {
  const toggle = (key, val) =>
    setFilters((f) => ({
      ...f,
      [key]: f[key].includes(val) ? f[key].filter((x) => x !== val) : f[key].concat(val),
    }));

  const shown = deals.filter(
    (d) =>
      (filters.tiers.length === 0 || filters.tiers.includes(tierOf(d.risk))) &&
      (filters.regions.length === 0 || filters.regions.includes(d.region)) &&
      (filters.segments.length === 0 || filters.segments.includes(d.segment))
  );

  const groups = regionOrder
    .map((region) => {
      const rows = shown.filter((d) => d.region === region);
      const atRisk = rows.reduce((s, d) => s + d.arr, 0);
      return { region, rows, atRisk };
    })
    .filter((g) => g.rows.length > 0);

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", gap: 18, flexWrap: "wrap", marginBottom: 18 }}>
        <FilterGroup label="Risk" values={TIERS} active={filters.tiers} toggle={(v) => toggle("tiers", v)} />
        <Divider />
        <FilterGroup label="Region" values={regionOrder} active={filters.regions} toggle={(v) => toggle("regions", v)} />
        <Divider />
        <FilterGroup label="Segment" values={SEGMENTS} active={filters.segments} toggle={(v) => toggle("segments", v)} />
        <div style={{ marginLeft: "auto", fontSize: 12.5, color: C.muted }}>
          {shown.length} of {deals.length} flagged deals
        </div>
      </div>

      {groups.map((g) => (
        <div key={g.region} style={{ marginBottom: 22 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "0 4px 9px" }}>
            <span style={{ fontSize: 13, fontWeight: 700, letterSpacing: "0.02em", color: C.text }}>
              {g.region}
            </span>
            <span
              style={{
                fontSize: 11.5,
                fontWeight: 500,
                color: C.muted,
                background: "oklch(0.95 0.004 260)",
                padding: "2px 9px",
                borderRadius: 20,
              }}
            >
              {g.rows.length} deals
            </span>
            <span style={{ fontSize: 12, color: "oklch(0.5 0.012 260)" }}>
              {money(g.atRisk)} forecasted at risk
            </span>
          </div>
          <div style={{ background: "#fff", border: `1px solid ${C.border}`, borderRadius: 12, overflow: "hidden" }}>
            <HeaderRow />
            {g.rows.map((d) => (
              <DealRow key={d.id} deal={d} onOpen={onOpen} onHover={onHover} onLeave={onLeave} />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
