# Eval — region-AGNOSTIC (naive: one global norm)

`python -m detector.evaluate data/pipeline.csv` — one global stage norm for every region. The demo data encodes real regional behavior (US fast, EMEA slow, APAC discounts early), so a one-size-fits-all detector both over- and under-flags.

### Overall

| Metric | Value |
| --- | --- |
| Precision | 0.763 |
| Recall | 0.937 |
| F1 | 0.841 |
| Confusion (TP / FP / FN / TN) | 74 / 23 / 5 / 498 |

### Per-rule

| Rule | Precision | Recall | Fired | Labeled | Correct |
| --- | --- | --- | --- | --- | --- |
| slipped_close_date | 1.000 | 1.000 | 17 | 17 | 17 |
| stalled_in_stage | 0.611 | 0.524 | 18 | 21 | 11 |
| commit_low_meddpicc | 0.735 | 1.000 | 34 | 25 | 25 |
| late_stage_no_economic_buyer | 0.818 | 1.000 | 11 | 9 | 9 |
| premature_deep_discount | 0.269 | 1.000 | 26 | 7 | 7 |
| imminent_close_no_paper_process | 0.905 | 1.000 | 21 | 19 | 19 |
