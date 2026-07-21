# Eval — BEFORE tuning

`python -m detector.evaluate data/pipeline.csv` on the bundled labeled set.

### Overall

| Metric | Value |
| --- | --- |
| Precision | 0.887 |
| Recall | 0.925 |
| F1 | 0.905 |
| Confusion (TP / FP / FN / TN) | 86 / 11 / 7 / 496 |

### Per-rule

| Rule | Precision | Recall | Fired | Labeled | Correct |
| --- | --- | --- | --- | --- | --- |
| slipped_close_date | 1.000 | 1.000 | 20 | 20 | 20 |
| stalled_in_stage | 1.000 | 0.600 | 15 | 25 | 15 |
| commit_low_meddpicc | 0.688 | 0.957 | 32 | 23 | 22 |
| late_stage_no_economic_buyer | 0.765 | 1.000 | 17 | 13 | 13 |
| premature_deep_discount | 0.462 | 1.000 | 26 | 12 | 12 |
| imminent_close_no_paper_process | 1.000 | 1.000 | 25 | 25 | 25 |
