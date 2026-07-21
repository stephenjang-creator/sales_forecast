"""Sales guru: an expert-AE agent that recommends plays to de-risk deals.

Two modes, both grounded in the deterministic detector over the MCP stdio
server:

- Deal mode (``--deal D-10023``): coaches ONE deal. It reads the deal's risk
  picture (``assess_deal``) and the deterministic plays mapped from its flags
  (``recommend_plays``), then personalizes those plays to the deal's specifics
  -- a talk track for the next call, sharpened next steps, the right owner.

- Region mode (``--region NA`` / ``--all``): prioritizes what a regional VP
  should do. It reads ``region_action_plan`` -- fast movers to close, deals to
  jump on a call and de-risk, and stalled/slipped deals to get back on track --
  and turns it into a ranked, specific worklist.

What it is NOT: it never changes a flag or invents a deal or number the tools
did not return. The rules own risk; the guru only recommends the motion.
Deterministic core, LLM coaches, human-in-the-loop -- so ``--dry-run`` returns
the deterministic plays with no key or network at all.

Usage:
    python -m agents.sales_guru --deal D-10023          # coach one deal
    python -m agents.sales_guru --region NA             # one region's priorities
    python -m agents.sales_guru --all                   # every region
    python -m agents.sales_guru --all --dry-run         # deterministic, no key
    python -m agents.sales_guru --region EMEA --json    # machine-readable

Needs ANTHROPIC_API_KEY for the agent path; --dry-run runs fully offline.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

from agents.mcp_client import (
    anthropic_tool_schema,
    call_tool,
    gather_deal_context,
    gather_region_plan,
    open_session,
)

DEFAULT_MODEL = os.environ.get("FORECAST_AGENT_MODEL", "claude-sonnet-4-6")
MAX_ITERS = 6
MAX_TOKENS = 1500

# --------------------------------------------------------------------------- #
# Structured "submit" tools -- force a clean, grounded final answer.
# --------------------------------------------------------------------------- #
_PLAY_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "actions": {"type": "array", "items": {"type": "string"}},
        "owner": {"type": "string"},
    },
    "required": ["title", "actions"],
}

_SUBMIT_COACHING = {
    "name": "submit_coaching",
    "description": (
        "Submit your final coaching for ONE deal. Call exactly once, after "
        "reading assess_deal and recommend_plays. Personalize the deterministic "
        "plays to THIS deal -- never invent a flag, deal, or number the tools "
        "did not return."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "deal_id": {"type": "string"},
            "summary": {"type": "string", "description": "One-line read of the risk."},
            "plays": {"type": "array", "items": _PLAY_SCHEMA},
            "talk_track": {
                "type": "string",
                "description": "What the rep should say / open with on the next call.",
            },
            "rationale": {"type": "string"},
        },
        "required": ["deal_id", "summary", "plays"],
    },
}

_PRIORITY_ITEM = {
    "type": "object",
    "properties": {
        "deal_id": {"type": "string"},
        "action": {"type": "string", "description": "The specific move for this deal."},
    },
    "required": ["deal_id", "action"],
}

_SUBMIT_PRIORITIES = {
    "name": "submit_region_priorities",
    "description": (
        "Submit the prioritized worklist for ONE region's VP. Call exactly once, "
        "after reading region_action_plan. Use only the deals the plan returned; "
        "put each in the bucket that matches its move."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "region": {"type": "string"},
            "headline": {"type": "string", "description": "The VP's single top priority."},
            "close_fast_movers": {"type": "array", "items": _PRIORITY_ITEM},
            "remove_risk": {"type": "array", "items": _PRIORITY_ITEM},
            "get_back_on_track": {"type": "array", "items": _PRIORITY_ITEM},
            "rationale": {"type": "string"},
        },
        "required": ["region", "headline"],
    },
}

_DEAL_SYSTEM = (
    "You are an expert enterprise sales coach (a 'sales guru'). For ONE deal, "
    "recommend the plays that remove its risk and move it forward. Ground every "
    "recommendation in the MCP tools: assess_deal gives the risk picture and "
    "MEDDPICC scores, recommend_plays gives the deterministic plays mapped from "
    "the deal's flags. Personalize those plays to THIS deal -- sharpen the next "
    "steps, name the owner, and write a talk track for the next call. You never "
    "change a flag and never invent a deal, contact, or number the tools did not "
    "return; you respond to the flags the detector set. When finished, call "
    "submit_coaching exactly once."
)

_REGION_SYSTEM = (
    "You are an expert sales leader advising a regional VP. Prioritize what they "
    "should do THIS WEEK. Ground everything in region_action_plan, which returns "
    "three ranked buckets: fast movers to close, flagged deals to jump on a call "
    "and de-risk, and stalled/slipped deals to get back on track. Turn it into a "
    "crisp, specific worklist: name the deals, say the move, lead with the single "
    "highest-leverage action. Use only the deals the plan returned; never invent "
    "a deal or number. When finished, call submit_region_priorities exactly once."
)


# --------------------------------------------------------------------------- #
# Deterministic fallbacks (also the --dry-run output): no LLM, tools only.
# --------------------------------------------------------------------------- #
def _deterministic_coaching(ctx: dict) -> dict:
    """Coaching straight from the plays tool -- the offline / fallback answer."""
    plays_payload = ctx.get("plays") or {}
    assessment = ctx.get("assessment") or {}
    plays = plays_payload.get("plays", []) if isinstance(plays_payload, dict) else []
    top = plays[0] if plays else None
    return {
        "deal_id": ctx["deal_id"],
        "summary": (
            assessment.get("hits", [{}])[0].get("reason", "No open risk flags.")
            if assessment.get("hits")
            else "No open risk flags on this deal."
        ),
        "plays": [
            {"title": p["title"], "actions": p["actions"], "owner": p["owner"]} for p in plays
        ],
        "talk_track": top["actions"][0] if top else "",
        "rationale": "Deterministic plays mapped from the deal's rule hits (no LLM).",
    }


def _deterministic_priorities(plan: dict) -> dict:
    """Region worklist straight from region_action_plan -- offline / fallback."""
    prio = plan.get("priorities", {}) if isinstance(plan, dict) else {}

    def _items(bucket: str) -> list[dict]:
        out = []
        for it in prio.get(bucket, []):
            play = it.get("play") or {}
            action = play.get("actions", [""])[0] if play.get("actions") else it.get("reason", "")
            out.append({"deal_id": it["deal_id"], "action": action})
        return out

    fast = _items("close_fast_movers")
    risk = _items("jump_on_calls_to_remove_risk")
    stuck = _items("get_back_on_track")
    headline = "No open priorities in this region."
    if fast:
        headline = f"Close {fast[0]['deal_id']} — it's a fast mover ready to pull forward."
    elif risk:
        headline = f"Jump on {risk[0]['deal_id']} to remove its risk."
    elif stuck:
        headline = f"Get {stuck[0]['deal_id']} back on track — it's stalled or slipped."
    return {
        "region": plan.get("region", ""),
        "headline": headline,
        "close_fast_movers": fast,
        "remove_risk": risk,
        "get_back_on_track": stuck,
        "rationale": "Deterministic regional worklist from region_action_plan (no LLM).",
    }


# --------------------------------------------------------------------------- #
# Agent loops (Anthropic tool-use over the MCP tools).
# --------------------------------------------------------------------------- #
async def _drive(
    client,
    session,
    model: str,
    system: str,
    user: str,
    submit_tool: dict,
    fallback: dict,
) -> dict:
    """Shared tool-use loop: dispatch tools until the model submits, else fall back."""
    tools = await anthropic_tool_schema(session)
    tools.append(submit_tool)
    messages: list[dict] = [{"role": "user", "content": user}]

    for _ in range(MAX_ITERS):
        resp = await client.messages.create(
            model=model,
            max_tokens=MAX_TOKENS,
            system=system,
            tools=tools,
            messages=messages,
        )
        messages.append({"role": "assistant", "content": resp.content})
        tool_uses = [b for b in resp.content if b.type == "tool_use"]
        if not tool_uses:
            break

        tool_results = []
        submitted: dict | None = None
        for block in tool_uses:
            if block.name == submit_tool["name"]:
                submitted = dict(block.input)
                content = "Recorded."
            else:
                payload = await call_tool(session, block.name, dict(block.input))
                content = json.dumps(payload)
            tool_results.append(
                {"type": "tool_result", "tool_use_id": block.id, "content": content}
            )
        if submitted is not None:
            return submitted
        messages.append({"role": "user", "content": tool_results})

    fallback = dict(fallback)
    fallback["_fallback"] = True
    return fallback


async def _run_deal_guru(
    client, session, deal_id: str, model: str, region_aware: bool = False
) -> dict:
    """Coach one deal to a submit_coaching call; return its dict."""
    ctx = await gather_deal_context(session, deal_id, region_aware)
    assessment = ctx["assessment"]
    if isinstance(assessment, dict) and "error" in assessment:
        return {"deal_id": deal_id, "error": assessment["error"]}
    user = (
        f"Deal: {deal_id}\n\n"
        f"Risk picture (assess_deal):\n{json.dumps(ctx['assessment'], indent=2)}\n\n"
        f"Deterministic plays (recommend_plays):\n{json.dumps(ctx['plays'], indent=2)}\n\n"
        "Personalize these plays to this deal, add a talk track for the next "
        "call, then call submit_coaching."
    )
    return await _drive(
        client,
        session,
        model,
        _DEAL_SYSTEM,
        user,
        _SUBMIT_COACHING,
        _deterministic_coaching(ctx),
    )


async def _run_region_guru(
    client, session, region: str, model: str, region_aware: bool = False
) -> dict:
    """Prioritize one region to a submit_region_priorities call; return its dict."""
    plan = await gather_region_plan(session, region, region_aware)
    if isinstance(plan, dict) and "error" in plan:
        return {"region": region, "error": plan["error"]}
    user = (
        f"Region: {region}\n\n"
        f"Prioritized plan (region_action_plan):\n{json.dumps(plan, indent=2)}\n\n"
        "Turn this into the VP's worklist: name the deals, say the move, lead "
        "with the highest-leverage action, then call submit_region_priorities."
    )
    return await _drive(
        client,
        session,
        model,
        _REGION_SYSTEM,
        user,
        _SUBMIT_PRIORITIES,
        _deterministic_priorities(plan),
    )


# --------------------------------------------------------------------------- #
# Entry points (real agent path + offline dry run).
# --------------------------------------------------------------------------- #
async def coach_deal(deal_id: str, model: str, csv_path: str | None, region_aware: bool) -> dict:
    from anthropic import AsyncAnthropic  # lazy: only needed for the agent path

    client = AsyncAnthropic()
    async with open_session(csv_path) as session:
        return await _run_deal_guru(client, session, deal_id, model, region_aware)


async def coach_region(region: str, model: str, csv_path: str | None, region_aware: bool) -> dict:
    from anthropic import AsyncAnthropic  # lazy

    client = AsyncAnthropic()
    async with open_session(csv_path) as session:
        return await _run_region_guru(client, session, region, model, region_aware)


async def coach_all(
    regions: list[str], model: str, csv_path: str | None, region_aware: bool
) -> dict:
    from anthropic import AsyncAnthropic  # lazy

    client = AsyncAnthropic()

    async def _one(region: str) -> dict:
        async with open_session(csv_path) as session:
            return await _run_region_guru(client, session, region, model, region_aware)

    plans = await asyncio.gather(*(_one(r) for r in regions))
    return {"regions": list(plans)}


async def _discover_regions(csv_path: str | None) -> list[str]:
    async with open_session(csv_path) as session:
        regions = await call_tool(session, "list_regions")
    if isinstance(regions, dict):  # {"error": ...}
        raise RuntimeError(regions.get("error", "could not list regions"))
    return list(regions)


async def dry_run_deal(deal_id: str, csv_path: str | None, region_aware: bool) -> dict:
    async with open_session(csv_path) as session:
        ctx = await gather_deal_context(session, deal_id, region_aware)
    if isinstance(ctx["assessment"], dict) and "error" in ctx["assessment"]:
        return {"deal_id": deal_id, "error": ctx["assessment"]["error"]}
    out = _deterministic_coaching(ctx)
    out["mode"] = "dry-run (deterministic plays, no LLM)"
    return out


async def dry_run_regions(regions: list[str], csv_path: str | None, region_aware: bool) -> dict:
    out = []
    async with open_session(csv_path) as session:
        for region in regions:
            plan = await gather_region_plan(session, region, region_aware)
            if isinstance(plan, dict) and "error" in plan:
                out.append({"region": region, "error": plan["error"]})
            else:
                out.append(_deterministic_priorities(plan))
    return {"regions": out, "mode": "dry-run (deterministic worklist, no LLM)"}


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _print_coaching(c: dict) -> None:
    if c.get("error"):
        print(f"  {c.get('deal_id', '')}: {c['error']}")
        return
    print("=" * 72)
    print(f"  SALES GURU — {c['deal_id']}")
    print("=" * 72)
    print(f"  {c.get('summary', '')}")
    for i, play in enumerate(c.get("plays", []), 1):
        owner = f"  [{play['owner']}]" if play.get("owner") else ""
        print(f"\n  {i}. {play['title']}{owner}")
        for act in play.get("actions", []):
            print(f"     • {act}")
    if c.get("talk_track"):
        print(f"\n  Next call: {c['talk_track']}")
    if c.get("rationale"):
        print(f"  → {c['rationale']}")


def _print_priorities(p: dict) -> None:
    if p.get("error"):
        print(f"\n  {p.get('region', '')}: {p['error']}")
        return
    print(f"\n  {p['region']} — {p.get('headline', '')}")
    buckets = [
        ("Close (fast movers)", "close_fast_movers"),
        ("Remove risk (get on a call)", "remove_risk"),
        ("Back on track (stalled/slipped)", "get_back_on_track"),
    ]
    for label, key in buckets:
        items = p.get(key, [])
        if not items:
            continue
        print(f"    {label}:")
        for it in items:
            print(f"      • {it['deal_id']}: {it['action']}")


def _print_region_report(result: dict) -> None:
    print("=" * 72)
    print("  SALES GURU — REGIONAL PRIORITIES")
    mode = result.get("mode")
    if mode:
        print(f"  ({mode})")
    print("=" * 72)
    for p in result["regions"]:
        _print_priorities(p)
    print("\n" + "=" * 72)
    print("  A prioritized worklist (opportunity + risk), not an attainment")
    print("  forecast. The rules own every flag; the guru recommends the move.")


async def _amain(args: argparse.Namespace) -> int:
    csv_path = args.csv
    ra = args.region_aware

    if args.deal:
        if args.dry_run:
            result = await dry_run_deal(args.deal, csv_path, ra)
        else:
            result = await coach_deal(args.deal, args.model, csv_path, ra)
        print(json.dumps(result, indent=2)) if args.json else _print_coaching(result)
        return 0

    regions = [args.region] if args.region else await _discover_regions(csv_path)
    if args.dry_run:
        result = await dry_run_regions(regions, csv_path, ra)
    elif args.region:
        one = await coach_region(args.region, args.model, csv_path, ra)
        result = {"regions": [one]}
    else:
        result = await coach_all(regions, args.model, csv_path, ra)
    print(json.dumps(result, indent=2)) if args.json else _print_region_report(result)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--deal", help="coach a single deal (e.g. D-10023)")
    group.add_argument("--region", help="prioritize a single region (e.g. NA)")
    group.add_argument("--all", action="store_true", help="prioritize every region")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Anthropic model id")
    parser.add_argument("--csv", default=None, help="pipeline CSV (else FORECAST_CSV/default)")
    parser.add_argument("--dry-run", action="store_true", help="deterministic plays, no LLM/key")
    parser.add_argument(
        "--region-aware",
        action="store_true",
        help="score with the per-region threshold overlay (US/EMEA/APAC)",
    )
    parser.add_argument("--json", action="store_true", help="emit JSON")
    args = parser.parse_args(argv)

    if not (args.deal or args.region or args.all):
        parser.error("choose one of --deal, --region, or --all")
    if not args.dry_run and not os.environ.get("ANTHROPIC_API_KEY"):
        print(
            "error: ANTHROPIC_API_KEY not set. Use --dry-run for offline "
            "deterministic plays, or export a key to run the guru.",
            file=sys.stderr,
        )
        return 1
    return asyncio.run(_amain(args))


if __name__ == "__main__":
    raise SystemExit(main())
