"""
generate_forecast_data.py
--------------------------
Synthetic pipeline generator for a RevOps Forecast Anomaly Detector.

Produces a labeled dataset where each opportunity carries:
  - CRM fields (segment, region, stage, dates, rep, discount)
  - Deal economics (MRR-based; MRR scales with company headcount, $3,250 floor,
    a tail of large ~$10K+ deals that run longer and less predictable; arr = mrr*12)
  - Firmographics (industry, employees, account_revenue)
  - Decision profile (champion_seniority, approval_layers, csuite_approval) --
    drives the fast-mover / complex-deal signals in detector.signals
  - Full MEDDPICC qualification scores (0-3 per element) + a rollup
  - A ground-truth `is_anomaly` flag and `anomaly_types` list

Regional behavior (US fast, EMEA slow/lingering, APAC discounts early) and the
region norms are shared with the detector via config.py, so anomalies are
labeled relative to each region's norm. No production data is used.

Runtime deps: pandas + config.py (region norms); faker optional (falls back to
a built-in name/company pool if not installed).

Usage:
    python generate_forecast_data.py --n 600 --seed 28 --out pipeline.csv
"""

import argparse
import math
import random
from datetime import date, timedelta

import pandas as pd

import config  # region norms live here so the detector and generator agree

# ----------------------------------------------------------------------
# Optional Faker -- degrade gracefully to a built-in pool if unavailable.
# ----------------------------------------------------------------------
try:
    from faker import Faker
    _fake = Faker()
    def _company(): return _fake.company()
    def _person():  return _fake.name()
    def _seed_faker(s): Faker.seed(s)
except ImportError:  # pragma: no cover
    _COMPANIES = ["Acme", "Northwind", "Globex", "Initech", "Umbra", "Contoso",
                  "Vandelay", "Soylent", "Hooli", "Stark", "Wayne", "Wonka",
                  "Cyberdyne", "Tyrell", "Aperture", "Nakatomi", "Gekko",
                  "Prestige", "Oscorp", "Massive Dynamic"]
    _SUFFIX = ["Systems", "Labs", "Group", "Holdings", "Partners", "Industries",
               "Technologies", "Solutions", "Digital", "Networks"]
    _FIRST = ["Alex", "Jordan", "Taylor", "Morgan", "Casey", "Riley", "Sam",
              "Jamie", "Avery", "Quinn", "Drew", "Cameron", "Reese", "Skyler"]
    _LAST = ["Nguyen", "Patel", "Garcia", "Kim", "Rossi", "Haddad", "Okafor",
             "Silva", "Novak", "Ivanov", "Chen", "Muller", "Sato", "Adeyemi"]
    def _company(): return f"{random.choice(_COMPANIES)} {random.choice(_SUFFIX)}"
    def _person():  return f"{random.choice(_FIRST)} {random.choice(_LAST)}"
    def _seed_faker(s): pass

# ----------------------------------------------------------------------
# Domain constants
# ----------------------------------------------------------------------
SEGMENTS = ["Enterprise", "Mid-Market", "SMB"]
SEG_WEIGHTS = [0.20, 0.50, 0.30]
REGIONS = ["NA", "EMEA", "APAC", "LATAM"]
REGION_WEIGHTS = [0.45, 0.30, 0.15, 0.10]

# ----------------------------------------------------------------------
# Deal economics -- MRR-based. Company size (segment) sets who's buying;
# most deals cluster just above the $3,250 floor (ASP ~$3,850 MRR), with a
# tail of large ~$10K+ MRR deals (mostly Enterprise) that run longer and
# are less predictable. arr = mrr * 12.
# ----------------------------------------------------------------------
MRR_FLOOR = 3250
# MRR scales with company size (headcount): larger accounts buy higher MRR, so
# the big ~$10K deals emerge from the largest firms. ASP stays ~$3,850 because
# most of the book is SMB/Mid-Market near the floor. arr = mrr * 12.
MRR_SIZE_SPAN = 8_000     # max size-driven uplift over the floor (USD/mo)
MRR_SIZE_EXP = 6.0        # convex: only large accounts get the big uplift
MRR_NOISE = 200           # per-deal exponential noise mean
MRR_CAP = 16_000
BIG_DEAL_MRR_FLOOR = 8000  # mrr at/above this => "big deal" behavior
_EMP_RANGE = (10, 80_000)  # headcount range spanning all segments

# Firmographics by segment. Revenue is derived from headcount so the two agree.
SEGMENT_EMPLOYEES = {
    "SMB": (10, 200),
    "Mid-Market": (200, 2500),
    "Enterprise": (2500, 80_000),
}
REVENUE_PER_EMPLOYEE = (120_000, 320_000)  # USD annual revenue per head
INDUSTRIES = [
    "Software", "Financial Services", "Healthcare", "Manufacturing",
    "Retail & eCommerce", "Media & Telecom", "Energy & Utilities",
    "Education", "Logistics", "Professional Services",
]
INDUSTRY_WEIGHTS = [0.20, 0.14, 0.12, 0.11, 0.10, 0.09, 0.07, 0.07, 0.05, 0.05]

# Decision profile: champion seniority + approval complexity, by segment.
# Enterprises skew to more senior champions but heavier approval processes.
SEG_CHAMPION_WEIGHTS = {  # over config.CHAMPION_LEVELS (IC..C-Suite)
    "SMB": [0.15, 0.35, 0.30, 0.15, 0.05],
    "Mid-Market": [0.10, 0.30, 0.35, 0.18, 0.07],
    "Enterprise": [0.08, 0.22, 0.35, 0.25, 0.10],
}
SEG_APPROVAL_LAYERS = {  # (layer counts, weights)
    "SMB": ([1, 2, 3, 4], [0.55, 0.30, 0.12, 0.03]),
    "Mid-Market": ([1, 2, 3, 4], [0.30, 0.40, 0.22, 0.08]),
    "Enterprise": ([1, 2, 3, 4], [0.10, 0.32, 0.36, 0.22]),
}
SEG_CSUITE_PROB = {"SMB": 0.05, "Mid-Market": 0.15, "Enterprise": 0.42}
# Name pools for the sales org (opportunity owners + their managers). Generous
# enough (30 x 30 = 900 combos) that every region gets a disjoint, globally
# unique set with room to spare. Independent of faker so it's fully reproducible.
ORG_FIRST = ["Alex", "Jordan", "Taylor", "Morgan", "Casey", "Riley", "Sam", "Jamie",
             "Avery", "Quinn", "Drew", "Cameron", "Reese", "Skyler", "Blake", "Harper",
             "Emerson", "Rowan", "Sage", "Devon", "Lane", "Marley", "Kendall", "Parker",
             "Dana", "Elliot", "Frankie", "Gray", "Hayden", "Noel"]
ORG_LAST = ["Nguyen", "Patel", "Garcia", "Kim", "Rossi", "Haddad", "Okafor", "Silva",
            "Novak", "Ivanov", "Chen", "Muller", "Sato", "Adeyemi", "Larsen", "Costa",
            "Fischer", "Duarte", "Bauer", "Moreau", "Vidal", "Schmidt", "Bianchi",
            "Kowalski", "Nakamura", "Petrov", "Reyes", "Tanaka", "Dubois", "Meyer"]

STAGES = ["Discovery", "Qualification", "Proposal", "Negotiation",
          "Closed Won", "Closed Lost"]
OPEN_STAGES = STAGES[:4]
STAGE_WEIGHTS = [0.18, 0.22, 0.22, 0.15, 0.14, 0.09]

# Next scheduled meeting: most open deals have one on the calendar soon (sooner
# for later stages); a fraction have none booked -- itself a "reach out" signal.
# Closed deals have no next meeting. Drawn from a separate RNG so adding it does
# not perturb any other generated column.
NO_MEETING_PROB = 0.18
STAGE_MEETING_HORIZON = {"Negotiation": 7, "Proposal": 10, "Qualification": 12, "Discovery": 14}

# Typical days a healthy deal sits in each open stage (for staleness checks).
STAGE_NORMAL_DAYS = {"Discovery": 21, "Qualification": 25,
                     "Proposal": 20, "Negotiation": 18}


def _region_stage_norm(region, stage):
    """Typical days in `stage` for `region` -- US short, EMEA long. Shared with
    the detector via config.REGION_STAGE_NORMAL_DAYS so labels and rules agree."""
    table = config.REGION_STAGE_NORMAL_DAYS.get(region, {})
    return table.get(stage, STAGE_NORMAL_DAYS.get(stage, 20))


def _size_factor(employees):
    """Company size as a 0..1 factor on a log headcount scale."""
    lo, hi = _EMP_RANGE
    e = max(lo, min(hi, employees))
    return (math.log(e) - math.log(lo)) / (math.log(hi) - math.log(lo))


def _mrr(employees):
    """MRR driven by company size -- larger accounts buy higher MRR. Anchored at
    the $3,250 floor; only the largest firms reach the big ~$10K+ deals."""
    size = _size_factor(employees)
    mrr = MRR_FLOOR + MRR_SIZE_SPAN * (size**MRR_SIZE_EXP) + random.expovariate(1 / MRR_NOISE)
    return round(min(mrr, MRR_CAP), -1)


def _decision_profile(segment):
    """Champion seniority, approval-layer count, and C-suite gate for a deal."""
    champion = random.choices(config.CHAMPION_LEVELS, weights=SEG_CHAMPION_WEIGHTS[segment])[0]
    layers_opts, layers_w = SEG_APPROVAL_LAYERS[segment]
    approval_layers = random.choices(layers_opts, weights=layers_w)[0]
    csuite = 1 if random.random() < SEG_CSUITE_PROB[segment] else 0
    return champion, approval_layers, csuite


def _log_uniform(lo, hi):
    """Draw from a log-uniform distribution (more small than large)."""
    return math.exp(random.uniform(math.log(lo), math.log(hi)))


def _firmographics(segment):
    """Headcount, derived annual revenue, and industry for the account."""
    lo, hi = SEGMENT_EMPLOYEES[segment]
    employees = int(round(_log_uniform(lo, hi), -1))
    rev = employees * random.uniform(*REVENUE_PER_EMPLOYEE)
    account_revenue = int(round(rev, -5))  # nearest $100k
    industry = random.choices(INDUSTRIES, weights=INDUSTRY_WEIGHTS)[0]
    return employees, account_revenue, industry


def _region_discount(region, stage):
    """Sample a healthy discount. APAC discounts early and often as normal
    practice; other regions rarely discount deeply before value is proven."""
    if region == "APAC" and stage in ("Discovery", "Qualification"):
        pool = [0, 0.10, 0.20, 0.30, 0.35, 0.40]
        weights = [0.20, 0.20, 0.20, 0.15, 0.15, 0.10]
    else:
        pool = [0, 0.05, 0.10, 0.15, 0.25, 0.40]
        weights = [0.40, 0.20, 0.15, 0.10, 0.10, 0.05]
    return round(random.choices(pool, weights=weights)[0], 2)

MEDDPICC = ["metrics", "economic_buyer", "decision_criteria", "decision_process",
            "paper_process", "identified_pain", "champion", "competition"]


# ----------------------------------------------------------------------
# MEDDPICC scoring
# ----------------------------------------------------------------------
def _meddpicc_scores(stage, healthy=True):
    """
    Return dict of 8 MEDDPICC element scores (0-3).
    Later stages should generally have higher qualification.
    Unhealthy deals get artificially low scores in a few elements.
    """
    stage_floor = {"Discovery": 0, "Qualification": 1,
                   "Proposal": 1, "Negotiation": 2,
                   "Closed Won": 2, "Closed Lost": 0}.get(stage, 0)
    scores = {}
    for el in MEDDPICC:
        base = random.randint(stage_floor, 3)
        if not healthy:
            # depress the elements that most predict slippage
            if el in ("economic_buyer", "decision_process", "paper_process"):
                base = random.randint(0, 1)
        scores[el] = base
    return scores


def _meddpicc_rollup(scores):
    """Total 0-24 and a normalized 0-100 confidence proxy."""
    total = sum(scores.values())
    return total, round(total / (len(MEDDPICC) * 3) * 100)


# ----------------------------------------------------------------------
# Record generation
# ----------------------------------------------------------------------
def _base_record(i, today):
    seg = random.choices(SEGMENTS, weights=SEG_WEIGHTS)[0]
    stage = random.choices(STAGES, weights=STAGE_WEIGHTS)[0]
    region = random.choices(REGIONS, weights=REGION_WEIGHTS)[0]
    employees, account_revenue, industry = _firmographics(seg)
    mrr = _mrr(employees)  # larger accounts buy higher MRR
    arr = mrr * 12
    is_big = mrr >= BIG_DEAL_MRR_FLOOR

    champion_seniority, approval_layers, csuite_approval = _decision_profile(seg)
    is_senior_champ = config.CHAMPION_LEVELS.index(champion_seniority) >= config.CHAMPION_LEVELS.index(
        config.CHAMPION_SENIOR_MIN
    )
    is_simple = approval_layers <= config.SIMPLE_APPROVAL_MAX_LAYERS and csuite_approval == 0
    is_complex = csuite_approval == 1 or approval_layers >= config.COMPLEX_APPROVAL_MIN_LAYERS
    is_fast = is_senior_champ and is_simple
    slow = is_big or is_complex  # big or complex deals run a longer, less predictable cycle

    if slow:
        created = today - timedelta(days=random.randint(60, 320))
    elif is_fast:
        created = today - timedelta(days=random.randint(10, 90))
    else:
        created = today - timedelta(days=random.randint(15, 200))
    # base close date: past for closed, future for open
    if stage in ("Closed Won", "Closed Lost"):
        close = created + timedelta(days=random.randint(20, 120))
    elif slow:
        close = today + timedelta(days=random.randint(35, 150))
    elif is_fast:
        close = today + timedelta(days=random.randint(5, 40))
    else:
        close = today + timedelta(days=random.randint(5, 90))

    # Healthy deals sit up to their REGION's typical duration for the stage --
    # so a long-sitting EMEA proposal is normal, a long NA deal is not.
    stage_entry = today - timedelta(
        days=random.randint(1, _region_stage_norm(region, stage)))

    scores = _meddpicc_scores(stage, healthy=True)
    total, conf = _meddpicc_rollup(scores)

    # Forecast category follows how reps actually call deals: Commit only appears
    # at Negotiation (and only with real qualification behind it), Best Case not
    # until Proposal, and early-stage deals sit in Pipeline/Omitted. Closed deals
    # get the "Closed" category in a post-pass (_assign_closed_forecast) so this
    # open-stage draw sequence stays byte-identical.
    if stage == "Negotiation" and conf >= 60:
        fcat = random.choice(["Commit", "Best Case"])
    elif stage in ("Proposal", "Negotiation"):
        fcat = random.choice(["Best Case", "Pipeline"])
    else:
        fcat = random.choice(["Pipeline", "Omitted"])
    # Big/complex deals are less predictable -- reps hedge them out of Commit.
    if slow and fcat == "Commit" and random.random() < 0.6:
        fcat = "Best Case"

    rec = {
        "deal_id": f"D-{10000 + i}",
        "account": _company(),
        "segment": seg,
        "region": region,
        "industry": industry,
        "employees": employees,
        "account_revenue": account_revenue,
        "champion_seniority": champion_seniority,
        "approval_layers": approval_layers,
        "csuite_approval": csuite_approval,
        "mrr": mrr,
        "arr": arr,
        "stage": stage,
        "forecast_category": fcat,
        "rep": None,  # filled by caller from a shared rep pool
        "created_date": created,
        "close_date": close,
        "orig_close_date": close,       # for slip detection
        "stage_entry_date": stage_entry,
        "close_date_pushes": 0,
        "discount_pct": _region_discount(region, stage),
        "is_anomaly": False,
        "anomaly_types": [],
    }
    rec.update({f"m_{k}": v for k, v in scores.items()})
    rec["meddpicc_total"] = total
    rec["meddpicc_confidence"] = conf
    return rec


# ----------------------------------------------------------------------
# Anomaly injectors -- each mutates a record and tags ground truth
# ----------------------------------------------------------------------
def inj_slipped_close(rec, today):
    """Close date pushed multiple times, now well past original."""
    if rec["stage"] in ("Closed Won", "Closed Lost"):
        return False
    pushes = random.randint(2, 4)
    rec["close_date_pushes"] = pushes
    rec["close_date"] = rec["orig_close_date"] + timedelta(days=45 * pushes)
    rec["anomaly_types"].append("slipped_close_date")
    return True


def inj_stalled_stage(rec, today):
    """Sitting in an open stage far longer than normal FOR ITS REGION.

    A stalled NA deal sits 3-5x NA's short norm; a stalled EMEA deal sits 3-5x
    EMEA's long norm. Judged against the global norm this is ambiguous -- which
    is exactly why the region-aware detector wins.
    """
    if rec["stage"] not in OPEN_STAGES:
        return False
    normal = _region_stage_norm(rec["region"], rec["stage"])
    rec["stage_entry_date"] = today - timedelta(days=normal * random.randint(3, 5))
    rec["anomaly_types"].append("stalled_in_stage")
    return True


def inj_commit_low_qual(rec, today):
    """Forecasted Commit/Best Case but MEDDPICC is weak -- happy-ears risk."""
    if rec["stage"] in ("Closed Won", "Closed Lost"):
        return False
    weak = _meddpicc_scores(rec["stage"], healthy=False)
    rec.update({f"m_{k}": v for k, v in weak.items()})
    total, conf = _meddpicc_rollup(weak)
    rec["meddpicc_total"] = total
    rec["meddpicc_confidence"] = conf
    rec["forecast_category"] = "Commit"
    rec["anomaly_types"].append("commit_low_meddpicc")
    return True


def inj_late_stage_no_eb(rec, today):
    """Negotiation/Proposal with no Economic Buyer identified."""
    if rec["stage"] not in ("Proposal", "Negotiation"):
        return False
    rec["m_economic_buyer"] = 0
    total, conf = _meddpicc_rollup(
        {k[2:]: v for k, v in rec.items() if k.startswith("m_")})
    rec["meddpicc_total"] = total
    rec["meddpicc_confidence"] = conf
    rec["anomaly_types"].append("late_stage_no_economic_buyer")
    return True


def inj_deep_discount_early(rec, today):
    """Heavy discount offered before value is established (early stage).

    Not injected in APAC: an early deep discount is normal practice there, so it
    is not an anomaly -- only a region-aware detector gets this right.
    """
    if rec["stage"] not in ("Discovery", "Qualification"):
        return False
    if rec["region"] in config.REGION_DISCOUNT_TOLERANT:
        return False
    rec["discount_pct"] = round(random.uniform(0.30, 0.50), 2)
    rec["anomaly_types"].append("premature_deep_discount")
    return True


def inj_close_before_paper(rec, today):
    """Close date sooner than paper_process qualification supports."""
    if rec["stage"] in ("Closed Won", "Closed Lost"):
        return False
    rec["m_paper_process"] = 0
    rec["close_date"] = today + timedelta(days=random.randint(2, 7))
    rec["forecast_category"] = "Commit"
    total, conf = _meddpicc_rollup(
        {k[2:]: v for k, v in rec.items() if k.startswith("m_")})
    rec["meddpicc_total"] = total
    rec["meddpicc_confidence"] = conf
    rec["anomaly_types"].append("imminent_close_no_paper_process")
    return True


INJECTORS = [inj_slipped_close, inj_stalled_stage, inj_commit_low_qual,
             inj_late_stage_no_eb, inj_deep_discount_early, inj_close_before_paper]

# Injectors that leave the forecast category alone (a deal keeps its stage-based
# category). The two that force "Commit" (commit_low_qual, close_before_paper)
# are the happy-ears anomalies -- they only make sense on a deal a rep is
# actually committing, so they're reserved for watched deals below.
FORECAST_NEUTRAL_INJECTORS = [inj_slipped_close, inj_stalled_stage,
                              inj_late_stage_no_eb, inj_deep_discount_early]


# ----------------------------------------------------------------------
# Derived fields (what the detector will actually consume)
# ----------------------------------------------------------------------
def _derive(rec, today):
    rec["days_in_stage"] = (today - rec["stage_entry_date"]).days
    rec["days_to_close"] = (rec["close_date"] - today).days
    rec["days_open"] = (today - rec["created_date"]).days
    rec["slip_days"] = (rec["close_date"] - rec["orig_close_date"]).days
    return rec


def _build_region_org(records, seed):
    """A region-disjoint sales org: opportunity owners + their sales managers.

    Returns ``{region: (owners, owner_to_manager)}``. Names are drawn from a
    dedicated RNG (independent of the main generation sequence) and de-duplicated
    globally, so NO owner or manager name is ever repeated across regions. Book
    sizes scale with each region's deal count (~20 deals/owner, ~4 owners/manager).
    """
    rng = random.Random(seed + 4242)
    used = set()

    def _name():
        while True:  # redraw until globally unique
            name = f"{rng.choice(ORG_FIRST)} {rng.choice(ORG_LAST)}"
            if name not in used:
                used.add(name)
                return name

    org = {}
    for region in REGIONS:
        count = sum(1 for r in records if r["region"] == region)
        if count == 0:
            continue
        n_owners = max(4, round(count / 20))
        n_managers = max(1, round(n_owners / 4))
        managers = [_name() for _ in range(n_managers)]
        owners = [_name() for _ in range(n_owners)]
        owner_to_manager = {o: managers[i % n_managers] for i, o in enumerate(owners)}
        org[region] = (owners, owner_to_manager)
    return org


def _assign_closed_forecast(records):
    """Forecast category for booked/lost deals.

    A **Closed Won** deal is booked: it carries no risk (nothing left to slip) and
    counts toward the period's forecast, so it gets the "Closed" category. A
    **Closed Lost** deal is gone -- it's excluded from the forecast entirely, so
    it gets "Omitted" (matching how CRMs drop lost deals out of the rollup).

    Open deals keep the stage-gated category assigned in ``_base_record`` (Commit
    only at Negotiation, Best Case only at Proposal+). This post-pass touches only
    closed-stage rows and uses no RNG, so every other column -- and the detector
    scorecard -- stays byte-identical.
    """
    for rec in records:
        if rec["stage"] == "Closed Won":
            rec["forecast_category"] = "Closed"
        elif rec["stage"] == "Closed Lost":
            rec["forecast_category"] = "Omitted"


def _next_meeting(rec, today, rng):
    """Upcoming meeting date for an open deal (or "" if none / closed).

    ``rng`` is a dedicated random.Random so this draw is independent of the
    main generation sequence -- every other column stays byte-identical.
    """
    if rec["stage"] not in OPEN_STAGES:
        return ""
    if rng.random() < NO_MEETING_PROB:
        return ""  # nothing on the calendar -- the VP/rep needs to book one
    horizon = STAGE_MEETING_HORIZON.get(rec["stage"], 14)
    days = rng.randint(1, horizon)
    dtc = rec["days_to_close"]
    if dtc and dtc > 0:
        days = min(days, max(1, dtc))  # never schedule the meeting past close
    return today + timedelta(days=days)


# ----------------------------------------------------------------------
# Main build
# ----------------------------------------------------------------------
def build(n=600, seed=42, anomaly_rate=0.18):
    random.seed(seed)
    _seed_faker(seed)
    today = date.today()

    reps = [_person() for _ in range(max(6, n // 40))]

    records = []
    for i in range(n):
        rec = _base_record(i, today)
        rec["rep"] = random.choice(reps)  # placeholder; region-specific owner set below
        records.append(rec)

    # Inject anomalies into a random subset. How MANY issues a deal accumulates,
    # and which kind, mirrors reality: a rep watches the deals they commit, so a
    # flagged Commit usually hides a single decisive flaw (the "happy ears" case).
    # Low-commitment deals (Pipeline/Omitted) get less attention, so when they go
    # wrong they stack up several *hygiene* problems -- which lifts them off the
    # single-issue risk-2 floor into the medium/high band, and keeps the top of
    # the risk range from being all-Commit. The pre-injection (stage-based)
    # forecast tells us how watched the deal is.
    n_anom = int(n * anomaly_rate)
    targets = random.sample(records, n_anom)
    for rec in targets:
        low_commitment = rec["forecast_category"] in ("Pipeline", "Omitted")
        if low_commitment:
            # Neglected: 2-3 forecast-neutral problems -> medium/high risk, still
            # Pipeline/Omitted (never force it up to Commit).
            pool = list(FORECAST_NEUTRAL_INJECTORS)
            want = random.choices([2, 3], weights=[0.55, 0.45])[0]
        else:
            # Watched (Commit/Best Case): usually one serious flaw, any type.
            pool = list(INJECTORS)
            want = random.choices([1, 2], weights=[0.70, 0.30])[0]
        random.shuffle(pool)  # shuffle a copy; never mutate the shared list
        applied = 0
        for inj in pool:
            if inj(rec, today):
                applied += 1
                if applied >= want:
                    break
        if applied:
            rec["is_anomaly"] = True

    for rec in records:
        _derive(rec, today)

    # Booked deals are "Closed" in the forecast (no RNG; open deals untouched).
    _assign_closed_forecast(records)

    # Assign next-meeting dates from a dedicated RNG so this new column does not
    # shift the main random sequence (every other column stays reproducible).
    # days_to_next_meeting is precomputed (like days_to_close) so the detector
    # reads a stable int instead of re-diffing dates against a drifting "today".
    meeting_rng = random.Random(seed + 777)
    for rec in records:
        nm = _next_meeting(rec, today, meeting_rng)
        rec["next_meeting_date"] = nm
        rec["days_to_next_meeting"] = (nm - today).days if nm != "" else ""

    # Assign a region-disjoint opportunity owner + sales manager to each deal.
    # Owners are distributed round-robin within their region (balanced, no RNG),
    # and the org names come from a dedicated RNG -- so this overwrites the
    # placeholder `rep` and adds `sales_manager` without touching any other
    # column, keeping the dataset reproducible.
    org = _build_region_org(records, seed)
    seen_per_region = {region: 0 for region in org}
    for rec in records:
        owners, owner_to_manager = org[rec["region"]]
        owner = owners[seen_per_region[rec["region"]] % len(owners)]
        seen_per_region[rec["region"]] += 1
        rec["rep"] = owner
        rec["sales_manager"] = owner_to_manager[owner]

    df = pd.DataFrame(records)
    df["anomaly_types"] = df["anomaly_types"].apply(lambda x: "|".join(x))

    col_order = [
        "deal_id", "account", "segment", "region",
        "industry", "employees", "account_revenue",
        "champion_seniority", "approval_layers", "csuite_approval",
        "mrr", "arr", "stage", "forecast_category",
        "rep", "sales_manager", "created_date", "stage_entry_date", "orig_close_date",
        "close_date", "next_meeting_date", "close_date_pushes", "discount_pct",
        "days_open", "days_in_stage", "days_to_close", "days_to_next_meeting", "slip_days",
        *[f"m_{k}" for k in MEDDPICC],
        "meddpicc_total", "meddpicc_confidence",
        "is_anomaly", "anomaly_types",
    ]
    return df[col_order]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=600)
    ap.add_argument("--seed", type=int, default=28)
    ap.add_argument("--anomaly-rate", type=float, default=0.18)
    ap.add_argument("--out", default="pipeline.csv")
    args = ap.parse_args()

    df = build(args.n, args.seed, args.anomaly_rate)
    df.to_csv(args.out, index=False)

    n_anom = int(df["is_anomaly"].sum())
    print(f"Wrote {len(df)} opportunities to {args.out}")
    print(f"  Anomalies: {n_anom} ({n_anom / len(df):.0%})")
    print(f"  Total ARR: ${df['arr'].sum():,.0f}")
    print("\nAnomaly type breakdown:")
    from collections import Counter
    c = Counter()
    for s in df.loc[df.is_anomaly, "anomaly_types"]:
        for t in s.split("|"):
            c[t] += 1
    for t, k in c.most_common():
        print(f"  {k:>3}  {t}")


if __name__ == "__main__":
    main()
