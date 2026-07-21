# Eval — region-AGNOSTIC (naive: one global norm)

`python -m detector.evaluate data/pipeline.csv` — one global stage norm for every region. The data encodes real regional behavior, so a one-size-fits-all detector both over- and under-flags.

### Overall

| Metric | Value |
| --- | --- |
| Precision | 0.741 |
| Recall | 0.988 |
| F1 | 0.847 |
| Confusion (TP / FP / FN / TN) | 83 / 29 / 1 / 487 |

### Per-rule

| Rule | Precision | Recall | Fired | Labeled | Correct |
| --- | --- | --- | --- | --- | --- |
| slipped_close_date | 1.000 | 1.000 | 50 | 50 | 50 |
| stalled_in_stage | 0.784 | 0.741 | 51 | 54 | 40 |
| commit_low_meddpicc | 0.667 | 1.000 | 9 | 6 | 6 |
| late_stage_no_economic_buyer | 0.800 | 1.000 | 15 | 12 | 12 |
| premature_deep_discount | 0.588 | 1.000 | 51 | 30 | 30 |
| imminent_close_no_paper_process | 0.889 | 1.000 | 9 | 8 | 8 |
