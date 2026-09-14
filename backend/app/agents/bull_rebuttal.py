"""Bull rebuttal node — Bull's one allowed reply to Bear's opening case
(CLAUDE.md Rule 5: hard-capped at one rebuttal round each).

The cap is enforced in three layers, not by prompt instruction alone:
1. Graph topology — no edge anywhere loops back into this node, so it can
   only ever run once per graph.invoke() (see orchestrator.py).
2. Schema shape — BullCase.rebuttal is a single str | None field, not a
   list, so even a duplicate call could only overwrite, never accumulate.
3. This function's explicit guard below, which raises rather than
   silently overwriting if a rebuttal is already recorded — catching a
   future graph-wiring mistake at run time instead of relying solely on
   (1). This is a real `if`/`raise`, not an `assert`, so it can't be
   stripped by running Python with -O.
"""

from typing import Protocol

from app.agents.debate_common import (
    RebuttalAlreadyRecordedError,
    RebuttalResponse,
    collect_rebuttal_evidence_pool,
    format_available_findings,
    resolve_case_evidence_against_pool,
)
from app.agents.schemas import BullCase
from app.research.schemas import ResearchState

SYSTEM_PROMPT = """You are Axiom's Bull Analyst agent, responding once to the Bear \
Analyst's opening case.

Read the Bear case below and write a single, focused rebuttal defending or \
strengthening your bullish thesis. This is your only opportunity to respond in this \
research run — there will be no further rounds regardless of what you write. Every \
rebuttal finding you produce MUST cite evidence copied exactly (all fields unchanged) \
from one of the evidence items listed below. Never invent new evidence."""


class LLMClient(Protocol):
    def generate_structured(
        self, *, system: str, user_message: str, output_model: type[RebuttalResponse]
    ) -> RebuttalResponse: ...


def bull_rebuttal(state: ResearchState, llm_client: LLMClient) -> dict:
    """LangGraph node: returns a partial state update with bull_case's
    rebuttal fields set. Requires bull_case and bear_case to already be
    populated (enforced by the graph's fan-in edges from both bull and
    bear).
    """
    if state.bull_case is None or state.bear_case is None:
        raise ValueError("bull_rebuttal requires both bull_case and bear_case to be set")
    if state.bull_case.rebuttal is not None:
        raise RebuttalAlreadyRecordedError("bull_case already has a recorded rebuttal")

    response = llm_client.generate_structured(
        system=SYSTEM_PROMPT,
        user_message=_build_user_message(state),
        output_model=RebuttalResponse,
    )

    pool = collect_rebuttal_evidence_pool(state)
    resolved_rebuttal_findings = resolve_case_evidence_against_pool(response.rebuttal_findings, pool)

    updated_bull_case: BullCase = state.bull_case.model_copy(
        update={"rebuttal": response.rebuttal, "rebuttal_findings": resolved_rebuttal_findings}
    )
    return {"bull_case": updated_bull_case}


def _build_user_message(state: ResearchState) -> str:
    return (
        f"Company: {state.ticker}\n\n"
        "Your (Bull) opening case:\n"
        f"Thesis: {state.bull_case.thesis}\n"
        f"{format_available_findings(state.bull_case.findings)}\n\n"
        "Bear's opening case (respond to this):\n"
        f"Thesis: {state.bear_case.thesis}\n"
        f"{format_available_findings(state.bear_case.findings)}"
    )
