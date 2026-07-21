"""Run the rule registry over a pipeline DataFrame.

Pure and offline: :func:`run` reads the columns produced by
``generate_forecast_data.py``, applies every rule in
:data:`detector.rules.ALL_RULES` to each row, and returns the frame with risk
columns appended. No rows are dropped -- the evaluator needs the clean deals
too.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

import config
from detector.rules import ALL_RULES, RuleHit


def evaluate_row(row: dict) -> list[RuleHit]:
    """Apply every registered rule to one row; return the hits it produced."""
    hits: list[RuleHit] = []
    for rule in ALL_RULES:
        hit = rule(row)
        if hit is not None:
            hits.append(hit)
    return hits


def _risk_score(hits: list[RuleHit]) -> int:
    """Sum severity weights across a deal's hits."""
    return sum(config.SEVERITY[hit.severity] for hit in hits)


def _top_reason(hits: list[RuleHit]) -> str:
    """Reason from the highest-severity hit (first one wins a tie)."""
    if not hits:
        return ""
    top = max(hits, key=lambda hit: config.SEVERITY[hit.severity])
    return top.reason


def run(df: pd.DataFrame) -> pd.DataFrame:
    """Score every deal in ``df``.

    Appends four columns and returns a copy (flagged and unflagged rows alike):
        hits: list[RuleHit] fired for the deal (possibly empty).
        risk_score: int, summed severity weights of those hits.
        predicted_anomaly: bool, True when at least one rule fired.
        top_reason: str, the highest-severity hit's reason ('' if none).
    """
    out = df.copy()
    all_hits = [evaluate_row(row) for row in out.to_dict("records")]
    out["hits"] = all_hits
    out["risk_score"] = [_risk_score(hits) for hits in all_hits]
    out["predicted_anomaly"] = [len(hits) > 0 for hits in all_hits]
    out["top_reason"] = [_top_reason(hits) for hits in all_hits]
    return out


def load(source: str | Path) -> pd.DataFrame:
    """Load a pipeline CSV into a DataFrame (no scoring applied).

    Accepts a path or any file-like object ``pandas.read_csv`` understands.
    The ``region`` code ``"NA"`` (North America) collides with pandas' default
    NaN sentinel and is otherwise silently dropped on read; since the column has
    no genuinely-missing values, any NaN there is restored to ``"NA"``.
    """
    df = pd.read_csv(source)
    if "region" in df.columns:
        df["region"] = df["region"].fillna("NA")
    return df


def run_path(path: str | Path) -> pd.DataFrame:
    """Convenience: load a CSV and score it in one call."""
    return run(load(path))
