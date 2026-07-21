# Eval — region-AGNOSTIC (naive: one global norm)

`python -m detector.evaluate data/pipeline.csv` — one global stage norm for every region. The demo data encodes real regional behavior (US fast, EMEA slow, APAC discounts early), so a one-size-fits-all detector both over- and under-flags.

### Overall

| Metric | Value |
| --- | --- |
| Precision | 0.764 |
| Recall | 0.944 |
| F1 | 0.844 |
| Confusion (TP / FP / FN / TN) | 84 / 26 / 5 / 485 |

### Per-rule

| Rule | Precision | Recall | Fired | Labeled | Correct |
| --- | --- | --- | --- | --- | --- |
| slipped_close_date | 1.000 | 1.000 | 23 | 23 | 23 |
| stalled_in_stage | 0.542 | 0.684 | 24 | 19 | 13 |
| commit_low_meddpicc | 0.743 | 1.000 | 35 | 26 | 26 |
| late_stage_no_economic_buyer | 0.750 | 1.000 | 16 | 12 | 12 |
| premature_deep_discount | 0.250 | 1.000 | 32 | 8 | 8 |
| imminent_close_no_paper_process | 0.917 | 0.957 | 24 | 23 | 22 |
