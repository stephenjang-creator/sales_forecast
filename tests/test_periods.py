"""Unit tests for the time-period engine (pure functions on crafted frames)."""

from __future__ import annotations

from datetime import date

import pandas as pd

import config
import periods


def test_period_keys() -> None:
    d = date(2026, 7, 15)
    assert periods.period_key(d, "month") == "2026-07"
    assert periods.period_key(d, "quarter") == "2026-Q3"
    assert periods.period_key(d, "year") == "2026"
    assert periods.month_period_to_grain("2026-07", "quarter") == "2026-Q3"
    assert periods.month_period_to_grain("2026-02", "quarter") == "2026-Q1"


def _scored() -> pd.DataFrame:
    rows = [
        # open, clean, Negotiation (win-rate 0.75), closes this month
        {
            "arr": 100_000,
            "stage": "Negotiation",
            "region": "EMEA",
            "predicted_anomaly": False,
            "forecast_category": "Commit",
            "close_date": "2026-07-15",
        },
        # open, flagged, Negotiation, closes next month -> haircut applies
        {
            "arr": 100_000,
            "stage": "Negotiation",
            "region": "EMEA",
            "predicted_anomaly": True,
            "forecast_category": "Commit",
            "close_date": "2026-08-15",
        },
        # already won this month
        {
            "arr": 200_000,
            "stage": "Closed Won",
            "region": "EMEA",
            "predicted_anomaly": False,
            "forecast_category": "Commit",
            "close_date": "2026-07-20",
        },
    ]
    return pd.DataFrame(rows)


def test_current_period_from_open_deals() -> None:
    scored = _scored()
    assert periods.current_period_key(scored, "month") == "2026-07"
    assert periods.current_period_key(scored, "quarter") == "2026-Q3"


def test_pipeline_by_period_weights_and_haircut() -> None:
    buckets = {b["period"]: b for b in periods.pipeline_by_period(_scored(), "month", "EMEA")}
    jul = buckets["2026-07"]
    assert jul["is_current"] is True
    assert jul["won_arr"] == 200_000
    assert jul["weighted_open_arr"] == 75_000  # 100k * 0.75
    assert jul["risk_adjusted_open_arr"] == 75_000  # clean deal, no haircut
    aug = buckets["2026-08"]
    assert aug["is_current"] is False
    # flagged: 100k * 0.75 * (1 - haircut)
    assert aug["risk_adjusted_open_arr"] == round(75_000 * (1 - config.FLAGGED_RISK_HAIRCUT), 0)


def _history() -> pd.DataFrame:
    rows = [
        {"period": "2025-06", "region": "EMEA", "bookings": 100, "quota": 100, "deals_won": 2},
        {"period": "2026-04", "region": "EMEA", "bookings": 90, "quota": 100, "deals_won": 2},
        {"period": "2026-05", "region": "EMEA", "bookings": 120, "quota": 100, "deals_won": 3},
        {"period": "2026-06", "region": "EMEA", "bookings": 150, "quota": 100, "deals_won": 3},
    ]
    return pd.DataFrame(rows)


def test_history_by_grain_month_and_quarter() -> None:
    months = periods.history_by_grain(_history(), "month", "EMEA")
    assert months[-1] == {
        "period": "2026-06",
        "bookings": 150.0,
        "quota": 100.0,
        "attainment_pct": 150.0,
        "deals_won": 3,
    }
    # Q2 2026 aggregates Apr+May+Jun.
    q = {r["period"]: r for r in periods.history_by_grain(_history(), "quarter", "EMEA")}
    assert q["2026-Q2"]["bookings"] == 360.0
    assert q["2026-Q2"]["quota"] == 300.0


def test_comparisons_mom_and_yoy() -> None:
    comp = periods.comparisons(_history(), "month", "EMEA")
    assert comp["latest_period"] == "2026-06"
    assert comp["sequential_label"] == "MoM"
    assert comp["prior_period"] == "2026-05"
    assert comp["sequential_change_pct"] == 25.0  # 150 vs 120
    assert comp["yoy_period"] == "2025-06"
    assert comp["yoy_change_pct"] == 50.0  # 150 vs 100


def test_bookings_rollup_projection() -> None:
    scored = _scored()
    targets = pd.DataFrame([{"period": "2026-07", "region": "EMEA", "quota": 500_000}])
    rollup = periods.bookings_rollup(scored, "month", "EMEA", targets=targets, hist=_history())
    assert rollup["current_period"] == "2026-07"
    assert rollup["won_so_far"] == 200_000
    assert rollup["expected_to_close"] == 75_000
    assert rollup["projected_bookings"] == 275_000
    assert rollup["quota"] == 500_000
    assert rollup["projected_attainment_pct"] == 55.0  # 275k / 500k
    assert "note" in rollup
