"""Crafted-row tests for the non-anomaly deal signals."""

from __future__ import annotations

import pandas as pd

from detector.engine import run
from detector.signals import (
    ALL_SIGNALS,
    classify,
    signal_complex_deal,
    signal_fast_mover,
    signal_meeting_at_risk,
)


def _deal(**overrides) -> dict:
    """An open deal with a neutral decision profile (no signal by default)."""
    row = {
        "stage": "Discovery",
        "champion_seniority": "Manager",
        "approval_layers": 2,
        "csuite_approval": 0,
    }
    row.update(overrides)
    return row


def test_registry() -> None:
    assert len(ALL_SIGNALS) == 3


def test_fast_mover_hits() -> None:
    row = _deal(champion_seniority="Director", approval_layers=1, csuite_approval=0)
    sig = signal_fast_mover(row)
    assert sig is not None
    assert sig.signal_id == "fast_mover" and sig.kind == "opportunity"
    assert "Director" in sig.reason
    assert signal_complex_deal(row) is None


def test_fast_mover_needs_senior_champion() -> None:
    # Simple process but only a Manager champion -> not a fast mover.
    assert signal_fast_mover(_deal(champion_seniority="Manager", approval_layers=1)) is None


def test_fast_mover_needs_simple_process() -> None:
    # Director champion but a C-suite gate -> not simple, not a fast mover.
    row = _deal(champion_seniority="VP", approval_layers=1, csuite_approval=1)
    assert signal_fast_mover(row) is None


def test_complex_deal_by_layers() -> None:
    sig = signal_complex_deal(_deal(approval_layers=3))
    assert sig is not None and sig.signal_id == "complex_deal" and sig.kind == "risk"
    assert "3 approval layers" in sig.reason


def test_complex_deal_by_csuite() -> None:
    sig = signal_complex_deal(_deal(approval_layers=1, csuite_approval=1))
    assert sig is not None
    assert "C-suite" in sig.reason


def test_meeting_at_risk_when_far_out() -> None:
    # A next meeting more than a week out => at risk.
    sig = signal_meeting_at_risk(_deal(next_meeting_date="2026-08-30", days_to_next_meeting=21))
    assert sig is not None
    assert sig.signal_id == "meeting_at_risk" and sig.kind == "risk"
    assert "21 days out" in sig.reason


def test_meeting_at_risk_when_none_booked() -> None:
    # No meeting booked (blank / NaN) => at risk, distinct reason.
    sig = signal_meeting_at_risk(_deal(next_meeting_date="", days_to_next_meeting=""))
    assert sig is not None
    assert "No next meeting booked" in sig.reason
    # A float NaN (as pandas reads a blank cell) is treated the same.
    assert signal_meeting_at_risk(_deal(next_meeting_date=float("nan"))) is not None


def test_meeting_at_risk_healthy_when_soon() -> None:
    # A meeting within the cadence window is fine.
    assert (
        signal_meeting_at_risk(_deal(next_meeting_date="2026-07-24", days_to_next_meeting=3))
        is None
    )


def test_signals_ignore_closed_deals() -> None:
    row = _deal(
        stage="Closed Won",
        champion_seniority="C-Suite",
        approval_layers=1,
        next_meeting_date="",
        days_to_next_meeting="",
    )
    assert classify(row) == []


def test_engine_appends_signal_columns() -> None:
    rows = [
        _deal(
            deal_id="fast",
            champion_seniority="VP",
            approval_layers=1,
            csuite_approval=0,
            next_meeting_date="2026-07-24",
            days_to_next_meeting=3,
        ),
        _deal(
            deal_id="complex",
            champion_seniority="Manager",
            approval_layers=4,
            csuite_approval=1,
            next_meeting_date="2026-07-24",
            days_to_next_meeting=3,
        ),
        _deal(
            deal_id="stale",
            next_meeting_date="",
            days_to_next_meeting="",  # no meeting -> meeting_at_risk
        ),
    ]
    scored = run(pd.DataFrame(rows))
    for col in ("signals", "fast_mover", "complex_deal", "meeting_at_risk"):
        assert col in scored.columns
    by_id = {r["deal_id"]: r for _, r in scored.iterrows()}
    assert by_id["fast"]["fast_mover"] and not by_id["fast"]["meeting_at_risk"]
    assert by_id["complex"]["complex_deal"]
    assert by_id["stale"]["meeting_at_risk"] and not by_id["stale"]["fast_mover"]
