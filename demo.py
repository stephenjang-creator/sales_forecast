"""One-command offline demo: the whole deterministic story, back to back.

Runs the no-key sections of the walkthrough with headers so you can trigger the
entire offline demo hands-free:

    python demo.py            # or: make demo

1. Eval scorecard vs. ground truth (region-aware)
2. Coach one deal (company + MRR, recommended plays)
3. A region's VP worklist (top deals grouped by play, calls to join + when)
4. Signals: fast movers, complex deals, and meeting-at-risk / value touch
5. Region performance forecast (month/quarter, risk- and mover-adjusted)

Everything here is deterministic and needs no ANTHROPIC_API_KEY. The LLM
sections (`--deal`/`--all` without --dry-run, `--chat`) and the Streamlit UI
(`make app`) are called out at the end.
"""

from __future__ import annotations

import subprocess
import sys

PY = sys.executable


def _pick_flagged_deal() -> str:
    """A real flagged deal_id from the loaded dataset (never a stale hardcode)."""
    try:
        import mcp_server  # local import: loads + scores the pipeline once

        df = mcp_server._df()
        flagged = df[df["predicted_anomaly"]].sort_values("risk_score", ascending=False)
        if not flagged.empty:
            return str(flagged.iloc[0]["deal_id"])
    except Exception:  # noqa: BLE001 - demo convenience, fall back to a known id
        pass
    return "D-10001"


def _header(n: int, title: str) -> None:
    print("\n" + "#" * 72)
    print(f"#  {n}. {title}")
    print("#" * 72 + "\n", flush=True)


def _run(cmd: list[str]) -> None:
    print("$ " + " ".join(cmd), flush=True)
    subprocess.run(cmd, check=False)


def main() -> int:
    deal = _pick_flagged_deal()
    guru = [PY, "-m", "agents.sales_guru"]

    print("=" * 72)
    print("  FORECAST ANOMALY DETECTOR — offline demo (no API key needed)")
    print("=" * 72)

    _header(1, "Detector accuracy vs. ground truth (region-aware)")
    _run([PY, "-m", "detector.evaluate", "data/pipeline.csv", "--region-aware"])

    _header(2, f"Coach one deal ({deal}) — company + MRR, recommended plays")
    _run(guru + ["--deal", deal, "--dry-run"])

    _header(3, "A region's VP worklist — top deals by play, calls to join + when")
    _run(guru + ["--region", "NA", "--dry-run"])

    _header(4, "Signals: value-touch worklist + meeting-at-risk deals")
    _run(guru + ["--region", "LATAM", "--dry-run"])
    print()
    _run([PY, "-c", "import mcp_server as s; print(s.signals_summary(region='NA'))"])

    _header(5, "Region performance forecast (month/quarter, risk- + mover-adjusted)")
    _run([PY, "-m", "agents.attainment", "--all", "--dry-run"])

    print("\n" + "=" * 72)
    print("  Next, with an ANTHROPIC_API_KEY (the LLM layer):")
    print(f"    python -m agents.sales_guru --deal {deal}     # personalized coaching")
    print("    python -m agents.sales_guru --chat --region NA  # ask, then keep prompting")
    print("    make app                                        # the Streamlit UI")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
