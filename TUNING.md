# Rule tuning — before / after

Tuning the two underperforming rules against the fixed labels in
`data/pipeline.csv`. Labels, the generator's injectors, and the four already-1.0
rules were left untouched. Full scorecards: [`eval_before.md`](eval_before.md),
[`eval_after.md`](eval_after.md).

## Overall

| Metric | Before | After |
| --- | --- | --- |
| Precision | 0.887 | 0.893 |
| Recall | 0.925 | 0.989 |
| **F1** | **0.905** | **0.939** |
| Confusion (TP/FP/FN/TN) | 86 / 11 / 7 / 496 | 92 / 11 / 1 / 496 |

## `stalled_in_stage` — fixed ✅

| | precision | recall | fired | labeled |
| --- | --- | --- | --- | --- |
| Before | 1.000 | 0.600 | 15 | 25 |
| After | 1.000 | 1.000 | 25 | 25 |

**Change:** `config.STALE_MULTIPLIER` `3` → `2.5` (threshold only; rule logic
unchanged).

**Tradeoff:** none, really — this was free recall. Healthy deals never sit past
**1.0×** the stage norm in the data (the generator only pushes stalled deals to
3–5× normal), so precision holds at 1.00 for any multiplier down to 1.0×; the old
3× line simply sat above the injected 3× floor and missed those deals. 2.5× was
chosen over a lower value to keep a tight, defensible "2.5× the norm = stalled"
semantic while still capturing every labeled stall.

## `premature_deep_discount` — left as-is, by design ⚖️

| | precision | recall | fired | labeled |
| --- | --- | --- | --- | --- |
| Before / After | 0.462 | 1.000 | 26 | 12 |

**Change:** none.

**Why not the proposed weak-value filter:** the intended fix was to fire only
when the discount is deep *and* value isn't established (`m_identified_pain` /
`m_metrics` low). Measured on the data, that condition **backfires** — it drops
precision to ~0.44 and recall to ~0.58 — because the generator's discount
injector never depresses pain/metrics, so true and false positives are
statistically identical on every qualification feature:

| among the 26 fired | pain | metrics | meddpicc_conf | discount |
| --- | --- | --- | --- | --- |
| 12 true positives | 1.42 | 1.58 | 53.6 | spread 0.31–0.47 |
| 14 false positives | 1.64 | 1.79 | 59.0 | **all exactly 0.40** |

Every false positive is a *natural* 40% catalog discount (the only value ≥ 0.30
in the generator's discrete natural pool), and **no true positive is exactly
0.40** (they're injected at continuous values like 0.37, 0.44). The only thing
that separates them is `discount != 0.40` — i.e. overfitting to the synthetic
generator, not a real business signal. `meddpicc_confidence < 60` was the best
*principled* lever (precision 0.46 → 0.57) but it trades recall down to 0.67 for
a roughly flat F1, so it buys nothing here.

**Conclusion:** precision > 0.75 at recall ≥ 0.9 is **not achievable on this
labeled set without overfitting**. We keep the rule at precision 0.46 / recall
1.00 and flag those false positives honestly. In a real deployment where deep
discounts genuinely correlate with thin qualification, the
`meddpicc_confidence < 60` (or weak pain/metrics) condition would be the correct
addition — the synthetic data just doesn't model that correlation.

## Net

F1 moved **0.905 → 0.939**, driven entirely by the `stalled_in_stage` recall
fix. One config value changed (`STALE_MULTIPLIER`); no rule logic, labels, or
rule ids were modified.
