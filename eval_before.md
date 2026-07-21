# Eval — region-AGNOSTIC (naive: one global norm)

`python -m detector.evaluate data/pipeline.csv` — one global stage norm for every region. The data encodes real regional behavior, so a one-size-fits-all detector both over- and under-flags.

### Overall

| Metric | Value |
| --- | --- |
| Precision | 0.736 |
| Recall | 0.964 |
| F1 | 0.835 |
| Confusion (TP / FP / FN / TN) | 81 / 29 / 3 / 487 |

### Per-rule

| Rule | Precision | Recall | Fired | Labeled | Correct |
| --- | --- | --- | --- | --- | --- |
| slipped_close_date | 1.000 | 1.000 | 23 | 23 | 23 |
| stalled_in_stage | 0.542 | 0.684 | 24 | 19 | 13 |
| commit_low_meddpicc | 0.714 | 0.909 | 28 | 22 | 20 |
| late_stage_no_economic_buyer | 0.857 | 1.000 | 14 | 12 | 12 |
| premature_deep_discount | 0.300 | 1.000 | 30 | 9 | 9 |
| imminent_close_no_paper_process | 0.909 | 0.952 | 22 | 21 | 20 |
