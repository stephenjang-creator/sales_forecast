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
# Symmetric to the haircut: an open fast_mover (empowered champion + simple
# process -> likely to close early) has its expected value lifted by this
# fraction, capped so effective win probability never exceeds 1.0. This puts the
# "potential movers" upside into the projection, not just the narration. A deal
# that is BOTH flagged and a fast mover takes the risk haircut (risk dominates).
FAST_MOVER_UPLIFT = 0.25
# Half-width of the low/high band around the likely estimate (±fraction).
ESTIMATE_BAND = 0.20

# --------------------------------------------------------------------------- #
# Region-aware thresholds (opt-in business overlay).
# Regions run their sales motion differently, and the demo data is generated to
# match (US moves fast, EMEA runs long and lingers in Proposal, APAC discounts
# early as normal practice -- see generate_forecast_data.py, which imports the
# norms below). When region_aware is enabled, staleness is judged against each
# region's own typical stage duration instead of the global STAGE_NORMAL_DAYS.
# --------------------------------------------------------------------------- #
# Typical days in each open stage, per region. Falls back to STAGE_NORMAL_DAYS.
REGION_STAGE_NORMAL_DAYS = {
    "NA": {"Discovery": 12, "Qualification": 14, "Proposal": 11, "Negotiation": 10},
    "EMEA": {"Discovery": 30, "Qualification": 36, "Proposal": 70, "Negotiation": 34},
    "APAC": {"Discovery": 21, "Qualification": 25, "Proposal": 20, "Negotiation": 18},
    "LATAM": {"Discovery": 24, "Qualification": 28, "Proposal": 23, "Negotiation": 21},
}
# Regions where an early deep discount is normal practice -> do not flag
# premature_deep_discount there.
REGION_DISCOUNT_TOLERANT = ("APAC",)

# --------------------------------------------------------------------------- #
# Deal signals (non-anomaly classification): fast movers vs complex deals.
# These read champion seniority and decision-process complexity to surface
# OPPORTUNITY and duration signals alongside the risk anomalies.
# --------------------------------------------------------------------------- #
# Champion seniority ladder, low -> high. "Director or above" is empowered.
CHAMPION_LEVELS = ("IC", "Manager", "Director", "VP", "C-Suite")
CHAMPION_SENIOR_MIN = "Director"  # this rank or higher => senior/empowered
SIMPLE_APPROVAL_MAX_LAYERS = 1  # <= this AND no C-suite => simple process
COMPLEX_APPROVAL_MIN_LAYERS = 3  # >= this OR C-suite => complex/long process

# --------------------------------------------------------------------------- #
# Regional "top actions" worklist (sales guru --region).
# A regional VP wants the few highest-leverage moves for the day, where one move
# (a play) may cover several deals. Each candidate deal contributes
#     arr  ×  base(urgency/opportunity)  ×  funnel_depth(stage)  ×  champion_boost
# to its action's score, so the ranking favors BOTTOM-OF-FUNNEL, well-championed
# deals (a few steps from close) while keeping fast movers high. All tunable.
# --------------------------------------------------------------------------- #
ACTION_PRIORITY_WEIGHT = {
    "high": 1.0,  # high-severity risk -- act first
    "medium": 0.6,  # medium-severity risk
    "low": 0.4,
    "opportunity": 0.9,  # fast movers to close -- kept high on purpose
}
# Funnel depth: deals closer to close (bottom of funnel) weigh more. Reuses
# STAGE_WIN_RATE (Negotiation 0.75 > Proposal 0.50 > Qualification 0.25 >
# Discovery 0.10), so "a few steps from close" floats to the top.
STAGE_DEPTH_DEFAULT = 0.3  # stage not in STAGE_WIN_RATE
# Fast movers close quickly regardless of current stage, so never let stage
# depth drag an opportunity below this floor.
OPPORTUNITY_STAGE_FLOOR = 0.5
# A good champion (empowered, or a strong MEDDPICC champion score) makes a deal
# more actionable -- boost its weight by this fraction.
CHAMPION_QUALITY_BONUS = 0.5
GOOD_M_CHAMPION_MIN = 2  # m_champion (0-3) at/above this counts as a good champion

# A regional VP delegates most plays to managers via notes (no cap -- that
# scales), but can personally JOIN only a few calls to pull deals forward, and
# picks the ones with a higher-level person involved. The call shortlist is
# capped and skews to senior stakeholders.
VP_CALL_CAPACITY = 3  # how many calls the VP can personally join in a day
CALL_STAKEHOLDER_MIN = "VP"  # champion at/above this rank => "higher-level person"
# The worklist surfaces the top-priority DEALS region-wide (grouped by play) and
# lists every one -- no hidden "+N more" tail. This bounds how many a VP sees.
REGION_MAX_DEALS = 10
