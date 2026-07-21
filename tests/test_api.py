"""Tests for the Intelligent Forecast HTTP API (FastAPI, offline).

Exercises the forecast payload shape, the agent routing + deterministic answers,
and the endpoints via a TestClient. No LLM, no network (ANTHROPIC_API_KEY unset
in CI, so /api/ask returns deterministic answers).
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from api import agents_web, forecast
from api.server import app

client = TestClient(app)


def test_full_payload_shape() -> None:
    p = forecast.full_payload()
    assert p["regionOrder"] == ["NA", "EMEA", "APAC", "LATAM"]
    assert p["deals"], "expected flagged deals"
    # Server sends the open-pipeline KPIs; the timeframe-scoped Booked tile is
    # composed client-side from bookedDeals + the header timeframe control.
    assert len(p["kpis"]) == 3  # at-risk + critical + top-region
    assert p["narrative"]
    assert len(p["scorecard"]["metrics"]) == 4
    assert len(p["scorecard"]["perRule"]) == 6
    d = p["deals"][0]
    expected = {
        "id",
        "account",
        "region",
        "segment",
        "industry",
        "stage",
        "stageRank",
        "fc",
        "fcRank",
        "risk",
        "tier",
        "amount",
        "arr",
        "mrr",
        "amountStr",
        "mrrStr",
        "owner",
        "manager",
        "closeDate",
        "nextMeeting",
        "rules",
    }
    assert expected <= set(d.keys())
    assert 0 <= d["risk"] <= 9
    assert d["tier"] in ("Critical", "High", "Medium", "Low")
    assert d["rules"] and {"id", "label", "reason", "action"} <= set(d["rules"][0].keys())


def test_sort_ranks_are_present_and_ordered() -> None:
    import config

    deals = forecast.flagged_deals()
    # Every flagged deal carries a numeric stage + forecast rank the UI sorts on.
    for d in deals:
        assert d["stageRank"] == config.STAGE_ORDER.get(d["stage"], 99)
        assert d["fcRank"] == config.FORECAST_ORDER.get(d["fc"], 99)
    # The canonical order the VP asked for: Qualification -> Discovery -> Proposal
    # -> Negotiation, and Closed -> Commit -> Best Case -> Pipeline -> Omitted.
    assert config.STAGE_ORDER["Qualification"] < config.STAGE_ORDER["Discovery"]
    assert config.STAGE_ORDER["Discovery"] < config.STAGE_ORDER["Negotiation"]
    assert config.FORECAST_ORDER["Closed"] < config.FORECAST_ORDER["Commit"]
    assert config.FORECAST_ORDER["Commit"] < config.FORECAST_ORDER["Omitted"]


def test_closed_forecast_categories() -> None:
    import pandas as pd

    from api.forecast import _csv_path

    df = pd.read_csv(_csv_path())
    # Closed Won is booked -> "Closed"; Closed Lost is dropped from the rollup
    # -> "Omitted".
    won = df[df["stage"] == "Closed Won"]
    lost = df[df["stage"] == "Closed Lost"]
    assert not won.empty and not lost.empty
    assert (won["forecast_category"] == "Closed").all()
    assert (lost["forecast_category"] == "Omitted").all()
    # Reps only call a deal Best Case at Proposal+ and Commit at Negotiation:
    # no healthy early-stage deal should be Best Case.
    early = df[df["stage"].isin(["Discovery", "Qualification"])]
    assert (early["forecast_category"] != "Best Case").all()


def test_booked_deals_have_no_risk() -> None:
    booked = forecast.booked_deals()
    assert booked, "expected Closed Won deals"
    for d in booked:
        assert d["stage"] == "Closed Won"
        assert d["fc"] == "Closed"
        assert d["closed"] is True
        assert d["risk"] == 0 and d["rules"] == []


def test_booked_deals_close_in_the_past() -> None:
    # A booked deal's close date is its booking date -- it must be in the past,
    # and spread over history so bookings roll up YoY/QoQ/MoM.
    from datetime import date

    booked = forecast.booked_deals()
    today = date.today().isoformat()
    isos = [d["closeISO"] for d in booked]
    assert all(iso and iso <= today for iso in isos)
    assert len({iso[:4] for iso in isos}) >= 2, "expected multiple booking years for YoY"


def test_open_deals_have_projected_close() -> None:
    from datetime import date

    today = date.today().isoformat()
    opens = forecast.flagged_deals()  # flagged deals are all open
    assert opens and all(d["closeISO"] and d["closeISO"] >= today for d in opens)


def test_pipeline_by_month_in_payload() -> None:
    p = forecast.full_payload()
    pbm = p["pipelineByMonth"]
    assert pbm, "expected per-month pipeline buckets"
    b = pbm[0]
    expected = {
        "period",
        "won_arr",
        "open_arr",
        "risk_adjusted_open_arr",
        "flagged_open_arr",
        "open_deals",
    }
    assert expected <= set(b.keys())
    # Buckets are chronological and keyed by calendar month.
    assert b["period"][:4].isdigit() and b["period"][4] == "-"


def test_bookings_summary_shape() -> None:
    bk = forecast.bookings_summary()
    for grain in ("month", "quarter", "year"):
        assert bk["series"][grain], f"expected a {grain} series"
    for key in ("ytd", "yoy", "qoq", "mom"):
        assert {"booked", "priorBooked", "pct"} <= set(bk[key].keys())
    # Booked totals reconcile: the year series sums to the all-time booked figure.
    year_total = sum(p["booked"] for p in bk["series"]["year"])
    booked_arr, _ = forecast._booked_totals()
    assert abs(year_total - round(booked_arr)) <= len(bk["series"]["year"])  # rounding


def test_deals_are_flagged_and_sorted() -> None:
    deals = forecast.flagged_deals()
    assert deals
    risks = [d["risk"] for d in deals]
    assert risks == sorted(risks, reverse=True)  # richest/riskiest first


def test_scorecard_matches_detector() -> None:
    sc = forecast.scorecard()
    labels = {m["label"]: m["value"] for m in sc["metrics"]}
    assert labels["F1"] == "0.847"  # region-agnostic, matches the model-health tab


def test_agent_routing() -> None:
    assert agents_web.route_agent("how do I rescue this deal?") == "Deal Rescue Planner"
    assert agents_web.route_agent("why is exposure concentrated?") == "Forecast Explainer"
    assert agents_web.route_agent("how much is at risk?") == "Pipeline Analyst"
    assert agents_web.route_agent("what should I worry about") == "Risk Triage Agent"


def test_ask_deterministic_without_key(monkeypatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    out = agents_web.ask("which deals should I chase first?", forecast.flagged_deals())
    assert out["source"] == "deterministic"
    assert out["agent"] == "Risk Triage Agent"
    assert "Chase these first" in out["text"]


def test_endpoints() -> None:
    assert client.get("/api/health").json() == {"status": "ok"}
    fc = client.get("/api/forecast").json()
    assert fc["deals"] and fc["kpis"]
    ask = client.post("/api/ask", json={"query": "how much Commit is at risk?"}).json()
    assert ask["agent"] == "Pipeline Analyst" and ask["text"]
