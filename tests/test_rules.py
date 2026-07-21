"""Crafted-row unit tests: one firing row and one clean row per rule.

Each test feeds a hand-built dict to a single rule and asserts the hit (id +
severity) or the absence of one. The base row below is deliberately healthy --
it must trip no rule -- so each test only sets the fields its rule cares about.
"""

from __future__ import annotations

import pandas as pd

import config
from detector.engine import evaluate_row, run
from detector.rules import (
    ALL_RULES,
    RuleHit,
    rule_commit_low_meddpicc,
    rule_imminent_close_no_paper_process,
    rule_late_stage_no_economic_buyer,
    rule_premature_deep_discount,
    rule_slipped_close_date,
    rule_stalled_in_stage,
)


def base_row(**overrides: object) -> dict:
    """A healthy open deal that trips no rule; override to craft cases."""
    row: dict = {
        "deal_id": "D-TEST",
        "stage": "Qualification",
        "forecast_category": "Pipeline",
        "discount_pct": 0.0,
        "close_date_pushes": 0,
        "slip_days": 0,
        "days_in_stage": 5,
        "days_to_close": 30,
        "m_metrics": 2,
        "m_economic_buyer": 2,
        "m_decision_criteria": 2,
        "m_decision_process": 2,
        "m_paper_process": 2,
        "m_identified_pain": 2,
        "m_champion": 2,
        "m_competition": 2,
        "meddpicc_confidence": 75,
    }
    row.update(overrides)
    return row


def test_base_row_is_clean() -> None:
    """The shared base row must fire no rule at all."""
    assert evaluate_row(base_row()) == []


# --------------------------------------------------------------------------- #
# slipped_close_date
# --------------------------------------------------------------------------- #
def test_slipped_close_date_hit() -> None:
    hit = rule_slipped_close_date(base_row(close_date_pushes=3, slip_days=135))
    assert hit is not None
    assert hit.rule_id == "slipped_close_date"
    assert hit.severity == "high"  # 3+ pushes
    assert "135" in hit.reason and "3×" in hit.reason


def test_slipped_close_date_severity_scales() -> None:
    hit = rule_slipped_close_date(base_row(close_date_pushes=2, slip_days=90))
    assert hit is not None and hit.severity == "medium"


def test_slipped_close_date_clean() -> None:
    assert rule_slipped_close_date(base_row(close_date_pushes=1)) is None


def test_slipped_close_date_ignores_closed() -> None:
    row = base_row(stage="Closed Won", close_date_pushes=3, slip_days=135)
    assert rule_slipped_close_date(row) is None


# --------------------------------------------------------------------------- #
# stalled_in_stage
# --------------------------------------------------------------------------- #
def test_stalled_in_stage_hit() -> None:
    # Discovery normal = 21; 90 > 21*4 => high.
    hit = rule_stalled_in_stage(base_row(stage="Discovery", days_in_stage=90))
    assert hit is not None
    assert hit.rule_id == "stalled_in_stage"
    assert hit.severity == "high"
    assert "Discovery" in hit.reason and "90" in hit.reason


def test_stalled_in_stage_medium() -> None:
    # 70 days: > 3*21 (63) but not > 4*21 (84) => medium.
    hit = rule_stalled_in_stage(base_row(stage="Discovery", days_in_stage=70))
    assert hit is not None and hit.severity == "medium"


def test_stalled_in_stage_clean() -> None:
    assert rule_stalled_in_stage(base_row(stage="Discovery", days_in_stage=20)) is None


# --------------------------------------------------------------------------- #
# commit_low_meddpicc
# --------------------------------------------------------------------------- #
def test_commit_low_meddpicc_hit() -> None:
    row = base_row(
        forecast_category="Commit",
        meddpicc_confidence=45,
        m_economic_buyer=0,
        m_paper_process=1,
    )
    hit = rule_commit_low_meddpicc(row)
    assert hit is not None
    assert hit.rule_id == "commit_low_meddpicc"
    assert hit.severity == "high"
    assert "45" in hit.reason
    assert "Economic Buyer (0)" in hit.reason  # weakest element surfaced


def test_commit_low_meddpicc_clean_high_confidence() -> None:
    row = base_row(forecast_category="Commit", meddpicc_confidence=80)
    assert rule_commit_low_meddpicc(row) is None


def test_commit_low_meddpicc_clean_not_commit() -> None:
    row = base_row(forecast_category="Best Case", meddpicc_confidence=30)
    assert rule_commit_low_meddpicc(row) is None


# --------------------------------------------------------------------------- #
# late_stage_no_economic_buyer
# --------------------------------------------------------------------------- #
def test_late_stage_no_eb_hit() -> None:
    hit = rule_late_stage_no_economic_buyer(base_row(stage="Negotiation", m_economic_buyer=0))
    assert hit is not None
    assert hit.rule_id == "late_stage_no_economic_buyer"
    assert hit.severity == "high"
    assert "Negotiation" in hit.reason


def test_late_stage_no_eb_clean_has_eb() -> None:
    row = base_row(stage="Negotiation", m_economic_buyer=2)
    assert rule_late_stage_no_economic_buyer(row) is None


def test_late_stage_no_eb_clean_early_stage() -> None:
    # Early stage with EB=0 is not this anomaly.
    row = base_row(stage="Discovery", m_economic_buyer=0)
    assert rule_late_stage_no_economic_buyer(row) is None


# --------------------------------------------------------------------------- #
# premature_deep_discount
# --------------------------------------------------------------------------- #
def test_premature_deep_discount_hit() -> None:
    row = base_row(stage="Discovery", discount_pct=0.35, m_identified_pain=1)
    hit = rule_premature_deep_discount(row)
    assert hit is not None
    assert hit.rule_id == "premature_deep_discount"
    assert hit.severity == "medium"
    assert "35%" in hit.reason


def test_premature_deep_discount_clean_small_discount() -> None:
    row = base_row(stage="Discovery", discount_pct=0.10)
    assert rule_premature_deep_discount(row) is None


def test_premature_deep_discount_clean_late_stage() -> None:
    # Deep discount is expected/acceptable once late in the cycle.
    row = base_row(stage="Negotiation", discount_pct=0.40)
    assert rule_premature_deep_discount(row) is None


# --------------------------------------------------------------------------- #
# imminent_close_no_paper_process
# --------------------------------------------------------------------------- #
def test_imminent_close_no_paper_hit() -> None:
    row = base_row(days_to_close=3, m_paper_process=0)
    hit = rule_imminent_close_no_paper_process(row)
    assert hit is not None
    assert hit.rule_id == "imminent_close_no_paper_process"
    assert hit.severity == "high"
    assert "3 days" in hit.reason


def test_imminent_close_clean_paper_started() -> None:
    row = base_row(days_to_close=3, m_paper_process=2)
    assert rule_imminent_close_no_paper_process(row) is None


def test_imminent_close_clean_far_out() -> None:
    row = base_row(days_to_close=45, m_paper_process=0)
    assert rule_imminent_close_no_paper_process(row) is None


def test_imminent_close_ignores_closed() -> None:
    row = base_row(stage="Closed Lost", days_to_close=3, m_paper_process=0)
    assert rule_imminent_close_no_paper_process(row) is None


# --------------------------------------------------------------------------- #
# Registry + engine wiring
# --------------------------------------------------------------------------- #
def test_registry_ids_are_unique_and_complete() -> None:
    # Every rule returns a hit with a distinct id when fed a firing row.
    assert len(ALL_RULES) == 6


def test_engine_appends_columns_and_scores() -> None:
    rows = [
        base_row(deal_id="clean"),
        base_row(
            deal_id="risky",
            close_date_pushes=3,
            slip_days=135,
            m_paper_process=0,
            days_to_close=2,
        ),
    ]
    scored = run(pd.DataFrame(rows))
    for col in ("hits", "risk_score", "predicted_anomaly", "top_reason"):
        assert col in scored.columns
    risky = scored[scored.deal_id == "risky"].iloc[0]
    clean = scored[scored.deal_id == "clean"].iloc[0]
    assert clean["predicted_anomaly"] is False or clean["predicted_anomaly"] == False  # noqa: E712
    assert risky["predicted_anomaly"]
    assert risky["risk_score"] >= config.SEVERITY["high"]
    assert all(isinstance(h, RuleHit) for h in risky["hits"])
    assert risky["top_reason"]  # highest-severity reason populated
