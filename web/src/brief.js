// Executive-summary PDF. Builds a one-page, print-optimized HTML document from
// the current forecast (scoped to the selected timeframe) and renders it through
// a hidden iframe, so the browser's "Save as PDF" produces a clean, selectable,
// vector PDF -- no third-party PDF library, no popup window.
import { inTimeframe, sumPipeline, tfLabel } from "./time.js";

const A = "#4f46e5"; // accent
const INK = "#1f2430";
const MUT = "#6b7280";
const FAINT = "#9aa1ac";
const LINE = "#e5e7eb";
const GREEN = "#15803d";
const RED = "#b91c1c";
const AMBER = "#b45309";
const BG = "#f8f9fb";

const money = (n) => {
  n = Number(n || 0);
  return n >= 1e6 ? `$${(n / 1e6).toFixed(2)}M` : `$${Math.round(n / 1000)}k`;
};
const delta = (x) => (x == null ? "—" : `${x >= 0 ? "▲" : "▼"} ${Math.abs(x).toFixed(1)}%`);
const deltaColor = (x) => (x == null ? MUT : x >= 0 ? GREEN : RED);
const tier = (r) => (r >= 8 ? "Critical" : r >= 5 ? "High" : r >= 3 ? "Medium" : "Low");
const tierColor = (r) => (r >= 8 ? RED : r >= 5 ? AMBER : MUT);
const esc = (s) =>
  String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");

function prettyDate(iso) {
  if (!iso) return "";
  const [y, m, d] = iso.split("-").map(Number);
  const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  return `${months[(m || 1) - 1]} ${d}, ${y}`;
}

function kpiCard(label, value, sub, color) {
  return `
    <div style="flex:1;border:1px solid ${LINE};border-radius:9px;padding:11px 13px;background:#fff">
      <div style="font-size:9px;text-transform:uppercase;letter-spacing:.04em;color:${MUT};margin-bottom:6px">${esc(label)}</div>
      <div style="font-size:19px;font-weight:700;color:${INK};font-family:'IBM Plex Mono',ui-monospace,monospace;line-height:1">${esc(value)}</div>
      <div style="font-size:10px;color:${color || MUT};margin-top:5px">${esc(sub)}</div>
    </div>`;
}

function momentumCell(label, value, pct) {
  return `
    <div style="flex:1;text-align:left">
      <div style="font-size:9px;text-transform:uppercase;letter-spacing:.04em;color:${MUT}">${esc(label)}</div>
      <div style="font-size:15px;font-weight:700;color:${INK};font-family:'IBM Plex Mono',ui-monospace,monospace;margin-top:3px">${esc(value)}</div>
      <div style="font-size:10px;font-weight:600;color:${deltaColor(pct)};margin-top:2px">${delta(pct)}</div>
    </div>`;
}

function buildHtml(data, timeframe) {
  const asOf = data.bookings?.asOf || "";
  const tl = tfLabel(timeframe);
  const p = sumPipeline(data.pipelineByMonth, timeframe, asOf);
  const bookedDeals = (data.bookedDeals || []).filter((d) => inTimeframe(d.closeISO, timeframe, asOf));

  const atRisk = data.deals
    .filter((d) => d.risk >= 5 && inTimeframe(d.closeISO, timeframe, asOf))
    .sort((a, b) => b.arr - a.arr);
  const topDeals = atRisk.slice(0, 6);
  const atRiskArr = atRisk.reduce((s, d) => s + d.arr, 0);

  const byRegion = {};
  atRisk.forEach((d) => (byRegion[d.region] = (byRegion[d.region] || 0) + d.arr));
  const regions = Object.entries(byRegion).sort((a, b) => b[1] - a[1]);
  const regionsLine =
    regions.map(([r, v]) => `<b style="color:${INK}">${esc(r)}</b> ${money(v)}`).join("&nbsp;&nbsp;·&nbsp;&nbsp;") ||
    "None";

  const bk = data.bookings || {};
  const f1 = (data.scorecard?.metrics || []).find((m) => m.label === "F1")?.value || "—";
  const totalDeals = /of (\d+)/.exec(
    (data.kpis || []).find((k) => /flagged/i.test(k.label))?.sub || ""
  )?.[1];
  const flaggedCount = data.deals.length;

  const rows =
    topDeals
      .map(
        (d) => `
        <tr style="border-top:1px solid ${LINE}">
          <td style="padding:6px 8px">
            <span style="font-weight:600;color:${INK}">${esc(d.account)}</span>
            <span style="color:${MUT};font-family:'IBM Plex Mono',ui-monospace,monospace;font-size:9.5px">&nbsp;${esc(d.mrrStr)}</span>
          </td>
          <td style="padding:6px 8px;color:${MUT}">${esc(d.region)}</td>
          <td style="padding:6px 8px;color:${MUT}">${esc(d.stage)}</td>
          <td style="padding:6px 8px">${esc(d.fc)}</td>
          <td style="padding:6px 8px;text-align:center"><b style="color:${tierColor(d.risk)}">${d.risk}</b> <span style="color:${MUT};font-size:9.5px">${tier(d.risk)}</span></td>
          <td style="padding:6px 8px;text-align:right;font-weight:600;font-family:'IBM Plex Mono',ui-monospace,monospace">${esc(d.amountStr)}</td>
        </tr>`
      )
      .join("") ||
    `<tr><td colspan="6" style="padding:10px 8px;color:${MUT}">No High or Critical deals in this period — the forecast is clean.</td></tr>`;

  return `<!doctype html><html><head><meta charset="utf-8"><title>Intelligent Forecast — Executive Summary</title>
<style>
  @page { size: letter; margin: 0.6in; }
  * { box-sizing: border-box; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
  html,body { margin:0; padding:0; }
  body { font-family: 'IBM Plex Sans', -apple-system, 'Segoe UI', Roboto, sans-serif; color:${INK}; font-size:11px; line-height:1.45; }
  h2 { font-size:11px; text-transform:uppercase; letter-spacing:.05em; color:${A}; margin:0 0 8px; font-weight:700; }
  table { width:100%; border-collapse:collapse; font-size:10.5px; }
  th { text-align:left; font-size:9px; text-transform:uppercase; letter-spacing:.04em; color:${MUT}; padding:0 8px 5px; font-weight:600; }
</style></head>
<body>
  <!-- Header -->
  <div style="display:flex;justify-content:space-between;align-items:flex-start;border-bottom:2px solid ${INK};padding-bottom:10px">
    <div style="display:flex;align-items:center;gap:9px">
      <div style="width:22px;height:22px;border-radius:6px;background:${A};color:#fff;display:flex;align-items:center;justify-content:center;font-weight:700;font-size:12px">◆</div>
      <div>
        <div style="font-size:17px;font-weight:700;letter-spacing:-0.01em">Intelligent Forecast</div>
        <div style="font-size:10px;color:${MUT}">Executive summary — pipeline &amp; bookings</div>
      </div>
    </div>
    <div style="text-align:right;font-size:10px;color:${MUT}">
      <div style="font-weight:600;color:${INK}">${esc(tl)}</div>
      <div>As of ${esc(prettyDate(asOf))}</div>
    </div>
  </div>

  <!-- Headline projection -->
  <div style="margin:14px 0;padding:14px 16px;border-radius:10px;background:${BG};border:1px solid ${LINE};border-left:3px solid ${A}">
    <div style="font-size:10px;text-transform:uppercase;letter-spacing:.05em;color:${A};font-weight:700">Projected bookings · ${esc(tl)}</div>
    <div style="font-size:30px;font-weight:700;font-family:'IBM Plex Mono',ui-monospace,monospace;letter-spacing:-0.02em;margin:2px 0 3px">${money(p.projected)}</div>
    <div style="font-size:11px;color:#3a4150">
      ${money(p.booked)} already booked + ${money(p.open)} open pipeline across ${p.openDeals} deals, risk-adjusted
      (stage win-rates, minus a haircut on ${money(p.atRisk)} of flagged exposure).
    </div>
  </div>

  <!-- KPI row -->
  <div style="display:flex;gap:9px;margin-bottom:16px">
    ${kpiCard("Booked · " + tl, money(p.booked), bookedDeals.length + " closed-won", GREEN)}
    ${kpiCard("Open pipeline · " + tl, money(p.open), p.openDeals + " deals to close", MUT)}
    ${kpiCard("Projected · " + tl, money(p.projected), "booked + risk-adjusted", INK)}
    ${kpiCard("At risk · " + tl, money(p.atRisk), flaggedCount + " flagged" + (totalDeals ? " of " + totalDeals : ""), AMBER)}
  </div>

  <!-- Bookings momentum -->
  <div style="margin-bottom:16px">
    <h2>Bookings momentum</h2>
    <div style="display:flex;gap:14px;border:1px solid ${LINE};border-radius:9px;padding:11px 14px">
      ${momentumCell("Booked YTD", money(bk.ytd?.booked), bk.ytd?.pct)}
      ${momentumCell("YoY · " + (bk.yoy?.period ?? ""), money(bk.yoy?.booked), bk.yoy?.pct)}
      ${momentumCell("QoQ · " + (bk.qoq?.period ?? ""), money(bk.qoq?.booked), bk.qoq?.pct)}
      ${momentumCell("MoM · " + (bk.mom?.period ?? ""), money(bk.mom?.booked), bk.mom?.pct)}
    </div>
  </div>

  <!-- Where the risk is -->
  <div style="margin-bottom:14px">
    <h2>Where the risk is — top exposures (High + Critical)</h2>
    <table>
      <thead><tr>
        <th>Account</th><th>Region</th><th>Stage</th><th>Forecast</th><th style="text-align:center">Risk</th><th style="text-align:right">ARR</th>
      </tr></thead>
      <tbody>${rows}</tbody>
    </table>
    <div style="font-size:10px;color:${MUT};margin-top:8px">
      <b style="color:${INK}">${atRisk.length}</b> deals carry ${money(atRiskArr)} of High/Critical exposure.
      By region: ${regionsLine}.
    </div>
  </div>

  <!-- Why you can trust it -->
  <div style="border:1px solid ${LINE};border-radius:9px;padding:11px 14px;background:${BG}">
    <h2 style="color:${INK}">Why you can trust the number</h2>
    <div style="font-size:10.5px;color:#3a4150">
      Every flag is a <b>deterministic MEDDPICC + pipeline-hygiene rule</b>, not a black-box score — a sales
      manager can verify each one against the CRM record. The projection is booked actuals plus a transparent
      risk haircut on open pipeline. The detector scores <b>F1 ${esc(f1)}</b> against labeled ground truth, and
      the model only explains and routes — it never decides a flag.
    </div>
  </div>

  <!-- Footer -->
  <div style="margin-top:12px;font-size:9px;color:${FAINT};display:flex;justify-content:space-between">
    <span>Intelligent Forecast · generated ${esc(prettyDate(asOf))}</span>
    <span>All data is synthetic — no real customer data.</span>
  </div>
</body></html>`;
}

export function exportExecutiveBrief(data, timeframe) {
  if (!data) return;
  const iframe = document.createElement("iframe");
  Object.assign(iframe.style, { position: "fixed", right: "0", bottom: "0", width: "0", height: "0", border: "0" });
  iframe.setAttribute("aria-hidden", "true");
  iframe.srcdoc = buildHtml(data, timeframe);
  iframe.onload = () => {
    const win = iframe.contentWindow;
    const cleanup = () => setTimeout(() => iframe.remove(), 500);
    win.onafterprint = cleanup;
    setTimeout(() => {
      win.focus();
      win.print();
      // Safety net for browsers that don't fire onafterprint.
      setTimeout(cleanup, 60000);
    }, 60);
  };
  document.body.appendChild(iframe);
}
