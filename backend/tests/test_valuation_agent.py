from datetime import date

import pytest

from app.agents.valuation import (
    ScenarioAssumptionsChoice,
    ValuationInputsMissingError,
    valuation_analyst,
)
from app.financials.models import MetricName, PeriodType
from app.financials.schemas import FinancialMetricRecord
from app.research.models import ResearchRunStatus
from app.research.schemas import ResearchState
from app.valuation.calculations import DCFAssumptions, run_dcf
from tests.fakes import FakeLLMClient


def _metric(id_, name, value, period_end=date(2026, 6, 30)):
    return FinancialMetricRecord(
        id=id_, metric_name=name, period_end=period_end, period_type=PeriodType.ANNUAL, value=value
    )


def _state() -> ResearchState:
    return ResearchState(
        research_run_id=42,
        company_id=7,
        ticker="AAPL",
        research_date=date(2026, 9, 6),
        status=ResearchRunStatus.VALUATION_RUNNING,
        financial_metrics=[
            _metric(301, MetricName.FREE_CASH_FLOW, 100.0),
            _metric(302, MetricName.SHARE_COUNT, 1000.0),
            _metric(303, MetricName.CASH, 200.0),
            _metric(304, MetricName.DEBT, 50.0),
            # An older period for the same metrics — must be ignored in favor
            # of the most recent period_end.
            _metric(305, MetricName.FREE_CASH_FLOW, 10.0, period_end=date(2025, 6, 30)),
        ],
    )


def _canned_choice() -> ScenarioAssumptionsChoice:
    return ScenarioAssumptionsChoice(
        bear=DCFAssumptions(growth_rate=0.04, years=5, discount_rate=0.12, terminal_growth_rate=0.02),
        base=DCFAssumptions(growth_rate=0.08, years=5, discount_rate=0.10, terminal_growth_rate=0.025),
        bull=DCFAssumptions(growth_rate=0.12, years=5, discount_rate=0.09, terminal_growth_rate=0.03),
        rationale="Base case assumes steady mid-single-digit growth given recent trends; "
        "bear/bull bracket macro and competitive risk.",
    )


def test_valuation_analyst_requests_scenario_assumptions_choice_output_model():
    llm_client = FakeLLMClient(response=_canned_choice())

    valuation_analyst(_state(), llm_client)

    assert llm_client.calls[0]["output_model"] is ScenarioAssumptionsChoice


def test_valuation_analyst_dcf_output_matches_calling_run_dcf_directly():
    # The point of this test: the LLM only chose assumptions (DCFAssumptions),
    # never a number. Every fair_value_per_share in the result must equal
    # calling run_dcf directly with those same assumptions and the same
    # base_fcf/shares_outstanding/net_cash pulled from state — proving the
    # arithmetic ran in Python, not the model.
    choice = _canned_choice()
    llm_client = FakeLLMClient(response=choice)

    result = valuation_analyst(_state(), llm_client)
    output = result["valuation_output"]

    base_fcf = 100.0
    shares_outstanding = 1000.0
    net_cash = 200.0 - 50.0

    for label, assumptions in (("bear", choice.bear), ("base", choice.base), ("bull", choice.bull)):
        expected = run_dcf(
            base_fcf=base_fcf,
            shares_outstanding=shares_outstanding,
            assumptions=assumptions,
            net_cash=net_cash,
        )
        actual = next(s for s in output.scenarios if s.scenario == label).fair_value_per_share
        assert actual == pytest.approx(expected)


def test_valuation_analyst_uses_most_recent_period_for_each_metric():
    # base_fcf must come from the 2026-06-30 period (100.0), not the older
    # 2025-06-30 period (10.0) also present in state.
    choice = _canned_choice()
    llm_client = FakeLLMClient(response=choice)

    result = valuation_analyst(_state(), llm_client)
    output = result["valuation_output"]

    base_case = next(s for s in output.scenarios if s.scenario == "base")
    expected = run_dcf(
        base_fcf=100.0, shares_outstanding=1000.0, assumptions=choice.base, net_cash=150.0
    )
    assert base_case.fair_value_per_share == pytest.approx(expected)


def test_valuation_analyst_attaches_llm_rationale_as_commentary():
    choice = _canned_choice()
    llm_client = FakeLLMClient(response=choice)

    result = valuation_analyst(_state(), llm_client)

    assert result["valuation_output"].commentary == choice.rationale


def test_valuation_analyst_evidence_cites_research_run_id():
    choice = _canned_choice()
    llm_client = FakeLLMClient(response=choice)

    result = valuation_analyst(_state(), llm_client)

    output = result["valuation_output"]
    assert len(output.evidence) == 3
    assert all(e.research_run_id == 42 for e in output.evidence)


def test_valuation_analyst_raises_when_free_cash_flow_missing():
    state = ResearchState(
        research_run_id=42,
        company_id=7,
        ticker="AAPL",
        research_date=date(2026, 9, 6),
        financial_metrics=[_metric(302, MetricName.SHARE_COUNT, 1000.0)],
    )
    llm_client = FakeLLMClient(response=_canned_choice())

    with pytest.raises(ValuationInputsMissingError):
        valuation_analyst(state, llm_client)


def test_valuation_analyst_raises_when_share_count_missing():
    state = ResearchState(
        research_run_id=42,
        company_id=7,
        ticker="AAPL",
        research_date=date(2026, 9, 6),
        financial_metrics=[_metric(301, MetricName.FREE_CASH_FLOW, 100.0)],
    )
    llm_client = FakeLLMClient(response=_canned_choice())

    with pytest.raises(ValuationInputsMissingError):
        valuation_analyst(state, llm_client)
