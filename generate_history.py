"""generate_history.py -- synthetic historical bookings + forward targets.

Companion to ``generate_forecast_data.py``. Produces two small labeled files the
attainment agents use to answer YoY / QoQ / MoM questions and to compute true
attainment (bookings / quota):

  data/history.csv   past 36 completed months of ACTUAL bookings per region,
                     with the quota that was set and deals_won.
  data/targets.csv   quota for the current month through the next few months,
                     so the current in-progress period has a target to measure
                     projected bookings against.

Bookings follow a plausible shape: per-region baseline, YoY growth, quarter
seasonality, an end-of-quarter ramp, and a little noise. Historical attainment
lands realistically around 100%. All data is synthetic. No production data.

Usage:
    python generate_history.py --seed 42 --years 3
"""

from __future__ import annotations

import argparse
import random
from datetime import date

import pandas as pd

REGIONS = ["NAM", "EMEA", "APAC", "LATAM"]  # NAM (not "NA": collides with pandas NaN)

# Rough current monthly bookings run-rate per region (before seasonality/noise).
# Calibrated to the pipeline's deal economics (ASP ~$3,850 MRR ≈ $46k ARR) so
# current-period attainment reads sensibly against projected pipeline bookings.
BASE_MONTHLY = {"NAM": 1_480_000, "EMEA": 940_000, "APAC": 470_000, "LATAM": 310_000}
AVG_DEAL = {"NAM": 60_000, "EMEA": 52_000, "APAC": 46_000, "LATAM": 44_000}

YOY_GROWTH = 0.15  # business grows ~15% year over year
QUARTER_SEASONALITY = {1: 0.90, 2: 1.00, 3: 1.05, 4: 1.20}  # Q4 heavy, Q1 soft
MONTH_IN_QUARTER = {0: 0.80, 1: 1.00, 2: 1.30}  # ramp toward quarter end
NOISE = 0.08  # +/- on actual bookings
TARGET_ATTAINMENT_SD = 0.06  # spread of historical bookings/quota around 1.0


def _month_floor(d: date) -> date:
    return date(d.year, d.month, 1)


def _add_months(d: date, n: int) -> date:
    idx = (d.year * 12 + (d.month - 1)) + n
    return date(idx // 12, idx % 12 + 1, 1)


def _quarter(month: int) -> int:
    return (month - 1) // 3 + 1


def _model_bookings(region: str, months_from_now: int, month: int) -> float:
    """Deterministic (noise-free) expected bookings for a region in a month.

    ``months_from_now`` is negative for the past. Used as the quota basis so a
    'normal' month attains ~100%.
    """
    growth = (1 + YOY_GROWTH) ** (months_from_now / 12.0)
    seasonal = QUARTER_SEASONALITY[_quarter(month)]
    ramp = MONTH_IN_QUARTER[(month - 1) % 3]
    return BASE_MONTHLY[region] * growth * seasonal * ramp


def build(seed: int = 42, years: int = 3) -> tuple[pd.DataFrame, pd.DataFrame]:
    random.seed(seed)
    anchor = _month_floor(date.today())  # first day of the current month
    n_hist = years * 12

    hist_rows = []
    for k in range(n_hist, 0, -1):  # oldest -> newest, all before the anchor
        m = _add_months(anchor, -k)
        period = f"{m.year:04d}-{m.month:02d}"
        for region in REGIONS:
            model = _model_bookings(region, -k, m.month)
            bookings = round(model * (1 + random.uniform(-NOISE, NOISE)), -2)
            target_attain = max(0.80, random.gauss(1.0, TARGET_ATTAINMENT_SD))
            quota = round(model / target_attain, -2)
            deals_won = max(1, round(bookings / AVG_DEAL[region]))
            hist_rows.append(
                {
                    "period": period,
                    "region": region,
                    "bookings": bookings,
                    "quota": quota,
                    "deals_won": deals_won,
                }
            )

    # Forward targets: current month + the next 5 (covers current & next quarter).
    tgt_rows = []
    for k in range(0, 6):
        m = _add_months(anchor, k)
        period = f"{m.year:04d}-{m.month:02d}"
        for region in REGIONS:
            quota = round(_model_bookings(region, k, m.month), -2)
            tgt_rows.append({"period": period, "region": region, "quota": quota})

    hist = pd.DataFrame(hist_rows)
    hist["attainment_pct"] = (hist["bookings"] / hist["quota"] * 100).round(1)
    targets = pd.DataFrame(tgt_rows)
    return hist, targets


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--years", type=int, default=3)
    ap.add_argument("--hist-out", default="data/history.csv")
    ap.add_argument("--targets-out", default="data/targets.csv")
    args = ap.parse_args()

    hist, targets = build(args.seed, args.years)
    hist.to_csv(args.hist_out, index=False)
    targets.to_csv(args.targets_out, index=False)

    print(f"Wrote {len(hist)} history rows to {args.hist_out}")
    print(f"  Months: {hist['period'].nunique()} x {hist['region'].nunique()} regions")
    print(f"  Total historical bookings: ${hist['bookings'].sum():,.0f}")
    print(f"  Mean attainment: {hist['attainment_pct'].mean():.1f}%")
    print(f"Wrote {len(targets)} target rows to {args.targets_out}")
    print(f"  Forward periods: {sorted(targets['period'].unique())}")


if __name__ == "__main__":
    main()
