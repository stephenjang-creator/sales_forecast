"""Streamlit UI for the Forecast Anomaly Detector.

Two modes (sidebar radio):
  - Demo (portfolio): scores the bundled labeled CSV and shows the eval
    scorecard up top so a reviewer immediately sees it works against ground
    truth, then a sortable/filterable table of flagged deals.
  - Bring your own CSV: runs the same pipeline on an uploaded file. If the file
    has no labels, the scorecard is hidden.

The deterministic rules own every flag. The optional LLM brief (behind a toggle,
per deal) only explains -- it never changes a flag -- and the whole app runs
without an API key.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from detector import narrative
from detector.engine import load, run
from detector.evaluate import ANOMALY_TYPES, overall_metrics, per_rule_metrics

DATA_PATH = Path(__file__).parent / "data" / "pipeline.csv"

FLAGGED_COLUMNS = [
    "deal_id",
    "account",
    "segment",
    "arr",
    "stage",
    "forecast_category",
    "risk_score",
    "top_reason",
]

st.set_page_config(page_title="Forecast Anomaly Detector", layout="wide")


@st.cache_data(show_spinner=False)
def _score_csv(path: str) -> pd.DataFrame:
    """Load and score a CSV from disk (cached by path)."""
    return run(load(path))


def _score_upload(file) -> pd.DataFrame:
    """Load and score an uploaded file object."""
    return run(load(file))


def _has_labels(df: pd.DataFrame) -> bool:
    """True when the frame carries the ground-truth label columns."""
    return "is_anomaly" in df.columns and "anomaly_types" in df.columns


def render_scorecard(scored: pd.DataFrame) -> None:
    """Overall precision/recall/F1 metrics plus the per-rule breakdown."""
    om = overall_metrics(scored)
    st.subheader("Evaluation vs. ground truth")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Precision", f"{om.precision:.3f}")
    c2.metric("Recall", f"{om.recall:.3f}")
    c3.metric("F1", f"{om.f1:.3f}")
    c4.metric("TP / FP / FN / TN", f"{om.tp} / {om.fp} / {om.fn} / {om.tn}")

    rules = per_rule_metrics(scored)
    table = pd.DataFrame(
        {
            "rule_id": [r.rule_id for r in rules],
            "precision": [round(r.precision, 3) for r in rules],
            "recall": [round(r.recall, 3) for r in rules],
            "fired": [r.fired for r in rules],
            "labeled": [r.labeled for r in rules],
            "correct": [r.correct for r in rules],
        }
    )
    st.caption(
        "Per-rule: when a rule fires, does the deal carry that id (precision), "
        "and of the deals that do, how many did it catch (recall)?"
    )
    st.dataframe(table, hide_index=True, use_container_width=True)


def render_flagged(scored: pd.DataFrame, use_narrative: bool) -> None:
    """Filterable table of flagged deals + a per-deal detail expander."""
    flagged = scored[scored["predicted_anomaly"]].copy()
    st.subheader(f"Flagged deals ({len(flagged)} of {len(scored)})")

    if flagged.empty:
        st.info("No deals were flagged.")
        return

    # Filters.
    f1, f2, f3 = st.columns(3)
    segments = sorted(flagged["segment"].dropna().unique().tolist())
    stages = sorted(flagged["stage"].dropna().unique().tolist())
    seg_pick = f1.multiselect("Segment", segments, default=segments)
    stage_pick = f2.multiselect("Stage", stages, default=stages)
    min_risk = f3.slider("Min risk score", 0, int(flagged["risk_score"].max()), 0)
    view = flagged[
        flagged["segment"].isin(seg_pick)
        & flagged["stage"].isin(stage_pick)
        & (flagged["risk_score"] >= min_risk)
    ].sort_values("risk_score", ascending=False)

    st.dataframe(
        view[FLAGGED_COLUMNS],
        hide_index=True,
        use_container_width=True,
        column_config={
            "arr": st.column_config.NumberColumn("ARR", format="$%d"),
            "risk_score": st.column_config.NumberColumn("Risk"),
            "top_reason": st.column_config.TextColumn("Top reason", width="large"),
        },
    )

    st.markdown("#### Deal detail")
    for _, row in view.iterrows():
        header = (
            f"{row['deal_id']} · {row['account']} · {row['stage']} · " f"risk {row['risk_score']}"
        )
        with st.expander(header):
            for hit in row["hits"]:
                st.markdown(f"- **{hit.severity.upper()} · {hit.rule_id}** — {hit.reason}")
            if use_narrative:
                if not narrative.is_available():
                    st.info("Set ANTHROPIC_API_KEY to enable LLM briefs.")
                elif st.button("Generate LLM brief", key=f"brief_{row['deal_id']}"):
                    with st.spinner("Writing brief…"):
                        text = narrative.brief(row.to_dict(), list(row["hits"]))
                    st.write(text or "_(no brief returned)_")


def main() -> None:
    st.title("Forecast Anomaly Detector")
    st.caption(
        "AI-first, human-in-the-loop RevOps. Deterministic MEDDPICC + hygiene "
        "rules own every flag; the LLM only explains. All data is synthetic."
    )

    mode = st.sidebar.radio("Mode", ["Demo (portfolio)", "Bring your own CSV"])
    use_narrative = st.sidebar.toggle("Show LLM briefs", value=False)
    if use_narrative and not narrative.is_available():
        st.sidebar.info("No ANTHROPIC_API_KEY detected — briefs disabled.")

    st.sidebar.markdown("---")
    st.sidebar.caption("Anomaly types:\n" + "\n".join(f"- {t}" for t in ANOMALY_TYPES))

    if mode == "Demo (portfolio)":
        if not DATA_PATH.exists():
            st.error(f"Bundled dataset not found at {DATA_PATH}. Run `make data`.")
            return
        scored = _score_csv(str(DATA_PATH))
        render_scorecard(scored)
        st.markdown("---")
        render_flagged(scored, use_narrative)
    else:
        upload = st.file_uploader(
            "Upload a pipeline CSV (same schema; labels optional)", type=["csv"]
        )
        if upload is None:
            st.info("Upload a CSV to run the detector.")
            return
        scored = _score_upload(upload)
        if _has_labels(scored):
            render_scorecard(scored)
            st.markdown("---")
        else:
            st.caption("No label columns found — scorecard hidden; showing flags only.")
        render_flagged(scored, use_narrative)


if __name__ == "__main__":
    main()
