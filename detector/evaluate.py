"""Score the detector against the dataset's ground-truth labels.

Compares the engine's ``predicted_anomaly`` to the ``is_anomaly`` column for
overall precision / recall / F1 and a confusion count, then breaks precision and
recall down per rule against the ``anomaly_types`` label column -- i.e. when a
rule fires, does the deal actually carry that rule's id, and of the deals that
truly carry it, how many did the rule catch.

Labels are read here only; they never reach :mod:`detector.rules`.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from detector.engine import run_path
from detector.rules import RuleHit

# Canonical anomaly vocabulary; each id maps 1:1 to a rule and a label.
ANOMALY_TYPES = [
    "slipped_close_date",
    "stalled_in_stage",
    "commit_low_meddpicc",
    "late_stage_no_economic_buyer",
    "premature_deep_discount",
    "imminent_close_no_paper_process",
]


@dataclass(frozen=True)
class OverallMetrics:
    """Binary anomaly-vs-clean scorecard."""

    precision: float
    recall: float
    f1: float
    tp: int
    fp: int
    fn: int
    tn: int


@dataclass(frozen=True)
class RuleMetrics:
    """One rule's precision/recall against its own labeled type."""

    rule_id: str
    precision: float
    recall: float
    fired: int  # deals this rule fired on
    labeled: int  # deals truly carrying this id
    correct: int  # fired AND carrying the id


def _safe_div(num: int, den: int) -> float:
    """Return num/den, or 0.0 when the denominator is zero."""
    return num / den if den else 0.0


def _label_set(cell: object) -> set[str]:
    """Parse a pipe-delimited ``anomaly_types`` cell into a set of ids."""
    if cell is None or (isinstance(cell, float) and pd.isna(cell)):
        return set()
    text = str(cell).strip()
    return {part for part in text.split("|") if part} if text else set()


def _fired_ids(hits: list[RuleHit]) -> set[str]:
    """The set of rule ids present in a row's hits."""
    return {hit.rule_id for hit in hits}


def overall_metrics(scored: pd.DataFrame) -> OverallMetrics:
    """Precision/recall/F1 and confusion counts from a scored frame."""
    truth = scored["is_anomaly"].astype(bool)
    pred = scored["predicted_anomaly"].astype(bool)
    tp = int((truth & pred).sum())
    fp = int((~truth & pred).sum())
    fn = int((truth & ~pred).sum())
    tn = int((~truth & ~pred).sum())
    precision = _safe_div(tp, tp + fp)
    recall = _safe_div(tp, tp + fn)
    f1 = _safe_div(2 * precision * recall, precision + recall)
    return OverallMetrics(precision, recall, f1, tp, fp, fn, tn)


def per_rule_metrics(scored: pd.DataFrame) -> list[RuleMetrics]:
    """Per-rule precision and recall against the ``anomaly_types`` labels."""
    fired_sets = scored["hits"].apply(_fired_ids)
    label_sets = scored["anomaly_types"].apply(_label_set)
    results: list[RuleMetrics] = []
    for rule_id in ANOMALY_TYPES:
        fired = fired_sets.apply(lambda ids, rid=rule_id: rid in ids)
        labeled = label_sets.apply(lambda ids, rid=rule_id: rid in ids)
        correct = int((fired & labeled).sum())
        n_fired = int(fired.sum())
        n_labeled = int(labeled.sum())
        results.append(
            RuleMetrics(
                rule_id=rule_id,
                precision=_safe_div(correct, n_fired),
                recall=_safe_div(correct, n_labeled),
                fired=n_fired,
                labeled=n_labeled,
                correct=correct,
            )
        )
    return results


def scorecard_markdown(scored: pd.DataFrame) -> str:
    """Return a markdown scorecard block suitable for pasting into the README."""
    om = overall_metrics(scored)
    rules = per_rule_metrics(scored)
    lines = [
        "### Overall",
        "",
        "| Metric | Value |",
        "| --- | --- |",
        f"| Precision | {om.precision:.3f} |",
        f"| Recall | {om.recall:.3f} |",
        f"| F1 | {om.f1:.3f} |",
        f"| Confusion (TP / FP / FN / TN) | {om.tp} / {om.fp} / {om.fn} / {om.tn} |",
        "",
        "### Per-rule",
        "",
        "| Rule | Precision | Recall | Fired | Labeled | Correct |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for rm in rules:
        lines.append(
            f"| {rm.rule_id} | {rm.precision:.3f} | {rm.recall:.3f} | "
            f"{rm.fired} | {rm.labeled} | {rm.correct} |"
        )
    return "\n".join(lines)


def scorecard_text(scored: pd.DataFrame) -> str:
    """Return a clean fixed-width scorecard for terminal output."""
    om = overall_metrics(scored)
    rules = per_rule_metrics(scored)
    total = len(scored)
    out: list[str] = []
    out.append("=" * 68)
    out.append("  FORECAST ANOMALY DETECTOR — EVALUATION")
    out.append("=" * 68)
    out.append(f"  Deals scored: {total}")
    out.append("")
    out.append("  Overall")
    out.append("  -------")
    out.append(f"    Precision : {om.precision:.3f}")
    out.append(f"    Recall    : {om.recall:.3f}")
    out.append(f"    F1        : {om.f1:.3f}")
    out.append("")
    out.append(f"    Confusion : TP={om.tp}  FP={om.fp}  FN={om.fn}  TN={om.tn}")
    out.append("")
    out.append("  Per-rule (against anomaly_types ground truth)")
    out.append("  ---------------------------------------------")
    header = f"    {'rule_id':<32}{'prec':>6}{'recall':>8}{'fired':>7}{'label':>7}"
    out.append(header)
    out.append(f"    {'-' * 58}")
    for rm in rules:
        out.append(
            f"    {rm.rule_id:<32}{rm.precision:>6.2f}{rm.recall:>8.2f}"
            f"{rm.fired:>7}{rm.labeled:>7}"
        )
    out.append("=" * 68)
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    """CLI: ``python -m detector.evaluate <pipeline.csv>``."""
    args = sys.argv[1:] if argv is None else argv
    path = Path(args[0]) if args else Path("data/pipeline.csv")
    if not path.exists():
        print(f"error: {path} not found", file=sys.stderr)
        return 1
    scored = run_path(path)
    print(scorecard_text(scored))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
