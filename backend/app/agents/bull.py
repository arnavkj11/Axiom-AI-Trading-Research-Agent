"""Bull Analyst agent — a LangGraph node.

Builds the strongest evidence-backed bullish case from the Fundamental,
Filing, and Valuation agents' findings (CLAUDE.md: Bull Analyst "builds
the strongest evidence-backed bull case from the preliminary thesis and
the other agents' findings"). It argues from evidence that already
exists — it does not gather new evidence — so every citation is checked
against that existing pool before the result is accepted.

No debate/rebuttal wiring here; that's a separate, later step.
"""

from typing import Protocol

from app.agents.debate_common import (
    collect_available_evidence,
    collect_available_findings,
    format_available_findings,
    format_available_valuation,
    resolve_case_evidence_against_pool,
)
from app.agents.schemas import BullCase
from app.research.schemas import ResearchState

SYSTEM_PROMPT = """You are Axiom's Bull Analyst agent, part of a multi-agent equity \
research platform.

Build the strongest evidence-backed BULLISH case for this company, using ONLY the \
findings and evidence already produced by the Fundamental, Filing, and Valuation agents \
below. Every finding you produce MUST cite at least one piece of evidence copied exactly \
(all fields unchanged) from one of the evidence items listed below. Never invent new \
evidence and never alter a field of an existing evidence item — cite it verbatim or not \
at all.

This is your OPENING case only. Do not write a rebuttal yet — you have not seen the Bear \
case. Leave any rebuttal field empty; you'll get a separate turn to respond after Bear \
has made its case."""


class LLMClient(Protocol):
    def generate_structured(
        self, *, system: str, user_message: str, output_model: type[BullCase]
    ) -> BullCase: ...


def bull_analyst(state: ResearchState, llm_client: LLMClient) -> dict:
    """LangGraph node: returns a partial state update with bull_case set."""
    findings_pool = collect_available_findings(state)
    case = llm_client.generate_structured(
        system=SYSTEM_PROMPT,
        user_message=_build_user_message(state, findings_pool),
        output_model=BullCase,
    )
    resolved_findings = resolve_case_evidence_against_pool(case.findings, collect_available_evidence(state))
    # A real LLM call filled these in on the opening case despite the
    # prompt instruction not to (nothing in BullCase's schema forbids it) —
    # enforce the invariant in Python rather than trusting the model: the
    # opening case can never legitimately carry a rebuttal yet.
    case = case.model_copy(
        update={"findings": resolved_findings, "rebuttal": None, "rebuttal_findings": []}
    )
    return {"bull_case": case}


def _build_user_message(state: ResearchState, findings_pool: list) -> str:
    return (
        f"Company: {state.ticker}\n\n"
        "Findings from upstream agents:\n"
        f"{format_available_findings(findings_pool)}\n\n"
        "Valuation:\n"
        f"{format_available_valuation(state.valuation_output)}"
    )
