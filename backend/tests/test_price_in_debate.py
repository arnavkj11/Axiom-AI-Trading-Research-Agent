"""How price reaches the agents.

The asymmetry here is deliberate: the Valuation Analyst must NOT see the
price while choosing DCF assumptions (it would anchor its growth/discount
rates to the market and produce a circular "independent" valuation), but
Bull, Bear and Judge MUST see it, because whether the stock is cheap is
the actual investment question.
"""

from datetime import date

from app.agents.debate_common import format_available_valuation
from app.agents.valuation import ScenarioAssumptionsChoice, valuation_analyst
from app.financials.models import MetricName, PeriodType
from app.financials.schemas import FinancialMetricRecord
from app.research.schemas import ResearchState
from app.valuation.calculations import DCFAssumptions
from tests.fakes import FakeLLMClient

PRICE = 180.42


def _metric(id_, name, value):
    return FinancialMetricRecord(
        id=id_,
        metric_name=name,
        period_end=date(2026, 6, 30),
        period_type=PeriodType.ANNUAL,
        value=value,
    )


def _state(**overrides) -> ResearchState:
    base = {
        "research_run_id": 1,
        "company_id": 7,
        "ticker": "AAPL",
        "research_date": date(2026, 9, 8),
        "financial_metrics": [
            _metric(1, MetricName.FREE_CASH_FLOW, 100.0),
            _metric(2, MetricName.SHARE_COUNT, 10.0),
        ],
    }
    return ResearchState(**{**base, **overrides})


def _choice() -> ScenarioAssumptionsChoice:
    return ScenarioAssumptionsChoice(
        bear=DCFAssumptions(growth_rate=0.03, years=5, discount_rate=0.10, terminal_growth_rate=0.02),
        base=DCFAssumptions(growth_rate=0.06, years=5, discount_rate=0.09, terminal_growth_rate=0.025),
        bull=DCFAssumptions(growth_rate=0.09, years=5, discount_rate=0.08, terminal_growth_rate=0.03),
        rationale="Steady growth.",
    )


def test_valuation_analyst_never_sees_the_price_in_its_prompt():
    # The anchoring guard. If the price leaks into this prompt, the model
    # can quietly reverse-engineer assumptions that land near the market
    # price, and the DCF stops being an independent opinion — which is the
    # only thing that makes it worth computing.
    llm_client = FakeLLMClient(_choice())

    valuation_analyst(_state(current_price=PRICE), llm_client)

    prompt = llm_client.calls[0]["user_message"] + llm_client.calls[0]["system"]
    assert "180.42" not in prompt
    assert "180" not in prompt


def test_valuation_output_still_carries_the_price():
    llm_client = FakeLLMClient(_choice())

    update = valuation_analyst(_state(current_price=PRICE), llm_client)

    assert update["valuation_output"].current_price == PRICE


def test_valuation_output_has_upside_once_a_price_is_known():
    llm_client = FakeLLMClient(_choice())

    update = valuation_analyst(_state(current_price=PRICE), llm_client)

    assert all(s.upside_pct is not None for s in update["valuation_output"].scenarios)


def test_valuation_output_has_no_upside_without_a_price():
    llm_client = FakeLLMClient(_choice())

    update = valuation_analyst(_state(), llm_client)

    assert all(s.upside_pct is None for s in update["valuation_output"].scenarios)


def test_debate_agents_are_shown_the_price_and_upside():
    # Bull/Bear/Judge all read valuation through this formatter, so this is
    # the single seam that decides whether the debate can reason about
    # value versus price at all.
    llm_client = FakeLLMClient(_choice())
    output = valuation_analyst(_state(current_price=PRICE), llm_client)["valuation_output"]

    rendered = format_available_valuation(output)

    assert "180.42" in rendered
    assert "upside" in rendered.lower()


def test_debate_agents_are_told_when_the_price_is_unknown():
    # Explicitly stated rather than silently absent, so the model doesn't
    # assume a price it was never given.
    llm_client = FakeLLMClient(_choice())
    output = valuation_analyst(_state(), llm_client)["valuation_output"]

    rendered = format_available_valuation(output)

    assert "unknown" in rendered.lower() or "no market price" in rendered.lower()
