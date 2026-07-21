"""Tunable thresholds for the Forecast Anomaly Detector.

Every magic number the rule engine relies on lives here so a RevOps admin can
retune the detector without touching rule logic. Rules import these constants;
they never hard-code values of their own.
"""

# MEDDPICC rollup bounds (8 elements scored 0-3 each).
MEDDPICC_MAX = 24

# A deal a rep has forecast as "Commit" should have real qualification behind
# it. Commit deals whose confidence proxy falls below this floor are suspect.
COMMIT_CONFIDENCE_FLOOR = 60  # 0-100 scale

# Pipeline stages.
LATE_STAGES = ("Proposal", "Negotiation")
OPEN_STAGES = ("Discovery", "Qualification", "Proposal", "Negotiation")
EARLY_STAGES = ("Discovery", "Qualification")

# Typical days a healthy deal sits in each open stage.
STAGE_NORMAL_DAYS = {
    "Discovery": 21,
    "Qualification": 25,
    "Proposal": 20,
    "Negotiation": 18,
}
# days_in_stage > normal * this => stalled.
# Tuned 3 -> 2.5: healthy deals never exceed 1.0x the stage norm in the data, so
# 2.5x keeps precision at 1.00 while catching genuinely stalled deals that sit
# just under the old 3x line (recall 0.60 -> 1.00). See TUNING.md.
STALE_MULTIPLIER = 2.5

# close_date_pushes >= this => the deal has slipped.
SLIP_PUSHES_MIN = 2

# discount at/above this share in an early stage => premature discounting.
DEEP_DISCOUNT_PCT = 0.30

# days_to_close <= this => the deal is imminent.
IMMINENT_CLOSE_DAYS = 7

# Ordinal weight per severity, used to sum a deal's risk score.
SEVERITY = {"low": 1, "medium": 2, "high": 3}

# --------------------------------------------------------------------------- #
# Attainment agent (presentation/estimation layer, NOT part of the detector).
# The detector reports risk exposure; the agent layer turns pipeline + risk into
# a risk-adjusted expected-bookings estimate. These are the heuristic anchors the
# agent is given (and the offline `--dry-run` baseline), kept here so they're
# tunable rather than buried in code.
# --------------------------------------------------------------------------- #
# Rough probability a deal in each stage converts to bookings this period.
STAGE_WIN_RATE = {
    "Discovery": 0.10,
    "Qualification": 0.25,
    "Proposal": 0.50,
    "Negotiation": 0.75,
    "Closed Won": 1.0,
    "Closed Lost": 0.0,
}
# An open deal the detector flagged has its expected value cut by this fraction
# (hygiene/qualification risk lowers the odds it lands as forecast).
FLAGGED_RISK_HAIRCUT = 0.40
# Half-width of the low/high band around the likely estimate (±fraction).
ESTIMATE_BAND = 0.20
