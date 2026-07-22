import { useEffect, useState } from "react";
import { askAgent, exportCsv, fetchForecast } from "./api.js";
import { ACCENT, C } from "./tokens.js";
import { inTimeframe, sumPipeline, tfLabel, tfShort } from "./time.js";
import Header from "./components/Header.jsx";
import AgentBar from "./components/AgentBar.jsx";
import Summary from "./components/Summary.jsx";
import FastMover from "./components/FastMover.jsx";
import DealsTab from "./components/DealsTab.jsx";
import BookingsTab from "./components/BookingsTab.jsx";
import HealthTab from "./components/HealthTab.jsx";
import Drawer from "./components/Drawer.jsx";
import HoverPeek, { peekPosition } from "./components/HoverPeek.jsx";

export default function App() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [tab, setTab] = useState("deals");
  const [query, setQuery] = useState("");
  const [result, setResult] = useState(null);
  const [asking, setAsking] = useState(false);
  // Bring-your-own Anthropic key: kept in memory for this session only (never
  // persisted to storage), passed per-request, and never saved server-side.
  const [apiKey, setApiKey] = useState("");
  const [filters, setFilters] = useState({ tiers: [], regions: [], segments: [] });
  const [hover, setHover] = useState(null);
  const [selected, setSelected] = useState(null);
  const [timeframe, setTimeframe] = useState("quarter"); // scopes booked figures only

  useEffect(() => {
    fetchForecast().then(setData).catch((e) => setError(String(e)));
  }, []);

  async function onAsk(q) {
    const text = (q || "").trim();
    if (!text || asking) return;
    setQuery(text);
    setAsking(true);
    try {
      setResult(await askAgent(text, apiKey.trim() || undefined));
    } catch {
      setResult({ agent: "Error", text: "Could not reach the agent service." });
    } finally {
      setAsking(false);
    }
  }

  function onShare() {
    if (!data) return;
    const top = data.deals.filter((d) => d.risk >= 5).slice(0, 5);
    const brief =
      `Intelligent Forecast brief\n${data.narrative}\n\nTop at-risk deals:\n` +
      top.map((d) => `• ${d.account} (${d.region}) — risk ${d.risk}, ${d.amountStr}, ${d.fc}`).join("\n");
    navigator.clipboard?.writeText(brief);
  }

  if (error)
    return <Center>Could not load the forecast — is the API running? ({error})</Center>;
  if (!data) return <Center>Loading forecast…</Center>;

  // The timeframe scopes the whole forecast by close date. Projection tiles +
  // narrative are computed client-side from the per-month pipeline buckets so they
  // react to the header control: booked (won) + open pipeline projected to close
  // → a risk-adjusted projection, plus flagged-at-risk ARR, all for the period.
  const asOf = data.bookings?.asOf;
  const money = (n) => (n >= 1e6 ? `$${(n / 1e6).toFixed(2)}M` : `$${Math.round(n / 1000)}k`);
  const tl = tfLabel(timeframe);
  const p = sumPipeline(data.pipelineByMonth, timeframe, asOf);
  const bookedInTf = (data.bookedDeals || []).filter((d) => inTimeframe(d.closeISO, timeframe, asOf));

  const byRegion = {};
  data.deals
    .filter((d) => d.risk >= 5 && inTimeframe(d.closeISO, timeframe, asOf))
    .forEach((d) => (byRegion[d.region] = (byRegion[d.region] || 0) + d.arr));
  const topRegion = Object.entries(byRegion).sort((a, b) => b[1] - a[1])[0];

  const kpis = [
    { label: `Booked · ${tl}`, value: money(p.booked), sub: `${bookedInTf.length} closed-won`, tone: "booked" },
    { label: `Open pipeline · ${tl}`, value: money(p.open), sub: `${p.openDeals} deals to close`, tone: "muted" },
    { label: `Projected · ${tl}`, value: money(p.projected), sub: "booked + risk-adjusted", tone: "muted" },
    { label: `At risk · ${tl}`, value: money(p.atRisk), sub: "flagged, in period", tone: "warning" },
  ];
  const narrative =
    `Projecting ${tfShort(timeframe)}: ${money(p.booked)} already booked + ${money(p.open)} open pipeline ` +
    `across ${p.openDeals} deals → ${money(p.projected)} risk-adjusted projection. ` +
    `${money(p.atRisk)} is flagged at risk` +
    (topRegion ? `, concentrated in ${topRegion[0]} (${money(topRegion[1])}).` : ".");

  const tabBtn = (key, label) => (
    <button
      onClick={() => setTab(key)}
      style={{
        height: 40,
        padding: "0 4px",
        marginRight: 22,
        border: "none",
        background: "transparent",
        fontFamily: "inherit",
        fontSize: 13.5,
        fontWeight: 600,
        cursor: "pointer",
        borderBottom: `2px solid ${tab === key ? ACCENT : "transparent"}`,
        color: tab === key ? C.text : C.muted,
      }}
    >
      {label}
    </button>
  );

  return (
    <div style={{ minHeight: "100vh", padding: "28px 32px 80px" }}>
      <div style={{ maxWidth: 1360, margin: "0 auto" }}>
        <Header
          onExport={() => exportCsv(data.deals)}
          onShare={onShare}
          timeframe={timeframe}
          onTimeframe={setTimeframe}
        />
        <AgentBar
          query={query}
          setQuery={setQuery}
          result={result}
          loading={asking}
          onAsk={onAsk}
          onClear={() => setResult(null)}
          apiKey={apiKey}
          setApiKey={setApiKey}
          serverHasKey={data.serverHasKey}
        />
        <Summary narrative={narrative} kpis={kpis} />
        <FastMover fastMover={data.fastMover} onOpen={setSelected} />

        <div style={{ display: "flex", alignItems: "center", gap: 4, borderBottom: `1px solid ${C.border}`, marginBottom: 20 }}>
          {tabBtn("deals", "Flagged deals")}
          {tabBtn("bookings", "Bookings")}
          {tabBtn("health", "Model health")}
        </div>

        {tab === "deals" && (
          <DealsTab
            deals={data.deals}
            bookedDeals={data.bookedDeals || []}
            regionOrder={data.regionOrder}
            asOf={asOf}
            timeframe={timeframe}
            filters={filters}
            setFilters={setFilters}
            onOpen={(d) => {
              setSelected(d);
              setHover(null);
            }}
            onHover={(deal, rect) => setHover({ deal, pos: peekPosition(rect) })}
            onLeave={() => setHover(null)}
          />
        )}
        {tab === "bookings" && <BookingsTab bookings={data.bookings} />}
        {tab === "health" && <HealthTab scorecard={data.scorecard} />}
      </div>

      {hover && !selected && <HoverPeek deal={hover.deal} pos={hover.pos} />}
      <Drawer
        deal={selected}
        onClose={() => setSelected(null)}
        onAsk={(d) => {
          setSelected(null);
          onAsk(`How do I rescue ${d.account}?`);
        }}
      />
    </div>
  );
}

function Center({ children }) {
  return (
    <div style={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", color: C.muted, fontSize: 14, padding: 24, textAlign: "center" }}>
      {children}
    </div>
  );
}
