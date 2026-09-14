"""Valuation Analyst agent — a LangGraph node.

Narrow by design (CLAUDE.md Rule 1): the LLM only chooses bear/base/bull
DCF assumptions and gives a brief rationale for them. It never computes a
fair value itself — run_scenario_analysis (deterministic Python, from
app/valuation/calculations.py) does that arithmetic. See
tests/test_valuation_agent.py for a test that proves this by calling
run_dcf directly with the model's chosen assumptions and asserting the
node's output matches exactly.

The current share price is deliberately kept OUT of this agent's prompt,
even though the run knows it. Shown the market price, a model tends to
drift toward assumptions that reproduce it — yielding a valuation that
looks independent but has quietly been reverse-engineered from the quote,
which Bull, Bear and Judge would then all inherit as if it were evidence.
The DCF is only worth computing if it can disagree with the market, so
price is injected into the *result* afterwards instead. Bull, Bear and
Judge do see it — that's where value-versus-price belongs.
tests/test_price_in_debate.py guards this boundary.
"""

from typing import Protocol

from pydantic import BaseModel

from app.financials.models import MetricName
from app.financials.schemas import FinancialMetricRecord
from app.research.schemas import ResearchState
from app.valuation.calculations import DCFAssumptions, ValuationOutput, run_scenario_analysis

SYSTEM_PROMPT = """You are Axiom's Valuation Analyst agent, part of a multi-agent equity \
research platform.

Choose reasonable bear/base/bull DCF assumptions (growth_rate, years, discount_rate, \
terminal_growth_rate) for the company described below, given its most recent free cash \
flow. terminal_growth_rate must be less than discount_rate in every scenario. Give a \
brief rationale explaining your reasoning for the assumptions you chose across the three \
scenarios.

You choose assumptions only. You never compute a fair value, present value, or any other \
number yourself — a separate deterministic calculation does that."""


class ScenarioAssumptionsChoice(BaseModel):
    bear: DCFAssumptions
    base: DCFAssumptions
    bull: DCFAssumptions
    rationale: str


class LLMClient(Protocol):
    def generate_structured(
        self, *, system: str, user_message: str, output_model: type[ScenarioAssumptionsChoice]
    ) -> ScenarioAssumptionsChoice: ...


class ValuationInputsMissingError(RuntimeError):
    """ResearchState.financial_metrics is missing a metric the DCF requires."""


def valuation_analyst(state: ResearchState, llm_client: LLMClient) -> dict:
    """LangGraph node: returns a partial state update with valuation_output set."""
    base_fcf, shares_outstanding, net_cash = _extract_dcf_inputs(state)

    choice = llm_client.generate_structured(
        system=SYSTEM_PROMPT,
        user_message=_build_user_message(state, base_fcf),
        output_model=ScenarioAssumptionsChoice,
    )

    output: ValuationOutput = run_scenario_analysis(
        base_fcf=base_fcf,
        shares_outstanding=shares_outstanding,
        bear_assumptions=choice.bear,
        base_assumptions=choice.base,
        bull_assumptions=choice.bull,
        research_run_id=state.research_run_id,
        net_cash=net_cash,
        # Injected only *after* the model has committed to its assumptions
        # above — see this module's docstring on why it never reaches the
        # prompt.
        current_price=state.current_price,
    )
    output = output.model_copy(update={"commentary": choice.rationale})
    return {"valuation_output": output}


def _extract_dcf_inputs(state: ResearchState) -> tuple[float, float, float]:
    base_fcf = _latest_metric_value(state.financial_metrics, MetricName.FREE_CASH_FLOW)
    shares_outstanding = _latest_metric_value(state.financial_metrics, MetricName.SHARE_COUNT)
    if base_fcf is None or shares_outstanding is None:
        raise ValuationInputsMissingError(
            "ResearchState.financial_metrics must include free_cash_flow and share_count"
        )
    cash = _latest_metric_value(state.financial_metrics, MetricName.CASH) or 0.0
    debt = _latest_metric_value(state.financial_metrics, MetricName.DEBT) or 0.0
    return base_fcf, shares_outstanding, cash - debt


def _latest_metric_value(
    metrics: list[FinancialMetricRecord], metric_name: MetricName
) -> float | None:
    candidates = [m for m in metrics if m.metric_name == metric_name]
    if not candidates:
        return None
    return max(candidates, key=lambda m: m.period_end).value


def _build_user_message(state: ResearchState, base_fcf: float) -> str:
    return (
        f"Company: {state.ticker}\n"
        f"Most recent annual free cash flow: {base_fcf}\n\n"
        "Choose bear/base/bull DCF assumptions for this company."
    )
