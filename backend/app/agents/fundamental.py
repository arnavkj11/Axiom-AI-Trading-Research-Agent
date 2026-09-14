"""Fundamental Analyst agent — a LangGraph node.

Reasons over the company's structured financial data and returns a
FundamentalAnalysis whose material findings cite real financial_metrics
rows (CLAUDE.md Rule: "no agent communicates in free-form prose", every
material Finding needs Evidence). The LLM never sees or invents metric
ids on its own — the prompt lists only the ids that actually exist in
ResearchState, and the FundamentalAnalysis schema's own validator rejects
a material finding with no evidence at all.
"""

from typing import Protocol

from app.agents.schemas import FundamentalAnalysis
from app.research.schemas import ResearchState

SYSTEM_PROMPT = """You are Axiom's Fundamental Analyst agent, part of a multi-agent \
equity research platform.

Analyze the company's quantitative financial health: growth, profitability, margin \
trends, cash flow, and balance sheet strength, using only the financial metrics \
provided below.

Every finding with importance >= 0.5 MUST cite at least one piece of evidence with \
evidence_type "financial_metric", using one of the metric_id values given in the \
input verbatim. Never invent a metric_id that isn't listed. Do not make claims that \
aren't grounded in the provided data."""


class LLMClient(Protocol):
    def generate_structured(
        self, *, system: str, user_message: str, output_model: type[FundamentalAnalysis]
    ) -> FundamentalAnalysis: ...


def fundamental_analyst(state: ResearchState, llm_client: LLMClient) -> dict:
    """LangGraph node: returns a partial state update with fundamental_analysis set."""
    analysis = llm_client.generate_structured(
        system=SYSTEM_PROMPT,
        user_message=_build_user_message(state),
        output_model=FundamentalAnalysis,
    )
    return {"fundamental_analysis": analysis}


def _build_user_message(state: ResearchState) -> str:
    lines = [f"Company: {state.ticker}", "", "Financial metrics (cite by metric_id):"]
    for metric in state.financial_metrics:
        lines.append(
            f"- metric_id={metric.id} {metric.metric_name.value} "
            f"({metric.period_type.value}, period_end={metric.period_end.isoformat()}): "
            f"{metric.value}"
        )
    return "\n".join(lines)
