"""Optional LLM briefs for flagged deals.

Presentation only. The deterministic rules decide *whether* a deal is an
anomaly; this module never changes that flag -- it only explains an
already-flagged deal in plain language and suggests the rep's next move,
grounded strictly in the row fields and rule hits it is handed.

Offline by default: with no ``ANTHROPIC_API_KEY`` set (or the ``anthropic``
package absent), :func:`brief` returns ``""`` and callers simply skip it.
Never import this from :mod:`detector.rules`, :mod:`detector.engine`, or
:mod:`detector.evaluate`.
"""

from __future__ import annotations

import os

from detector.rules import RuleHit

MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 300

SYSTEM_PROMPT = (
    "You are a RevOps forecast analyst. You are given one sales opportunity's "
    "fields and the deterministic risk rules that already flagged it. Write a "
    "2-3 sentence brief for the deal's rep: first the risk, then the single "
    "highest-leverage next action. Ground everything ONLY in the fields and "
    "rule hits provided -- invent no facts, cite no numbers you were not given, "
    "and never dispute or change the flag. Be direct and specific."
)

# Fields worth showing the model; kept small and deterministic.
_CONTEXT_FIELDS = [
    "deal_id",
    "account",
    "segment",
    "arr",
    "stage",
    "forecast_category",
    "close_date_pushes",
    "days_in_stage",
    "days_to_close",
    "discount_pct",
    "meddpicc_confidence",
    "meddpicc_total",
]


def _row_context(row: dict) -> str:
    """Render the relevant row fields as a compact, model-friendly block."""
    lines = []
    for key in _CONTEXT_FIELDS:
        if key in row and row[key] is not None and row[key] != "":
            lines.append(f"- {key}: {row[key]}")
    return "\n".join(lines)


def _hits_block(hits: list[RuleHit]) -> str:
    """Render the rule hits (id, severity, reason) as a bullet list."""
    return "\n".join(f"- [{hit.severity.upper()}] {hit.rule_id}: {hit.reason}" for hit in hits)


def build_prompt(row: dict, hits: list[RuleHit]) -> str:
    """The user message sent to the model (exposed for testing/inspection)."""
    return (
        "Opportunity fields:\n"
        f"{_row_context(row)}\n\n"
        "Rules that flagged it:\n"
        f"{_hits_block(hits)}\n\n"
        "Write the brief."
    )


def is_available() -> bool:
    """True when a brief can actually be generated (key + SDK present)."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return False
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return False
    return True


def brief(row: dict, hits: list[RuleHit]) -> str:
    """Return a 2-3 sentence risk brief for a flagged deal.

    Returns ``""`` when no API key/SDK is available or the deal has no hits, so
    the pipeline runs end to end offline. Any API error is swallowed into ``""``
    -- the narrative is a nicety, never a dependency.
    """
    if not hits or not is_available():
        return ""
    try:
        import anthropic

        client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": build_prompt(row, hits)}],
        )
        parts = [block.text for block in response.content if block.type == "text"]
        return "".join(parts).strip()
    except Exception:  # pragma: no cover - network/SDK failure => graceful skip
        return ""
