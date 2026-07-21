"""Sales guru: an expert-AE agent that recommends plays to de-risk deals.

Two modes, both grounded in the deterministic detector over the MCP stdio
server:

- Deal mode (``--deal D-10023``): coaches ONE deal. It reads the deal's risk
  picture (``assess_deal``) and the deterministic plays mapped from its flags
  (``recommend_plays``), then personalizes those plays to the deal's specifics
  -- a talk track for the next call, sharpened next steps, the right owner.

- Region mode (``--region NA`` / ``--all``): prioritizes what a regional VP
  should do TODAY. It reads ``region_top_actions`` -- the region's active
  pipeline grouped by the play each deal needs, so ONE action can cover several
  deals (e.g. "run a MEDDPICC call on these 5 deals"), ranked by ARR-at-stake --
  and returns the top N (default 3) as a prioritized worklist.

- Chat mode (``--chat``): an interactive REPL with all the detector tools. Ask
  "what are my top 3 things in NA?", then keep prompting ("tell me about #2",
  "who owns the first one?", "show me those deals") -- the conversation persists.

What it is NOT: it never changes a flag or invents a deal or number the tools
did not return. The rules own risk; the guru only recommends the motion.
Deterministic core, LLM coaches, human-in-the-loop -- so ``--dry-run`` returns
the deterministic plays / worklist with no key or network at all.

Usage:
    python -m agents.sales_guru --deal D-10023          # coach one deal
    python -m agents.sales_guru --region NA             # a region's top 3 actions
    python -m agents.sales_guru --all                   # every region
    python -m agents.sales_guru --all --dry-run         # deterministic, no key
    python -m agents.sales_guru --chat                  # interactive; ask + follow up
    python -m agents.sales_guru --chat --region NA      # chat, seeded on a region

Needs ANTHROPIC_API_KEY for the agent + chat paths; --dry-run runs fully offline.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

import config
from agents.mcp_client import (
    anthropic_tool_schema,
    call_tool,
    gather_deal_context,
    gather_region_actions,
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

_ACTION_ITEM = {
    "type": "object",
    "properties": {
        "priority": {"type": "integer"},
        "action": {"type": "string", "description": "The move, as an imperative."},
        "why": {"type": "string", "description": "The risk removed / opportunity taken."},
        "owner": {"type": "string"},
        "deal_count": {"type": "integer", "description": "How many deals this action covers."},
        "mrr_at_stake": {"type": "number", "description": "Combined MRR of the covered deals."},
        "deals": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "Every account this action covers (the tool already bounded the "
                "set), each as company + MRR (+ stage), e.g. 'Acme Group "
                "($8,200/mo) — Negotiation'. Never a deal_id."
            ),
        },
    },
    "required": ["priority", "action", "deals"],
}

_CALL_ITEM = {
    "type": "object",
    "properties": {
        "deal": {"type": "string", "description": "Company + MRR, e.g. 'Acme Group ($8,200/mo)'."},
        "why": {"type": "string", "description": "Why the VP should personally join this call."},
    },
    "required": ["deal", "why"],
}

_SUBMIT_ACTIONS = {
    "name": "submit_region_actions",
    "description": (
        "Submit the regional VP's prioritized worklist. Call exactly once, after "
        "reading region_top_actions. `actions` are plays the VP DELEGATES to "
        "managers via a note (one move may cover several deals): for each, list "
        "every account the tool surfaced for it, by company + MRR (the tool's "
        "deals[].label), most-actionable first -- the tool already capped the set, "
        "so do not drop or summarize any. `calls_to_join` is the short list of "
        "deals the VP should personally join a call on -- use only "
        "region_top_actions' vp_should_join_calls, named by company + MRR. Keep "
        "actions in priority order; use only the deals the tool returned; never "
        "show a deal_id."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "region": {"type": "string"},
            "headline": {"type": "string", "description": "The single top priority today."},
            "actions": {"type": "array", "items": _ACTION_ITEM},
            "calls_to_join": {"type": "array", "items": _CALL_ITEM},
            "rationale": {"type": "string"},
        },
        "required": ["region", "actions"],
    },
}

_DEAL_SYSTEM = (
    "You are an expert enterprise sales coach (a 'sales guru'). For ONE deal, "
    "recommend the plays that remove its risk and move it forward. Ground every "
    "recommendation in the MCP tools: assess_deal gives the risk picture and "
    "MEDDPICC scores, recommend_plays gives the deterministic plays mapped from "
    "the deal's flags. Personalize those plays to THIS deal -- sharpen the next "
    "steps, name the owner, and write a talk track for the next call. Refer to the "
    "deal by its COMPANY and MRR (assess_deal's label / account + mrr), not the "
    "deal_id. You never change a flag and never invent a deal, contact, or number "
    "the tools did not return; you respond to the flags the detector set. When "
    "finished, call submit_coaching exactly once."
)

_REGION_SYSTEM = (
    "You are an expert sales leader advising a regional VP. Give them the top few "
    "things to do TODAY, in priority order. Ground everything in "
    "region_top_actions, which scans the region's active pipeline; its ranking "
    "already favors bottom-of-funnel, well-championed deals (a few steps from "
    "close) and fast movers. Respect the VP's two levers: the `actions` are plays "
    "they DELEGATE to their managers via a note -- one play may cover several "
    "deals (e.g. run a MEDDPICC call on 5 deals) -- so state each as an imperative "
    "and name the deals it covers. The `vp_should_join_calls` list is the handful "
    "of deals the VP should personally join a call on (calls are scarce, so it's "
    "short and skews to senior-stakeholder deals); pass those through as "
    "calls_to_join. Lead with the highest-leverage action. Always name deals by "
    "COMPANY and MRR (the tool's deals[].label, e.g. 'Acme Group ($8,200/mo)') -- "
    "never a deal_id -- and for each action list every account the tool surfaced "
    "(it already capped the set to the top-priority deals; don't drop any). Use "
    "only the deals the tool returned; never invent a deal or number. When "
    "finished, call submit_region_actions once."
)

_CHAT_SYSTEM = (
    "You are an expert enterprise sales coach (a 'sales guru') for a RevOps team, "
    "in an interactive chat. Answer the user's questions about their pipeline "
    "using the MCP tools, which wrap a deterministic detector. Key tools: "
    "region_top_actions (a region's top prioritized things to do -- use this for "
    "'what are my top 3 things?'), recommend_plays and assess_deal (one deal), "
    "list_deals / assess_region / signals_summary (browse and roll up). Ground "
    "every answer in the tools; the deterministic rules own every flag -- you "
    "explain and recommend the play, you never change a flag or invent a deal, "
    "contact, or number the tools did not return. Be concise and specific. Always "
    "refer to a deal by its COMPANY and MRR (the tools' label / account + mrr, "
    "e.g. 'Acme Group ($8,200/mo)'), never a deal_id -- that's how reps think. "
    "When you list priorities keep them in the tool's ranked order, and show a few "
    "named accounts rather than a long dump. It's fine to call several tools before "
    "answering, and to ask a clarifying question (e.g. which region) when needed."
)


# --------------------------------------------------------------------------- #
# Deterministic fallbacks (also the --dry-run output): no LLM, tools only.
# --------------------------------------------------------------------------- #
def _deal_headline(assessment: dict, deal_id: str) -> dict:
    """Rep-friendly identity for a deal: company + MRR (falls back to deal_id)."""
    account = assessment.get("account")
    mrr = assessment.get("mrr")
    label = assessment.get("label")
    if not label:
        label = (
            f"{account} (${mrr:,.0f}/mo)" if account and mrr is not None else (account or deal_id)
        )
    return {"deal_id": deal_id, "account": account, "mrr": mrr, "label": label}


def _deterministic_coaching(ctx: dict) -> dict:
    """Coaching straight from the plays tool -- the offline / fallback answer."""
    plays_payload = ctx.get("plays") or {}
    assessment = ctx.get("assessment") or {}
    plays = plays_payload.get("plays", []) if isinstance(plays_payload, dict) else []
    top = plays[0] if plays else None
    return {
        **_deal_headline(assessment, ctx["deal_id"]),
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


def _deal_line(deal: dict) -> str:
    """'Acme Group ($8,200/mo) — Negotiation' from a tool deal dict."""
    label = deal.get("label") or deal.get("account") or deal.get("deal_id", "")
    stage = deal.get("stage")
    return f"{label} — {stage}" if stage else str(label)


def _deterministic_actions(plan: dict) -> dict:
    """Region worklist straight from region_top_actions -- offline / fallback.

    Lists every surfaced deal by company + MRR (the tool already bounded the set
    to the top-priority deals region-wide), most-actionable first. No hidden tail.
    """
    tool_actions = plan.get("actions", []) if isinstance(plan, dict) else []
    actions = []
    for a in tool_actions:
        deals = a.get("deals", [])
        actions.append(
            {
                "priority": a["priority"],
                "action": a["title"],
                "why": a["first_step"],
                "owner": a.get("owner", ""),
                "kind": a.get("kind", ""),
                "deal_count": a.get("deal_count", len(deals)),
                "mrr_at_stake": a.get("mrr_at_stake"),
                "deals": [_deal_line(d) for d in deals],
            }
        )
    if actions:
        top = actions[0]
        mrr = top.get("mrr_at_stake") or 0.0
        headline = f"{top['action']} — {top['deal_count']} deals · ${mrr:,.0f}/mo"
    else:
        headline = "No open priorities in this region."
    calls = [
        {
            "deal": c.get("label") or c.get("account") or c["deal_id"],
            "why": f"{c['stakeholder']} — {c['move']}",
        }
        for c in (plan.get("vp_should_join_calls", []) if isinstance(plan, dict) else [])
    ]
    return {
        "region": plan.get("region", ""),
        "headline": headline,
        "actions": actions,
        "calls_to_join": calls,
        "rationale": "Deterministic top actions from region_top_actions (no LLM).",
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
    result = await _drive(
        client,
        session,
        model,
        _DEAL_SYSTEM,
        user,
        _SUBMIT_COACHING,
        _deterministic_coaching(ctx),
    )
    # Ensure a rep-friendly company + MRR header regardless of the LLM's output.
    return {**_deal_headline(assessment, deal_id), **result}


async def _run_region_guru(
    client, session, region: str, model: str, region_aware: bool = False, max_deals: int = 10
) -> dict:
    """Prioritize one region to a submit_region_actions call; return its dict."""
    plan = await gather_region_actions(session, region, region_aware, max_deals)
    if isinstance(plan, dict) and "error" in plan:
        return {"region": region, "error": plan["error"]}
    user = (
        f"Region: {region}. Give the VP their top things to do today.\n\n"
        f"Ranked actions (region_top_actions):\n{json.dumps(plan, indent=2)}\n\n"
        "State each as an imperative, name the deals it covers, lead with the "
        "highest-leverage action, then call submit_region_actions."
    )
    return await _drive(
        client,
        session,
        model,
        _REGION_SYSTEM,
        user,
        _SUBMIT_ACTIONS,
        _deterministic_actions(plan),
    )


async def _agent_reply(client, session, model: str, tools: list[dict], messages: list[dict]) -> str:
    """Run the tool-use loop for one chat turn; return the guru's text answer.

    Appends the assistant turn and any tool_result turns to ``messages`` in
    place, so the conversation carries across calls (the user can keep prompting).
    """
    text = ""
    for _ in range(MAX_ITERS):
        resp = await client.messages.create(
            model=model,
            max_tokens=MAX_TOKENS,
            system=_CHAT_SYSTEM,
            tools=tools,
            messages=messages,
        )
        messages.append({"role": "assistant", "content": resp.content})
        tool_uses = [b for b in resp.content if b.type == "tool_use"]
        text = "".join(b.text for b in resp.content if b.type == "text")
        if not tool_uses:
            return text
        tool_results = []
        for block in tool_uses:
            payload = await call_tool(session, block.name, dict(block.input))
            tool_results.append(
                {"type": "tool_result", "tool_use_id": block.id, "content": json.dumps(payload)}
            )
        messages.append({"role": "user", "content": tool_results})
    return text or "(reached the tool-call limit without a final answer)"


# --------------------------------------------------------------------------- #
# Entry points (real agent path + offline dry run).
# --------------------------------------------------------------------------- #
async def coach_deal(deal_id: str, model: str, csv_path: str | None, region_aware: bool) -> dict:
    from anthropic import AsyncAnthropic  # lazy: only needed for the agent path

    client = AsyncAnthropic()
    async with open_session(csv_path) as session:
        return await _run_deal_guru(client, session, deal_id, model, region_aware)


async def coach_region(
    region: str, model: str, csv_path: str | None, region_aware: bool, max_deals: int = 10
) -> dict:
    from anthropic import AsyncAnthropic  # lazy

    client = AsyncAnthropic()
    async with open_session(csv_path) as session:
        return await _run_region_guru(client, session, region, model, region_aware, max_deals)


async def coach_all(
    regions: list[str], model: str, csv_path: str | None, region_aware: bool, max_deals: int = 10
) -> dict:
    from anthropic import AsyncAnthropic  # lazy

    client = AsyncAnthropic()

    async def _one(region: str) -> dict:
        async with open_session(csv_path) as session:
            return await _run_region_guru(client, session, region, model, region_aware, max_deals)

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


async def dry_run_regions(
    regions: list[str], csv_path: str | None, region_aware: bool, max_deals: int = 10
) -> dict:
    out = []
    async with open_session(csv_path) as session:
        for region in regions:
            plan = await gather_region_actions(session, region, region_aware, max_deals)
            if isinstance(plan, dict) and "error" in plan:
                out.append({"region": region, "error": plan["error"]})
            else:
                out.append(_deterministic_actions(plan))
    return {"regions": out, "mode": "dry-run (deterministic worklist, no LLM)"}


async def chat(model: str, csv_path: str | None, region_aware: bool, opener: str | None) -> int:
    """Interactive REPL: ask the guru anything; keep prompting. Needs a key.

    ``region_aware`` is surfaced to the model as context; it still passes the
    flag explicitly on tool calls when it wants the overlay. ``opener`` seeds the
    first user turn (e.g. the --region preset) so the session starts on-topic.
    """
    from anthropic import AsyncAnthropic  # lazy: only needed for the agent path

    client = AsyncAnthropic()
    async with open_session(csv_path) as session:
        tools = await anthropic_tool_schema(session)
        messages: list[dict] = []
        print("=" * 72)
        print("  SALES GURU — interactive. Ask e.g. 'what are my top 3 things in NA?'")
        print("  Type 'exit' or Ctrl-D to quit." + ("  (region-aware ON)" if region_aware else ""))
        print("=" * 72)
        pending = opener
        while True:
            if pending is not None:
                user_msg, pending = pending, None
                print(f"\nyou> {user_msg}")
            else:
                try:
                    user_msg = input("\nyou> ").strip()
                except EOFError:
                    print()
                    break
                if not user_msg:
                    continue
                if user_msg.lower() in ("exit", "quit", ":q"):
                    break
            messages.append({"role": "user", "content": user_msg})
            reply = await _agent_reply(client, session, model, tools, messages)
            print(f"\nguru> {reply}")
    return 0


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _print_coaching(c: dict) -> None:
    label = c.get("label") or c.get("account") or c.get("deal_id", "")
    if c.get("error"):
        print(f"  {label}: {c['error']}")
        return
    print("=" * 72)
    print(f"  SALES GURU — {label}")
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
    for a in p.get("actions", []):
        tag = "⚡" if a.get("kind") == "opportunity" else "⚠"
        stake = ""
        if a.get("mrr_at_stake") is not None:
            count = a.get("deal_count", len(a.get("deals", [])))
            plural = "s" if count != 1 else ""
            stake = f" — {count} deal{plural} · ${a['mrr_at_stake']:,.0f}/mo"
        owner = f"  [{a['owner']}]" if a.get("owner") else ""
        print(f"    {a['priority']}. {tag} {a['action']}{stake}{owner}")
        if a.get("why"):
            print(f"       ↳ {a['why']}")
        for deal in a.get("deals", []):
            print(f"       • {deal}")
    calls = p.get("calls_to_join", [])
    if calls:
        print("    ☎ Join these calls yourself (VP time is scarce):")
        for c in calls:
            name = c.get("deal") or c.get("deal_id", "")
            print(f"       • {name}: {c['why']}")


def _print_region_report(result: dict) -> None:
    print("=" * 72)
    print("  SALES GURU — TOP THINGS TO DO (by region)")
    mode = result.get("mode")
    if mode:
        print(f"  ({mode})")
    print("=" * 72)
    for p in result["regions"]:
        _print_priorities(p)
    print("\n" + "=" * 72)
    print("  The top-priority deals region-wide, grouped by the play to run (every")
    print("  one listed). A prioritized worklist, not an attainment forecast.")


async def _amain(args: argparse.Namespace) -> int:
    csv_path = args.csv
    ra = args.region_aware

    if args.chat:
        opener = f"What are my top priorities in {args.region} today?" if args.region else None
        return await chat(args.model, csv_path, ra, opener)

    if args.deal:
        if args.dry_run:
            result = await dry_run_deal(args.deal, csv_path, ra)
        else:
            result = await coach_deal(args.deal, args.model, csv_path, ra)
        print(json.dumps(result, indent=2)) if args.json else _print_coaching(result)
        return 0

    regions = [args.region] if args.region else await _discover_regions(csv_path)
    if args.dry_run:
        result = await dry_run_regions(regions, csv_path, ra, args.max_deals)
    elif args.region:
        one = await coach_region(args.region, args.model, csv_path, ra, args.max_deals)
        result = {"regions": [one]}
    else:
        result = await coach_all(regions, args.model, csv_path, ra, args.max_deals)
    print(json.dumps(result, indent=2)) if args.json else _print_region_report(result)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--deal", help="coach a single deal (e.g. D-10023)")
    group.add_argument("--region", help="prioritize a single region (e.g. NA)")
    group.add_argument("--all", action="store_true", help="prioritize every region")
    group.add_argument(
        "--chat",
        action="store_true",
        help="interactive chat: ask for your top things, then follow up",
    )
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Anthropic model id")
    parser.add_argument("--csv", default=None, help="pipeline CSV (else FORECAST_CSV/default)")
    parser.add_argument(
        "--max-deals",
        type=int,
        default=config.REGION_MAX_DEALS,
        help=f"top deals to surface per region, all listed (default {config.REGION_MAX_DEALS})",
    )
    parser.add_argument("--dry-run", action="store_true", help="deterministic plays, no LLM/key")
    parser.add_argument(
        "--region-aware",
        action="store_true",
        help="score with the per-region threshold overlay (US/EMEA/APAC)",
    )
    parser.add_argument("--json", action="store_true", help="emit JSON")
    args = parser.parse_args(argv)

    if not (args.deal or args.region or args.all or args.chat):
        parser.error("choose one of --deal, --region, --all, or --chat")
    if args.chat and args.dry_run:
        parser.error("--chat is interactive and needs a key; it has no --dry-run")
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
