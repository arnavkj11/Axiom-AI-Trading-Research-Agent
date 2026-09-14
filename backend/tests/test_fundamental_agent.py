from datetime import date

from app.agents.fundamental import fundamental_analyst
from app.agents.schemas import (
    FinancialMetricEvidence,
    Finding,
    FundamentalAnalysis,
    Stance,
)
from app.financials.models import MetricName, PeriodType
from app.financials.schemas import FinancialMetricRecord
from app.research.models import ResearchRunStatus
from app.research.schemas import ResearchState
from tests.fakes import FakeLLMClient


def _state() -> ResearchState:
    return ResearchState(
        research_run_id=1,
        company_id=7,
        ticker="AAPL",
        research_date=date(2026, 9, 6),
        status=ResearchRunStatus.FUNDAMENTAL_RUNNING,
        financial_metrics=[
            FinancialMetricRecord(
                id=101,
                metric_name=MetricName.OPERATING_MARGIN,
                period_end=date(2026, 6, 30),
                period_type=PeriodType.QUARTERLY,
                value=0.342,
            ),
            FinancialMetricRecord(
                id=102,
                metric_name=MetricName.REVENUE_GROWTH,
                period_end=date(2026, 6, 30),
                period_type=PeriodType.QUARTERLY,
                value=0.08,
            ),
        ],
    )


def _canned_analysis() -> FundamentalAnalysis:
    return FundamentalAnalysis(
        stance=Stance.BULLISH,
        confidence=0.81,
        findings=[
            Finding(
                claim="Operating margin expanded year-over-year",
                importance=0.88,
                evidence=[
                    FinancialMetricEvidence(
                        metric_id=101,
                        metric_name=MetricName.OPERATING_MARGIN,
                        period_end=date(2026, 6, 30),
                        value=0.342,
                    )
                ],
            )
        ],
    )


def test_fundamental_analyst_returns_state_update_with_llm_output():
    llm_client = FakeLLMClient(response=_canned_analysis())

    result = fundamental_analyst(_state(), llm_client)

    assert result == {"fundamental_analysis": _canned_analysis()}


def test_fundamental_analyst_requests_fundamental_analysis_output_model():
    llm_client = FakeLLMClient(response=_canned_analysis())

    fundamental_analyst(_state(), llm_client)

    assert llm_client.calls[0]["output_model"] is FundamentalAnalysis


def test_fundamental_analyst_prompt_includes_real_metric_ids_not_free_floating_claims():
    llm_client = FakeLLMClient(response=_canned_analysis())

    fundamental_analyst(_state(), llm_client)

    prompt = llm_client.calls[0]["user_message"]
    assert "metric_id=101" in prompt
    assert "operating_margin" in prompt
    assert "metric_id=102" in prompt
    assert "revenue_growth" in prompt


def test_fundamental_analyst_prompt_includes_ticker():
    llm_client = FakeLLMClient(response=_canned_analysis())

    fundamental_analyst(_state(), llm_client)

    assert "AAPL" in llm_client.calls[0]["user_message"]
