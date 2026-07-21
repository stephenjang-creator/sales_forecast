"""Deterministic sales playbook: recommended plays to de-risk a flagged deal.

Each anomaly rule maps to a standard sales play -- the motion a good AE would run
to remove that specific risk. This is the auditable, offline half of the "sales
guru": it never calls an LLM and is a pure function of the rule hits. The LLM
guru (``agents/sales_guru.py``) personalizes these plays to a deal's specifics;
the plays here are the grounded anchor it starts from.

Adding a play for a new anomaly is a one-entry edit to :data:`PLAYBOOK`.
"""

from __future__ import annotations

from dataclasses import dataclass

import config
from detector.rules import RuleHit


@dataclass(frozen=True)
class Play:
    """A recommended play to address one risk.

    Attributes:
        rule_id: The anomaly this play addresses (matches a RuleHit id).
        title: Short name of the play.
        why: The risk it removes, in one line.
        actions: Concrete next steps, most important first.
        owner: Who should run it (rep / manager / deal desk).
    """

    rule_id: str
    title: str
    why: str
    actions: tuple[str, ...]
    owner: str


PLAYBOOK: dict[str, Play] = {
    "slipped_close_date": Play(
        rule_id="slipped_close_date",
        title="Reset the close plan with a mutual action plan",
        why="Repeated slips mean the close date isn't tied to real, agreed steps.",
        actions=(
            "Co-build a written mutual action plan with the champion, working "
            "backward from a compelling event to a realistic close date.",
            "Confirm every remaining step (technical, legal, procurement) has an "
            "owner and a date before re-committing the deal.",
            "If it has slipped 3+ times, take it to a manager deal review and stop "
            "forecasting the current date.",
        ),
        owner="rep + manager",
    ),
    "stalled_in_stage": Play(
        rule_id="stalled_in_stage",
        title="Re-engage and manufacture a next step",
        why="The deal has gone quiet far past the normal pace for its stage.",
        actions=(
            "Book a next-step-defining call; open with a value recap, not a " "'checking in' ask.",
            "Anchor to a compelling event (budget cycle, renewal, initiative "
            "deadline) to create real urgency.",
            "If the champion is unresponsive, multi-thread to a second contact and "
            "consider a manager-to-manager touch.",
        ),
        owner="rep",
    ),
    "commit_low_meddpicc": Play(
        rule_id="commit_low_meddpicc",
        title="Close the MEDDPICC gaps before it stays in Commit",
        why="Forecast as Commit on thin qualification is a happy-ears risk.",
        actions=(
            "Run a qualification call targeting the two weakest MEDDPICC elements "
            "named in the flag.",
            "Confirm metrics, the economic buyer, and the decision process in "
            "writing (recap email the champion agrees to).",
            "Downgrade the forecast to Best Case until the gaps are closed.",
        ),
        owner="rep + manager",
    ),
    "late_stage_no_economic_buyer": Play(
        rule_id="late_stage_no_economic_buyer",
        title="Get to the Economic Buyer now",
        why="No one who can sign is engaged this late in the cycle.",
        actions=(
            "Ask the champion for a warm intro to the economic buyer, using a "
            "business case / ROI as the reason for the conversation.",
            "Run an executive value-alignment meeting to confirm budget authority "
            "and the success metrics that matter to them.",
            "If the champion won't open the door, treat that as a red flag and "
            "test for a mobilizer elsewhere in the account.",
        ),
        owner="rep + exec sponsor",
    ),
    "premature_deep_discount": Play(
        rule_id="premature_deep_discount",
        title="Re-anchor on value before price",
        why="A deep discount before value is established trains the buyer to push.",
        actions=(
            "Pause the discount and run value/ROI discovery to establish quantified "
            "pain and metrics first.",
            "Tie any discount to reciprocal concessions (multi-year, case study, "
            "expansion commitment, faster close).",
            "Loop in deal desk to structure pricing rather than dropping list.",
        ),
        owner="rep + deal desk",
    ),
    "imminent_close_no_paper_process": Play(
        rule_id="imminent_close_no_paper_process",
        title="Kick off procurement and legal immediately",
        why="Closing within days with no paper process started is unrealistic.",
        actions=(
            "Confirm the signatory and the exact procurement/legal steps and their "
            "typical timelines today.",
            "Send the order form / MSA to legal now and set a redlines deadline.",
            "Re-baseline the close date against the real paper-process timeline "
            "instead of hoping it compresses.",
        ),
        owner="rep + deal desk",
    ),
}


# The "close it" motion for a clean fast mover. Not an anomaly play -- there is
# no risk to remove -- but a regional VP's worklist wants the specific move to
# pull an empowered-champion / simple-process deal forward, so it lives here with
# the rest of the plays. ``rule_id`` doubles as the fast_mover signal id.
FAST_MOVER_PLAY = Play(
    rule_id="fast_mover",
    title="Pull it forward and close",
    why="An empowered champion and a simple process mean this can close early.",
    actions=(
        "Confirm the paper process (order form, signatory) and clear any "
        "procurement unknowns now, while momentum is high.",
        "Propose an earlier close date tied to the champion's timeline and ask "
        "for the verbal commit.",
        "Keep a same-week next step on the calendar so there is no gap the deal " "can stall in.",
    ),
    owner="rep",
)

# Rules that mean a deal has come off the rails (stalled or slipped) -- the
# "get it back on track" bucket of a regional action plan.
STALLED_SLIPPED_RULES = ("slipped_close_date", "stalled_in_stage")


def recommend_plays(hits: list[RuleHit]) -> list[Play]:
    """The recommended plays for a deal's rule hits (deduped, in hit order)."""
    plays: list[Play] = []
    seen: set[str] = set()
    for hit in hits:
        play = PLAYBOOK.get(hit.rule_id)
        if play is not None and play.rule_id not in seen:
            plays.append(play)
            seen.add(play.rule_id)
    return plays


def primary_hit(hits: list[RuleHit]) -> RuleHit | None:
    """A deal's highest-severity hit that has a play (first wins ties)."""
    playable = [hit for hit in hits if hit.rule_id in PLAYBOOK]
    if not playable:
        return None
    return max(playable, key=lambda hit: config.SEVERITY[hit.severity])


def primary_play(hits: list[RuleHit]) -> Play | None:
    """The single play for a deal's highest-severity hit (first wins ties).

    Used where one deal gets one headline move (e.g. a regional VP worklist),
    rather than the full :func:`recommend_plays` list.
    """
    hit = primary_hit(hits)
    return PLAYBOOK[hit.rule_id] if hit is not None else None
