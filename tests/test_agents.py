"""Tests for the attainment agent layer.

Covers the deterministic baseline math (pure), the MCP stdio round-trip and
context gathering (offline, real server subprocess), and the Anthropic agent
loop driven by a fake client so the tool-dispatch + submit path is exercised
without a key or network.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import config
from agents.attainment import _aggregate, _run_region_agent
from agents.baseline import baseline_from_deals
from agents.mcp_client import call_tool, gather_region_context, open_session


# --------------------------------------------------------------------------- #
# Baseline (pure, no I/O)
# --------------------------------------------------------------------------- #
def test_baseline_weights_and_haircut() -> None:
    deals = [
        {
            "arr": 100_000,
            "stage": "Negotiation",
            "forecast_category": "Commit",
            "predicted_anomaly": False,
        },
        {
            "arr": 100_000,
            "stage": "Negotiation",
            "forecast_category": "Commit",
            "predicted_anomaly": True,
        },
        {
            "arr": 50_000,
            "stage": "Discovery",
            "forecast_category": "Pipeline",
            "predicted_anomaly": False,
        },
        {
            "arr": 200_000,
            "stage": "Closed Won",
            "forecast_category": "Commit",
            "predicted_anomaly": False,
        },
    ]
    out = baseline_from_deals(deals)
    # Negotiation win-rate 0.75: clean = 75k; flagged = 75k * (1 - haircut).
    haircut = config.FLAGGED_RISK_HAIRCUT
    expected_likely = (
        100_000 * 0.75 + 100_000 * 0.75 * (1 - haircut) + 50_000 * 0.10 + 200_000 * 1.0
    )
    assert out["expected_bookings"]["likely"] == round(expected_likely, 0)
    assert out["expected_bookings"]["low"] < out["expected_bookings"]["likely"]
    assert out["expected_bookings"]["high"] > out["expected_bookings"]["likely"]
    assert out["closed_won_arr"] == 200_000
    assert out["risk_haircut_arr"] > 0  # the flagged deal was discounted


def test_baseline_empty() -> None:
    out = baseline_from_deals([])
    assert out["expected_bookings"]["likely"] == 0


def test_baseline_fast_mover_uplift_symmetry() -> None:
    base = {"arr": 100_000, "stage": "Negotiation", "forecast_category": "Commit"}
    plain = baseline_from_deals([{**base, "predicted_anomaly": False, "signals": []}])
    mover = baseline_from_deals([{**base, "predicted_anomaly": False, "signals": ["fast_mover"]}])
    flagged = baseline_from_deals([{**base, "predicted_anomaly": True, "signals": []}])

    # A fast mover lifts the estimate above plain; a flagged deal cuts it below.
    assert mover["expected_bookings"]["likely"] > plain["expected_bookings"]["likely"]
    assert flagged["expected_bookings"]["likely"] < plain["expected_bookings"]["likely"]
    assert mover["mover_uplift_arr"] > 0 and mover["risk_haircut_arr"] == 0
    assert flagged["risk_haircut_arr"] > 0 and flagged["mover_uplift_arr"] == 0
    # Uplift never books more than the deal's ARR.
    assert mover["expected_bookings"]["likely"] <= base["arr"]
    # Risk dominates: a flagged fast mover takes the haircut, gets no uplift.
    both = baseline_from_deals([{**base, "predicted_anomaly": True, "signals": ["fast_mover"]}])
    assert both["risk_haircut_arr"] > 0 and both["mover_uplift_arr"] == 0


def test_aggregate_sums_regions() -> None:
    preds = [
        {"region": "NA", "month": {"projected_bookings": 2}, "quarter": {"projected_bookings": 5}},
        {
            "region": "EMEA",
            "month": {"projected_bookings": 20},
            "quarter": {"projected_bookings": 50},
        },
    ]
    agg = _aggregate(preds)
    assert agg["month_projected_bookings"] == 22
    assert agg["quarter_projected_bookings"] == 55
    assert agg["regions"] == ["NA", "EMEA"]


# --------------------------------------------------------------------------- #
# MCP stdio round-trip (offline; spawns the real server)
# --------------------------------------------------------------------------- #
def test_gather_region_context_over_stdio() -> None:
    async def _run() -> dict:
        async with open_session() as session:
            regions = await call_tool(session, "list_regions")
            assert "EMEA" in regions
            return await gather_region_context(session, "EMEA")

    ctx = asyncio.run(_run())
    assert ctx["region"] == "EMEA"
    assert isinstance(ctx["rollup"], dict) and ctx["rollup"]["deals"] > 0
    assert isinstance(ctx["deals"], list) and ctx["deals"]
    assert all(d["predicted_anomaly"] for d in ctx["flagged_deals"])


# --------------------------------------------------------------------------- #
# Agent loop with a fake Anthropic client (no key, no network)
# --------------------------------------------------------------------------- #
def _block(**kw) -> SimpleNamespace:
    return SimpleNamespace(**kw)


class _FakeMessages:
    """Scripted responses: first a tool call, then a submit_prediction call."""

    def __init__(self) -> None:
        self._turn = 0

    async def create(self, **_kw):
        self._turn += 1
        if self._turn == 1:
            return SimpleNamespace(
                content=[
                    _block(type="text", text="Let me check the region."),
                    _block(
                        type="tool_use",
                        name="assess_region",
                        input={"region": "EMEA"},
                        id="t1",
                    ),
                ]
            )
        return SimpleNamespace(
            content=[
                _block(
                    type="tool_use",
                    name="submit_prediction",
                    input={
                        "region": "EMEA",
                        "expected_bookings": {"low": 1.0, "likely": 2.0, "high": 3.0},
                        "confidence": "medium",
                        "rationale": "grounded in tools",
                    },
                    id="t2",
                )
            ]
        )


class _FakeClient:
    def __init__(self) -> None:
        self.messages = _FakeMessages()


def test_run_region_agent_dispatches_tools_and_submits() -> None:
    async def _run() -> dict:
        async with open_session() as session:
            return await _run_region_agent(_FakeClient(), session, "EMEA", "fake-model")

    result = asyncio.run(_run())
    assert result["region"] == "EMEA"
    assert result["expected_bookings"] == {"low": 1.0, "likely": 2.0, "high": 3.0}
    assert result["confidence"] == "medium"
    assert "_baseline" in result  # baseline anchor attached
    assert not result.get("_fallback")


def test_run_region_agent_falls_back_without_submit() -> None:
    class _NeverSubmits:
        def __init__(self) -> None:
            self.messages = SimpleNamespace(create=self._create)

        async def _create(self, **_kw):
            # Always returns plain text, never a tool_use -> loop ends, fallback.
            return SimpleNamespace(content=[_block(type="text", text="thinking...")])

    async def _run() -> dict:
        async with open_session() as session:
            return await _run_region_agent(_NeverSubmits(), session, "APAC", "fake-model")

    result = asyncio.run(_run())
    assert result["region"] == "APAC"
    assert result["_fallback"] is True
    assert result["expected_bookings"]["likely"] >= 0
