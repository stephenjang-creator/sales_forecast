# Forecast Anomaly Detector

A RevOps forecast-hygiene detector for a B2B SaaS pipeline. It reads a pipeline
export, applies **deterministic rules grounded in MEDDPICC** qualification and
deal-hygiene signals, flags at-risk opportunities with a plain-English reason for
every flag, and scores its own accuracy against a labeled test set. An optional
LLM layer writes a short "why it's at risk, what to do next" brief per flagged
deal — but the **human-in-the-loop** split is the whole point: the deterministic
rules own the decision, and the model only explains and coaches. That keeps the
system auditable — a sales manager can read any flag and verify it against the
CRM record. All data is synthetic.

## Eval scorecard

The bundled dataset (`data/pipeline.csv`, 600 deals, seed 31) encodes real
**regional behavior** — US deals move fast, EMEA deals run long and linger in
Proposal, APAC discounts early as normal practice — with anomalies labeled
relative to each region's norm. So the detector is scored two ways
(`make eval` / `make eval-region`):

| Metric | Region-agnostic (one global norm) | **Region-aware (each region's norm)** |
| --- | --- | --- |
| Precision | 0.764 | **0.908** |
| Recall | 0.944 | **1.000** |
| **F1** | **0.844** | **0.952** |
| Confusion (TP/FP/FN/TN) | 84 / 26 / 5 / 485 | 89 / 9 / 0 / 502 |

Region-aware scoring recovers **+10.8 F1 points** — the two region-sensitive
rules tell the story:

| Rule (region-aware) | Precision | Recall | vs agnostic |
| --- | --- | --- | --- |
| slipped_close_date | 1.000 | 1.000 | — |
| **stalled_in_stage** | **1.000** | **1.000** | agnostic 0.542 / 0.684 |
| commit_low_meddpicc | 0.743 | 1.000 | region-independent |
| late_stage_no_economic_buyer | 0.750 | 1.000 | region-independent |
| **premature_deep_discount** | **0.421** | 1.000 | agnostic 0.250 prec |
| imminent_close_no_paper_process | 0.917 | 0.957 | — |

**Reading the numbers, honestly** (full before/after in [`TUNING.md`](TUNING.md)):

- **`stalled_in_stage`:** the global norm over-flags EMEA's normally-long
  proposals *and* misses NA's fast-region stalls; judging against each region's
  own norm fixes both (0.54/0.68 → 1.00/1.00).
- **`premature_deep_discount`:** region-aware stops false-flagging APAC's normal
  early discounts (0.25 → 0.42 precision). The residual false positives are
  natural 40% catalog discounts in other regions — feature-identical to the real
  ones, so we flag them honestly rather than overfit.
- **`commit_low_meddpicc` (0.74/1.00) / `late_stage_no_economic_buyer` (0.75/1.00)**
  carry some realistic co-injection overlap and are region-independent (identical
  in both modes).

_(Numbers regenerate with the dataset; `make data && make eval` to refresh.)_

## Quickstart

```bash
# 1. Install deps
pip install -r requirements.txt

# 2. (optional) regenerate the labeled dataset — it's already committed
make data       # python generate_forecast_data.py --n 600 --seed 31 --out data/pipeline.csv

# 3. Run the deterministic-core unit tests
make test       # pytest -q

# 4. Print the eval scorecard against the bundled labeled CSV
make eval       # python -m detector.evaluate data/pipeline.csv

# 5. Launch the two-mode Streamlit UI
make app        # streamlit run app.py

# 6. Run the MCP server so an agent can query the pipeline (see "Agent / MCP")
make mcp        # python mcp_server.py
```

The core (`rules`, `engine`, `evaluate`) makes **zero network calls** and runs
end to end with no API key. Only `detector/narrative.py` touches the Anthropic
API; set `ANTHROPIC_API_KEY` to enable LLM briefs, or leave it unset and they're
skipped.

## How the rules map to MEDDPICC

Each rule maps 1:1 to a ground-truth `anomaly_types` id and to the MEDDPICC (and
deal-hygiene) signal it watches. Adding a new anomaly type is a one-function
change in `detector/rules.py` plus one line in the `ALL_RULES` registry.

| Rule (`rule_id`) | MEDDPICC / hygiene signal | Fires when | Severity |
| --- | --- | --- | --- |
| `slipped_close_date` | Deal hygiene (forecast discipline) | `close_date_pushes ≥ 2` | medium → high (3+) |
| `stalled_in_stage` | Decision **P**rocess velocity | open & `days_in_stage > normal × 3` | medium → high (>4×) |
| `commit_low_meddpicc` | Overall MEDDPICC confidence | `forecast = Commit` & `confidence < 60` | high |
| `late_stage_no_economic_buyer` | **E**conomic Buyer | Proposal/Negotiation & `m_economic_buyer = 0` | high |
| `premature_deep_discount` | **M**etrics / Identified **P**ain (value unproven) | early stage & `discount ≥ 30%` | medium |
| `imminent_close_no_paper_process` | **P**aper Process | open & `days_to_close ≤ 7` & `m_paper_process = 0` | high |

All thresholds live in `config.py` so a RevOps admin can retune the detector
without touching rule logic.

## Architecture

```
sales_forecast/
├── generate_forecast_data.py   # synthetic labeled pipeline (region-aware behavior)
├── generate_history.py         # synthetic historical bookings + forward targets
├── data/
│   ├── pipeline.csv            # bundled labeled demo dataset
│   ├── history.csv             # 36 months of actual bookings + quota per region
│   └── targets.csv             # current + forward quotas per region
├── config.py                   # every tunable threshold (+ win-rates/haircut)
├── periods.py                  # time bucketing, history rollups, MoM/QoQ/YoY
├── detector/
│   ├── rules.py                # pure rule functions + ALL_RULES registry
│   ├── engine.py               # run rules over a DataFrame → risk columns
│   ├── evaluate.py             # score vs. ground truth; scorecard_markdown()
│   └── narrative.py            # optional, offline-safe LLM briefs
├── agents/                     # attainment estimation layer (over the MCP tools)
│   ├── baseline.py             # deterministic risk-adjusted expected-bookings
│   ├── mcp_client.py           # stdio client + Anthropic tool bridge
│   └── attainment.py           # one agent per region + portfolio roll-up
├── tests/
│   ├── test_rules.py           # a firing row + a clean row per rule
│   ├── test_mcp_tools.py       # each MCP tool called directly
│   ├── test_periods.py         # period math, history rollups, comparisons
│   └── test_agents.py          # baseline math + stdio round-trip + agent loop
├── app.py                      # Streamlit two-mode UI
├── mcp_server.py               # FastMCP server exposing the detector to agents
├── EXAMPLES.md                 # agent questions → tool calls
└── Makefile
```

- **`rules.py`** — one pure `def rule_x(row: dict) -> RuleHit | None` per anomaly.
  Every `reason` is built only from the row's own values.
- **`engine.py`** — `run(df)` applies all rules to every row and appends `hits`,
  `risk_score`, `predicted_anomaly`, and `top_reason` without dropping any rows.
- **`evaluate.py`** — overall precision/recall/F1 + confusion, plus per-rule
  precision/recall against `anomaly_types`. Labels are read here only, never in
  the rules.
- **`narrative.py`** — presentation only; returns `""` with no key so the
  pipeline is offline by default. Never imported by the deterministic core.
- **`mcp_server.py`** — read-only MCP tools that wrap `engine`/`evaluate` so an
  agent can query the pipeline conversationally. Zero LLM calls in any tool.

## The UI

`make app` opens a two-mode Streamlit app:

- **Demo (portfolio):** scores the bundled labeled CSV, shows the eval scorecard
  up top (so a reviewer immediately sees it works against ground truth), then a
  sortable/filterable table of flagged deals (filter by **region**, segment,
  stage, and min risk) with a per-deal detail expander.
- **Bring your own CSV:** runs the identical pipeline on an uploaded file (same
  schema; labels optional — the scorecard hides itself when labels are absent).

LLM briefs sit behind a per-deal toggle, so the app is fully usable without a key.

### Region-aware thresholds (opt-in)

Regions run their sales motion differently, and the demo data is generated to
match. The sidebar **Region-aware thresholds** toggle judges each deal against
its region's own norms (all tunable in `config.py`):

| Region | Behavior (baked into the data) | Effect on rules |
| --- | --- | --- |
| **NA (US)** | Deals move fast (short time-in-stage) | `stalled_in_stage` uses NA's short norm → catches fast-region stalls the global norm misses |
| **EMEA** | Deals run long; proposals linger (~70-day norm) | `stalled_in_stage` uses EMEA's long norm → stops over-flagging normal long proposals |
| **APAC** | Early deep discounts are normal practice | `premature_deep_discount` is suppressed |

Because the labels are region-relative, region-aware scoring **materially
outperforms** the naive one-global-norm detector: **F1 0.844 → 0.952** (see the
scorecard above and [`TUNING.md`](TUNING.md)). It's **off by default** for
backward-compatible reproducibility; enable it via the UI toggle,
`engine.run(df, region_aware=True)`, `make eval-region`, or the `region_aware`
param on the MCP tools / `--region-aware` on the agent CLI. Rules stay pure
functions of a row — the flag rides in on the row dict.

## Agent / MCP

`mcp_server.py` exposes the deterministic detector as an [MCP](https://modelcontextprotocol.io)
server so any MCP client (Claude Desktop, Claude Code, a custom agent) can ask
the pipeline questions — regional roll-ups, single-deal risk, shaky-Commit
exposure — and get **structured JSON back**. The agent narrates; the rules still
own every flag. It's read-only and makes zero LLM calls. The dataset is loaded
and scored once at startup; point it at your own export via `FORECAST_CSV`.

**Risk tools:** `list_deals`, `assess_deal`, `assess_segment`, `assess_region`,
`forecast_summary`, `get_scorecard`, `list_regions`, `list_segments`.
**Time / bookings tools:** `bookings_rollup` (current month/quarter projection +
attainment), `pipeline_by_period` (bookings distribution across periods),
`bookings_history` (actuals by period), `period_comparison` (MoM/QoQ/YoY).
See [`EXAMPLES.md`](EXAMPLES.md) for natural-language questions and the tool call
each should trigger.

Every scoring tool also accepts **`region_aware=True`** to apply the per-region
threshold overlay (see [Region-aware thresholds](#region-aware-thresholds-opt-in)),
and the attainment agents take a matching `--region-aware` flag. The server
pre-scores both modes at startup, so the flag is a free per-call switch.

**Register with Claude Code** (one-liner, run from this directory):

```bash
claude mcp add forecast-detector \
  -e FORECAST_CSV="$(pwd)/data/pipeline.csv" \
  -- "$(which python)" "$(pwd)/mcp_server.py"
```

**Register with Claude Desktop** — add to `claude_desktop_config.json` (use
absolute paths; the `command` should be the Python from the env where you
`pip install -r requirements.txt`):

```json
{
  "mcpServers": {
    "forecast-detector": {
      "command": "/absolute/path/to/sales_forecast/.venv/bin/python",
      "args": ["/absolute/path/to/sales_forecast/mcp_server.py"],
      "env": {
        "FORECAST_CSV": "/absolute/path/to/sales_forecast/data/pipeline.csv"
      }
    }
  }
}
```

Then ask, e.g., _"How's EMEA looking?"_ → `assess_region("EMEA")`, or _"How
confident are you in these flags?"_ → `get_scorecard()`. The tools report **risk
exposure, not a predicted attainment number** — the detector flags
hygiene/qualification risk, it does not forecast bookings.

### Deploy the server locally on stdio

The server speaks MCP over stdio, so "deploying" it is just running it — clients
launch it as a subprocess and talk over stdin/stdout:

```bash
make mcp        # python mcp_server.py — waits for an MCP client on stdio
```

Register it with Claude Code (one-liner above) or Claude Desktop (JSON above),
or drive it from your own code with the SDK's `stdio_client` — see
`agents/mcp_client.py` for a working `open_session()` that spawns and connects to
it.

## Predicting regional attainment (agents)

The detector reports *risk*, not a forecast — but you often want the next step:
**how much will each region book this month/quarter, and how does that compare
YoY?** That lives in a separate agent layer (`agents/`) on top of the MCP tools,
so the deterministic core stays honest and the projection is clearly labeled as a
model estimate.

`agents/attainment.py` runs **one agent per region, concurrently**. Each agent:

1. spawns the MCP server on stdio and pulls its region's current-period rollups
   and history (`bookings_rollup`, `period_comparison`, `assess_region`,
   `list_deals`);
2. anchors on deterministic tool math — for the current period,
   **won-so-far + risk-adjusted expected-to-close** (stage win-rates × ARR minus a
   haircut on flagged deals; win-rates/haircut in `config.py`), measured against
   the period's **quota** from `data/targets.csv`;
3. returns a structured projection for **this month and this quarter**
   (projected bookings, attainment %, YoY change) plus key risks;

then a final step aggregates the regions into a portfolio total.

```bash
export ANTHROPIC_API_KEY=sk-...
make attainment                              # all regions, month + quarter + portfolio
python -m agents.attainment --region EMEA    # a single region
python -m agents.attainment --all --json     # machine-readable

make attainment-dry                          # NO key: deterministic tool rollups only
```

`--dry-run` runs the whole stdio + tools + rollup pipeline with no key or network
(it just calls the deterministic period tools), so you can verify the plumbing
and get real numbers offline. Sample offline output on the bundled data:

```
  NA     This month:   $1,155,381 (39% attain, YoY -53%) [2026-07]
         This quarter: $5,127,714 (44% attain, YoY -49%) [2026-Q3]
  EMEA   This month:   $511,829   (28% attain, YoY -70%) [2026-07]
         This quarter: $4,322,346 (60% attain, YoY -33%) [2026-Q3]
  …
  PORTFOLIO  month $2,402,448   quarter $13,863,299
```

**Read the current period as pace, not a final result.** It's in progress and
reflects only currently-open pipeline, so a mid-period projection sits below a
completed historical period — hence the negative early YoY. For settled trends,
`period_comparison` / `bookings_history` report YoY/QoQ/MoM on **completed**
periods (e.g. EMEA 2026-Q2 finished at 99% attainment, +15% YoY).

Attainment uses **synthetic quotas** (`data/targets.csv`); swap in your team's
real targets and historical win-rates (`config.py`) to make it your own.

---

_All data in this project is synthetic (`generate_forecast_data.py`,
`generate_history.py`). No real customer or company data is ever used or
committed._
