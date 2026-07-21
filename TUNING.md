# Tuning & the region-aware win

The demo data encodes real regional behavior — **US deals move fast, EMEA deals
run long and linger in Proposal, APAC discounts early as normal practice** (see
`generate_forecast_data.py`, which imports the region norms from `config.py`).
Anomalies are labeled *relative to each region's norm*: a "stalled" NA deal sits
3–5× NA's short norm, a "stalled" EMEA deal sits 3–5× EMEA's long norm, and APAC
early discounts are simply not anomalies.

That makes region-awareness measurable: a detector using one global norm both
over- and under-flags, and judging each region against its own norm fixes it.
Full scorecards: [`eval_before.md`](eval_before.md) (agnostic),
[`eval_after.md`](eval_after.md) (region-aware).

## Overall

| Metric | Region-agnostic (naive) | **Region-aware** |
| --- | --- | --- |
| Precision | 0.763 | **0.929** |
| Recall | 0.937 | **1.000** |
| **F1** | **0.841** | **0.963** |
| Confusion (TP/FP/FN/TN) | 74 / 23 / 5 / 498 | 79 / 6 / 0 / 515 |

Enabling region-aware scoring recovers **+12.2 F1 points** on this data.

## `stalled_in_stage` — the headline

| | precision | recall |
| --- | --- | --- |
| Region-agnostic | 0.611 | 0.524 |
| Region-aware | **1.000** | **1.000** |

The global norm fails two ways at once: it **over-flags** EMEA proposals that sit
50–70 days (normal for EMEA, but past the global 2.5× line → false positives) and
**misses** NA deals stalled 30–50 days (well past NA's fast norm, but under the
global line → false negatives). Judging `days_in_stage` against
`config.REGION_STAGE_NORMAL_DAYS[region][stage]` (× the global `STALE_MULTIPLIER`
of 2.5) removes both.

## `premature_deep_discount` — APAC tolerance

| | precision | recall | fired |
| --- | --- | --- | --- |
| Region-agnostic | 0.269 | 1.000 | 26 |
| Region-aware | **0.538** | 1.000 | 13 |

APAC's frequent early discounts are normal practice, so the agnostic rule
false-flags them; region-aware suppresses `premature_deep_discount` for APAC
(`config.REGION_DISCOUNT_TOLERANT`). The residual false positives are natural 40%
catalog discounts in non-APAC regions — the same generator artifact documented
before (true and false positives are feature-identical), not a fixable signal, so
we flag them honestly rather than overfit.

## The other rules

`slipped_close_date` and `imminent_close_no_paper_process` are near-perfect and
region-independent. `commit_low_meddpicc` (0.74 / 1.00) and
`late_stage_no_economic_buyer` (0.82 / 1.00) carry some co-injection overlap —
deals that trip a second rule's condition — which is realistic risk, not a bug.
They score identically in both modes (they don't depend on region).

## Config

- `STALE_MULTIPLIER = 2.5` — global; applied to the region norm when region-aware.
- `REGION_STAGE_NORMAL_DAYS` — per-region typical days per open stage (US short,
  EMEA long, esp. Proposal).
- `REGION_DISCOUNT_TOLERANT = ("APAC",)`.

Default scoring stays **region-agnostic** (`engine.run(df)` /
`make eval`) for backward-compatible reproducibility; pass `region_aware=True`
(engine, MCP tools, the UI toggle, `--region-aware` on the eval and agent CLIs)
for the recommended regional scoring.
