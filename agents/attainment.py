"""Predict risk-adjusted regional attainment with one agent per region.

Each region gets its own agent that talks to the deterministic detector over the
MCP stdio server, grounds itself in a transparent baseline, and returns a
structured expected-bookings estimate. Regions are run concurrently; a final
step aggregates them into a portfolio view.

What this is NOT: a quota-attainment percentage (the synthetic data has no
quota) and not a deterministic forecast of record. It is a *model estimate* of
expected bookings, risk-adjusted by the detector's flags, meant to be read
alongside the flags -- human-in-the-loop, not autopilot.

Usage:
    python -m agents.attainment --all            # every region + portfolio
    python -m agents.attainment --region EMEA    # one region
    python -m agents.attainment --all --dry-run  # no LLM/key; baseline only
    python -m agents.attainment --all --json     # machine-readable output

Needs ANTHROPIC_API_KEY for the agent path; --dry-run runs fully offline.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

from agents.baseline import baseline_from_deals
from agents.mcp_client import (
    anthropic_tool_schema,
    call_tool,
    gather_region_context,
    open_session,
)

DEFAULT_MODEL = os.environ.get("FORECAST_AGENT_MODEL", "claude-sonnet-4-6")
MAX_ITERS = 6
MAX_TOKENS = 1500

_PERIOD_SCHEMA = {
    "type": "object",
    "properties": {
        "period": {"type": "string"},
        "projected_bookings": {"type": "number"},
        "attainment_pct": {"type": "number"},
        "yoy_change_pct": {"type": "number"},
    },
    "required": ["period", "projected_bookings"],
}

_SUBMIT_TOOL = {
    "name": "submit_prediction",
    "description": (
        "Submit your final risk-adjusted attainment estimate for the region. Call "
        "this exactly once, after gathering evidence with the other tools."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "region": {"type": "string"},
            "month": _PERIOD_SCHEMA,
            "quarter": _PERIOD_SCHEMA,
            "expected_bookings": {
                "type": "object",
                "description": "Whole-region open-pipeline estimate (context).",
                "properties": {
                    "low": {"type": "number"},
                    "likely": {"type": "number"},
                    "high": {"type": "number"},
                },
                "required": ["low", "likely", "high"],
            },
            "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
            "key_risks": {"type": "array", "items": {"type": "string"}},
            "recommended_actions": {"type": "array", "items": {"type": "string"}},
            "rationale": {"type": "string"},
        },
        "required": ["region", "quarter", "confidence", "rationale"],
    },
}

_SYSTEM = (
    "You are a RevOps forecast analyst. For ONE region, project how much it will "
    "book THIS MONTH and THIS QUARTER, and how that compares year-over-year. "
    "These are risk-adjusted estimates, not guaranteed forecasts. Ground every "
    "number in the MCP tools: bookings_rollup gives the current-period projection "
    "(won-so-far + risk-adjusted expected-to-close) and quota; period_comparison "
    "and bookings_history give the actuals to compare against; assess_region, "
    "list_deals and forecast_summary explain the risk. The current period is IN "
    "PROGRESS -- treat its attainment as pace, not a final result, and say so. "
    "You are handed the tool outputs as anchors; stay consistent with them unless "
    "you can justify a change from other tool evidence. Call get_scorecard if you "
    "want to caveat reliability. When finished, call submit_prediction exactly "
    "once. Never invent deals or numbers the tools did not return."
)


def _fmt_usd(x: float) -> str:
    return f"${x:,.0f}"


# --------------------------------------------------------------------------- #
# Agent loop (Anthropic tool-use over the MCP tools).
# --------------------------------------------------------------------------- #
async def _run_region_agent(
    client, session, region: str, model: str, region_aware: bool = False
) -> dict:
    """Drive one region's agent to a submit_prediction call; return its dict."""
    ctx = await gather_region_context(session, region, region_aware)
    baseline = baseline_from_deals(ctx["deals"])
    tools = await anthropic_tool_schema(session)
    tools.append(_SUBMIT_TOOL)

    user = (
        f"Region: {region}\n\n"
        f"Current MONTH rollup (bookings_rollup):\n"
        f"{json.dumps(ctx['month_rollup'], indent=2)}\n\n"
        f"Current QUARTER rollup (bookings_rollup):\n"
        f"{json.dumps(ctx['quarter_rollup'], indent=2)}\n\n"
        f"Historical quarter comparison (period_comparison):\n"
        f"{json.dumps(ctx['quarter_history'], indent=2)}\n\n"
        f"Whole-region open-pipeline baseline (context):\n{json.dumps(baseline, indent=2)}\n\n"
        f"There are {len(ctx['flagged_deals'])} flagged deals in this region. "
        "Verify with the tools as needed, then submit your prediction with month "
        "and quarter projections and a YoY read."
    )
    messages: list[dict] = [{"role": "user", "content": user}]

    for _ in range(MAX_ITERS):
        resp = await client.messages.create(
            model=model,
            max_tokens=MAX_TOKENS,
            system=_SYSTEM,
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
            if block.name == "submit_prediction":
                submitted = dict(block.input)
                submitted["_baseline"] = baseline
                content = "Prediction recorded."
            else:
                payload = await call_tool(session, block.name, dict(block.input))
                content = json.dumps(payload)
            tool_results.append(
                {"type": "tool_result", "tool_use_id": block.id, "content": content}
            )
        if submitted is not None:
            return submitted
        messages.append({"role": "user", "content": tool_results})

    # Model never submitted; fall back to the deterministic tool rollups.
    return {
        "region": region,
        "month": _period_summary(ctx["month_rollup"]),
        "quarter": _period_summary(ctx["quarter_rollup"]),
        "expected_bookings": baseline["expected_bookings"],
        "confidence": "low",
        "rationale": "Agent did not submit; using deterministic tool rollups.",
        "key_risks": [],
        "recommended_actions": [],
        "_baseline": baseline,
        "_fallback": True,
    }


def _period_summary(rollup: dict) -> dict:
    """Pull the headline fields out of a bookings_rollup result."""
    if not isinstance(rollup, dict):
        return {}
    return {
        "period": rollup.get("current_period"),
        "projected_bookings": rollup.get("projected_bookings"),
        "attainment_pct": rollup.get("projected_attainment_pct"),
        "yoy_change_pct": rollup.get("yoy_change_pct"),
    }


async def predict_region(
    region: str, model: str, csv_path: str | None, region_aware: bool = False
) -> dict:
    """Run a single region's agent end to end over its own MCP session."""
    from anthropic import AsyncAnthropic  # lazy: only needed for the agent path

    client = AsyncAnthropic()
    async with open_session(csv_path) as session:
        return await _run_region_agent(client, session, region, model, region_aware)


# --------------------------------------------------------------------------- #
# Fan-out + portfolio aggregation.
# --------------------------------------------------------------------------- #
def _sum_projected(predictions: list[dict], period: str) -> float:
    """Sum projected_bookings across regions for 'month' or 'quarter'."""
    total = 0.0
    for p in predictions:
        block = p.get(period) or {}
        total += float(block.get("projected_bookings") or 0)
    return round(total, 0)


def _aggregate(predictions: list[dict]) -> dict:
    """Sum region projections into a deterministic portfolio total."""
    return {
        "regions": [p["region"] for p in predictions],
        "month_projected_bookings": _sum_projected(predictions, "month"),
        "quarter_projected_bookings": _sum_projected(predictions, "quarter"),
    }


async def _discover_regions(csv_path: str | None) -> list[str]:
    async with open_session(csv_path) as session:
        regions = await call_tool(session, "list_regions")
    if isinstance(regions, dict):  # {"error": ...}
        raise RuntimeError(regions.get("error", "could not list regions"))
    return list(regions)


async def predict_all(
    regions: list[str], model: str, csv_path: str | None, region_aware: bool = False
) -> dict:
    """Fan out one agent per region concurrently, then aggregate."""
    from anthropic import AsyncAnthropic  # lazy

    client = AsyncAnthropic()

    async def _one(region: str) -> dict:
        async with open_session(csv_path) as session:
            return await _run_region_agent(client, session, region, model, region_aware)

    predictions = await asyncio.gather(*(_one(r) for r in regions))
    predictions = list(predictions)
    return {"regions": predictions, "portfolio": _aggregate(predictions)}


# --------------------------------------------------------------------------- #
# Offline dry run: prove the stdio + tools + baseline flow with no key.
# --------------------------------------------------------------------------- #
async def dry_run(regions: list[str], csv_path: str | None, region_aware: bool = False) -> dict:
    """Compute each region's month + quarter rollup and YoY via the tools only."""
    out = []
    async with open_session(csv_path) as session:
        for region in regions:
            month = await call_tool(
                session,
                "bookings_rollup",
                {"grain": "month", "region": region, "region_aware": region_aware},
            )
            quarter = await call_tool(
                session,
                "bookings_rollup",
                {"grain": "quarter", "region": region, "region_aware": region_aware},
            )
            comp = await call_tool(
                session, "period_comparison", {"grain": "quarter", "region": region}
            )
            out.append(
                {
                    "region": region,
                    "month": _period_summary(month),
                    "quarter": _period_summary(quarter),
                    "quarter_history": comp if isinstance(comp, dict) else {},
                }
            )
    return {
        "regions": out,
        "portfolio": _aggregate(out),
        "mode": "dry-run (deterministic tool rollups, no LLM)",
    }


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _fmt_period(block: dict) -> str:
    """One-line 'projected $X (Y% attainment, YoY +Z%)' from a period block."""
    if not block or block.get("projected_bookings") is None:
        return "n/a"
    parts = [_fmt_usd(block["projected_bookings"])]
    extra = []
    if block.get("attainment_pct") is not None:
        extra.append(f"{block['attainment_pct']:.0f}% attain")
    if block.get("yoy_change_pct") is not None:
        extra.append(f"YoY {block['yoy_change_pct']:+.0f}%")
    if extra:
        parts.append(f"({', '.join(extra)})")
    if block.get("period"):
        parts.append(f"[{block['period']}]")
    return " ".join(parts)


def _print_report(result: dict) -> None:
    mode = result.get("mode", "agent")
    print("=" * 72)
    print("  REGIONAL ATTAINMENT — PROJECTED BOOKINGS (risk-adjusted)")
    print(f"  ({mode})")
    print("=" * 72)
    for r in result["regions"]:
        print(f"\n  {r['region']}")
        print(f"    This month:   {_fmt_period(r.get('month', {}))}")
        print(f"    This quarter: {_fmt_period(r.get('quarter', {}))}")
        if r.get("confidence"):
            print(f"    Confidence: {r['confidence']}")
        for risk in r.get("key_risks", [])[:3]:
            print(f"    ⚠ {risk}")
        if r.get("rationale"):
            print(f"    → {r['rationale']}")
    pf = result["portfolio"]
    print("\n" + "-" * 72)
    print(
        f"  PORTFOLIO  month {_fmt_usd(pf['month_projected_bookings'])}   "
        f"quarter {_fmt_usd(pf['quarter_projected_bookings'])}"
    )
    print("=" * 72)
    print("  Current period is in progress — read attainment as pace, not a")
    print("  final result. Estimate, not a guaranteed forecast.")


async def _amain(args: argparse.Namespace) -> int:
    csv_path = args.csv
    if args.region:
        regions = [args.region]
    else:
        regions = await _discover_regions(csv_path)

    ra = args.region_aware
    if args.dry_run:
        result = await dry_run(regions, csv_path, ra)
    elif args.region:
        pred = await predict_region(args.region, args.model, csv_path, ra)
        result = {"regions": [pred], "portfolio": _aggregate([pred])}
    else:
        result = await predict_all(regions, args.model, csv_path, ra)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        _print_report(result)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--all", action="store_true", help="predict every region")
    group.add_argument("--region", help="predict a single region (e.g. EMEA)")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Anthropic model id")
    parser.add_argument("--csv", default=None, help="pipeline CSV (else FORECAST_CSV/default)")
    parser.add_argument("--dry-run", action="store_true", help="baseline only, no LLM/key")
    parser.add_argument(
        "--region-aware",
        action="store_true",
        help="score with the per-region threshold overlay (US/EMEA/APAC)",
    )
    parser.add_argument("--json", action="store_true", help="emit JSON")
    args = parser.parse_args(argv)

    if not args.dry_run and not args.region and not os.environ.get("ANTHROPIC_API_KEY"):
        print(
            "error: ANTHROPIC_API_KEY not set. Use --dry-run for an offline "
            "baseline, or export a key to run the agents.",
            file=sys.stderr,
        )
        return 1
    return asyncio.run(_amain(args))


if __name__ == "__main__":
    raise SystemExit(main())
