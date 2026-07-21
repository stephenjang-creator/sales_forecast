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

### 14. Region-aware scoring
> **"Score the pipeline the way each region actually sells."**

- **How:** every scoring tool takes `region_aware=True` (e.g.
  `assess_region("APAC", region_aware=True)`, `list_deals(region_aware=True)`,
  `get_scorecard(region_aware=True)`), and the agent CLI takes `--region-aware`.
- **Effect:** US flags stalls sooner, EMEA proposals get more slack, APAC's early
  deep discounts stop being flagged. Off by default (region-agnostic baseline).
- **Narration tip:** it changes what's flagged, so `get_scorecard(region_aware=True)`
  shifts vs the baseline — precision up, recall down where a region tolerates the
  behavior. Say which mode you used.

### 15. Deal signals (fast movers & complex deals)
> **"Which deals will move fast, and which will drag?"**

- **Calls:** `signals_summary(region="NA")` for counts + ARR, then
  `list_deals(signal="fast_mover")` or `list_deals(signal="complex_deal")` to pull
  them; `assess_deal(...)` returns a deal's `decision_profile` and `signals`.
- **What they mean:** `fast_mover` = Director+ champion and a simple process (few
  approvals, no C-suite) → likely to close quickly. `complex_deal` = C-suite gate
  or 3+ approval layers → expect a longer, less predictable cycle. `meeting_at_risk`
  = next meeting more than a week out (or none booked) → momentum slipping; run a
  **value touch** (surfaces in `recommend_plays` and the regional worklist).
- **Narration tip:** these are opportunity/duration signals, *not* anomalies —
  read them alongside the risk flags to prioritize (a fast mover with no risk
  flag is a clean pull-forward; a complex deal forecast as Commit is worth a look).

---

## Sales-guru questions (what to DO, and what a VP should do first)

### 16. What should I do about this deal?
> **"D-10023 is flagged — what plays should I run?"**

- **Call:** `recommend_plays("D-10023")` (deterministic), then optionally the
  `sales_guru` agent to personalize.
- **Returns:** the deal's `hits` plus an ordered list of `plays`, each with a
  title, the risk it removes (`why`), concrete `actions`, and an `owner`.
- **What it means:** each play maps to a flag the rules already set — the plays
  *respond* to flags, they never change them. `premature_deep_discount` → "Re-anchor
  on value before price"; `late_stage_no_economic_buyer` → "Get to the Economic
  Buyer now"; and so on.
- **Narration tip:** read the play's actions back as a checklist and name the
  owner. For a personalized talk track, run
  `python -m agents.sales_guru --deal D-10023` (or `--dry-run` for the plays alone).

### 17. Regional VP priorities — "what are my top 3 things?"
> **"I run NA — what are the top 3 things my team should do today?"**

- **Call:** `region_top_actions("NA", max_deals=10)` (deterministic), or the
  `sales_guru` agent (`--region NA` / `--all`) to narrate it.
- **Returns:** the top `max_deals` (default 10) deals region-wide, grouped by the
  play to run — a ranked list of `actions` (each **one play that can cover several
  deals**, with `kind`, `deal_count`, `arr_at_stake`, `mrr_at_stake`, the covered
  `deals`, and a `priority_score`), plus a short **`vp_should_join_calls`** list.
  Every surfaced deal is listed — there is no "+N more" tail; `surfaced_deals` /
  `actionable_deals` report the budget vs. the region total.
- **How it's ranked:** each deal's weight = urgency × funnel-depth(stage) ×
  champion-boost, so **bottom-of-funnel, well-championed deals** (a few steps from
  close) and **fast movers** rise to the top; the top `max_deals` are taken, then
  grouped by play. Each covered deal carries `label` (company + MRR),
  `champion_seniority`, and `good_champion`.
- **Two levers (matches how a VP works):** the `actions` are plays to **delegate
  to managers via a note** — they scale, so no cap. Each call in
  `vp_should_join_calls` carries a **`next_meeting_date`** so the VP knows when to
  join (or that none is booked). `vp_should_join_calls` is a
  short, capped list (`config.VP_CALL_CAPACITY`) of **senior-stakeholder** deals
  (VP+/C-suite champion, or a C-suite approver) for the VP to **personally join**,
  because calls are scarce.
- **Narration tip:** name deals the way reps do — **company + MRR** (each deal
  carries a `label` like `Acme Group ($6,930/mo)`), showing a few of the most
  actionable accounts and summarizing the rest by dollar value, never a list of
  ids. Lead with action #1 as an imperative; tell the VP which managers to notify
  vs. which few calls to join themselves. It's a worklist, **not** an attainment
  forecast — pair with `bookings_rollup` for the number.
- **Run the agent:** `python -m agents.sales_guru --region NA` (or `--all`), or
  add `--dry-run` for the deterministic worklist with no key.

### 18. Ask the guru, then keep prompting (interactive)
> **"What are my top 3 things in NA?"** → **"Tell me more about #2."** → **"Who
> owns the first one, and show me those deals."**

- **Run:** `python -m agents.sales_guru --chat` (or `--chat --region NA` to seed
  the first question). Needs `ANTHROPIC_API_KEY`.
- **How it works:** a conversational agent with every MCP tool available. It
  answers the first question via `region_top_actions`, and because the
  conversation persists, follow-ups ("drill into #2", "assess D-10339") reuse the
  context and call `assess_deal` / `recommend_plays` / `list_deals` as needed.
- **Guardrail:** same as every tool — it explains and recommends the play but
  never changes a flag or invents a deal/number the tools didn't return.
