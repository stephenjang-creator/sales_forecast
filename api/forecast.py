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

import pandas as pd

import config
import periods
from detector.engine import load, run
from detector.evaluate import overall_metrics, per_rule_metrics
from detector.plays import PLAYBOOK, VALUE_TOUCH_PLAY
from detector.rules import RuleHit

_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
_DEFAULT_CSV = _DATA_DIR / "pipeline.csv"

REGION_ORDER = ["NAM", "EMEA", "APAC", "LATAM"]

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


def _close_date(value) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10])
    except (ValueError, TypeError):
        return None


def _close_str(value) -> str | None:
    d = _close_date(value)
    return f"{d:%b} {d.day}, {d.year}" if d else None  # portable (no %-d)


def _deal_dict(row) -> dict:
    hits = list(row["hits"])
    risk = _risk_0_9(int(row["risk_score"]))
    arr = float(row["arr"])
    mrr = float(row["mrr"]) if "mrr" in row and row["mrr"] == row["mrr"] else round(arr / 12)
    nm = row.get("next_meeting_date")
    stage = str(row["stage"])
    fc = str(row["forecast_category"])
    return {
        "id": str(row["deal_id"]),
        "account": str(row["account"]),
        "region": str(row["region"]),
        "segment": str(row["segment"]),
        "industry": str(row.get("industry", "")),
        "stage": stage,
        "stageRank": config.STAGE_ORDER.get(stage, 99),
        "fc": fc,
        "fcRank": config.FORECAST_ORDER.get(fc, 99),
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
        "closeISO": (cd.isoformat() if (cd := _close_date(row.get("close_date"))) else None),
        "nextMeeting": (None if nm is None or nm != nm else str(nm)),
        "rules": _rule_dicts(hits),
        "closed": fc == "Closed",  # Closed Won: booked, no risk, no action
    }


def flagged_deals() -> list[dict]:
    """Every flagged (at-risk) deal, richest first, as UI dicts."""
    df = _scored()
    flagged = df[df["predicted_anomaly"]].sort_values("risk_score", ascending=False)
    return [_deal_dict(row) for _, row in flagged.iterrows()]


def booked_deals() -> list[dict]:
    """Closed Won deals -- booked revenue for the period, richest first.

    These are done: no anomaly can fire on a closed deal, so they carry no risk
    and need no action. They still count toward the period forecast, which is why
    the dashboard shows them (highlighted) rather than hiding them.
    """
    df = _scored()
    won = df[df["stage"] == "Closed Won"].sort_values("arr", ascending=False)
    return [_deal_dict(row) for _, row in won.iterrows()]


def _booked_totals() -> tuple[float, int]:
    """(booked ARR, deal count) for Closed Won -- the locked part of the forecast."""
    df = _scored()
    won = df[df["stage"] == "Closed Won"]
    return float(won["arr"].sum()), int(len(won))


def _shift_month(year: int, month: int, delta: int) -> tuple[int, int]:
    """(year, month) shifted by ``delta`` months (handles year rollover)."""
    idx = year * 12 + (month - 1) + delta
    return idx // 12, idx % 12 + 1


def _won_frame():
    df = _scored()
    won = df[df["stage"] == "Closed Won"].copy()
    won["_cd"] = pd.to_datetime(won["close_date"])
    return won


def bookings_summary() -> dict:
    """Booked (Closed Won) revenue over time, for YoY / QoQ / MoM / YTD.

    Returns the booked series at month/quarter/year grain plus period-over-period
    deltas: MoM and QoQ compare the latest *complete* period to the one before
    (the current period is still in progress), YoY compares the last two complete
    years, and YTD compares this calendar year through today against the same
    window last year. All computed from the closed-won deals in the pipeline.
    """
    won = _won_frame()
    today = date.today()

    def keys(d: date) -> tuple[str, str, str]:
        return (f"{d.year}-{d.month:02d}", f"{d.year}-Q{(d.month - 1) // 3 + 1}", f"{d.year}")

    month: dict[str, list] = {}
    quarter: dict[str, list] = {}
    year: dict[str, list] = {}
    for _, r in won.iterrows():
        arr = float(r["arr"])
        mk, qk, yk = keys(r["_cd"].date())
        for store, k in ((month, mk), (quarter, qk), (year, yk)):
            b = store.setdefault(k, [0.0, 0])
            b[0] += arr
            b[1] += 1

    def series(store: dict) -> list[dict]:
        return [
            {"period": k, "booked": round(store[k][0]), "deals": store[k][1]} for k in sorted(store)
        ]

    def delta(store: dict, cur_key: str, prior_key: str, cur_label=None) -> dict:
        cur = store.get(cur_key, [0.0, 0])
        prior = store.get(prior_key, [0.0, 0])
        return {
            "period": cur_label or cur_key,
            "booked": round(cur[0]),
            "priorPeriod": prior_key,
            "priorBooked": round(prior[0]),
            "pct": periods._pct_change(cur[0], prior[0]),
            "deals": cur[1],
        }

    # MoM/QoQ: latest COMPLETE period (current is partial) vs the one before.
    lc_y, lc_m = _shift_month(today.year, today.month, -1)
    p_y, p_m = _shift_month(today.year, today.month, -2)
    mom = delta(month, f"{lc_y}-{lc_m:02d}", f"{p_y}-{p_m:02d}")
    cur_q = (today.month - 1) // 3 + 1
    lcq_y, lcq = (today.year, cur_q - 1) if cur_q > 1 else (today.year - 1, 4)
    pq_y, pq = (lcq_y, lcq - 1) if lcq > 1 else (lcq_y - 1, 4)
    qoq = delta(quarter, f"{lcq_y}-Q{lcq}", f"{pq_y}-Q{pq}")
    yoy = delta(year, str(today.year - 1), str(today.year - 2))

    # YTD: this calendar year through today vs the same window last year.
    def ytd_between(y: int) -> float:
        cd = won["_cd"]
        m = (cd >= pd.Timestamp(y, 1, 1)) & (cd <= pd.Timestamp(y, today.month, today.day))
        return float(won.loc[m, "arr"].sum())

    ytd_cur, ytd_prior = ytd_between(today.year), ytd_between(today.year - 1)
    ytd = {
        "period": f"{today.year} YTD",
        "booked": round(ytd_cur),
        "priorPeriod": f"{today.year - 1} YTD",
        "priorBooked": round(ytd_prior),
        "pct": periods._pct_change(ytd_cur, ytd_prior),
    }

    return {
        "series": {"month": series(month), "quarter": series(quarter), "year": series(year)},
        "ytd": ytd,
        "mom": mom,
        "qoq": qoq,
        "yoy": yoy,
        "asOf": today.isoformat(),
    }


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

    # The Booked KPI + booked narrative clause are timeframe-scoped, so the client
    # composes them from bookedDeals + the header timeframe control. The server
    # owns the open-pipeline tiles and the open-pipeline half of the narrative.
    kpis = [
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
        f"{money(flagged_arr)} of open pipeline is flagged across {total_flagged} of "
        f"{total_deals} deals; {money(at_risk_arr)} of Commit + Best Case is at risk across "
        f"{len(at_risk)} — {top_region[0]} carries the most exposure at "
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
    scored = _scored()
    has_region = "region" in scored.columns
    by_region = (
        {r: periods.pipeline_by_period(scored, "month", r) for r in REGION_ORDER}
        if has_region
        else {}
    )
    return {
        "deals": deals,
        "bookedDeals": booked_deals(),
        "bookings": bookings_summary(),
        "pipelineByMonth": periods.pipeline_by_period(scored, "month"),
        "pipelineByMonthByRegion": by_region,
        **kpis_and_summary(deals),
        "fastMover": fast_mover(),
        "scorecard": scorecard(),
        "regionOrder": REGION_ORDER,
        "generatedFrom": _csv_path().name,
    }
