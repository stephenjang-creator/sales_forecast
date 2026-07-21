"""
generate_forecast_data.py
--------------------------
Synthetic pipeline generator for a RevOps Forecast Anomaly Detector.

Produces a labeled dataset where each opportunity carries:
  - Standard CRM fields (segment, ARR, stage, dates, rep, discount)
  - Full MEDDPICC qualification scores (0-3 per element) + a rollup
  - A ground-truth `is_anomaly` flag and `anomaly_types` list

Anomalies are injected deliberately so the detector has a real test set
to score precision/recall against. No production data is used.

Runtime deps: pandas (required), faker (optional -- falls back to a built-in
name/company pool if not installed).

Usage:
    python generate_forecast_data.py --n 600 --seed 42 --out pipeline.csv
"""

import argparse
import random
from datetime import date, timedelta

import pandas as pd

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
ARR_RANGE = {
    "Enterprise": (80_000, 400_000),
    "Mid-Market": (20_000, 80_000),
    "SMB": (3_000, 20_000),
}
STAGES = ["Discovery", "Qualification", "Proposal", "Negotiation",
          "Closed Won", "Closed Lost"]
OPEN_STAGES = STAGES[:4]
STAGE_WEIGHTS = [0.18, 0.22, 0.22, 0.15, 0.14, 0.09]

# Typical days a healthy deal sits in each open stage (for staleness checks)
STAGE_NORMAL_DAYS = {"Discovery": 21, "Qualification": 25,
                     "Proposal": 20, "Negotiation": 18}

MEDDPICC = ["metrics", "economic_buyer", "decision_criteria", "decision_process",
            "paper_process", "identified_pain", "champion", "competition"]

# Forecast categories a rep/AE would set
FORECAST_CATEGORY = ["Omitted", "Pipeline", "Best Case", "Commit"]


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
    lo, hi = ARR_RANGE[seg]
    arr = round(random.uniform(lo, hi), -2)
    stage = random.choices(STAGES, weights=STAGE_WEIGHTS)[0]

    created = today - timedelta(days=random.randint(15, 200))
    # base close date: some in past for closed, future for open
    if stage in ("Closed Won", "Closed Lost"):
        close = created + timedelta(days=random.randint(20, 120))
    else:
        close = today + timedelta(days=random.randint(5, 90))

    stage_entry = today - timedelta(
        days=random.randint(1, STAGE_NORMAL_DAYS.get(stage, 20)))

    scores = _meddpicc_scores(stage, healthy=True)
    total, conf = _meddpicc_rollup(scores)

    # forecast category loosely tied to stage + qualification
    if stage == "Negotiation" and conf >= 60:
        fcat = random.choice(["Commit", "Best Case"])
    elif stage in ("Proposal", "Negotiation"):
        fcat = random.choice(["Best Case", "Pipeline"])
    else:
        fcat = random.choice(["Pipeline", "Omitted"])

    rec = {
        "deal_id": f"D-{10000 + i}",
        "account": _company(),
        "segment": seg,
        "region": random.choices(REGIONS, weights=REGION_WEIGHTS)[0],
        "arr": arr,
        "stage": stage,
        "forecast_category": fcat,
        "rep": None,  # filled by caller from a shared rep pool
        "created_date": created,
        "close_date": close,
        "orig_close_date": close,       # for slip detection
        "stage_entry_date": stage_entry,
        "close_date_pushes": 0,
        "discount_pct": round(random.choices(
            [0, .05, .10, .15, .25, .40],
            weights=[.40, .20, .15, .10, .10, .05])[0], 2),
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
    """Sitting in an open stage far longer than normal."""
    if rec["stage"] not in OPEN_STAGES:
        return False
    normal = STAGE_NORMAL_DAYS[rec["stage"]]
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
    """Heavy discount offered before value is established (early stage)."""
    if rec["stage"] not in ("Discovery", "Qualification"):
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


# ----------------------------------------------------------------------
# Derived fields (what the detector will actually consume)
# ----------------------------------------------------------------------
def _derive(rec, today):
    rec["days_in_stage"] = (today - rec["stage_entry_date"]).days
    rec["days_to_close"] = (rec["close_date"] - today).days
    rec["days_open"] = (today - rec["created_date"]).days
    rec["slip_days"] = (rec["close_date"] - rec["orig_close_date"]).days
    return rec


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
        rec["rep"] = random.choice(reps)
        records.append(rec)

    # Inject anomalies into a random subset
    n_anom = int(n * anomaly_rate)
    targets = random.sample(records, n_anom)
    for rec in targets:
        random.shuffle(INJECTORS)
        applied = 0
        want = random.choices([1, 2], weights=[0.75, 0.25])[0]
        for inj in INJECTORS:
            if inj(rec, today):
                applied += 1
                if applied >= want:
                    break
        if applied:
            rec["is_anomaly"] = True

    for rec in records:
        _derive(rec, today)

    df = pd.DataFrame(records)
    df["anomaly_types"] = df["anomaly_types"].apply(lambda x: "|".join(x))

    col_order = [
        "deal_id", "account", "segment", "region", "arr", "stage", "forecast_category",
        "rep", "created_date", "stage_entry_date", "orig_close_date",
        "close_date", "close_date_pushes", "discount_pct",
        "days_open", "days_in_stage", "days_to_close", "slip_days",
        *[f"m_{k}" for k in MEDDPICC],
        "meddpicc_total", "meddpicc_confidence",
        "is_anomaly", "anomaly_types",
    ]
    return df[col_order]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=600)
    ap.add_argument("--seed", type=int, default=42)
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
