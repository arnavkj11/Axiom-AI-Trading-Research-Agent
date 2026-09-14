from datetime import date

import pytest

from app.agents.bull_rebuttal import bull_rebuttal
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


def _state(bull_rebuttal_already=None) -> ResearchState:
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
            rebuttal=bull_rebuttal_already,
        ),
        bear_case=BearCase(
            thesis="Growth is decelerating.",
            confidence=0.6,
            findings=[Finding(claim="Revenue growth is negative", importance=0.7, evidence=[BEAR_EVIDENCE])],
        ),
    )


def _response(evidence) -> RebuttalResponse:
    return RebuttalResponse(
        rebuttal="The revenue dip is one-time and margin trends dominate long term.",
        rebuttal_findings=[
            Finding(claim="Revenue dip is one-time", importance=0.6, evidence=[evidence])
        ],
    )


def test_bull_rebuttal_returns_updated_bull_case_with_rebuttal_set():
    llm_client = FakeLLMClient(response=_response(BULL_EVIDENCE))

    result = bull_rebuttal(_state(), llm_client)

    updated = result["bull_case"]
    assert updated.rebuttal == "The revenue dip is one-time and margin trends dominate long term."
    assert updated.rebuttal_findings == _response(BULL_EVIDENCE).rebuttal_findings


def test_bull_rebuttal_preserves_original_thesis_and_findings():
    llm_client = FakeLLMClient(response=_response(BULL_EVIDENCE))

    result = bull_rebuttal(_state(), llm_client)

    updated = result["bull_case"]
    assert updated.thesis == "Margins are expanding."
    assert updated.findings == _state().bull_case.findings


def test_bull_rebuttal_requests_rebuttal_response_output_model():
    llm_client = FakeLLMClient(response=_response(BULL_EVIDENCE))

    bull_rebuttal(_state(), llm_client)

    assert llm_client.calls[0]["output_model"] is RebuttalResponse


def test_bull_rebuttal_prompt_includes_bears_opening_case():
    llm_client = FakeLLMClient(response=_response(BULL_EVIDENCE))

    bull_rebuttal(_state(), llm_client)

    prompt = llm_client.calls[0]["user_message"]
    assert "Growth is decelerating." in prompt
    assert "Revenue growth is negative" in prompt


def test_bull_rebuttal_allows_citing_bears_evidence():
    llm_client = FakeLLMClient(response=_response(BEAR_EVIDENCE))

    result = bull_rebuttal(_state(), llm_client)

    assert result["bull_case"].rebuttal_findings[0].evidence[0] == BEAR_EVIDENCE


def test_bull_rebuttal_rejects_fabricated_evidence():
    llm_client = FakeLLMClient(response=_response(OTHER_EVIDENCE))

    with pytest.raises(EvidenceNotInPoolError):
        bull_rebuttal(_state(), llm_client)


def test_bull_rebuttal_raises_when_rebuttal_already_recorded():
    llm_client = FakeLLMClient(response=_response(BULL_EVIDENCE))

    with pytest.raises(RebuttalAlreadyRecordedError):
        bull_rebuttal(_state(bull_rebuttal_already="Already rebutted once."), llm_client)


def test_bull_rebuttal_does_not_call_llm_when_rebuttal_already_recorded():
    llm_client = FakeLLMClient(response=_response(BULL_EVIDENCE))

    with pytest.raises(RebuttalAlreadyRecordedError):
        bull_rebuttal(_state(bull_rebuttal_already="Already rebutted once."), llm_client)

    assert llm_client.calls == []
