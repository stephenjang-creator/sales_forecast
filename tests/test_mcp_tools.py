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
        "label",
        "region",
        "segment",
        "industry",
        "owner",
        "sales_manager",
        "mrr",
        "stage",
        "forecast_category",
        "arr",
        "close_date",
        "next_meeting_date",
        "risk_score",
        "predicted_anomaly",
        "signals",
        "top_reason",
    }
    assert set(deals[0].keys()) == expected
    # Rep-friendly label: company + MRR, e.g. "Acme Group ($3,990/mo)".
    assert deals[0]["account"] in deals[0]["label"] and "/mo)" in deals[0]["label"]
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
    for sig in ("fast_mover", "complex_deal", "meeting_at_risk"):
        assert {"count", "arr"} == set(summary[sig].keys())
    json.dumps(summary)


def test_meeting_at_risk_signal_and_value_touch_play() -> None:
    # The cadence signal is filterable and carries the next_meeting_date.
    at_risk = srv.list_deals(signal="meeting_at_risk", limit=5)
    assert at_risk, "expected some meeting-at-risk deals"
    assert all("meeting_at_risk" in d["signals"] for d in at_risk)
    # recommend_plays appends the value-touch play for a meeting-at-risk deal.
    df = srv._df()
    mask = df["meeting_at_risk"]
    deal_id = str(df[mask].iloc[0]["deal_id"])
    plays = srv.recommend_plays(deal_id)
    # A clean-but-at-risk deal still gets the value touch; a flagged one gets it
    # appended after its anomaly plays.
    if "error" not in plays:
        assert any(p["rule_id"] == "meeting_at_risk" for p in plays["plays"])


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


def test_recommend_plays_for_flagged_deal() -> None:
    deal_id = _a_flagged_deal_id()
    result = srv.recommend_plays(deal_id)
    assert result["deal_id"] == deal_id
    assert result["account"] in result["label"]  # rep-friendly company + MRR label
    assert result["hits"], "a flagged deal must carry hits"
    assert result["plays"], "a flagged deal must get at least one play"
    play = result["plays"][0]
    assert {"rule_id", "title", "why", "actions", "owner"} <= set(play.keys())
    assert play["actions"] and all(isinstance(a, str) for a in play["actions"])
    # Every play maps to one of the deal's hits, or is the signal-driven
    # meeting_at_risk value touch (a play that responds to a signal, not a rule).
    hit_ids = {h["rule_id"] for h in result["hits"]} | {"meeting_at_risk"}
    assert all(p["rule_id"] in hit_ids for p in result["plays"])
    json.dumps(result)


def test_recommend_plays_not_found() -> None:
    assert "error" in srv.recommend_plays("D-00000-nope")


def test_region_top_actions_grouped_and_ranked() -> None:
    plan = srv.region_top_actions("NAM", max_deals=10)
    assert plan["region"] == "NAM"
    assert plan["active_deals"] > 0
    actions = plan["actions"]
    assert actions, "expected at least one action"
    # Every surfaced deal is listed; the total is bounded by max_deals (no tail).
    total_deals = sum(a["deal_count"] for a in actions)
    assert total_deals == plan["surfaced_deals"] <= 10
    # Actions ranked by priority_score, descending, priority 1..N in order.
    scores = [a["priority_score"] for a in actions]
    assert scores == sorted(scores, reverse=True)
    assert [a["priority"] for a in actions] == list(range(1, len(actions) + 1))
    for a in actions:
        assert a["kind"] in ("risk", "opportunity")
        assert a["deal_count"] == len(a["deals"])  # one action, many deals, all listed
        assert a["deals"], "an action must cover at least one deal"
        assert abs(a["arr_at_stake"] - round(sum(d["arr"] for d in a["deals"]), 0)) < 1.0
        assert {"title", "first_step", "owner", "mrr_at_stake"} <= set(a.keys())
        for deal in a["deals"]:
            # Rep-friendly: every deal carries a company + MRR label + org.
            assert {"champion_seniority", "good_champion", "label", "mrr"} <= set(deal.keys())
            assert {"owner", "sales_manager"} <= set(deal.keys())
            assert deal["account"] in deal["label"]
    json.dumps(plan)


def test_owner_and_manager_surfaced_and_region_disjoint() -> None:
    # Every deal carries an opportunity owner + sales manager, and the manager
    # filter works.
    d = srv.list_deals(limit=1)[0]
    assert d["owner"] and d["sales_manager"]
    full = srv.assess_deal(d["deal_id"])
    assert full["owner"] == d["owner"] and full["sales_manager"] == d["sales_manager"]
    under_mgr = srv.list_deals(sales_manager=d["sales_manager"], limit=500)
    assert under_mgr and all(x["sales_manager"] == d["sales_manager"] for x in under_mgr)
    # Owners and managers never repeat across regions.
    df = srv._df()
    for col in ("rep", "sales_manager"):
        by_region = df.groupby("region")[col].apply(set)
        regions = list(by_region.index)
        for i in range(len(regions)):
            for j in range(i + 1, len(regions)):
                assert not (by_region[regions[i]] & by_region[regions[j]]), f"{col} repeats"


def test_region_top_actions_deal_budget_bounds_and_lists_all() -> None:
    # A small budget surfaces exactly that many deals, each fully listed.
    plan = srv.region_top_actions("NAM", max_deals=5)
    assert plan["surfaced_deals"] == 5
    assert sum(a["deal_count"] for a in plan["actions"]) == 5
    assert plan["actionable_deals"] >= plan["surfaced_deals"]
    # Raising the budget surfaces more (no hidden tail at the low budget).
    bigger = srv.region_top_actions("NAM", max_deals=15)
    assert bigger["surfaced_deals"] > 5


def test_region_top_actions_vp_call_shortlist_is_capped_and_senior() -> None:
    import config

    plan = srv.region_top_actions("NAM")
    calls = plan["vp_should_join_calls"]
    assert len(calls) <= config.VP_CALL_CAPACITY  # calls are scarce
    for c in calls:
        expected = {"deal_id", "stakeholder", "move", "arr", "label", "mrr", "next_meeting_date"}
        assert expected <= set(c.keys())
        assert c["stakeholder"], "a call-worthy deal names its senior stakeholder"
        # Open call-worthy deals should mostly have a meeting the VP can join;
        # the field is always present (may be None if none is booked).
        assert "next_meeting_date" in c


def test_region_top_actions_region_aware_and_unknown() -> None:
    aware = srv.region_top_actions("APAC", region_aware=True)
    assert aware["region_aware"] is True
    assert "error" in srv.region_top_actions("Nowhere")


def test_priority_weight_favors_bottom_of_funnel_and_champion() -> None:
    import pandas as pd

    late = pd.Series({"stage": "Negotiation", "champion_seniority": "VP", "m_champion": 3})
    early = pd.Series({"stage": "Discovery", "champion_seniority": "IC", "m_champion": 0})
    # Same ARR, same severity: bottom-of-funnel + good champion outweighs early.
    assert srv._deal_priority_weight(late, "risk", "high") > srv._deal_priority_weight(
        early, "risk", "high"
    )
    # A good champion boosts an otherwise identical deal.
    champ = pd.Series({"stage": "Proposal", "champion_seniority": "Director", "m_champion": 3})
    nochamp = pd.Series({"stage": "Proposal", "champion_seniority": "IC", "m_champion": 0})
    assert srv._deal_priority_weight(champ, "risk", "medium") > srv._deal_priority_weight(
        nochamp, "risk", "medium"
    )
    # A fast mover stays high even early-stage (opportunity base + stage floor).
    fast_early = pd.Series({"stage": "Discovery", "champion_seniority": "VP", "m_champion": 3})
    assert srv._deal_priority_weight(fast_early, "opportunity", "opportunity") >= 0.9 * 0.5


def test_good_champion_and_senior_stakeholder() -> None:
    import pandas as pd

    assert srv._good_champion(pd.Series({"champion_seniority": "Director", "m_champion": 0}))
    assert srv._good_champion(pd.Series({"champion_seniority": "IC", "m_champion": 3}))
    assert not srv._good_champion(pd.Series({"champion_seniority": "Manager", "m_champion": 1}))
    # Senior stakeholder (VP+ or C-suite approver) => call-worthy.
    assert srv._senior_stakeholder(pd.Series({"champion_seniority": "C-Suite"})) is not None
    assert srv._senior_stakeholder(pd.Series({"champion_seniority": "Director"})) is None
    assert (
        srv._senior_stakeholder(pd.Series({"champion_seniority": "Manager", "csuite_approval": 1}))
        is not None
    )


def test_next_meeting_date_surfaced() -> None:
    # Every deal item carries next_meeting_date; open deals usually have one
    # booked, closed deals never do.
    df = srv._df()
    assert "next_meeting_date" in df.columns
    deal = srv.list_deals(limit=1)[0]
    assert "next_meeting_date" in deal
    full = srv.assess_deal(deal["deal_id"])
    assert "next_meeting_date" in full
    # A call-worthy deal is open, so most of the shortlist can be joined.
    for region in ("NAM", "EMEA"):
        plan = srv.region_top_actions(region)
        for c in plan["vp_should_join_calls"]:
            assert "next_meeting_date" in c


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
    # "NAM" collides with pandas' NaN sentinel; the loader must preserve it.
    result = srv.assess_region("NAM")
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
    assert set(regions) == {"NAM", "EMEA", "APAC", "LATAM"}
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
    # Regression: "NAM" in history/targets must survive pandas' NaN parsing.
    result = srv.bookings_rollup("quarter", "NAM")
    assert result["quota"] > 0
    assert result["projected_attainment_pct"] is not None
    assert result.get("yoy_period_actual", {}).get("bookings", 0) > 0


def test_pipeline_by_period_marks_current() -> None:
    result = srv.pipeline_by_period("quarter", "APAC")
    buckets = result["periods"]
    assert buckets and any(b["is_current"] for b in buckets)
    for b in buckets:
        assert {
            "won_arr",
            "open_arr",
            "risk_adjusted_open_arr",
            "flagged_open_arr",
            "fast_mover_open_arr",
            "open_deals",
        } <= set(b)
    json.dumps(result)


def test_pipeline_by_period_fast_mover_uplift() -> None:
    # NAM has open fast movers; their uplift must lift risk_adjusted above the
    # naive (weighted - full haircut) floor, and fast_mover_open_arr is surfaced.
    cur = next(b for b in srv.pipeline_by_period("quarter", "NAM")["periods"] if b["is_current"])
    assert cur["fast_mover_open_arr"] > 0
    # Uplift pushes risk-adjusted above weighted-minus-haircut-on-everything.
    floor = cur["weighted_open_arr"] * (1 - 0.40)
    assert cur["risk_adjusted_open_arr"] > floor


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
        assert "error" in srv.assess_region("NAM")
        assert "error" in srv.list_regions()
        # Non-region tools still work.
        assert isinstance(srv.list_segments(), list)
    finally:
        monkeypatch.delenv("FORECAST_CSV", raising=False)
        srv.reload()  # restore default state for other tests
