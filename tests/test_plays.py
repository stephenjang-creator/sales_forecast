"""Tests for the deterministic sales playbook (detector/plays.py)."""

from __future__ import annotations

from detector.evaluate import ANOMALY_TYPES
from detector.plays import (
    FAST_MOVER_PLAY,
    PLAYBOOK,
    STALLED_SLIPPED_RULES,
    VALUE_TOUCH_PLAY,
    primary_play,
    recommend_plays,
)
from detector.rules import RuleHit


def test_playbook_covers_every_rule() -> None:
    # Every anomaly type must map to a play; ids line up so the mapping is total.
    assert set(PLAYBOOK.keys()) == set(ANOMALY_TYPES)
    for rid, play in PLAYBOOK.items():
        assert play.rule_id == rid
        assert play.actions and all(isinstance(a, str) and a for a in play.actions)
        assert play.owner


def test_recommend_plays_dedupes_and_keeps_order() -> None:
    hits = [
        RuleHit("stalled_in_stage", "high", "stuck"),
        RuleHit("commit_low_meddpicc", "high", "thin"),
        RuleHit("stalled_in_stage", "medium", "still stuck"),  # duplicate id
    ]
    plays = recommend_plays(hits)
    ids = [p.rule_id for p in plays]
    assert ids == ["stalled_in_stage", "commit_low_meddpicc"]  # deduped, in order


def test_recommend_plays_empty_for_clean_deal() -> None:
    assert recommend_plays([]) == []


def test_recommend_plays_ignores_unknown_rule() -> None:
    assert recommend_plays([RuleHit("not_a_rule", "low", "x")]) == []


def test_primary_play_picks_highest_severity() -> None:
    hits = [
        RuleHit("premature_deep_discount", "medium", "discount"),
        RuleHit("commit_low_meddpicc", "high", "thin"),
    ]
    play = primary_play(hits)
    assert play is not None and play.rule_id == "commit_low_meddpicc"


def test_primary_play_none_when_no_playable_hits() -> None:
    assert primary_play([]) is None
    assert primary_play([RuleHit("not_a_rule", "high", "x")]) is None


def test_fast_mover_play_shape() -> None:
    assert FAST_MOVER_PLAY.rule_id == "fast_mover"
    assert FAST_MOVER_PLAY.actions and FAST_MOVER_PLAY.owner


def test_value_touch_play_shape() -> None:
    # The play for the meeting_at_risk signal; not an anomaly, so not in PLAYBOOK.
    assert VALUE_TOUCH_PLAY.rule_id == "meeting_at_risk"
    assert "meeting_at_risk" not in PLAYBOOK
    assert VALUE_TOUCH_PLAY.actions and VALUE_TOUCH_PLAY.owner
    assert "value touch" in VALUE_TOUCH_PLAY.title.lower()


def test_stalled_slipped_rules_are_known_plays() -> None:
    for rid in STALLED_SLIPPED_RULES:
        assert rid in PLAYBOOK
