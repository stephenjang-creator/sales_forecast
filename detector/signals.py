"""Deal signals: non-anomaly classification (opportunities + duration).

The anomaly rules in :mod:`detector.rules` flag *risk*. Signals are the other
half of the picture -- deterministic, row-pure classifiers that surface how a
deal is likely to move based on champion seniority and decision-process
complexity:

- ``fast_mover`` (opportunity): a Director-or-above champion AND a simple
  decision process (few approval layers, no C-suite gate) -- likely to close
  quickly.
- ``complex_deal`` (risk/duration): C-suite sign-off or 3+ approval layers --
  expect a longer, less predictable cycle.

Signals are not scored against ``is_anomaly`` -- they are deterministic
derivations from the row, surfaced for triage, not accuracy measurement. Adding
a signal is a one-function change: write ``def signal_x(row)`` and append it to
:data:`ALL_SIGNALS`.
"""

from __future__ import annotations

from dataclasses import dataclass

import config
from detector.rules import _int, _is_open, _str


def _has_next_meeting(row: dict) -> bool:
    """True when a next meeting date is on the calendar."""
    return _str(row, "next_meeting_date") != ""


@dataclass(frozen=True)
class Signal:
    """A single fired deal signal.

    Attributes:
        signal_id: ``"fast_mover"`` | ``"complex_deal"``.
        kind: ``"opportunity"`` | ``"risk"``.
        reason: Human-readable justification built from the row's own values.
    """

    signal_id: str
    kind: str
    reason: str


def _champion_rank(row: dict) -> int:
    """Ordinal rank of the champion's seniority (-1 if absent/unknown)."""
    level = _str(row, "champion_seniority")
    return config.CHAMPION_LEVELS.index(level) if level in config.CHAMPION_LEVELS else -1


def _is_senior_champion(row: dict) -> bool:
    """True when the champion is Director-or-above (empowered)."""
    return _champion_rank(row) >= config.CHAMPION_LEVELS.index(config.CHAMPION_SENIOR_MIN)


def _requires_csuite(row: dict) -> bool:
    """True when the decision process needs C-suite sign-off."""
    return _int(row, "csuite_approval") == 1


def _is_simple_process(row: dict) -> bool:
    """Few approval layers and no C-suite gate."""
    return _int(
        row, "approval_layers"
    ) <= config.SIMPLE_APPROVAL_MAX_LAYERS and not _requires_csuite(row)


def _is_complex_process(row: dict) -> bool:
    """Many approval layers or a C-suite gate."""
    return (
        _requires_csuite(row) or _int(row, "approval_layers") >= config.COMPLEX_APPROVAL_MIN_LAYERS
    )


# --------------------------------------------------------------------------- #
# Signals -- one pure function per signal type.
# --------------------------------------------------------------------------- #
def signal_fast_mover(row: dict) -> Signal | None:
    """Empowered champion + simple process => likely to close fast."""
    if not _is_open(row):
        return None
    if _is_senior_champion(row) and _is_simple_process(row):
        layers = _int(row, "approval_layers")
        reason = (
            f"{_str(row, 'champion_seniority')} champion with a simple decision "
            f"process ({layers} approval layer{'s' if layers != 1 else ''}, no "
            f"C-suite gate) -- likely a fast mover."
        )
        return Signal("fast_mover", "opportunity", reason)
    return None


def signal_complex_deal(row: dict) -> Signal | None:
    """C-suite sign-off or 3+ approval layers => expect a longer cycle."""
    if not _is_open(row):
        return None
    if _is_complex_process(row):
        layers = _int(row, "approval_layers")
        gate = "C-suite sign-off required" if _requires_csuite(row) else f"{layers} approval layers"
        reason = f"Complex decision process ({gate}) -- expect a longer, less predictable cycle."
        return Signal("complex_deal", "risk", reason)
    return None


def signal_meeting_at_risk(row: dict) -> Signal | None:
    """No next meeting, or one more than a week out => momentum at risk.

    A weak next step (or none) is a leading indicator that a deal is drifting.
    The fix is a value touch: reach out with something useful and set a sooner
    next step. Reads the precomputed ``days_to_next_meeting`` so it stays stable
    regardless of when the detector runs.
    """
    if not _is_open(row):
        return None
    if not _has_next_meeting(row):
        return Signal(
            "meeting_at_risk",
            "risk",
            "No next meeting booked -- run a value touch to set a near-term next step.",
        )
    days = _int(row, "days_to_next_meeting")
    if days > config.NEXT_MEETING_MAX_DAYS:
        reason = (
            f"Next meeting is {days} days out (> {config.NEXT_MEETING_MAX_DAYS}-day "
            f"cadence) -- run a value touch to pull a sooner next step in."
        )
        return Signal("meeting_at_risk", "risk", reason)
    return None


# Registry: engine.py iterates this without knowing individual signal names.
ALL_SIGNALS = [signal_fast_mover, signal_complex_deal, signal_meeting_at_risk]


def classify(row: dict) -> list[Signal]:
    """Apply every registered signal to one row; return the signals it produced."""
    out: list[Signal] = []
    for fn in ALL_SIGNALS:
        sig = fn(row)
        if sig is not None:
            out.append(sig)
    return out
