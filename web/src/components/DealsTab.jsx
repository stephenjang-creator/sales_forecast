import { useRef, useState } from "react";
import { ACCENT, C, MONO, tierColors, tierOf } from "../tokens.js";
import { inTimeframe } from "../time.js";

const GRID = "74px minmax(170px,1.5fr) 136px 118px 116px 100px 112px";
const TIERS = ["Critical", "High", "Medium", "Low"];
const SEGMENTS = ["Enterprise", "Mid-Market", "SMB"];

const FORECAST_INFO =
  "Forecast rollup, most-committed first — Closed (Won, booked) › Commit " +
  "(only at Negotiation) › Best Case (only at Proposal+) › Pipeline (in the funnel) " +
  "› Omitted (early or lost — left out of the number).";

// Columns, in table order. `key` maps into SORT_KEYS below; `align` right-aligns ARR.
const COLUMNS = [
  { key: "risk", label: "Risk", align: "left" },
  { key: "account", label: "Account", align: "left" },
  { key: "owner", label: "Opportunity owner", align: "left" },
  { key: "manager", label: "Sales manager", align: "left" },
  { key: "stage", label: "Stage", align: "left" },
  { key: "fc", label: "Forecast", align: "left", info: FORECAST_INFO },
  { key: "arr", label: "ARR", align: "right" },
];

// Each column's sort accessor + natural default direction. Stage/Forecast sort by
// the numeric rank the API attaches (funnel/confidence order), not alphabetically.
const SORT_KEYS = {
  risk: { get: (d) => d.risk, defaultDir: "desc" },
  account: { get: (d) => (d.account || "").toLowerCase(), defaultDir: "asc" },
  owner: { get: (d) => (d.owner || "").toLowerCase(), defaultDir: "asc" },
  manager: { get: (d) => (d.manager || "").toLowerCase(), defaultDir: "asc" },
  stage: { get: (d) => (d.stageRank ?? 99), defaultDir: "asc" },
  fc: { get: (d) => (d.fcRank ?? 99), defaultDir: "asc" },
  arr: { get: (d) => d.arr, defaultDir: "desc" },
};

function sortRows(rows, sort) {
  const { get } = SORT_KEYS[sort.col];
  const dir = sort.dir === "asc" ? 1 : -1;
  return [...rows].sort((a, b) => {
    const va = get(a);
    const vb = get(b);
    if (va < vb) return -dir;
    if (va > vb) return dir;
    return b.risk - a.risk || b.arr - a.arr; // stable tiebreak: riskiest/richest
  });
}

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

// Forecast badge, per the v2 ladder: Commit filled dark; Best Case / Pipeline
// gray-bordered; Omitted faint; Closed green.
function forecastStyle(fc) {
  if (fc === "Commit")
    return { background: "oklch(0.3 0.014 262)", color: "#fff", border: "none" };
  if (fc === "Closed")
    return { background: C.closedBadgeBg, color: C.closedBadgeFg, border: "none" };
  if (fc === "Omitted")
    return { background: C.omittedBg, color: C.omittedFg, border: `1px solid ${C.border}` };
  // Best Case + Pipeline
  return { background: "oklch(0.95 0.004 260)", color: "oklch(0.45 0.012 260)", border: `1px solid ${C.border}` };
}

function ForecastBadge({ fc }) {
  return (
    <span
      style={{ fontSize: 11, fontWeight: 600, padding: "3px 9px", borderRadius: 6, ...forecastStyle(fc) }}
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

// A booked Closed Won deal: light-green, ✓ instead of a risk score, no hover peek
// -- but it still opens the drawer (which shows the booked, no-action variant).
function ClosedRow({ deal, onOpen }) {
  return (
    <div
      onClick={() => onOpen(deal)}
      style={{
        display: "grid",
        gridTemplateColumns: GRID,
        alignItems: "center",
        padding: "11px 16px",
        borderBottom: `1px solid ${C.closedBorder}`,
        background: C.closedBg,
        cursor: "pointer",
      }}
    >
      <div style={{ display: "inline-flex", alignItems: "center", gap: 9, width: "fit-content" }}>
        <div style={{ width: 4, height: 28, borderRadius: 3, background: C.closedBand }} />
        <div
          title="Closed Won — booked, no risk"
          style={{
            minWidth: 30,
            height: 26,
            padding: "0 7px",
            borderRadius: 7,
            background: C.closedChipBg,
            color: C.closedChipFg,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontWeight: 700,
            fontSize: 14,
          }}
        >
          ✓
        </div>
      </div>
      <div style={{ minWidth: 0 }}>
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
        <div style={{ fontSize: 11, color: C.closedBadgeFg, fontFamily: MONO, marginTop: 1 }}>
          {deal.id} · Closed Won
        </div>
      </div>
      <Cell text={deal.owner} />
      <Cell text={deal.manager} />
      <div style={{ fontSize: 12.5, color: C.cell }}>{deal.stage}</div>
      <div>
        <ForecastBadge fc="Closed" />
      </div>
      <div style={{ textAlign: "right", fontSize: 13.5, fontWeight: 600, color: "oklch(0.26 0.014 262)", fontFamily: MONO }}>
        {deal.amountStr}
      </div>
    </div>
  );
}

// A clickable, sortable column header. Active column renders in the accent color
// with a ↑/↓ suffix; inactive columns are muted (per the v2 spec).
function SortHeader({ col, sort, onSort }) {
  const active = sort.col === col.key;
  const right = col.align === "right";
  const arrow = active ? (sort.dir === "asc" ? " ↑" : " ↓") : "";
  return (
    <button
      onClick={() => onSort(col.key)}
      title={`Sort by ${col.label}`}
      style={{
        display: "flex",
        alignItems: "center",
        gap: 5,
        justifyContent: right ? "flex-end" : "flex-start",
        border: "none",
        background: "transparent",
        padding: 0,
        cursor: "pointer",
        fontFamily: "inherit",
        fontSize: 10.5,
        fontWeight: 600,
        letterSpacing: "0.04em",
        textTransform: "uppercase",
        color: active ? ACCENT : C.muted,
        transition: "color .12s",
      }}
      onMouseOver={(e) => !active && (e.currentTarget.style.color = C.text)}
      onMouseOut={(e) => !active && (e.currentTarget.style.color = C.muted)}
    >
      {right && (
        <span>
          {col.label}
          {arrow}
        </span>
      )}
      {!right && (
        <span>
          {col.label}
          {arrow}
        </span>
      )}
      {col.info && (
        <span
          title={col.info}
          onClick={(e) => e.stopPropagation()}
          style={{ fontSize: 10, opacity: 0.55, cursor: "help", fontWeight: 700 }}
        >
          ⓘ
        </span>
      )}
    </button>
  );
}

function HeaderRow({ sort, onSort }) {
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
      {COLUMNS.map((c) => (
        <SortHeader key={c.key} col={c} sort={sort} onSort={onSort} />
      ))}
    </div>
  );
}

function money(n) {
  return n >= 1e6 ? `$${(n / 1e6).toFixed(2)}M` : `$${Math.round(n / 1000)}k`;
}

// Region group header — click anywhere to fold/unfold. Counts stay visible when
// collapsed so a VP can hide a region and still see its exposure.
function RegionHeader({ region, count, atRisk, booked, bookedCount, collapsed, onToggle }) {
  return (
    <button
      onClick={onToggle}
      aria-expanded={!collapsed}
      style={{
        display: "flex",
        alignItems: "center",
        gap: 10,
        width: "100%",
        padding: "2px 4px 9px",
        border: "none",
        background: "transparent",
        cursor: "pointer",
        fontFamily: "inherit",
        textAlign: "left",
      }}
    >
      <span
        style={{
          display: "inline-flex",
          alignItems: "center",
          justifyContent: "center",
          width: 16,
          fontSize: 11,
          color: C.muted,
          transform: collapsed ? "rotate(-90deg)" : "none",
          transition: "transform .15s",
        }}
      >
        ▼
      </span>
      <span style={{ fontSize: 13, fontWeight: 700, letterSpacing: "0.02em", color: C.text }}>
        {region}
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
        {count} deals
      </span>
      <span style={{ fontSize: 12, color: "oklch(0.5 0.012 260)" }}>
        {money(atRisk)} forecasted at risk
      </span>
      {booked > 0 && (
        <span style={{ fontSize: 12, color: C.positive, fontWeight: 500 }}>
          · {money(booked)} booked ({bookedCount})
        </span>
      )}
      {collapsed && (
        <span style={{ fontSize: 11.5, color: C.faint, marginLeft: 2 }}>· hidden</span>
      )}
    </button>
  );
}

export default function DealsTab({
  deals,
  bookedDeals = [],
  regionOrder,
  asOf,
  timeframe,
  filters,
  setFilters,
  onOpen,
  onHover,
  onLeave,
}) {
  const [sort, setSort] = useState({ col: "risk", dir: "desc" });
  const [collapsed, setCollapsed] = useState({});
  const [showClosed, setShowClosed] = useState(true);

  const toggle = (key, val) =>
    setFilters((f) => ({
      ...f,
      [key]: f[key].includes(val) ? f[key].filter((x) => x !== val) : f[key].concat(val),
    }));

  const onSort = (col) =>
    setSort((s) =>
      s.col === col
        ? { col, dir: s.dir === "asc" ? "desc" : "asc" }
        : { col, dir: SORT_KEYS[col].defaultDir }
    );

  const toggleRegion = (region) =>
    setCollapsed((c) => ({ ...c, [region]: !c[region] }));

  // Region + segment filters apply to both lists; the risk-tier filter only
  // makes sense for flagged deals (booked deals have no risk).
  const inRegionSeg = (d) =>
    (filters.regions.length === 0 || filters.regions.includes(d.region)) &&
    (filters.segments.length === 0 || filters.segments.includes(d.segment));

  // Open flagged deals are never timeframe-scoped. Booked deals are scoped by the
  // header timeframe (which booking window to count) and the Closed Won toggle.
  const shown = deals.filter(
    (d) => inRegionSeg(d) && (filters.tiers.length === 0 || filters.tiers.includes(tierOf(d.risk)))
  );
  const closedShown = showClosed
    ? bookedDeals.filter((d) => inRegionSeg(d) && inTimeframe(d.closeISO, timeframe, asOf))
    : [];

  const groups = regionOrder
    .map((region) => {
      const flaggedRows = sortRows(shown.filter((d) => d.region === region), sort);
      // Booked rows always sort to the bottom of their region by ARR desc.
      const closedRows = sortRows(
        closedShown.filter((d) => d.region === region),
        { col: "arr", dir: "desc" }
      );
      return {
        region,
        flaggedRows,
        closedRows,
        atRisk: flaggedRows.reduce((s, d) => s + d.arr, 0),
        booked: closedRows.reduce((s, d) => s + d.arr, 0),
      };
    })
    .filter((g) => g.flaggedRows.length > 0 || g.closedRows.length > 0);

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", gap: 18, flexWrap: "wrap", marginBottom: 18 }}>
        <FilterGroup label="Risk" values={TIERS} active={filters.tiers} toggle={(v) => toggle("tiers", v)} />
        <Divider />
        <FilterGroup label="Region" values={regionOrder} active={filters.regions} toggle={(v) => toggle("regions", v)} />
        <Divider />
        <FilterGroup label="Segment" values={SEGMENTS} active={filters.segments} toggle={(v) => toggle("segments", v)} />
        <Divider />
        <ClosedToggle on={showClosed} count={bookedDeals.length} onToggle={() => setShowClosed((v) => !v)} />
        <div style={{ marginLeft: "auto", fontSize: 12.5, color: C.muted }}>
          {shown.length} of {deals.length} flagged
          {showClosed && bookedDeals.length > 0 && (
            <span style={{ color: C.positive }}> · {closedShown.length} booked</span>
          )}
        </div>
      </div>

      {groups.map((g) => {
        const isCollapsed = !!collapsed[g.region];
        return (
          <div key={g.region} style={{ marginBottom: 22 }}>
            <RegionHeader
              region={g.region}
              count={g.flaggedRows.length}
              atRisk={g.atRisk}
              booked={g.booked}
              bookedCount={g.closedRows.length}
              collapsed={isCollapsed}
              onToggle={() => toggleRegion(g.region)}
            />
            {!isCollapsed && (
              <div style={{ background: "#fff", border: `1px solid ${C.border}`, borderRadius: 12, overflow: "hidden" }}>
                <HeaderRow sort={sort} onSort={onSort} />
                {g.flaggedRows.map((d) => (
                  <DealRow key={d.id} deal={d} onOpen={onOpen} onHover={onHover} onLeave={onLeave} />
                ))}
                {g.closedRows.map((d) => (
                  <ClosedRow key={d.id} deal={d} onOpen={onOpen} />
                ))}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

// Toggle for the booked Closed Won rows — green (shown) by default, click to
// filter them out.
function ClosedToggle({ on, count, onToggle }) {
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
        Closed won
      </span>
      <button
        onClick={onToggle}
        title={on ? "Hide booked Closed Won deals" : "Show booked Closed Won deals"}
        style={{
          height: 28,
          padding: "0 12px",
          borderRadius: 20,
          fontSize: 12,
          fontWeight: 500,
          fontFamily: "inherit",
          cursor: "pointer",
          transition: "all .12s",
          border: `1px solid ${on ? C.toggleShownBorder : C.border}`,
          background: on ? C.toggleShownBg : "#fff",
          color: on ? C.closedBadgeFg : "oklch(0.45 0.012 260)",
        }}
      >
        {on ? `✓ Shown (${count})` : `Hidden (${count})`}
      </button>
    </div>
  );
}
