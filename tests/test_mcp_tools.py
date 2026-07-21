"""Tests for the MCP tool functions, called directly (not over the wire).

These import the underlying callables from ``mcp_server`` and assert the shape
of each tool's return plus a couple of ground-truth-anchored facts (a known
flagged deal comes back flagged; region roll-ups are sane). No transport, no
LLM, no network.
"""

from __future__ import annotations

import json

import mcp_server as srv
from detector.engine import load


def _a_flagged_deal_id() -> str:
    """A deal_id the deterministic engine flags on the seeded dataset."""
    df = srv._df()
    flagged = df[df["predicted_anomaly"]]
    assert not flagged.empty, "seeded dataset should contain flagged deals"
    return str(flagged.iloc[0]["deal_id"])


def test_state_loaded_and_scored() -> None:
    df = srv._df()
    for col in ("hits", "risk_score", "predicted_anomaly", "top_reason"):
        assert col in df.columns
    assert len(df) == 600


def test_list_deals_shape_and_cap() -> None:
    deals = srv.list_deals(limit=5)
    assert isinstance(deals, list) and len(deals) <= 5
    expected = {
        "deal_id",
        "account",
        "region",
        "segment",
        "industry",
        "mrr",
        "stage",
        "forecast_category",
        "arr",
        "close_date",
        "risk_score",
        "predicted_anomaly",
        "signals",
        "top_reason",
    }
    assert set(deals[0].keys()) == expected
    json.dumps(deals)  # must be JSON-serializable


def test_signals_surfaced() -> None:
    # Fast-mover filter + assess_deal decision profile & signals + summary.
    fast = srv.list_deals(signal="fast_mover", limit=5)
    assert fast, "expected some fast movers"
    assert all("fast_mover" in d["signals"] for d in fast)
    full = srv.assess_deal(fast[0]["deal_id"])
    assert full["decision_profile"]["champion_seniority"] is not None
    assert any(s["signal_id"] == "fast_mover" for s in full["signals"])

    summary = srv.signals_summary(region="EMEA")
    for sig in ("fast_mover", "complex_deal"):
        assert {"count", "arr"} == set(summary[sig].keys())
    json.dumps(summary)


def test_firmographics_and_mrr() -> None:
    # Deal economics: arr == mrr * 12, and firmographics are surfaced.
    deal = srv.list_deals(limit=1)[0]
    assert deal["mrr"] >= 3250  # MRR floor
    assert abs(deal["arr"] - deal["mrr"] * 12) < 1.0
    full = srv.assess_deal(deal["deal_id"])
    for key in ("industry", "employees", "account_revenue", "mrr"):
        assert full[key] is not None
    industries = srv.list_industries()
    assert isinstance(industries, list) and deal["industry"] in industries
    # industry filter narrows the set
    filtered = srv.list_deals(industry=industries[0], limit=500)
    assert all(d["industry"] == industries[0] for d in filtered)


def test_list_deals_flagged_only() -> None:
    deals = srv.list_deals(flagged_only=True, limit=50)
    assert deals, "expected some flagged deals"
    assert all(d["predicted_anomaly"] for d in deals)
    # Sorted by risk_score descending.
    scores = [d["risk_score"] for d in deals]
    assert scores == sorted(scores, reverse=True)


def test_list_deals_region_filter() -> None:
    deals = srv.list_deals(region="EMEA", limit=100)
    assert isinstance(deals, list)
    assert all(d["region"] == "EMEA" for d in deals)


def test_assess_deal_known_flagged() -> None:
    deal_id = _a_flagged_deal_id()
    result = srv.assess_deal(deal_id)
    assert result["deal_id"] == deal_id
    assert result["predicted_anomaly"] is True
    assert len(result["meddpicc"]) == 8
    assert result["hits"], "a flagged deal must carry at least one hit"
    hit = result["hits"][0]
    assert {"rule_id", "severity", "reason"} <= set(hit.keys())
    json.dumps(result)


def test_assess_deal_not_found() -> None:
    result = srv.assess_deal("D-00000-nope")
    assert "error" in result


def test_assess_segment_rollup() -> None:
    result = srv.assess_segment("Enterprise")
    for key in (
        "deals",
        "flagged",
        "total_arr",
        "at_risk_arr",
        "commit_arr",
        "at_risk_pct_of_commit",
        "top_reasons",
        "avg_meddpicc_confidence",
        "note",
    ):
        assert key in result
    assert result["deals"] > 0
    assert result["flagged"] <= result["deals"]
    assert result["at_risk_arr"] <= result["total_arr"] + 1e-6
    assert "not a predicted" in result["note"].lower()


def test_assess_segment_unknown() -> None:
    assert "error" in srv.assess_segment("Nonexistent")


def test_assess_region_emea_sane() -> None:
    result = srv.assess_region("EMEA")
    assert result["region"] == "EMEA"
    assert result["deals"] > 0
    assert 0 <= result["at_risk_pct_of_commit"] <= 100
    assert isinstance(result["top_reasons"], list)
    json.dumps(result)


def test_assess_region_na_not_dropped() -> None:
    # "NA" collides with pandas' NaN sentinel; the loader must preserve it.
    result = srv.assess_region("NA")
    assert "error" not in result
    assert result["deals"] > 0


def test_forecast_summary_commit_exposure() -> None:
    result = srv.forecast_summary("Commit")
    assert result["forecast_category"] == "Commit"
    for rule in ("commit_low_meddpicc", "imminent_close_no_paper_process"):
        assert {"count", "arr"} == set(result[rule].keys())
    assert result["flagged_arr"] <= result["total_arr"] + 1e-6
    json.dumps(result)


def test_forecast_summary_all() -> None:
    result = srv.forecast_summary()
    assert result["forecast_category"] == "ALL"
    assert result["deals"] == 600


def test_get_scorecard_shape() -> None:
    sc = srv.get_scorecard()
    assert {"precision", "recall", "f1", "tp", "fp", "fn", "tn"} <= set(sc["overall"].keys())
    assert len(sc["per_rule"]) == 6
    assert 0.0 <= sc["overall"]["precision"] <= 1.0
    json.dumps(sc)


def test_list_regions_and_segments() -> None:
    regions = srv.list_regions()
    assert set(regions) == {"NA", "EMEA", "APAC", "LATAM"}
    segments = srv.list_segments()
    assert set(segments) == {"Enterprise", "Mid-Market", "SMB"}


def test_bookings_rollup_current_period() -> None:
    result = srv.bookings_rollup("quarter", "EMEA")
    assert result["region"] == "EMEA"
    assert result["grain"] == "quarter"
    assert "current_period" in result
    # projected = won-so-far + expected-to-close
    assert result["projected_bookings"] == round(
        result["won_so_far"] + result["expected_to_close"], 0
    )
    # quota + attainment present because targets are bundled
    assert result["quota"] > 0
    assert result["projected_attainment_pct"] is not None
    assert "yoy_change_pct" in result  # history bundled -> YoY context
    json.dumps(result)


def test_bookings_rollup_bad_grain() -> None:
    assert "error" in srv.bookings_rollup("week", "EMEA")


def test_region_aware_param_changes_scoring() -> None:
    # Default (agnostic) vs region-aware overlay produce different scorecards.
    assert srv.get_scorecard()["overall"] != srv.get_scorecard(region_aware=True)["overall"]
    # APAC tolerates early discounts -> region-aware flags <= agnostic there.
    a0 = srv.assess_region("APAC")
    a1 = srv.assess_region("APAC", region_aware=True)
    assert a1["flagged"] <= a0["flagged"]
    json.dumps(srv.list_deals(region="EMEA", flagged_only=True, region_aware=True))


def test_region_aware_defaults_match_baseline() -> None:
    # Omitting the flag must equal region_aware=False (baseline preserved).
    assert srv.get_scorecard() == srv.get_scorecard(region_aware=False)


def test_bookings_rollup_na_region_has_quota_and_yoy() -> None:
    # Regression: "NA" in history/targets must survive pandas' NaN parsing.
    result = srv.bookings_rollup("quarter", "NA")
    assert result["quota"] > 0
    assert result["projected_attainment_pct"] is not None
    assert result.get("yoy_period_actual", {}).get("bookings", 0) > 0


def test_pipeline_by_period_marks_current() -> None:
    result = srv.pipeline_by_period("quarter", "APAC")
    buckets = result["periods"]
    assert buckets and any(b["is_current"] for b in buckets)
    for b in buckets:
        assert {"won_arr", "open_arr", "risk_adjusted_open_arr", "open_deals"} <= set(b)
    json.dumps(result)


def test_bookings_history_and_comparison() -> None:
    hist = srv.bookings_history("quarter", "EMEA", last_n=4)
    assert len(hist["periods"]) == 4
    for row in hist["periods"]:
        assert {"period", "bookings", "quota", "attainment_pct", "deals_won"} <= set(row)

    comp = srv.period_comparison("year", "EMEA")
    assert comp["grain"] == "year"
    assert "yoy_change_pct" in comp
    json.dumps(comp)


def test_region_tools_degrade_without_region_column(tmp_path, monkeypatch) -> None:
    # Build a region-less CSV and point the server at it; region tools must
    # return an informative error rather than crash.
    df = load("data/pipeline.csv").drop(columns=["region"])
    csv = tmp_path / "no_region.csv"
    df.to_csv(csv, index=False)
    monkeypatch.setenv("FORECAST_CSV", str(csv))
    srv.reload()
    try:
        assert "error" in srv.assess_region("NA")
        assert "error" in srv.list_regions()
        # Non-region tools still work.
        assert isinstance(srv.list_segments(), list)
    finally:
        monkeypatch.delenv("FORECAST_CSV", raising=False)
        srv.reload()  # restore default state for other tests
