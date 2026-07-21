"""Shape the scored pipeline into the payload the Intelligent Forecast UI needs.

Pure read layer over the deterministic detector: loads + scores the pipeline
once, then exposes flagged deals (with owner/manager/MRR/ARR + per-rule reason
and recommended step), KPI tiles, the AI summary line, the model-health
scorecard, and the fast-mover banner. No LLM here -- the rules own every flag.
"""

from __future__ import annotations

import os
from datetime import date
from functools import lru_cache
from pathlib import Path

import config
from detector.engine import load, run
from detector.evaluate import overall_metrics, per_rule_metrics
from detector.plays import PLAYBOOK, VALUE_TOUCH_PLAY
from detector.rules import RuleHit

_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
_DEFAULT_CSV = _DATA_DIR / "pipeline.csv"

REGION_ORDER = ["NA", "EMEA", "APAC", "LATAM"]

# Pretty labels for the rule ids (the raw id is mono-styled in the drawer).
RULE_LABELS = {
    "slipped_close_date": "Slipped close date",
    "stalled_in_stage": "Stalled in stage",
    "commit_low_meddpicc": "Low-confidence Commit",
    "late_stage_no_economic_buyer": "No economic buyer mapped",
    "premature_deep_discount": "Premature deep discount",
    "imminent_close_no_paper_process": "Imminent close, no paper",
    "meeting_at_risk": "Next meeting too far out",
}


def _csv_path() -> Path:
    return Path(os.environ.get("FORECAST_CSV", str(_DEFAULT_CSV)))


@lru_cache(maxsize=1)
def _scored():
    """Load + score the pipeline once (region-agnostic; cached)."""
    return run(load(_csv_path()))


def money(n: float) -> str:
    """'$1.20M' for >= 1e6, else '$830k'."""
    n = float(n or 0)
    return f"${n / 1e6:.2f}M" if n >= 1e6 else f"${round(n / 1000)}k"


def tier_of(risk: int) -> str:
    if risk >= 8:
        return "Critical"
    if risk >= 5:
        return "High"
    if risk >= 3:
        return "Medium"
    return "Low"


def _risk_0_9(risk_score: int) -> int:
    """Map the engine's severity-sum risk_score onto the design's 0-9 scale."""
    return max(0, min(int(risk_score), 9))


def _action_for(rule_id: str) -> str:
    """The one-line recommended step for a rule (from the deterministic playbook)."""
    play = PLAYBOOK.get(rule_id) or (VALUE_TOUCH_PLAY if rule_id == "meeting_at_risk" else None)
    return play.actions[0] if play else "Review with the deal team."


def _rule_dicts(hits: list[RuleHit]) -> list[dict]:
    return [
        {
            "id": h.rule_id,
            "label": RULE_LABELS.get(h.rule_id, h.rule_id),
            "reason": h.reason,
            "action": _action_for(h.rule_id),
        }
        for h in hits
    ]


def _close_str(value) -> str | None:
    try:
        d = date.fromisoformat(str(value)[:10])
    except (ValueError, TypeError):
        return None
    return f"{d:%b} {d.day}, {d.year}"  # portable (no platform-specific %-d)


def _deal_dict(row) -> dict:
    hits = list(row["hits"])
    risk = _risk_0_9(int(row["risk_score"]))
    arr = float(row["arr"])
    mrr = float(row["mrr"]) if "mrr" in row and row["mrr"] == row["mrr"] else round(arr / 12)
    nm = row.get("next_meeting_date")
    return {
        "id": str(row["deal_id"]),
        "account": str(row["account"]),
        "region": str(row["region"]),
        "segment": str(row["segment"]),
        "industry": str(row.get("industry", "")),
        "stage": str(row["stage"]),
        "fc": str(row["forecast_category"]),
        "risk": risk,
        "tier": tier_of(risk),
        "amount": arr,
        "arr": arr,
        "mrr": mrr,
        "amountStr": money(arr),
        "mrrStr": f"${round(mrr):,} MRR",
        "owner": str(row.get("rep", "")),
        "manager": str(row.get("sales_manager", "")),
        "closeDate": _close_str(row.get("close_date")),
        "nextMeeting": (None if nm is None or nm != nm else str(nm)),
        "rules": _rule_dicts(hits),
    }


def flagged_deals() -> list[dict]:
    """Every flagged (at-risk) deal, richest first, as UI dicts."""
    df = _scored()
    flagged = df[df["predicted_anomaly"]].sort_values("risk_score", ascending=False)
    return [_deal_dict(row) for _, row in flagged.iterrows()]


def kpis_and_summary(deals: list[dict]) -> dict:
    """KPI tiles + the AI summary sentence, computed from the flagged deals."""
    total_flagged = len(deals)
    total_deals = len(_scored())
    at_risk = [d for d in deals if d["risk"] >= 5]  # High + Critical
    at_risk_arr = sum(d["arr"] for d in at_risk)
    flagged_arr = sum(d["arr"] for d in deals)
    critical = [d for d in deals if d["risk"] >= 8]

    by_region: dict[str, float] = {}
    for d in at_risk:
        by_region[d["region"]] = by_region.get(d["region"], 0.0) + d["arr"]
    top_region = max(by_region.items(), key=lambda kv: kv[1]) if by_region else ("--", 0.0)

    kpis = [
        {
            "label": "Forecasted, flagged",
            "value": money(flagged_arr),
            "sub": f"{total_flagged} of {total_deals} deals",
            "tone": "muted",
        },
        {
            "label": "At risk (High + Critical)",
            "value": money(at_risk_arr),
            "sub": f"{len(at_risk)} deals",
            "tone": "warning",
        },
        {
            "label": "Critical deals",
            "value": str(len(critical)),
            "sub": "risk 8-9",
            "tone": "critical",
        },
        {
            "label": "Top-exposure region",
            "value": top_region[0],
            "sub": money(top_region[1]),
            "tone": "muted",
        },
    ]
    narrative = (
        f"{money(at_risk_arr)} of Commit + Best Case is flagged across {len(at_risk)} "
        f"at-risk deals — {top_region[0]} carries the most exposure at "
        f"{money(top_region[1])}, driven by low-confidence Commits and slipped close dates."
    )
    return {"kpis": kpis, "narrative": narrative}


def scorecard() -> dict:
    """Model-health tab: overall metrics + per-rule precision/recall."""
    df = _scored()
    om = overall_metrics(df)
    metrics = [
        {"label": "Precision", "value": f"{om.precision:.3f}"},
        {"label": "Recall", "value": f"{om.recall:.3f}"},
        {"label": "F1", "value": f"{om.f1:.3f}"},
        {"label": "TP / FP / FN / TN", "value": f"{om.tp} / {om.fp} / {om.fn} / {om.tn}"},
    ]
    per_rule = [
        {
            "id": rm.rule_id,
            "precision": f"{rm.precision:.3f}",
            "recall": f"{rm.recall:.3f}",
            "fired": rm.fired,
            "labeled": rm.labeled,
            "correct": rm.correct,
        }
        for rm in per_rule_metrics(df)
    ]
    return {"metrics": metrics, "perRule": per_rule}


def fast_mover() -> dict | None:
    """The banner deal: the biggest open fast mover (empowered champion, simple
    process) -- the upside a VP should accelerate this week."""
    df = _scored()
    if "fast_mover" not in df.columns:
        return None
    movers = df[df["fast_mover"] & df["stage"].isin(config.OPEN_STAGES)]
    if movers.empty:
        return None
    row = movers.sort_values("arr", ascending=False).iloc[0]
    d = _deal_dict(row)
    when = d["nextMeeting"] or "no meeting booked yet"
    return {
        **d,
        "meta": f"{d['amountStr']} · {d['fc']} · {d['region']} · {d['segment']}",
        "line": (
            f"Empowered champion and a simple decision process — {d['stage']} and "
            f"cleared to move fast. Next touch: {when}."
        ),
        "note": (
            "One of the cleanest pull-forwards on the board. Confirm the paper "
            "process and one nudge this week can pull the close date in."
        ),
    }


def full_payload() -> dict:
    """Everything the dashboard needs in one call."""
    deals = flagged_deals()
    return {
        "deals": deals,
        **kpis_and_summary(deals),
        "fastMover": fast_mover(),
        "scorecard": scorecard(),
        "regionOrder": REGION_ORDER,
        "generatedFrom": _csv_path().name,
    }
