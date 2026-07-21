"""Thin async client for talking to ``mcp_server.py`` over stdio.

Launches the server as a subprocess, exposes its tools, and parses their JSON
returns back into Python objects. Also converts the MCP tool list into the
schema shape the Anthropic Messages API expects, so an agent loop can offer the
same tools to the model.

Nothing here is detector logic -- it's transport plumbing shared by the
attainment agents and the ``--dry-run`` path.
"""

from __future__ import annotations

import contextlib
import json
import os
import sys
from pathlib import Path
from typing import Any, AsyncIterator

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SERVER_PATH = Path(__file__).resolve().parent.parent / "mcp_server.py"


@contextlib.asynccontextmanager
async def open_session(csv_path: str | None = None) -> AsyncIterator[ClientSession]:
    """Start the MCP server over stdio and yield an initialized session.

    ``csv_path`` overrides ``FORECAST_CSV`` for the spawned server so an agent
    can point at a specific export.
    """
    env = dict(os.environ)
    if csv_path:
        env["FORECAST_CSV"] = csv_path
    params = StdioServerParameters(command=sys.executable, args=[str(SERVER_PATH)], env=env)
    # Route the server's stderr (request logging) to devnull so agent output
    # stays clean; tool errors still come back in-band as {"error": ...}.
    with open(os.devnull, "w") as errlog:
        async with stdio_client(params, errlog=errlog) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                yield session


def _parse_tool_result(result: Any) -> Any:
    """Pull the JSON payload out of an MCP CallToolResult."""
    structured = getattr(result, "structuredContent", None)
    if isinstance(structured, dict):
        # FastMCP wraps non-dict returns as {"result": ...}; unwrap that.
        return structured.get("result", structured)
    for block in getattr(result, "content", []) or []:
        text = getattr(block, "text", None)
        if text is not None:
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return text
    return None


async def call_tool(session: ClientSession, name: str, arguments: dict | None = None) -> Any:
    """Call an MCP tool and return its parsed JSON payload."""
    result = await session.call_tool(name, arguments or {})
    return _parse_tool_result(result)


async def anthropic_tool_schema(session: ClientSession) -> list[dict]:
    """The server's tools in Anthropic Messages `tools=` format."""
    listed = await session.list_tools()
    schema = []
    for tool in listed.tools:
        schema.append(
            {
                "name": tool.name,
                "description": tool.description or "",
                "input_schema": tool.inputSchema or {"type": "object", "properties": {}},
            }
        )
    return schema


async def gather_deal_context(
    session: ClientSession, deal_id: str, region_aware: bool = False
) -> dict:
    """Everything the sales guru needs to coach ONE deal, via tools.

    Pairs the full risk picture (``assess_deal``) with the deterministic plays
    (``recommend_plays``) so the agent personalizes an existing motion instead
    of inventing one. ``region_aware`` opts into the per-region overlay.
    """
    ra = {"region_aware": region_aware}
    assessment = await call_tool(session, "assess_deal", {"deal_id": deal_id, **ra})
    plays = await call_tool(session, "recommend_plays", {"deal_id": deal_id, **ra})
    return {"deal_id": deal_id, "assessment": assessment, "plays": plays}


async def gather_region_actions(
    session: ClientSession, region: str, region_aware: bool = False, top_n: int = 3
) -> dict:
    """The region's top-N prioritized actions (``region_top_actions``), via tools."""
    return await call_tool(
        session,
        "region_top_actions",
        {"region": region, "region_aware": region_aware, "top_n": top_n},
    )


async def gather_region_context(
    session: ClientSession, region: str, region_aware: bool = False
) -> dict:
    """Collect everything an attainment agent needs for one region, via tools.

    ``region_aware`` opts the scoring-dependent tools into the per-region
    threshold overlay.
    """
    ra = {"region_aware": region_aware}
    rollup = await call_tool(session, "assess_region", {"region": region, **ra})
    deals = await call_tool(session, "list_deals", {"region": region, "limit": 1000, **ra})
    flagged = await call_tool(
        session,
        "list_deals",
        {"region": region, "flagged_only": True, "limit": 1000, **ra},
    )
    month_rollup = await call_tool(
        session, "bookings_rollup", {"grain": "month", "region": region, **ra}
    )
    quarter_rollup = await call_tool(
        session, "bookings_rollup", {"grain": "quarter", "region": region, **ra}
    )
    quarter_history = await call_tool(
        session, "period_comparison", {"grain": "quarter", "region": region}
    )
    return {
        "region": region,
        "rollup": rollup,
        "deals": deals if isinstance(deals, list) else [],
        "flagged_deals": flagged if isinstance(flagged, list) else [],
        "month_rollup": month_rollup,
        "quarter_rollup": quarter_rollup,
        "quarter_history": quarter_history,
    }
