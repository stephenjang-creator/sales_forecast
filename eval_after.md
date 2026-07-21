# Eval — region-AWARE (each region's own norms)

`python -m detector.evaluate data/pipeline.csv --region-aware` — staleness judged against each region's typical stage duration, APAC's early discounts treated as normal. Recommended mode for regional data.

### Overall

| Metric | Value |
| --- | --- |
| Precision | 0.929 |
| Recall | 1.000 |
| F1 | 0.963 |
| Confusion (TP / FP / FN / TN) | 79 / 6 / 0 / 515 |

### Per-rule

| Rule | Precision | Recall | Fired | Labeled | Correct |
| --- | --- | --- | --- | --- | --- |
| slipped_close_date | 1.000 | 1.000 | 17 | 17 | 17 |
| stalled_in_stage | 1.000 | 1.000 | 21 | 21 | 21 |
| commit_low_meddpicc | 0.735 | 1.000 | 34 | 25 | 25 |
| late_stage_no_economic_buyer | 0.818 | 1.000 | 11 | 9 | 9 |
| premature_deep_discount | 0.538 | 1.000 | 13 | 7 | 7 |
| imminent_close_no_paper_process | 0.905 | 1.000 | 21 | 19 | 19 |
