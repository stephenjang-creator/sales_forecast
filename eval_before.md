# Eval — region-AGNOSTIC (naive: one global norm)

`python -m detector.evaluate data/pipeline.csv` — the detector using a single global stage norm for every region. The demo data now encodes real regional behavior (US fast, EMEA slow, APAC discounts early), so a one-size-fits-all detector both over- and under-flags.

### Overall

| Metric | Value |
| --- | --- |
| Precision | 0.762 |
| Recall | 0.952 |
| F1 | 0.847 |
| Confusion (TP / FP / FN / TN) | 80 / 25 / 4 / 491 |

### Per-rule

| Rule | Precision | Recall | Fired | Labeled | Correct |
| --- | --- | --- | --- | --- | --- |
| slipped_close_date | 1.000 | 1.000 | 28 | 28 | 28 |
| stalled_in_stage | 0.700 | 0.778 | 20 | 18 | 14 |
| commit_low_meddpicc | 0.630 | 0.708 | 27 | 24 | 17 |
| late_stage_no_economic_buyer | 0.571 | 1.000 | 14 | 8 | 8 |
| premature_deep_discount | 0.310 | 1.000 | 29 | 9 | 9 |
| imminent_close_no_paper_process | 0.905 | 1.000 | 21 | 19 | 19 |
