"""MCP server exposing the deterministic Forecast Anomaly Detector.

Any MCP client (Claude Desktop, Claude Code, a custom agent) can interrogate the
pipeline conversationally -- "how's EMEA looking?", "what's the risk on
D-10023?", "how much Commit is shaky?" -- and the tools answer with structured
JSON. The calling agent narrates; the deterministic rules decide every flag.
That preserves the human-in-the-loop split, and ``narrative.py`` is deliberately
NOT called from inside any tool.

Read-only: no CRM writes, no mutation of the dataset. The pipeline is loaded and
scored once at startup and held in memory. The CSV path comes from the
``FORECAST_CSV`` env var (default: the bundled ``data/pipeline.csv``).

Run it with ``python mcp_server.py`` (or ``make mcp``). The underlying tool
functions are plain callables, so tests import and call them directly rather
than going over the wire.
"""

from __future__ import annotations

import os
from collections import Counter
from dataclasses import asdict
from pathlib import Path

import pandas as pd
from mcp.server.fastmcp import FastMCP

import periods
from detector.engine import load, run
from detector.evaluate import overall_metrics, per_rule_metrics, scorecard_markdown
from detector.rules import RuleHit

mcp = FastMCP("forecast-detector")

_DATA_DIR = Path(__file__).parent / "data"
_DEFAULT_CSV = _DATA_DIR / "pipeline.csv"

# 8 MEDDPICC elements -> their score columns.
_MEDDPICC_COLS = {
    "metrics": "m_metrics",
    "economic_buyer": "m_economic_buyer",
    "decision_criteria": "m_decision_criteria",
    "decision_process": "m_decision_process",
    "paper_process": "m_paper_process",
    "identified_pain": "m_identified_pain",
    "champion": "m_champion",
    "competition": "m_competition",
}

_RISK_EXPOSURE_NOTE = (
    "Reports risk exposure (hygiene/qualification signals), NOT a predicted "
    "attainment or bookings number. The detector flags deals to inspect; it does "
    "not forecast what will close."
)


# --------------------------------------------------------------------------- #
# In-memory state: load + score the pipeline once, reuse for every tool.
# --------------------------------------------------------------------------- #
class _State:
    df: pd.DataFrame | None = None  # region-agnostic scoring (default)
    df_region: pd.DataFrame | None = None  # region-aware scoring (overlay)
    csv_path: Path = _DEFAULT_CSV
    hist: pd.DataFrame | None = None
    targets: pd.DataFrame | None = None


_state = _State()


def _csv_path() -> Path:
    """Resolve the CSV path from ``FORECAST_CSV`` or the bundled default."""
    return Path(os.environ.get("FORECAST_CSV", str(_DEFAULT_CSV)))


def _history_path() -> Path:
    return Path(os.environ.get("FORECAST_HISTORY", str(_DATA_DIR / "history.csv")))


def _targets_path() -> Path:
    return Path(os.environ.get("FORECAST_TARGETS", str(_DATA_DIR / "targets.csv")))


def reload() -> None:
    """(Re)load the pipeline (and history/targets, if present) into memory.

    Scores the pipeline twice -- region-agnostic (default) and with the
    region-aware overlay -- so tools can serve either without re-scoring.
    """
    path = _csv_path()
    _state.csv_path = path
    df = load(path)
    _state.df = run(df)
    _state.df_region = run(df, region_aware=True)
    hp, tp = _history_path(), _targets_path()
    _state.hist = periods.load_history(hp) if hp.exists() else None
    _state.targets = periods.load_targets(tp) if tp.exists() else None


def _df(region_aware: bool = False) -> pd.DataFrame:
    """Return the scored pipeline (region-aware overlay when requested)."""
    if _state.df is None:
        reload()
    frame = _state.df_region if region_aware else _state.df
    assert frame is not None
    return frame


_NO_HISTORY = {"error": "No history data loaded; run `make history` (data/history.csv)."}


def _has_region() -> bool:
    """True when the loaded dataset carries a ``region`` column."""
    return "region" in _df().columns


# --------------------------------------------------------------------------- #
# Serialization helpers -- coerce numpy/pandas scalars to native JSON types.
# --------------------------------------------------------------------------- #
def _region_of(row: pd.Series) -> str | None:
    """The row's region as a plain str, or None if the column is absent/blank."""
    if "region" not in row or pd.isna(row["region"]):
        return None
    return str(row["region"])


def _opt_str(row: pd.Series, key: str) -> str | None:
    """A plain-str column value, or None when the column is absent/blank."""
    if key not in row or pd.isna(row[key]):
        return None
    return str(row[key])


def _opt_num(row: pd.Series, key: str, cast=float):
    """A numeric column value, or None when the column is absent/blank."""
    if key not in row or pd.isna(row[key]):
        return None
    return cast(row[key])


def _firmographics(row: pd.Series) -> dict:
    """Account firmographics (present only if the dataset carries them)."""
    return {
        "industry": _opt_str(row, "industry"),
        "employees": _opt_num(row, "employees", int),
        "account_revenue": _opt_num(row, "account_revenue", int),
        "mrr": _opt_num(row, "mrr", float),
    }


def _compact_deal(row: pd.Series) -> dict:
    """A small deal summary safe to return in a list."""
    return {
        "deal_id": str(row["deal_id"]),
        "account": str(row["account"]),
        "region": _region_of(row),
        "segment": str(row["segment"]),
        "industry": _opt_str(row, "industry"),
        "mrr": _opt_num(row, "mrr", float),
        "stage": str(row["stage"]),
        "forecast_category": str(row["forecast_category"]),
        "arr": float(row["arr"]),
        "close_date": str(row["close_date"]) if "close_date" in row else None,
        "risk_score": int(row["risk_score"]),
        "predicted_anomaly": bool(row["predicted_anomaly"]),
        "top_reason": str(row["top_reason"]) if row["top_reason"] else "",
    }


def _hits_of(row: pd.Series) -> list[RuleHit]:
    """The row's rule hits (already a list of RuleHit from the engine)."""
    return list(row["hits"])


def _top_rule_counts(sub: pd.DataFrame, n: int = 3) -> list[dict]:
    """Top ``n`` anomaly rule ids by how many flagged deals carry them."""
    counter: Counter[str] = Counter()
    for hits in sub.loc[sub["predicted_anomaly"], "hits"]:
        for hit in hits:
            counter[hit.rule_id] += 1
    return [{"rule_id": rid, "count": int(c)} for rid, c in counter.most_common(n)]


def _rule_slice(sub: pd.DataFrame, rule_id: str) -> dict:
    """Count and ARR of deals in ``sub`` that fired ``rule_id``."""
    mask = sub["hits"].apply(lambda hs: any(h.rule_id == rule_id for h in hs))
    return {"count": int(mask.sum()), "arr": float(sub.loc[mask, "arr"].sum())}


def _rollup(sub: pd.DataFrame) -> dict:
    """Shared risk-exposure roll-up for a segment or region slice."""
    flagged_mask = sub["predicted_anomaly"]
    commit_mask = sub["forecast_category"] == "Commit"
    commit_arr = float(sub.loc[commit_mask, "arr"].sum())
    at_risk_commit_arr = float(sub.loc[commit_mask & flagged_mask, "arr"].sum())
    return {
        "deals": int(len(sub)),
        "flagged": int(flagged_mask.sum()),
        "total_arr": float(sub["arr"].sum()),
        "at_risk_arr": float(sub.loc[flagged_mask, "arr"].sum()),
        "commit_arr": commit_arr,
        "at_risk_commit_arr": at_risk_commit_arr,
        "at_risk_pct_of_commit": (
            round(100 * at_risk_commit_arr / commit_arr, 1) if commit_arr else 0.0
        ),
        "top_reasons": _top_rule_counts(sub),
        "avg_meddpicc_confidence": (
            round(float(sub["meddpicc_confidence"].mean()), 1) if len(sub) else 0.0
        ),
        "note": _RISK_EXPOSURE_NOTE,
    }


# --------------------------------------------------------------------------- #
# Tools -- crisp docstrings; the agent reads these to pick a tool.
# --------------------------------------------------------------------------- #
@mcp.tool()
def list_deals(
    segment: str | None = None,
    region: str | None = None,
    stage: str | None = None,
    industry: str | None = None,
    rep: str | None = None,
    flagged_only: bool = False,
    limit: int = 25,
    region_aware: bool = False,
) -> list[dict] | dict:
    """List pipeline deals, optionally filtered, highest risk first.

    Use to browse or narrow the pipeline before drilling in. Any filter left as
    None is ignored (segment, region, stage, industry, rep). Set
    flagged_only=True to see only at-risk deals. Set region_aware=True to score
    with the per-region threshold overlay (US flags stalls sooner, EMEA proposals
    get slack, APAC tolerates early discounts). Returns up to `limit` compact deal
    summaries (deal_id, account, region, segment, industry, mrr, stage,
    forecast_category, arr, risk_score, predicted_anomaly, top_reason).
    """
    try:
        df = _df(region_aware)
        if region is not None and not _has_region():
            return {"error": "No 'region' column in this dataset; run `make data`."}
        mask = pd.Series(True, index=df.index)
        if segment is not None:
            mask &= df["segment"] == segment
        if region is not None:
            mask &= df["region"] == region
        if stage is not None:
            mask &= df["stage"] == stage
        if industry is not None:
            if "industry" not in df.columns:
                return {"error": "No 'industry' column in this dataset; run `make data`."}
            mask &= df["industry"] == industry
        if rep is not None:
            mask &= df["rep"] == rep
        if flagged_only:
            mask &= df["predicted_anomaly"]
        sub = df[mask].sort_values("risk_score", ascending=False).head(int(limit))
        return [_compact_deal(row) for _, row in sub.iterrows()]
    except Exception as exc:  # noqa: BLE001 - tools never raise
        return {"error": str(exc)}


@mcp.tool()
def assess_deal(deal_id: str, region_aware: bool = False) -> dict:
    """Full risk picture for one deal by its deal_id (e.g. "D-10023").

    Returns identity, ARR, stage, forecast_category, meddpicc_confidence, the 8
    MEDDPICC element scores, the list of rule `hits` (rule_id, severity, reason),
    risk_score, and predicted_anomaly. Set region_aware=True to apply the
    per-region threshold overlay. Returns {"error": ...} if not found.
    """
    try:
        df = _df(region_aware)
        matches = df[df["deal_id"] == deal_id]
        if matches.empty:
            return {"error": f"deal_id {deal_id!r} not found"}
        row = matches.iloc[0]
        return {
            "deal_id": str(row["deal_id"]),
            "account": str(row["account"]),
            "region": _region_of(row),
            "segment": str(row["segment"]),
            **_firmographics(row),
            "stage": str(row["stage"]),
            "forecast_category": str(row["forecast_category"]),
            "arr": float(row["arr"]),
            "meddpicc_confidence": int(row["meddpicc_confidence"]),
            "meddpicc": {el: int(row[col]) for el, col in _MEDDPICC_COLS.items()},
            "hits": [asdict(hit) for hit in _hits_of(row)],
            "risk_score": int(row["risk_score"]),
            "predicted_anomaly": bool(row["predicted_anomaly"]),
        }
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


@mcp.tool()
def assess_segment(segment: str, region_aware: bool = False) -> dict:
    """Risk-exposure roll-up for a segment (Enterprise / Mid-Market / SMB).

    Returns deals, flagged, total_arr, at_risk_arr, commit_arr,
    at_risk_pct_of_commit (share of Commit ARR that is flagged), top_reasons
    (top 3 anomaly types by count), and avg_meddpicc_confidence. Set
    region_aware=True to apply the per-region threshold overlay. This is risk
    exposure, not a predicted attainment/bookings number.
    """
    try:
        df = _df(region_aware)
        sub = df[df["segment"] == segment]
        if sub.empty:
            return {"error": f"no deals in segment {segment!r}"}
        return {"segment": segment, **_rollup(sub)}
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


@mcp.tool()
def assess_region(region: str, region_aware: bool = False) -> dict:
    """Risk-exposure roll-up for a region (NA / EMEA / APAC / LATAM).

    Same shape as assess_segment: deals, flagged, ARR totals, at_risk_pct_of_commit,
    top_reasons, avg_meddpicc_confidence. Set region_aware=True to score with the
    per-region threshold overlay. Reports risk exposure, not a predicted
    attainment number. Returns {"error": ...} if the dataset has no region column.
    """
    try:
        if not _has_region():
            return {"error": "No 'region' column in this dataset; run `make data`."}
        df = _df(region_aware)
        sub = df[df["region"] == region]
        if sub.empty:
            return {"error": f"no deals in region {region!r}"}
        return {"region": region, **_rollup(sub)}
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


@mcp.tool()
def forecast_summary(forecast_category: str | None = None, region_aware: bool = False) -> dict:
    """How much forecast exposure is actually shaky, across the pipeline.

    Optionally filter to one forecast_category (Commit / Best Case / Pipeline /
    Omitted). Returns total_arr and flagged_arr for the slice plus the count and
    ARR of the two most forecast-damaging anomalies -- commit_low_meddpicc and
    imminent_close_no_paper_process -- so an agent can quantify at-risk Commit.
    Set region_aware=True to apply the per-region threshold overlay.
    """
    try:
        df = _df(region_aware)
        sub = df if forecast_category is None else df[df["forecast_category"] == forecast_category]
        flagged_mask = sub["predicted_anomaly"]
        return {
            "forecast_category": forecast_category or "ALL",
            "deals": int(len(sub)),
            "total_arr": float(sub["arr"].sum()),
            "flagged_arr": float(sub.loc[flagged_mask, "arr"].sum()),
            "commit_low_meddpicc": _rule_slice(sub, "commit_low_meddpicc"),
            "imminent_close_no_paper_process": _rule_slice(sub, "imminent_close_no_paper_process"),
            "note": _RISK_EXPOSURE_NOTE,
        }
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


@mcp.tool()
def get_scorecard(region_aware: bool = False) -> dict:
    """The detector's own accuracy vs. ground-truth labels, for self-caveating.

    Use when asked "how confident/reliable are you?". Returns overall precision,
    recall, F1 and confusion counts, plus per-rule precision and recall. Note
    that some rules trade precision for recall by design (see the reason text).
    region_aware=True scores with the per-region overlay (the labels are
    region-agnostic, so region-aware precision rises and recall dips slightly).
    """
    try:
        df = _df(region_aware)
        om = overall_metrics(df)
        rules = per_rule_metrics(df)
        return {
            "overall": {
                "precision": round(om.precision, 3),
                "recall": round(om.recall, 3),
                "f1": round(om.f1, 3),
                "tp": om.tp,
                "fp": om.fp,
                "fn": om.fn,
                "tn": om.tn,
            },
            "per_rule": [
                {
                    "rule_id": rm.rule_id,
                    "precision": round(rm.precision, 3),
                    "recall": round(rm.recall, 3),
                    "fired": rm.fired,
                    "labeled": rm.labeled,
                    "correct": rm.correct,
                }
                for rm in rules
            ],
            "note": "Computed on the bundled labeled dataset (all data synthetic).",
        }
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


@mcp.tool()
def list_regions() -> list[str] | dict:
    """Distinct region values present, so an agent can pick a valid filter."""
    try:
        if not _has_region():
            return {"error": "No 'region' column in this dataset; run `make data`."}
        return sorted(str(r) for r in _df()["region"].dropna().unique())
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


@mcp.tool()
def list_segments() -> list[str] | dict:
    """Distinct segment values present, so an agent can pick a valid filter."""
    try:
        return sorted(str(s) for s in _df()["segment"].dropna().unique())
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


@mcp.tool()
def list_industries() -> list[str] | dict:
    """Distinct industry values present, so an agent can pick a valid filter."""
    try:
        df = _df()
        if "industry" not in df.columns:
            return {"error": "No 'industry' column in this dataset; run `make data`."}
        return sorted(str(s) for s in df["industry"].dropna().unique())
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


# --------------------------------------------------------------------------- #
# Time-period tools: current-period rollups + historical comparisons.
# --------------------------------------------------------------------------- #
@mcp.tool()
def bookings_rollup(
    grain: str = "quarter", region: str | None = None, region_aware: bool = False
) -> dict:
    """Projected bookings for the CURRENT in-progress month or quarter.

    grain is "month" or "quarter". Returns won-so-far this period + risk-adjusted
    expected-to-close from open deals closing in the period = projected_bookings,
    plus quota and projected_attainment_pct, and prior-period / year-ago actuals
    for context. This is the answer to "how much will <region> book this
    month/quarter?". Note: the period is in progress, so read attainment as pace.
    region_aware=True applies the per-region threshold overlay to the risk
    adjustment.
    """
    try:
        if grain not in ("month", "quarter"):
            return {"error": "grain must be 'month' or 'quarter'"}
        if region is not None and not _has_region():
            return {"error": "No 'region' column in this dataset; run `make data`."}
        return periods.bookings_rollup(
            _df(region_aware), grain, region, targets=_state.targets, hist=_state.hist
        )
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


@mcp.tool()
def pipeline_by_period(
    grain: str = "quarter", region: str | None = None, region_aware: bool = False
) -> dict:
    """Break the pipeline into calendar periods by each deal's close_date.

    grain is "month" or "quarter". Each period returns won ARR, open ARR,
    stage-weighted open ARR, risk-adjusted open ARR, flagged open ARR and
    open-deal count, with the current period flagged. Use to see how bookings are
    distributed across upcoming periods, not just the current one. region_aware=True
    applies the per-region threshold overlay.
    """
    try:
        if grain not in ("month", "quarter"):
            return {"error": "grain must be 'month' or 'quarter'"}
        if region is not None and not _has_region():
            return {"error": "No 'region' column in this dataset; run `make data`."}
        return {
            "grain": grain,
            "region": region or "ALL",
            "periods": periods.pipeline_by_period(_df(region_aware), grain, region),
        }
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


@mcp.tool()
def bookings_history(grain: str = "quarter", region: str | None = None, last_n: int = 8) -> dict:
    """Historical ACTUAL bookings by period (for YoY / QoQ / MoM baselines).

    grain is "month", "quarter", or "year". Returns the last `last_n` completed
    periods with bookings, quota, attainment_pct and deals_won. region=None
    aggregates across all regions. Use this to ground trend questions in actuals.
    """
    try:
        if _state.hist is None:
            return _NO_HISTORY
        if grain not in periods.GRAINS:
            return {"error": f"grain must be one of {periods.GRAINS}"}
        return {
            "grain": grain,
            "region": region or "ALL",
            "periods": periods.history_by_grain(_state.hist, grain, region, last_n),
        }
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


@mcp.tool()
def period_comparison(grain: str = "quarter", region: str | None = None) -> dict:
    """MoM / QoQ / YoY change for the latest COMPLETED period, from actuals.

    grain is "month" (MoM), "quarter" (QoQ), or "year" (YoY) for the sequential
    delta; the year-over-year delta is always included too. Returns the latest
    period's bookings and attainment, the prior period, and the same period a
    year earlier, with percent changes. Pair with bookings_rollup to compare the
    in-progress period against history.
    """
    try:
        if _state.hist is None:
            return _NO_HISTORY
        if grain not in periods.GRAINS:
            return {"error": f"grain must be one of {periods.GRAINS}"}
        return periods.comparisons(_state.hist, grain, region)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


# --------------------------------------------------------------------------- #
# Resources (nice-to-have): readable without a tool call.
# --------------------------------------------------------------------------- #
@mcp.resource("forecast://scorecard")
def scorecard_resource() -> str:
    """Markdown eval scorecard for the loaded dataset."""
    return scorecard_markdown(_df())


@mcp.resource("forecast://dataset")
def dataset_resource() -> str:
    """Small metadata summary of the loaded pipeline (counts + source path)."""
    df = _df()
    flagged = int(df["predicted_anomaly"].sum())
    lines = [
        f"source: {_state.csv_path}",
        f"deals: {len(df)}",
        f"flagged: {flagged}",
        f"total_arr: {float(df['arr'].sum()):.0f}",
        f"regions: {'present' if _has_region() else 'absent'}",
    ]
    return "\n".join(lines)


# Load and score once at import so both the server and the tests share state.
try:  # pragma: no cover - startup convenience; tools re-check via _df()
    reload()
except Exception:  # noqa: BLE001 - defer errors to individual tool calls
    _state.df = None


if __name__ == "__main__":
    mcp.run()
