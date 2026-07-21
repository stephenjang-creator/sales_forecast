"""Deterministic anomaly rules.

Each rule is a pure function of a single pipeline row (a plain ``dict``) and
returns a :class:`RuleHit` when the deal trips the rule, or ``None`` when it is
clean. Every ``reason`` is built only from the row's own values -- no LLM, no
outside state -- so a sales manager can read a flag and verify it against the
CRM record.

``rule_id`` on each hit is deliberately identical to the matching id in the
dataset's ``anomaly_types`` label column, which lets :mod:`detector.evaluate`
score each rule against its own ground truth.

Adding a new anomaly type is a one-function change: write ``def rule_x(row)``
and append it to :data:`ALL_RULES`.
"""

from __future__ import annotations

from dataclasses import dataclass

import config

# MEDDPICC element -> the row column that holds its 0-3 score.
MEDDPICC_ELEMENTS = {
    "Metrics": "m_metrics",
    "Economic Buyer": "m_economic_buyer",
    "Decision Criteria": "m_decision_criteria",
    "Decision Process": "m_decision_process",
    "Paper Process": "m_paper_process",
    "Identified Pain": "m_identified_pain",
    "Champion": "m_champion",
    "Competition": "m_competition",
}


@dataclass(frozen=True)
class RuleHit:
    """A single fired rule.

    Attributes:
        rule_id: Matches an ``anomaly_types`` id exactly.
        severity: One of ``"low"``, ``"medium"``, ``"high"``.
        reason: Human-readable justification built from the row's own values.
    """

    rule_id: str
    severity: str
    reason: str


# --------------------------------------------------------------------------- #
# Small typed accessors -- pandas hands us numpy scalars; normalize them.
# --------------------------------------------------------------------------- #
def _int(row: dict, key: str) -> int:
    """Return ``row[key]`` as a plain int (0 if missing/blank)."""
    val = row.get(key)
    if val is None or val == "":
        return 0
    return int(val)


def _float(row: dict, key: str) -> float:
    """Return ``row[key]`` as a plain float (0.0 if missing/blank)."""
    val = row.get(key)
    if val is None or val == "":
        return 0.0
    return float(val)


def _str(row: dict, key: str) -> str:
    """Return ``row[key]`` as a stripped str ('' if missing)."""
    val = row.get(key)
    return "" if val is None else str(val).strip()


def _is_open(row: dict) -> bool:
    """True when the deal sits in an open (non-closed) stage."""
    return _str(row, "stage") in config.OPEN_STAGES


def _two_weakest_meddpicc(row: dict) -> str:
    """Name the two lowest-scoring MEDDPICC elements, e.g.
    'Economic Buyer (0), Paper Process (1)'. Ties break by canonical order."""
    scored = [(label, _int(row, col)) for label, col in MEDDPICC_ELEMENTS.items()]
    scored.sort(key=lambda pair: pair[1])
    return ", ".join(f"{label} ({score})" for label, score in scored[:2])


def _region_aware(row: dict) -> bool:
    """Whether the caller opted into region-specific thresholds for this row.

    The engine injects ``_region_aware`` into the row dict, so a rule stays a
    pure function of its input. Absent/false => the region-agnostic defaults.
    """
    return bool(row.get("_region_aware", False))


def _stage_norm(row: dict) -> int:
    """Typical days-in-stage for a row: the region's own norm when region-aware,
    else the global default. US runs short, EMEA long (esp. Proposal)."""
    stage = _str(row, "stage")
    if _region_aware(row):
        table = config.REGION_STAGE_NORMAL_DAYS.get(_str(row, "region"))
        if table and stage in table:
            return table[stage]
    return config.STAGE_NORMAL_DAYS[stage]


# --------------------------------------------------------------------------- #
# Rules -- one pure function per anomaly type.
# --------------------------------------------------------------------------- #
def rule_slipped_close_date(row: dict) -> RuleHit | None:
    """Close date pushed repeatedly -- the forecast keeps sliding right."""
    if not _is_open(row):
        return None
    pushes = _int(row, "close_date_pushes")
    if pushes < config.SLIP_PUSHES_MIN:
        return None
    slip_days = _int(row, "slip_days")
    severity = "high" if pushes >= 3 else "medium"
    reason = f"Close date pushed {pushes}× " f"(now {slip_days} days past the original close date)."
    return RuleHit("slipped_close_date", severity, reason)


def rule_stalled_in_stage(row: dict) -> RuleHit | None:
    """Deal has sat in one open stage far longer than a healthy deal would."""
    stage = _str(row, "stage")
    if stage not in config.OPEN_STAGES:
        return None
    normal = _stage_norm(row)
    days = _int(row, "days_in_stage")
    if days <= normal * config.STALE_MULTIPLIER:
        return None
    severity = "high" if days > normal * 4 else "medium"
    region_note = f" ({_str(row, 'region')} norm)" if _region_aware(row) else ""
    reason = (
        f"Stuck in {stage} for {days} days -- {days / normal:.1f}× the "
        f"{normal}-day norm for this stage{region_note}."
    )
    return RuleHit("stalled_in_stage", severity, reason)


def rule_commit_low_meddpicc(row: dict) -> RuleHit | None:
    """Rep forecast this deal as Commit, but qualification is thin."""
    if _str(row, "forecast_category") != "Commit":
        return None
    conf = _int(row, "meddpicc_confidence")
    if conf >= config.COMMIT_CONFIDENCE_FLOOR:
        return None
    weakest = _two_weakest_meddpicc(row)
    reason = (
        f"Forecast as Commit at only {conf}/100 MEDDPICC confidence "
        f"(floor {config.COMMIT_CONFIDENCE_FLOOR}); weakest links: {weakest}."
    )
    return RuleHit("commit_low_meddpicc", "high", reason)


def rule_late_stage_no_economic_buyer(row: dict) -> RuleHit | None:
    """Late-stage deal with no Economic Buyer engaged."""
    stage = _str(row, "stage")
    if stage not in config.LATE_STAGES:
        return None
    if _int(row, "m_economic_buyer") != 0:
        return None
    reason = (
        f"In {stage} with no Economic Buyer identified (m_economic_buyer=0) -- "
        f"no one who can sign is engaged."
    )
    return RuleHit("late_stage_no_economic_buyer", "high", reason)


def rule_premature_deep_discount(row: dict) -> RuleHit | None:
    """Heavy discount extended before value has been established."""
    stage = _str(row, "stage")
    if stage not in config.EARLY_STAGES:
        return None
    if _region_aware(row) and _str(row, "region") in config.REGION_DISCOUNT_TOLERANT:
        return None  # early deep discounts are normal practice in this region
    discount = _float(row, "discount_pct")
    if discount < config.DEEP_DISCOUNT_PCT:
        return None
    pain = _int(row, "m_identified_pain")
    metrics = _int(row, "m_metrics")
    reason = (
        f"{discount:.0%} discount offered in {stage}, before value is proven "
        f"(identified pain {pain}/3, metrics {metrics}/3)."
    )
    return RuleHit("premature_deep_discount", "medium", reason)


def rule_imminent_close_no_paper_process(row: dict) -> RuleHit | None:
    """Deal is days from close with no paper/legal process underway."""
    if not _is_open(row):
        return None
    days_to_close = _int(row, "days_to_close")
    if days_to_close > config.IMMINENT_CLOSE_DAYS:
        return None
    if _int(row, "m_paper_process") != 0:
        return None
    reason = (
        f"Closing in {days_to_close} days with no paper process started "
        f"(m_paper_process=0) -- procurement/legal has not begun."
    )
    return RuleHit("imminent_close_no_paper_process", "high", reason)


# Registry: engine.py iterates this without knowing individual rule names.
# Add a new anomaly type by appending its function here.
ALL_RULES = [
    rule_slipped_close_date,
    rule_stalled_in_stage,
    rule_commit_low_meddpicc,
    rule_late_stage_no_economic_buyer,
    rule_premature_deep_discount,
    rule_imminent_close_no_paper_process,
]
