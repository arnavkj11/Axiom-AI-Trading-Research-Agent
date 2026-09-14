"""Bear rebuttal node — mirrors bull_rebuttal.py. Bear's one allowed reply
to Bull's opening case; same three-layer cap enforcement (see
bull_rebuttal.py's module docstring).
"""

from typing import Protocol

from app.agents.debate_common import (
    RebuttalAlreadyRecordedError,
    RebuttalResponse,
    collect_rebuttal_evidence_pool,
    format_available_findings,
    resolve_case_evidence_against_pool,
)
from app.agents.schemas import BearCase
from app.research.schemas import ResearchState

SYSTEM_PROMPT = """You are Axiom's Bear Analyst agent, responding once to the Bull \
Analyst's opening case.

Read the Bull case below and write a single, focused rebuttal defending or \
strengthening your bearish thesis. This is your only opportunity to respond in this \
research run — there will be no further rounds regardless of what you write. Every \
rebuttal finding you produce MUST cite evidence copied exactly (all fields unchanged) \
from one of the evidence items listed below. Never invent new evidence."""


class LLMClient(Protocol):
    def generate_structured(
        self, *, system: str, user_message: str, output_model: type[RebuttalResponse]
    ) -> RebuttalResponse: ...


def bear_rebuttal(state: ResearchState, llm_client: LLMClient) -> dict:
    """LangGraph node: returns a partial state update with bear_case's
    rebuttal fields set. Requires bull_case and bear_case to already be
    populated (enforced by the graph's fan-in edges from both bull and
    bear).
    """
    if state.bull_case is None or state.bear_case is None:
        raise ValueError("bear_rebuttal requires both bull_case and bear_case to be set")
    if state.bear_case.rebuttal is not None:
        raise RebuttalAlreadyRecordedError("bear_case already has a recorded rebuttal")

    response = llm_client.generate_structured(
        system=SYSTEM_PROMPT,
        user_message=_build_user_message(state),
        output_model=RebuttalResponse,
    )

    pool = collect_rebuttal_evidence_pool(state)
    resolved_rebuttal_findings = resolve_case_evidence_against_pool(response.rebuttal_findings, pool)

    updated_bear_case: BearCase = state.bear_case.model_copy(
        update={"rebuttal": response.rebuttal, "rebuttal_findings": resolved_rebuttal_findings}
    )
    return {"bear_case": updated_bear_case}


def _build_user_message(state: ResearchState) -> str:
    return (
        f"Company: {state.ticker}\n\n"
        "Your (Bear) opening case:\n"
        f"Thesis: {state.bear_case.thesis}\n"
        f"{format_available_findings(state.bear_case.findings)}\n\n"
        "Bull's opening case (respond to this):\n"
        f"Thesis: {state.bull_case.thesis}\n"
        f"{format_available_findings(state.bull_case.findings)}"
    )
