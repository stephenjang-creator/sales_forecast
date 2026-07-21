# Eval — region-AWARE (each region's own norms)

`python -m detector.evaluate data/pipeline.csv --region-aware` — staleness judged against each region's typical stage duration, and APAC's early discounts treated as normal. Recommended mode for regional data.

### Overall

| Metric | Value |
| --- | --- |
| Precision | 0.908 |
| Recall | 1.000 |
| F1 | 0.952 |
| Confusion (TP / FP / FN / TN) | 89 / 9 / 0 / 502 |

### Per-rule

| Rule | Precision | Recall | Fired | Labeled | Correct |
| --- | --- | --- | --- | --- | --- |
| slipped_close_date | 1.000 | 1.000 | 23 | 23 | 23 |
| stalled_in_stage | 1.000 | 1.000 | 19 | 19 | 19 |
| commit_low_meddpicc | 0.743 | 1.000 | 35 | 26 | 26 |
| late_stage_no_economic_buyer | 0.750 | 1.000 | 16 | 12 | 12 |
| premature_deep_discount | 0.421 | 1.000 | 19 | 8 | 8 |
| imminent_close_no_paper_process | 0.917 | 0.957 | 24 | 23 | 22 |
