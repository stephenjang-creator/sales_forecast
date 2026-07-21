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


def baseline_from_deals(deals: list[dict]) -> dict:
    """Risk-adjusted expected-bookings estimate from compact deal dicts.

    Each deal needs ``arr``, ``stage``, ``forecast_category`` and
    ``predicted_anomaly`` (exactly the ``list_deals`` shape). Returns the likely
    estimate plus a low/high band and the intermediate components, so the number
    is auditable.
    """
    open_stages = set(config.OPEN_STAGES)
    open_pipeline_arr = 0.0
    weighted = 0.0  # stage-weighted, before risk haircut
    risk_adjusted = 0.0  # after haircut on flagged open deals
    closed_won_arr = 0.0

    for deal in deals:
        arr = float(deal.get("arr", 0.0) or 0.0)
        stage = str(deal.get("stage", ""))
        flagged = bool(deal.get("predicted_anomaly", False))
        rate = _win_rate(stage)

        if stage == "Closed Won":
            closed_won_arr += arr
        if stage in open_stages:
            open_pipeline_arr += arr

        expected = arr * rate
        weighted += expected
        if flagged and stage in open_stages:
            expected *= 1.0 - config.FLAGGED_RISK_HAIRCUT
        risk_adjusted += expected

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
        "risk_haircut_arr": round(weighted - risk_adjusted, 0),
        "method": (
            "stage win-rates x ARR, minus a "
            f"{config.FLAGGED_RISK_HAIRCUT:.0%} haircut on flagged open deals; "
            f"band ±{band:.0%}"
        ),
    }
