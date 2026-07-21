"""Agent bar: route a natural-language question to one of four agents and answer.

Answers are computed from the real flagged deals (deterministic, always works).
When ANTHROPIC_API_KEY is set, the deterministic answer + a compact forecast
context are handed to the model for a sharper, grounded reply -- one API call,
no subprocess, and it falls back to the deterministic text on any error. The
rules still own every flag; the agent only explains and recommends.
"""

from __future__ import annotations

import os
import re

from api.forecast import money

# Keyword routing -- first match wins (mirrors the design spec).
_ROUTES = [
    (
        re.compile(r"rescue|save|de-?risk|next step|action|fix|recover|turn ?around"),
        "Deal Rescue Planner",
    ),
    (re.compile(r"why|explain|reason|driver|cause"), "Forecast Explainer"),
    (
        re.compile(r"total|sum|how much|exposure|pipeline|quarter|revenue|\$|amount|value"),
        "Pipeline Analyst",
    ),
]

AGENTS = ["Risk Triage Agent", "Forecast Explainer", "Pipeline Analyst", "Deal Rescue Planner"]

_SYSTEM = (
    "You are {agent}, one of four RevOps forecast agents on an executive "
    "dashboard. Answer the user's question in 2-3 tight sentences, grounded ONLY "
    "in the forecast context provided. The deterministic rules own every flag -- "
    "you explain and recommend, never invent a deal or number not in the context. "
    "Name deals by company and dollars. Lead with the action or the number."
)


def route_agent(query: str) -> str:
    q = (query or "").lower()
    for pattern, agent in _ROUTES:
        if pattern.search(q):
            return agent
    return "Risk Triage Agent"


def _aggregates(deals: list[dict]) -> dict:
    at_risk = sorted((d for d in deals if d["risk"] >= 5), key=lambda d: d["risk"], reverse=True)
    by_region: dict[str, float] = {}
    for d in at_risk:
        by_region[d["region"]] = by_region.get(d["region"], 0.0) + d["arr"]
    top_region = max(by_region.items(), key=lambda kv: kv[1]) if by_region else ("--", 0.0)
    critical = [d for d in at_risk if d["risk"] >= 8]
    return {
        "at_risk": at_risk,
        "at_risk_arr": sum(d["arr"] for d in at_risk),
        "top_region": top_region,
        "critical": critical,
        "top3": at_risk[:3],
    }


def deterministic_answer(agent: str, deals: list[dict]) -> str:
    a = _aggregates(deals)
    top3, top_region, critical = a["top3"], a["top_region"], a["critical"]
    if not a["at_risk"]:
        return "Nothing is currently flagged as High or Critical — the forecast is clean."
    if agent == "Risk Triage Agent":
        names = "; ".join(f"{d['account']} (risk {d['risk']}, {d['amountStr']})" for d in top3)
        carry = money(sum(d["arr"] for d in top3))
        return (
            f"Chase these first: {names}. Together they carry {carry} of exposure and "
            f"every one is forecast as Commit or Best Case."
        )
    if agent == "Forecast Explainer":
        return (
            f"{top_region[0]} carries the most exposure ({money(top_region[1])}). The "
            f"recurring driver is deals forecast as Commit below the 60 MEDDPICC floor, "
            f"plus close dates that have slipped past their original date — both hygiene "
            f"rules, not model guesses."
        )
    if agent == "Deal Rescue Planner":
        top = a["at_risk"][0]
        step = top["rules"][0]["action"] if top["rules"] else "Set a dated mutual action plan."
        return (
            f"Highest-value save is {top['account']} ({top['amountStr']}). {step} "
            f"Do the same across the {len(top3)} top accounts before the forecast call."
        )
    return (
        f"{money(a['at_risk_arr'])} of Commit + Best Case is flagged across "
        f"{len(a['at_risk'])} at-risk deals. Largest concentration is {top_region[0]} at "
        f"{money(top_region[1])}; {len(critical)} deals are Critical (risk 8-9)."
    )


def _context(deals: list[dict]) -> str:
    a = _aggregates(deals)
    lines = [
        f"At-risk (High+Critical): {len(a['at_risk'])} deals, {money(a['at_risk_arr'])} ARR.",
        f"Top-exposure region: {a['top_region'][0]} ({money(a['top_region'][1])}).",
        f"Critical (risk 8-9): {len(a['critical'])}.",
        "Top deals:",
    ]
    for d in a["at_risk"][:8]:
        reasons = "; ".join(r["reason"] for r in d["rules"])
        lines.append(
            f"- {d['account']} ({d['region']}, {d['segment']}): risk {d['risk']}, "
            f"{d['amountStr']} ARR, {d['fc']}, owner {d['owner']} / mgr {d['manager']}. {reasons}"
        )
    return "\n".join(lines)


def llm_answer(agent: str, query: str, deals: list[dict], deterministic: str) -> str:
    """One grounded Anthropic call; falls back to the deterministic answer on error."""
    try:
        from anthropic import Anthropic

        client = Anthropic()
        model = os.environ.get("FORECAST_AGENT_MODEL", "claude-sonnet-4-6")
        msg = client.messages.create(
            model=model,
            max_tokens=350,
            system=_SYSTEM.format(agent=agent),
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Forecast context:\n{_context(deals)}\n\n"
                        f"A deterministic draft answer: {deterministic}\n\n"
                        f"Question: {query}\n\n"
                        "Answer as the agent, grounded only in the context above."
                    ),
                }
            ],
        )
        text = "".join(b.text for b in msg.content if getattr(b, "type", None) == "text").strip()
        return text or deterministic
    except Exception:  # noqa: BLE001 - never fail the request; fall back
        return deterministic


def ask(query: str, deals: list[dict]) -> dict:
    """Route + answer. Uses the LLM when ANTHROPIC_API_KEY is set, else deterministic."""
    agent = route_agent(query)
    deterministic = deterministic_answer(agent, deals)
    if os.environ.get("ANTHROPIC_API_KEY"):
        text = llm_answer(agent, query, deals, deterministic)
        source = "llm"
    else:
        text, source = deterministic, "deterministic"
    return {"agent": agent, "text": text, "source": source}
