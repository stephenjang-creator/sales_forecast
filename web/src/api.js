// Thin API client. In dev, Vite proxies /api -> FastAPI (:8000); in prod the
// same FastAPI process serves both the app and /api, so relative paths work.
export async function fetchForecast() {
  const res = await fetch("/api/forecast");
  if (!res.ok) throw new Error(`forecast ${res.status}`);
  return res.json();
}

export async function askAgent(query) {
  const res = await fetch("/api/ask", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query }),
  });
  if (!res.ok) throw new Error(`ask ${res.status}`);
  return res.json();
}

// Client-side CSV export of the flagged deals.
export function exportCsv(deals) {
  const cols = ["id", "account", "region", "segment", "industry", "owner", "manager", "stage", "fc", "risk", "tier", "mrr", "arr", "closeDate", "nextMeeting"];
  const esc = (v) => `"${String(v ?? "").replace(/"/g, '""')}"`;
  const rows = [cols.join(",")].concat(
    deals.map((d) => cols.map((c) => esc(d[c])).join(","))
  );
  const blob = new Blob([rows.join("\n")], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "intelligent-forecast-flagged.csv";
  a.click();
  URL.revokeObjectURL(url);
}
