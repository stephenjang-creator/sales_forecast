"""Deterministic risk-adjusted expected-bookings baseline.

A transparent, no-LLM heuristic that turns a list of deals (as returned by the
MCP ``list_deals`` tool) into an expected-bookings estimate: stage win-rates give
a weighted pipeline, and deals the detector flagged get an extra haircut. The
attainment agents are handed this number as an anchor, and ``--dry-run`` reports
it directly so the whole flow is verifiable offline.

It is a heuristic, not a forecast of record -- the win-rates and haircut live in
``config.py`` and should be tuned to a real team's historical conversion.
"""

from __future__ import annotations

import config


def _win_rate(stage: str) -> float:
    """Stage conversion probability (0.0 for unknown/closed-lost)."""
    return config.STAGE_WIN_RATE.get(stage, 0.0)


def _adjust(expected: float, arr: float, flagged: bool, fast_mover: bool) -> float:
    """Apply the risk haircut (flagged) or the fast-mover uplift to an open deal.

    Risk dominates: a deal that is both flagged and a fast mover takes the
    haircut. The uplift is capped so expected value never exceeds the deal's ARR.
    """
    if flagged:
        return expected * (1.0 - config.FLAGGED_RISK_HAIRCUT)
    if fast_mover:
        return min(expected * (1.0 + config.FAST_MOVER_UPLIFT), arr)
    return expected


def baseline_from_deals(deals: list[dict]) -> dict:
    """Risk-adjusted expected-bookings estimate from compact deal dicts.

    Each deal needs ``arr``, ``stage``, ``forecast_category`` and
    ``predicted_anomaly`` (exactly the ``list_deals`` shape); the ``signals``
    list, when present, drives the fast-mover uplift. Returns the likely estimate
    plus a low/high band and the intermediate components, so the number is
    auditable.
    """
    open_stages = set(config.OPEN_STAGES)
    open_pipeline_arr = 0.0
    weighted = 0.0  # stage-weighted, before risk/opportunity adjustment
    risk_adjusted = 0.0  # after haircut on flagged + uplift on fast movers
    haircut_arr = 0.0  # total reduction from flagged deals (>= 0)
    uplift_arr = 0.0  # total increase from fast movers (>= 0)
    closed_won_arr = 0.0

    for deal in deals:
        arr = float(deal.get("arr", 0.0) or 0.0)
        stage = str(deal.get("stage", ""))
        flagged = bool(deal.get("predicted_anomaly", False))
        fast_mover = "fast_mover" in (deal.get("signals") or [])
        rate = _win_rate(stage)

        if stage == "Closed Won":
            closed_won_arr += arr
        is_open = stage in open_stages
        if is_open:
            open_pipeline_arr += arr

        expected = arr * rate
        weighted += expected
        adjusted = _adjust(expected, arr, flagged and is_open, fast_mover and is_open)
        if adjusted < expected:
            haircut_arr += expected - adjusted
        elif adjusted > expected:
            uplift_arr += adjusted - expected
        risk_adjusted += adjusted

    band = config.ESTIMATE_BAND
    likely = round(risk_adjusted, 0)
    return {
        "expected_bookings": {
            "low": round(risk_adjusted * (1 - band), 0),
            "likely": likely,
            "high": round(risk_adjusted * (1 + band), 0),
        },
        "open_pipeline_arr": round(open_pipeline_arr, 0),
        "closed_won_arr": round(closed_won_arr, 0),
        "weighted_pipeline_arr": round(weighted, 0),
        "risk_haircut_arr": round(haircut_arr, 0),
        "mover_uplift_arr": round(uplift_arr, 0),
        "method": (
            "stage win-rates x ARR, minus a "
            f"{config.FLAGGED_RISK_HAIRCUT:.0%} haircut on flagged open deals, plus "
            f"a {config.FAST_MOVER_UPLIFT:.0%} uplift on fast movers (capped at ARR); "
            f"band ±{band:.0%}"
        ),
    }
