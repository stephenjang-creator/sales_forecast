import { useEffect, useState } from "react";
import { askAgent, exportCsv, fetchForecast } from "./api.js";
import { ACCENT, C } from "./tokens.js";
import { inTimeframe, tfLabel, tfShort } from "./time.js";
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
      setResult(await askAgent(text));
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

  // Booked figures are timeframe-scoped (client-side); the open pipeline is not.
  const asOf = data.bookings?.asOf;
  const money = (n) => (n >= 1e6 ? `$${(n / 1e6).toFixed(2)}M` : `$${Math.round(n / 1000)}k`);
  const bookedInTf = (data.bookedDeals || []).filter((d) => inTimeframe(d.closeISO, timeframe, asOf));
  const bookedArr = bookedInTf.reduce((s, d) => s + d.arr, 0);
  const kpis = [
    {
      label: `Booked · ${tfLabel(timeframe)}`,
      value: money(bookedArr),
      sub: `${bookedInTf.length} closed-won`,
      tone: "booked",
    },
    ...data.kpis,
  ];
  const narrative =
    `Booked ${tfShort(timeframe)}: ${money(bookedArr)} across ${bookedInTf.length} closed-won. ` +
    data.narrative;

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
