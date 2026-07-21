# Eval — region-AWARE (each region's own norms)

`python -m detector.evaluate data/pipeline.csv --region-aware` — staleness judged against each region's typical stage duration, APAC's early discounts treated as normal. Recommended mode.

### Overall

| Metric | Value |
| --- | --- |
| Precision | 0.923 |
| Recall | 1.000 |
| F1 | 0.960 |
| Confusion (TP / FP / FN / TN) | 84 / 7 / 0 / 509 |

### Per-rule

| Rule | Precision | Recall | Fired | Labeled | Correct |
| --- | --- | --- | --- | --- | --- |
| slipped_close_date | 1.000 | 1.000 | 50 | 50 | 50 |
| stalled_in_stage | 1.000 | 1.000 | 54 | 54 | 54 |
| commit_low_meddpicc | 0.667 | 1.000 | 9 | 6 | 6 |
| late_stage_no_economic_buyer | 0.800 | 1.000 | 15 | 12 | 12 |
| premature_deep_discount | 0.833 | 1.000 | 36 | 30 | 30 |
| imminent_close_no_paper_process | 0.889 | 1.000 | 9 | 8 | 8 |
