# Eval — region-AWARE (each region's own norms)

`python -m detector.evaluate data/pipeline.csv --region-aware` — staleness judged against each region's typical stage duration, and APAC's early discounts treated as normal. This is the recommended mode for regional data.

### Overall

| Metric | Value |
| --- | --- |
| Precision | 0.891 |
| Recall | 0.976 |
| F1 | 0.932 |
| Confusion (TP / FP / FN / TN) | 82 / 10 / 2 / 506 |

### Per-rule

| Rule | Precision | Recall | Fired | Labeled | Correct |
| --- | --- | --- | --- | --- | --- |
| slipped_close_date | 1.000 | 1.000 | 28 | 28 | 28 |
| stalled_in_stage | 1.000 | 1.000 | 18 | 18 | 18 |
| commit_low_meddpicc | 0.630 | 0.708 | 27 | 24 | 17 |
| late_stage_no_economic_buyer | 0.571 | 1.000 | 14 | 8 | 8 |
| premature_deep_discount | 0.500 | 1.000 | 18 | 9 | 9 |
| imminent_close_no_paper_process | 0.905 | 1.000 | 21 | 19 | 19 |
