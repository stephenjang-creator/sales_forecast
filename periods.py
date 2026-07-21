"""Time-period math over the pipeline and the historical bookings files.

Pure, offline, deterministic. Two jobs:

1. **Pipeline by period** -- bucket the scored pipeline by the calendar period
   each deal's ``close_date`` falls in, and within the current period compute the
   won-so-far + risk-adjusted expected-to-close rollup an agent needs for
   "how much will we book this month/quarter?".
2. **History by period** -- roll the monthly ``history.csv`` up to month / quarter
   / year, compute attainment (bookings / quota), and derive MoM / QoQ / YoY
   comparisons.

The risk-adjustment reuses the same ``config`` win-rates and haircut as
``agents/baseline.py`` so the number is consistent everywhere.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

import config

GRAINS = ("month", "quarter", "year")


# --------------------------------------------------------------------------- #
# Period keys
# --------------------------------------------------------------------------- #
def _to_date(value: object) -> date:
    """Parse a 'YYYY-MM-DD' string (or date) into a date."""
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def period_key(d: date, grain: str) -> str:
    """Calendar period key: '2026-07', '2026-Q3', or '2026'."""
    if grain == "month":
        return f"{d.year:04d}-{d.month:02d}"
    if grain == "quarter":
        return f"{d.year:04d}-Q{(d.month - 1) // 3 + 1}"
    if grain == "year":
        return f"{d.year:04d}"
    raise ValueError(f"unknown grain {grain!r}")


def month_period_to_grain(month_period: str, grain: str) -> str:
    """Convert a monthly key ('2026-07') up to the requested grain."""
    year, month = int(month_period[:4]), int(month_period[5:7])
    return period_key(date(year, month, 1), grain)


# --------------------------------------------------------------------------- #
# Pipeline bucketing
# --------------------------------------------------------------------------- #
def _win_rate(stage: str) -> float:
    return config.STAGE_WIN_RATE.get(stage, 0.0)


def current_period_key(scored: pd.DataFrame, grain: str) -> str | None:
    """The in-progress period: the one holding the earliest open-deal close."""
    open_rows = scored[scored["stage"].isin(config.OPEN_STAGES)]
    source = open_rows if not open_rows.empty else scored
    if source.empty:
        return None
    earliest = min(_to_date(v) for v in source["close_date"])
    return period_key(earliest, grain)


def pipeline_by_period(scored: pd.DataFrame, grain: str, region: str | None = None) -> list[dict]:
    """Bucket the pipeline by close-date period.

    Each bucket carries won ARR (already Closed Won), open pipeline ARR, the
    stage-weighted open ARR, the risk-adjusted open ARR (weighted, minus a
    haircut on flagged deals and plus an uplift on fast movers), flagged open ARR,
    fast-mover open ARR, and open-deal count. The current in-progress period is
    marked ``is_current``.
    """
    df = scored
    if region is not None:
        if "region" not in df.columns:
            raise ValueError("no region column")
        df = df[df["region"] == region]

    open_stages = set(config.OPEN_STAGES)
    haircut = config.FLAGGED_RISK_HAIRCUT
    uplift = config.FAST_MOVER_UPLIFT
    buckets: dict[str, dict] = {}
    for row in df.to_dict("records"):
        key = period_key(_to_date(row["close_date"]), grain)
        b = buckets.setdefault(
            key,
            {
                "period": key,
                "won_arr": 0.0,
                "open_arr": 0.0,
                "weighted_open_arr": 0.0,
                "risk_adjusted_open_arr": 0.0,
                "flagged_open_arr": 0.0,
                "fast_mover_open_arr": 0.0,
                "open_deals": 0,
            },
        )
        arr = float(row["arr"])
        stage = str(row["stage"])
        if stage == "Closed Won":
            b["won_arr"] += arr
        if stage in open_stages:
            flagged = bool(row["predicted_anomaly"])
            fast_mover = bool(row.get("fast_mover", False))
            weighted = arr * _win_rate(stage)
            # Risk dominates: a flagged fast mover takes the haircut, not the uplift.
            if flagged:
                adjusted = weighted * (1 - haircut)
            elif fast_mover:
                adjusted = min(weighted * (1 + uplift), arr)
            else:
                adjusted = weighted
            b["open_arr"] += arr
            b["weighted_open_arr"] += weighted
            b["risk_adjusted_open_arr"] += adjusted
            b["open_deals"] += 1
            if flagged:
                b["flagged_open_arr"] += arr
            elif fast_mover:
                b["fast_mover_open_arr"] += arr

    current = current_period_key(scored if region is None else df, grain)
    out = []
    for key in sorted(buckets):
        b = buckets[key]
        b = {k: (round(v, 0) if isinstance(v, float) else v) for k, v in b.items()}
        b["is_current"] = key == current
        out.append(b)
    return out


# --------------------------------------------------------------------------- #
# History loading + aggregation
# --------------------------------------------------------------------------- #
def _read_region_csv(path: str | Path) -> pd.DataFrame:
    """Read a CSV, restoring the 'NA' region that pandas reads as NaN."""
    df = pd.read_csv(path)
    if "region" in df.columns:
        df["region"] = df["region"].fillna("NA")
    return df


def load_history(path: str | Path) -> pd.DataFrame:
    return _read_region_csv(path)


def load_targets(path: str | Path) -> pd.DataFrame:
    return _read_region_csv(path)


def _region_filter(df: pd.DataFrame, region: str | None) -> pd.DataFrame:
    return df if region is None else df[df["region"] == region]


def history_by_grain(
    hist: pd.DataFrame, grain: str, region: str | None = None, last_n: int | None = None
) -> list[dict]:
    """Roll monthly history up to a grain: bookings, quota, attainment, deals."""
    df = _region_filter(hist, region).copy()
    df["gkey"] = df["period"].apply(lambda p: month_period_to_grain(p, grain))
    grouped = df.groupby("gkey")[["bookings", "quota", "deals_won"]].sum().reset_index()
    grouped = grouped.sort_values("gkey")
    rows = []
    for r in grouped.to_dict("records"):
        quota = float(r["quota"])
        bookings = float(r["bookings"])
        rows.append(
            {
                "period": r["gkey"],
                "bookings": round(bookings, 0),
                "quota": round(quota, 0),
                "attainment_pct": round(bookings / quota * 100, 1) if quota else None,
                "deals_won": int(r["deals_won"]),
            }
        )
    if last_n is not None:
        rows = rows[-last_n:]
    return rows


def _pct_change(current: float, prior: float) -> float | None:
    if not prior:
        return None
    return round((current - prior) / prior * 100, 1)


def _prior_year_key(period: str, grain: str) -> str:
    if grain == "year":
        return str(int(period) - 1)
    if grain == "quarter":
        year, q = period.split("-Q")
        return f"{int(year) - 1}-Q{q}"
    year, month = period.split("-")
    return f"{int(year) - 1}-{month}"


def comparisons(hist: pd.DataFrame, grain: str, region: str | None = None) -> dict:
    """MoM/QoQ/YoY-style deltas on actuals for the latest complete period."""
    series = history_by_grain(hist, grain, region)
    if not series:
        return {"error": "no history"}
    by_key = {r["period"]: r for r in series}
    latest = series[-1]
    prior = series[-2] if len(series) >= 2 else None
    yoy = by_key.get(_prior_year_key(latest["period"], grain))
    label = {"month": "MoM", "quarter": "QoQ", "year": "YoY"}[grain]
    return {
        "grain": grain,
        "latest_period": latest["period"],
        "latest_bookings": latest["bookings"],
        "latest_attainment_pct": latest["attainment_pct"],
        "sequential_label": label,
        "prior_period": prior["period"] if prior else None,
        "prior_bookings": prior["bookings"] if prior else None,
        "sequential_change_pct": (
            _pct_change(latest["bookings"], prior["bookings"]) if prior else None
        ),
        "yoy_period": yoy["period"] if yoy else None,
        "yoy_bookings": yoy["bookings"] if yoy else None,
        "yoy_change_pct": (_pct_change(latest["bookings"], yoy["bookings"]) if yoy else None),
    }


def _target_for_period(targets: pd.DataFrame, gkey: str, grain: str, region: str | None) -> float:
    df = _region_filter(targets, region).copy()
    df["gkey"] = df["period"].apply(lambda p: month_period_to_grain(p, grain))
    return float(df[df["gkey"] == gkey]["quota"].sum())


# --------------------------------------------------------------------------- #
# The headline: current-period bookings rollup
# --------------------------------------------------------------------------- #
def bookings_rollup(
    scored: pd.DataFrame,
    grain: str,
    region: str | None = None,
    targets: pd.DataFrame | None = None,
    hist: pd.DataFrame | None = None,
) -> dict:
    """Projected bookings for the current in-progress month/quarter.

    projected = Closed-Won so far this period + risk-adjusted expected bookings
    from open deals closing in the period. Adds quota-based attainment (if
    targets given) and prior/YoY actuals for context (if history given).
    """
    current = current_period_key(scored, grain)
    if current is None:
        return {"error": "no deals to roll up"}
    buckets = {b["period"]: b for b in pipeline_by_period(scored, grain, region)}
    cur = buckets.get(
        current,
        {"won_arr": 0.0, "risk_adjusted_open_arr": 0.0, "open_arr": 0.0, "open_deals": 0},
    )
    won = float(cur["won_arr"])
    expected_open = float(cur["risk_adjusted_open_arr"])
    projected = round(won + expected_open, 0)

    result = {
        "grain": grain,
        "region": region or "ALL",
        "current_period": current,
        "won_so_far": round(won, 0),
        "expected_to_close": round(expected_open, 0),
        "projected_bookings": projected,
        "open_pipeline_arr": round(float(cur["open_arr"]), 0),
        "open_deals": int(cur["open_deals"]),
        "basis": (
            "won-so-far + risk-adjusted expected-to-close (stage win-rates, "
            f"{config.FLAGGED_RISK_HAIRCUT:.0%} haircut on flagged deals, "
            f"{config.FAST_MOVER_UPLIFT:.0%} uplift on fast movers)"
        ),
    }

    if targets is not None:
        quota = _target_for_period(targets, current, grain, region)
        result["quota"] = round(quota, 0)
        result["projected_attainment_pct"] = round(projected / quota * 100, 1) if quota else None

    if hist is not None:
        series = {r["period"]: r for r in history_by_grain(hist, grain, region)}
        prior_actual = series.get(sorted(series)[-1]) if series else None
        yoy_actual = series.get(_prior_year_key(current, grain))
        if prior_actual:
            result["prior_period_actual"] = {
                "period": prior_actual["period"],
                "bookings": prior_actual["bookings"],
            }
            result["vs_prior_period_pct"] = _pct_change(projected, prior_actual["bookings"])
        if yoy_actual:
            result["yoy_period_actual"] = {
                "period": yoy_actual["period"],
                "bookings": yoy_actual["bookings"],
            }
            result["yoy_change_pct"] = _pct_change(projected, yoy_actual["bookings"])
        result["note"] = (
            "Current period is IN PROGRESS and reflects only currently-open "
            "pipeline; a mid-period projection sits below a completed historical "
            "period, so a negative vs-prior/YoY delta is expected this early. "
            "Read it as coverage/pace, not a final result."
        )

    return result
