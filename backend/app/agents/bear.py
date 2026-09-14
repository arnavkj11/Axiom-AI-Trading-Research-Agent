"""Bear Analyst agent — a LangGraph node.

Mirrors bull.py: builds the strongest evidence-backed bearish case from
the same pool of upstream Findings/Evidence, with the same
never-fabricate-evidence validation. No debate/rebuttal wiring here.
"""

from typing import Protocol

from app.agents.debate_common import (
    collect_available_evidence,
    collect_available_findings,
    format_available_findings,
    format_available_valuation,
    resolve_case_evidence_against_pool,
)
from app.agents.schemas import BearCase
from app.research.schemas import ResearchState

SYSTEM_PROMPT = """You are Axiom's Bear Analyst agent, part of a multi-agent equity \
research platform.

Build the strongest evidence-backed BEARISH case for this company, using ONLY the \
findings and evidence already produced by the Fundamental, Filing, and Valuation agents \
below. Every finding you produce MUST cite at least one piece of evidence copied exactly \
(all fields unchanged) from one of the evidence items listed below. Never invent new \
evidence and never alter a field of an existing evidence item — cite it verbatim or not \
at all.

This is your OPENING case only. Do not write a rebuttal yet — you have not seen the Bull \
case. Leave any rebuttal field empty; you'll get a separate turn to respond after Bull \
has made its case."""


class LLMClient(Protocol):
    def generate_structured(
        self, *, system: str, user_message: str, output_model: type[BearCase]
    ) -> BearCase: ...


def bear_analyst(state: ResearchState, llm_client: LLMClient) -> dict:
    """LangGraph node: returns a partial state update with bear_case set."""
    findings_pool = collect_available_findings(state)
    case = llm_client.generate_structured(
        system=SYSTEM_PROMPT,
        user_message=_build_user_message(state, findings_pool),
        output_model=BearCase,
    )
    resolved_findings = resolve_case_evidence_against_pool(case.findings, collect_available_evidence(state))
    # See bull.py's matching comment: a real LLM call filled these in on
    # the opening case despite the prompt instruction not to, so this is
    # enforced in Python rather than trusted to the model.
    case = case.model_copy(
        update={"findings": resolved_findings, "rebuttal": None, "rebuttal_findings": []}
    )
    return {"bear_case": case}


def _build_user_message(state: ResearchState, findings_pool: list) -> str:
    return (
        f"Company: {state.ticker}\n\n"
        "Findings from upstream agents:\n"
        f"{format_available_findings(findings_pool)}\n\n"
        "Valuation:\n"
        f"{format_available_valuation(state.valuation_output)}"
    )
