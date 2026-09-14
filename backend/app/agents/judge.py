"""Judge agent — the final LangGraph node before the graph ends.

Reads the full debate: Fundamental/Filing/Valuation findings, both
opening cases, and both rebuttals, and produces the final JudgeVerdict
(stance, conviction, synthesis). Runs only after both bull_rebuttal and
bear_rebuttal complete (LangGraph fan-in barrier — see orchestrator.py),
so both rebuttal fields are guaranteed populated by the time this runs.
"""

from typing import Protocol

from app.agents.debate_common import (
    collect_full_debate_evidence_pool,
    format_available_findings,
    format_available_valuation,
    resolve_case_evidence_against_pool,
)
from app.agents.schemas import JudgeVerdict
from app.research.schemas import ResearchState

SYSTEM_PROMPT = """You are Axiom's Judge agent, part of a multi-agent equity research \
platform.

You have read the Fundamental, Filing, and Valuation agents' findings, and watched the \
Bull and Bear agents debate — including one rebuttal round each. Weigh the full debate \
and produce a final stance (BULLISH/BEARISH/NEUTRAL), a conviction score (0-100), and a \
synthesis report, including a summary of how the rebuttal round changed (or didn't \
change) the picture.

Every finding in key_findings, risks, or catalysts with importance >= 0.5 MUST cite \
evidence copied exactly (all fields unchanged) from one of the evidence items produced \
during this research run, listed below — including evidence that appears only in a \
rebuttal. Never invent new evidence."""


class LLMClient(Protocol):
    def generate_structured(
        self, *, system: str, user_message: str, output_model: type[JudgeVerdict]
    ) -> JudgeVerdict: ...


def judge_agent(state: ResearchState, llm_client: LLMClient) -> dict:
    """LangGraph node: returns a partial state update with judge_verdict set."""
    if state.bull_case is None or state.bear_case is None:
        raise ValueError("judge_agent requires both bull_case and bear_case to be set")

    verdict = llm_client.generate_structured(
        system=SYSTEM_PROMPT,
        user_message=_build_user_message(state),
        output_model=JudgeVerdict,
    )

    pool = collect_full_debate_evidence_pool(state)
    resolved = resolve_case_evidence_against_pool(
        verdict.key_findings + verdict.risks + verdict.catalysts, pool
    )
    n_key, n_risks = len(verdict.key_findings), len(verdict.risks)
    verdict = verdict.model_copy(
        update={
            "key_findings": resolved[:n_key],
            "risks": resolved[n_key : n_key + n_risks],
            "catalysts": resolved[n_key + n_risks :],
        }
    )

    return {"judge_verdict": verdict}


def _build_user_message(state: ResearchState) -> str:
    fundamental_findings = state.fundamental_analysis.findings if state.fundamental_analysis else []
    filing_findings = state.filing_analysis.findings if state.filing_analysis else []
    return (
        f"Company: {state.ticker}\n\n"
        "Fundamental findings:\n"
        f"{format_available_findings(fundamental_findings)}\n\n"
        "Filing findings:\n"
        f"{format_available_findings(filing_findings)}\n\n"
        "Valuation:\n"
        f"{format_available_valuation(state.valuation_output)}\n\n"
        "Bull case (opening):\n"
        f"Thesis: {state.bull_case.thesis}\n"
        f"{format_available_findings(state.bull_case.findings)}\n"
        "Bull rebuttal:\n"
        f"{state.bull_case.rebuttal}\n"
        f"{format_available_findings(state.bull_case.rebuttal_findings)}\n\n"
        "Bear case (opening):\n"
        f"Thesis: {state.bear_case.thesis}\n"
        f"{format_available_findings(state.bear_case.findings)}\n"
        "Bear rebuttal:\n"
        f"{state.bear_case.rebuttal}\n"
        f"{format_available_findings(state.bear_case.rebuttal_findings)}"
    )
