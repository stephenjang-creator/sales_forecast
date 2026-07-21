"""Tests for the sales-guru agent layer.

Covers the deterministic fallbacks / dry-run mappers (pure), the deal-coaching,
region-priorities, and interactive-chat loops driven by a fake Anthropic client
so the tool-dispatch + submit path is exercised with no key and no network. The
MCP server runs as a real offline subprocess.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from agents.mcp_client import (
    anthropic_tool_schema,
    call_tool,
    gather_deal_context,
    gather_region_actions,
    open_session,
)
from agents.sales_guru import (
    _agent_reply,
    _deterministic_actions,
    _deterministic_coaching,
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


def test_deterministic_actions_from_top_actions() -> None:
    plan = {
        "region": "NA",
        "actions": [
            {
                "priority": 1,
                "kind": "opportunity",
                "title": "Pull it forward and close",
                "first_step": "confirm paper process",
                "owner": "rep",
                "deal_count": 2,
                "mrr_at_stake": 12500,
                "deals": [
                    {
                        "deal_id": "D-9",
                        "label": "Acme ($8,000/mo)",
                        "mrr": 8000,
                        "stage": "Negotiation",
                    },
                    {
                        "deal_id": "D-4",
                        "label": "Globex ($4,500/mo)",
                        "mrr": 4500,
                        "stage": "Proposal",
                    },
                ],
            },
        ],
        "vp_should_join_calls": [
            {
                "deal_id": "D-9",
                "label": "Acme ($8,000/mo)",
                "stakeholder": "VP champion engaged",
                "move": "Pull forward",
            }
        ],
    }
    out = _deterministic_actions(plan)
    assert out["region"] == "NA"
    assert "Pull it forward and close" in out["headline"]  # leads with #1
    a = out["actions"][0]
    assert a["action"] == "Pull it forward and close"
    # Deals are named by company + MRR (+ stage), not deal_id.
    assert a["top_deals"] == ["Acme ($8,000/mo) — Negotiation", "Globex ($4,500/mo) — Proposal"]
    assert a["more"] is None  # only 2 deals, nothing to summarize
    # VP-personal calls carry through, named by company + MRR.
    assert out["calls_to_join"] == [
        {"deal": "Acme ($8,000/mo)", "why": "VP champion engaged — Pull forward"}
    ]


def test_deterministic_actions_summarizes_the_tail() -> None:
    # More than DEALS_SHOWN deals -> a few named, the rest aggregated by MRR.
    deals = [
        {
            "deal_id": f"D-{i}",
            "label": f"Co{i} (${1000 + i}/mo)",
            "mrr": 1000 + i,
            "stage": "Proposal",
        }
        for i in range(8)
    ]
    plan = {
        "region": "NA",
        "actions": [
            {
                "priority": 1,
                "kind": "risk",
                "title": "Reset the plan",
                "first_step": "rebuild MAP",
                "owner": "rep + manager",
                "deal_count": 8,
                "mrr_at_stake": 8028,
                "deals": deals,
            }
        ],
    }
    a = _deterministic_actions(plan)["actions"][0]
    assert len(a["top_deals"]) == 5  # DEALS_SHOWN
    assert a["more"].startswith("plus 3 more")  # 8 - 5
    assert "/mo)" in a["more"]  # remainder carries a dollar value, not a bare count


def test_deterministic_actions_empty_region() -> None:
    out = _deterministic_actions({"region": "X", "actions": []})
    assert out["headline"].startswith("No open priorities")
    assert out["actions"] == []
    assert out["calls_to_join"] == []


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
class _ActionsClient:
    """Reads region_top_actions, then submits the prioritized worklist."""

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
                        name="region_top_actions",
                        input={"region": "NA", "top_n": 3},
                        id="t1",
                    )
                ]
            )
        return SimpleNamespace(
            content=[
                _block(
                    type="tool_use",
                    name="submit_region_actions",
                    input={
                        "region": "NA",
                        "headline": "Close the fast movers first",
                        "actions": [
                            {
                                "priority": 1,
                                "action": "Pull forward and close",
                                "why": "empowered champions, simple process",
                                "owner": "rep",
                                "top_deals": ["Acme ($8,000/mo)", "Globex ($4,500/mo)"],
                                "more": "plus 5 more ($20,000/mo)",
                            }
                        ],
                        "calls_to_join": [{"deal": "Acme ($8,000/mo)", "why": "VP champion"}],
                        "rationale": "grounded",
                    },
                    id="t2",
                )
            ]
        )


def test_run_region_guru_dispatches_and_submits() -> None:
    async def _run() -> dict:
        async with open_session() as session:
            return await _run_region_guru(_ActionsClient(), session, "NA", "fake")

    result = asyncio.run(_run())
    assert result["region"] == "NA"
    assert result["headline"] == "Close the fast movers first"
    # Deals are named by company + MRR, not deal_id.
    assert result["actions"][0]["top_deals"][0] == "Acme ($8,000/mo)"
    assert result["calls_to_join"][0]["deal"] == "Acme ($8,000/mo)"
    assert not result.get("_fallback")


def test_run_region_guru_falls_back_without_submit() -> None:
    class _NeverSubmits:
        def __init__(self) -> None:
            self.messages = SimpleNamespace(create=self._create)

        async def _create(self, **_kw):
            return SimpleNamespace(content=[_block(type="text", text="thinking")])

    async def _run() -> dict:
        async with open_session() as session:
            return await _run_region_guru(_NeverSubmits(), session, "NA", "fake")

    result = asyncio.run(_run())
    assert result["region"] == "NA"
    assert result["_fallback"] is True
    assert result["actions"], "fallback must carry the deterministic top actions"


# --------------------------------------------------------------------------- #
# Interactive chat turn with a fake client
# --------------------------------------------------------------------------- #
class _ChatClient:
    """Turn 1: call region_top_actions. Turn 2: answer in plain text."""

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
                        name="region_top_actions",
                        input={"region": "NA", "top_n": 3},
                        id="c1",
                    )
                ]
            )
        return SimpleNamespace(
            content=[_block(type="text", text="Your top move is to close the fast movers.")]
        )


def test_agent_reply_uses_tools_then_answers() -> None:
    async def _run() -> tuple[str, list]:
        async with open_session() as session:
            tools = await anthropic_tool_schema(session)
            messages = [{"role": "user", "content": "What are my top 3 things in NA?"}]
            reply = await _agent_reply(_ChatClient(), session, "fake", tools, messages)
            return reply, messages

    reply, messages = asyncio.run(_run())
    assert "fast movers" in reply
    # The conversation grew (assistant tool_use + tool_result + assistant text),
    # so follow-up prompts keep context.
    assert len(messages) >= 4


# --------------------------------------------------------------------------- #
# Gather helpers over stdio (offline; real server)
# --------------------------------------------------------------------------- #
def test_gather_helpers_over_stdio() -> None:
    deal_id = _flagged_deal_id()

    async def _run() -> tuple[dict, dict]:
        async with open_session() as session:
            ctx = await gather_deal_context(session, deal_id)
            plan = await gather_region_actions(session, "NA")
            return ctx, plan

    ctx, plan = asyncio.run(_run())
    assert ctx["assessment"]["deal_id"] == deal_id
    assert ctx["plays"]["plays"]
    assert plan["region"] == "NA" and "actions" in plan
