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
    assert len(p["kpis"]) == 4
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
        "fc",
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


def test_deals_are_flagged_and_sorted() -> None:
    deals = forecast.flagged_deals()
    assert deals
    risks = [d["risk"] for d in deals]
    assert risks == sorted(risks, reverse=True)  # richest/riskiest first


def test_scorecard_matches_detector() -> None:
    sc = forecast.scorecard()
    labels = {m["label"]: m["value"] for m in sc["metrics"]}
    assert labels["F1"] == "0.835"  # region-agnostic, matches the model-health tab


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
