from datetime import date

import pytest

from app.agents.bear_rebuttal import bear_rebuttal
from app.agents.debate_common import EvidenceNotInPoolError, RebuttalAlreadyRecordedError, RebuttalResponse
from app.agents.schemas import (
    BearCase,
    BullCase,
    FilingAnalysis,
    FinancialMetricEvidence,
    Finding,
    FundamentalAnalysis,
    Stance,
)
from app.financials.models import MetricName
from app.research.models import ResearchRunStatus
from app.research.schemas import ResearchState
from tests.fakes import FakeLLMClient

BULL_EVIDENCE = FinancialMetricEvidence(
    metric_id=1, metric_name=MetricName.OPERATING_MARGIN, period_end=date(2026, 6, 30), value=0.34
)
BEAR_EVIDENCE = FinancialMetricEvidence(
    metric_id=2, metric_name=MetricName.REVENUE_GROWTH, period_end=date(2026, 6, 30), value=-0.05
)
OTHER_EVIDENCE = FinancialMetricEvidence(
    metric_id=999, metric_name=MetricName.DEBT, period_end=date(2026, 6, 30), value=500.0
)


def _state(bear_rebuttal_already=None) -> ResearchState:
    return ResearchState(
        research_run_id=1,
        company_id=7,
        ticker="AAPL",
        research_date=date(2026, 9, 6),
        status=ResearchRunStatus.RUNNING,
        fundamental_analysis=FundamentalAnalysis(stance=Stance.BULLISH, confidence=0.8, findings=[]),
        filing_analysis=FilingAnalysis(stance=Stance.NEUTRAL, confidence=0.5, findings=[]),
        bull_case=BullCase(
            thesis="Margins are expanding.",
            confidence=0.75,
            findings=[Finding(claim="Margin expanded", importance=0.8, evidence=[BULL_EVIDENCE])],
        ),
        bear_case=BearCase(
            thesis="Growth is decelerating.",
            confidence=0.6,
            findings=[Finding(claim="Revenue growth is negative", importance=0.7, evidence=[BEAR_EVIDENCE])],
            rebuttal=bear_rebuttal_already,
        ),
    )


def _response(evidence) -> RebuttalResponse:
    return RebuttalResponse(
        rebuttal="Margin expansion won't offset decelerating top-line growth.",
        rebuttal_findings=[
            Finding(claim="Margin gains are not enough to offset the slowdown", importance=0.6, evidence=[evidence])
        ],
    )


def test_bear_rebuttal_returns_updated_bear_case_with_rebuttal_set():
    llm_client = FakeLLMClient(response=_response(BEAR_EVIDENCE))

    result = bear_rebuttal(_state(), llm_client)

    updated = result["bear_case"]
    assert updated.rebuttal == "Margin expansion won't offset decelerating top-line growth."
    assert updated.rebuttal_findings == _response(BEAR_EVIDENCE).rebuttal_findings


def test_bear_rebuttal_preserves_original_thesis_and_findings():
    llm_client = FakeLLMClient(response=_response(BEAR_EVIDENCE))

    result = bear_rebuttal(_state(), llm_client)

    updated = result["bear_case"]
    assert updated.thesis == "Growth is decelerating."
    assert updated.findings == _state().bear_case.findings


def test_bear_rebuttal_requests_rebuttal_response_output_model():
    llm_client = FakeLLMClient(response=_response(BEAR_EVIDENCE))

    bear_rebuttal(_state(), llm_client)

    assert llm_client.calls[0]["output_model"] is RebuttalResponse


def test_bear_rebuttal_prompt_includes_bulls_opening_case():
    llm_client = FakeLLMClient(response=_response(BEAR_EVIDENCE))

    bear_rebuttal(_state(), llm_client)

    prompt = llm_client.calls[0]["user_message"]
    assert "Margins are expanding." in prompt
    assert "Margin expanded" in prompt


def test_bear_rebuttal_allows_citing_bulls_evidence():
    llm_client = FakeLLMClient(response=_response(BULL_EVIDENCE))

    result = bear_rebuttal(_state(), llm_client)

    assert result["bear_case"].rebuttal_findings[0].evidence[0] == BULL_EVIDENCE


def test_bear_rebuttal_rejects_fabricated_evidence():
    llm_client = FakeLLMClient(response=_response(OTHER_EVIDENCE))

    with pytest.raises(EvidenceNotInPoolError):
        bear_rebuttal(_state(), llm_client)


def test_bear_rebuttal_raises_when_rebuttal_already_recorded():
    llm_client = FakeLLMClient(response=_response(BEAR_EVIDENCE))

    with pytest.raises(RebuttalAlreadyRecordedError):
        bear_rebuttal(_state(bear_rebuttal_already="Already rebutted once."), llm_client)


def test_bear_rebuttal_does_not_call_llm_when_rebuttal_already_recorded():
    llm_client = FakeLLMClient(response=_response(BEAR_EVIDENCE))

    with pytest.raises(RebuttalAlreadyRecordedError):
        bear_rebuttal(_state(bear_rebuttal_already="Already rebutted once."), llm_client)

    assert llm_client.calls == []
