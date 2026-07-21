"""Tests for the sales-guru agent layer.

Covers the deterministic fallbacks / dry-run mappers (pure), and both agent
loops (deal coaching + region priorities) driven by a fake Anthropic client so
the tool-dispatch + submit path is exercised with no key and no network. The
MCP server runs as a real offline subprocess.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from agents.mcp_client import call_tool, gather_deal_context, gather_region_plan, open_session
from agents.sales_guru import (
    _deterministic_coaching,
    _deterministic_priorities,
    _run_deal_guru,
    _run_region_guru,
)


def _block(**kw) -> SimpleNamespace:
    return SimpleNamespace(**kw)


def _flagged_deal_id() -> str:
    async def _run() -> str:
        async with open_session() as session:
            deals = await call_tool(session, "list_deals", {"flagged_only": True, "limit": 1})
            return deals[0]["deal_id"]

    return asyncio.run(_run())


# --------------------------------------------------------------------------- #
# Deterministic fallback / dry-run mappers (pure over tool payloads)
# --------------------------------------------------------------------------- #
def test_deterministic_coaching_from_context() -> None:
    ctx = {
        "deal_id": "D-1",
        "assessment": {"hits": [{"rule_id": "stalled_in_stage", "reason": "stuck 90d"}]},
        "plays": {
            "plays": [
                {
                    "rule_id": "stalled_in_stage",
                    "title": "Re-engage",
                    "actions": ["call"],
                    "owner": "rep",
                }
            ]
        },
    }
    out = _deterministic_coaching(ctx)
    assert out["deal_id"] == "D-1"
    assert out["plays"][0]["title"] == "Re-engage"
    assert out["talk_track"] == "call"
    assert "stuck 90d" in out["summary"]


def test_deterministic_priorities_buckets() -> None:
    plan = {
        "region": "NA",
        "priorities": {
            "close_fast_movers": [
                {"deal_id": "D-9", "play": {"actions": ["pull forward"]}, "reason": "fast"}
            ],
            "jump_on_calls_to_remove_risk": [
                {"deal_id": "D-8", "play": {"actions": ["qualify"]}, "reason": "thin"}
            ],
            "get_back_on_track": [
                {"deal_id": "D-7", "play": {"actions": ["reset plan"]}, "reason": "slipped"}
            ],
        },
    }
    out = _deterministic_priorities(plan)
    assert out["region"] == "NA"
    assert "D-9" in out["headline"]  # leads with the fast mover
    assert out["close_fast_movers"][0] == {"deal_id": "D-9", "action": "pull forward"}
    assert out["remove_risk"][0]["deal_id"] == "D-8"
    assert out["get_back_on_track"][0]["action"] == "reset plan"


def test_deterministic_priorities_empty_region() -> None:
    out = _deterministic_priorities({"region": "X", "priorities": {}})
    assert out["headline"].startswith("No open priorities")
    assert out["close_fast_movers"] == []


# --------------------------------------------------------------------------- #
# Deal-coaching loop with a fake client (real server, no key)
# --------------------------------------------------------------------------- #
class _CoachingClient:
    """First calls assess_deal, then submits coaching."""

    def __init__(self, deal_id: str) -> None:
        self.messages = SimpleNamespace(create=self._create)
        self._deal_id = deal_id
        self._turn = 0

    async def _create(self, **_kw):
        self._turn += 1
        if self._turn == 1:
            return SimpleNamespace(
                content=[
                    _block(type="text", text="Reading the deal."),
                    _block(
                        type="tool_use",
                        name="assess_deal",
                        input={"deal_id": self._deal_id},
                        id="t1",
                    ),
                ]
            )
        return SimpleNamespace(
            content=[
                _block(
                    type="tool_use",
                    name="submit_coaching",
                    input={
                        "deal_id": self._deal_id,
                        "summary": "thin qualification",
                        "plays": [
                            {"title": "Close the gaps", "actions": ["qualify"], "owner": "rep"}
                        ],
                        "talk_track": "open with value",
                        "rationale": "grounded in tools",
                    },
                    id="t2",
                )
            ]
        )


def test_run_deal_guru_dispatches_and_submits() -> None:
    deal_id = _flagged_deal_id()

    async def _run() -> dict:
        async with open_session() as session:
            return await _run_deal_guru(_CoachingClient(deal_id), session, deal_id, "fake")

    result = asyncio.run(_run())
    assert result["deal_id"] == deal_id
    assert result["summary"] == "thin qualification"
    assert result["plays"][0]["title"] == "Close the gaps"
    assert not result.get("_fallback")


def test_run_deal_guru_falls_back_without_submit() -> None:
    deal_id = _flagged_deal_id()

    class _NeverSubmits:
        def __init__(self) -> None:
            self.messages = SimpleNamespace(create=self._create)

        async def _create(self, **_kw):
            return SimpleNamespace(content=[_block(type="text", text="hmm")])

    async def _run() -> dict:
        async with open_session() as session:
            return await _run_deal_guru(_NeverSubmits(), session, deal_id, "fake")

    result = asyncio.run(_run())
    assert result["deal_id"] == deal_id
    assert result["_fallback"] is True
    assert result["plays"], "fallback must carry the deterministic plays"


# --------------------------------------------------------------------------- #
# Region-priorities loop with a fake client
# --------------------------------------------------------------------------- #
class _PrioritiesClient:
    """Reads region_action_plan, then submits priorities."""

    def __init__(self) -> None:
        self.messages = SimpleNamespace(create=self._create)
        self._turn = 0

    async def _create(self, **_kw):
        self._turn += 1
        if self._turn == 1:
            return SimpleNamespace(
                content=[
                    _block(
                        type="tool_use",
                        name="region_action_plan",
                        input={"region": "NA"},
                        id="t1",
                    )
                ]
            )
        return SimpleNamespace(
            content=[
                _block(
                    type="tool_use",
                    name="submit_region_priorities",
                    input={
                        "region": "NA",
                        "headline": "Close the fast movers first",
                        "close_fast_movers": [{"deal_id": "D-1", "action": "pull forward"}],
                        "remove_risk": [],
                        "get_back_on_track": [],
                        "rationale": "grounded",
                    },
                    id="t2",
                )
            ]
        )


def test_run_region_guru_dispatches_and_submits() -> None:
    async def _run() -> dict:
        async with open_session() as session:
            return await _run_region_guru(_PrioritiesClient(), session, "NA", "fake")

    result = asyncio.run(_run())
    assert result["region"] == "NA"
    assert result["headline"] == "Close the fast movers first"
    assert result["close_fast_movers"][0]["deal_id"] == "D-1"
    assert not result.get("_fallback")


# --------------------------------------------------------------------------- #
# Gather helpers over stdio (offline; real server)
# --------------------------------------------------------------------------- #
def test_gather_helpers_over_stdio() -> None:
    deal_id = _flagged_deal_id()

    async def _run() -> tuple[dict, dict]:
        async with open_session() as session:
            ctx = await gather_deal_context(session, deal_id)
            plan = await gather_region_plan(session, "NA")
            return ctx, plan

    ctx, plan = asyncio.run(_run())
    assert ctx["assessment"]["deal_id"] == deal_id
    assert ctx["plays"]["plays"]
    assert plan["region"] == "NA" and "priorities" in plan
