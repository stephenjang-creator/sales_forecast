# Eval — region-AWARE (each region's own norms)

`python -m detector.evaluate data/pipeline.csv --region-aware` — staleness judged against each region's typical stage duration, APAC's early discounts treated as normal. Recommended mode.

### Overall

| Metric | Value |
| --- | --- |
| Precision | 0.922 |
| Recall | 0.988 |
| F1 | 0.954 |
| Confusion (TP / FP / FN / TN) | 83 / 7 / 1 / 509 |

### Per-rule

| Rule | Precision | Recall | Fired | Labeled | Correct |
| --- | --- | --- | --- | --- | --- |
| slipped_close_date | 1.000 | 1.000 | 23 | 23 | 23 |
| stalled_in_stage | 1.000 | 1.000 | 19 | 19 | 19 |
| commit_low_meddpicc | 0.714 | 0.909 | 28 | 22 | 20 |
| late_stage_no_economic_buyer | 0.857 | 1.000 | 14 | 12 | 12 |
| premature_deep_discount | 0.600 | 1.000 | 15 | 9 | 9 |
| imminent_close_no_paper_process | 0.909 | 0.952 | 22 | 21 | 20 |
