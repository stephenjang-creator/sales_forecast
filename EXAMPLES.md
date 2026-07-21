# EXAMPLES.md — agent questions → tool calls

How a conversational agent should map natural-language RevOps questions to the
MCP tools exposed by `mcp_server.py`. The tools return structured JSON; the agent
narrates. The deterministic rules own every flag — the agent never re-decides
risk, it only explains and routes.

All numbers below are from the bundled synthetic dataset (`data/pipeline.csv`,
seed 42); yours will differ if you point `FORECAST_CSV` at your own export.

---

### 1. Regional roll-up
> **"How is EMEA looking this month?"**

- **Call:** `assess_region("EMEA")`
- **Returns:** deals, flagged count, total/at-risk ARR, `at_risk_pct_of_commit`,
  `top_reasons`, `avg_meddpicc_confidence`.
- **Narration tip:** Lead with flagged count and the share of Commit ARR at risk.
  Honor the `note`: this is **risk exposure, not an attainment forecast** — say
  "X of EMEA's Commit dollars sit on flagged deals," not "EMEA will land at Y."

### 2. Single-deal risk
> **"What's the risk on D-10024?"**

- **Call:** `assess_deal("D-10024")`
- **Returns:** stage, forecast_category, `meddpicc_confidence`, the 8 element
  scores, and every rule `hit` with its `reason` and `severity`.
- **Narration tip:** Read the hit reasons back verbatim — they already cite the
  deal's own numbers (e.g. "Stuck in Negotiation for 72 days — 4.0× the norm").

### 3. Shaky Commit exposure
> **"How much of our Commit forecast is actually shaky?"**

- **Call:** `forecast_summary("Commit")`
- **Returns:** total vs. flagged ARR for Commit, plus the count and ARR of
  `commit_low_meddpicc` and `imminent_close_no_paper_process` deals.
- **Narration tip:** These two rules are the forecast-killers — quantify the
  dollars ("~$2.0M of Commit is flagged for thin MEDDPICC") and hand back the
  deal list via a follow-up `list_deals(forecast_category=... , flagged_only=True)`.

### 4. Prioritized worklist
> **"Give me the five riskiest enterprise deals to review."**

- **Call:** `list_deals(segment="Enterprise", flagged_only=True, limit=5)`
- **Returns:** compact deals sorted by `risk_score` (highest first), each with a
  `top_reason`.
- **Narration tip:** Present as a triage list; offer to `assess_deal` any of them.

### 5. Segment comparison
> **"Is SMB or Mid-Market in worse shape?"**

- **Calls:** `assess_segment("SMB")` and `assess_segment("Mid-Market")`
- **Returns:** two roll-ups to compare on flagged %, at-risk ARR, and
  `avg_meddpicc_confidence`.
- **Narration tip:** Compare `at_risk_pct_of_commit` and average confidence side
  by side; don't invent a bookings number.

### 6. Reliability / self-caveat
> **"How confident should I be in these flags?"**

- **Call:** `get_scorecard()`
- **Returns:** overall precision / recall / F1 + per-rule precision and recall
  against ground truth.
- **Narration tip:** Be honest about the trade-offs, e.g. "`premature_deep_discount`
  runs ~0.46 precision — it deliberately over-flags early deep discounts, so treat
  those as 'worth a look,' not certain problems," and "`stalled_in_stage` recall is
  ~0.60 by design, so I may miss borderline stalls."

### 7. Discovering valid filters
> **"Which regions do we even have data for?"**

- **Call:** `list_regions()` (or `list_segments()`)
- **Returns:** the distinct values present, so the agent picks a valid filter
  before calling `assess_region` / `list_deals`.

### 8. "Not a forecast" guardrail (risk tools)
> **"Which deals in APAC should I worry about?"**

- **Call:** `assess_region("APAC")` / `list_deals(region="APAC", flagged_only=True)`
- **Correct narration:** The risk tools report **hygiene/qualification risk
  exposure**, not predicted attainment. Answer with "APAC has N flagged deals and
  $X of Commit at risk — here's what to fix." For a bookings number, use the
  time/bookings tools below.

---

## Time & bookings questions (rollups, YoY / QoQ / MoM)

### 9. Current-period rollup
> **"How much will EMEA book this quarter?"**

- **Call:** `bookings_rollup(grain="quarter", region="EMEA")`
- **Returns:** `won_so_far` + `expected_to_close` = `projected_bookings`, plus
  `quota` and `projected_attainment_pct`, with prior-period and year-ago actuals.
- **Narration tip:** The period is in progress — quote projected vs quota as
  *pace* and cite the `note`. "EMEA is pacing to ~$3.1M this quarter (43% of
  quota) with the quarter still open."

### 10. Month vs quarter
> **"What's the July number looking like versus the whole quarter?"**

- **Calls:** `bookings_rollup(grain="month", region=...)` and
  `pipeline_by_period(grain="month", region=...)` to see how bookings spread
  across the coming months.

### 11. Year-over-year / quarter-over-quarter (completed periods)
> **"How did we do YoY last quarter?"** / **"Is NA growing QoQ?"**

- **Call:** `period_comparison(grain="quarter", region="NA")`
- **Returns:** latest *completed* period's bookings + attainment, the prior
  quarter (QoQ), and the same quarter a year ago (YoY), with percent changes.
- **Narration tip:** Use this for settled trends (e.g. "NA finished Q2 +15% YoY,
  +7% QoQ at 99% attainment") — not the in-progress period, which understates.

### 12. Historical trend
> **"Show me EMEA bookings by quarter for the last two years."**

- **Call:** `bookings_history(grain="quarter", region="EMEA", last_n=8)`
- **Returns:** per-period bookings, quota, attainment_pct, deals_won.

### 13. Full attainment projection (agent, not a single tool)
> **"Project every region's month and quarter attainment."**

- **Run:** `python -m agents.attainment --all` (one agent per region over the
  tools above, then a portfolio roll-up). `--dry-run` gives the deterministic
  rollups with no key.
