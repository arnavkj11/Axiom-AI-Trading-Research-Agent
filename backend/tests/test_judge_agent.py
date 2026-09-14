from datetime import date

import pytest

from app.agents.debate_common import EvidenceNotInPoolError
from app.agents.judge import judge_agent
from app.agents.schemas import (
    BearCase,
    BullCase,
    FilingAnalysis,
    FinancialMetricEvidence,
    Finding,
    FundamentalAnalysis,
    JudgeVerdict,
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
BULL_REBUTTAL_EVIDENCE = FinancialMetricEvidence(
    metric_id=3, metric_name=MetricName.FREE_CASH_FLOW, period_end=date(2026, 6, 30), value=200.0
)
BEAR_REBUTTAL_EVIDENCE = FinancialMetricEvidence(
    metric_id=4, metric_name=MetricName.DEBT, period_end=date(2026, 6, 30), value=800.0
)
OTHER_EVIDENCE = FinancialMetricEvidence(
    metric_id=999, metric_name=MetricName.CASH, period_end=date(2026, 6, 30), value=50.0
)


def _state() -> ResearchState:
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
            rebuttal="Cash generation supports continued buybacks despite the slowdown.",
            rebuttal_findings=[
                Finding(claim="FCF remains strong", importance=0.6, evidence=[BULL_REBUTTAL_EVIDENCE])
            ],
        ),
        bear_case=BearCase(
            thesis="Growth is decelerating.",
            confidence=0.6,
            findings=[Finding(claim="Revenue growth is negative", importance=0.7, evidence=[BEAR_EVIDENCE])],
            rebuttal="Rising debt limits the runway for further buybacks.",
            rebuttal_findings=[
                Finding(claim="Debt has climbed", importance=0.6, evidence=[BEAR_REBUTTAL_EVIDENCE])
            ],
        ),
    )


def _verdict_citing(evidence) -> JudgeVerdict:
    return JudgeVerdict(
        stance=Stance.NEUTRAL,
        conviction=55,
        synthesis="Margin strength is offset by decelerating growth and rising leverage.",
        bull_summary="Margins expanding, strong FCF.",
        bear_summary="Growth decelerating, debt rising.",
        rebuttal_summary="Neither rebuttal fully resolves the other's concern.",
        key_findings=[Finding(claim="Balanced picture", importance=0.9, evidence=[evidence])],
    )


def test_judge_agent_returns_state_update_with_verdict():
    llm_client = FakeLLMClient(response=_verdict_citing(BULL_EVIDENCE))

    result = judge_agent(_state(), llm_client)

    assert result == {"judge_verdict": _verdict_citing(BULL_EVIDENCE)}


def test_judge_agent_requests_judge_verdict_output_model():
    llm_client = FakeLLMClient(response=_verdict_citing(BULL_EVIDENCE))

    judge_agent(_state(), llm_client)

    assert llm_client.calls[0]["output_model"] is JudgeVerdict


def test_judge_agent_prompt_includes_both_cases_and_both_rebuttals():
    llm_client = FakeLLMClient(response=_verdict_citing(BULL_EVIDENCE))

    judge_agent(_state(), llm_client)

    prompt = llm_client.calls[0]["user_message"]
    assert "Margins are expanding." in prompt
    assert "Growth is decelerating." in prompt
    assert "Cash generation supports continued buybacks despite the slowdown." in prompt
    assert "Rising debt limits the runway for further buybacks." in prompt


def test_judge_agent_accepts_verdict_citing_only_a_rebuttal_finding():
    # This is the case most likely to expose a pool-construction bug: the
    # cited evidence exists ONLY in bull_case.rebuttal_findings, never in
    # the opening findings.
    llm_client = FakeLLMClient(response=_verdict_citing(BULL_REBUTTAL_EVIDENCE))

    result = judge_agent(_state(), llm_client)

    assert result["judge_verdict"].key_findings[0].evidence[0] == BULL_REBUTTAL_EVIDENCE


def test_judge_agent_accepts_verdict_citing_bear_rebuttal_finding():
    llm_client = FakeLLMClient(response=_verdict_citing(BEAR_REBUTTAL_EVIDENCE))

    result = judge_agent(_state(), llm_client)

    assert result["judge_verdict"].key_findings[0].evidence[0] == BEAR_REBUTTAL_EVIDENCE


def test_judge_agent_rejects_verdict_citing_fabricated_evidence():
    llm_client = FakeLLMClient(response=_verdict_citing(OTHER_EVIDENCE))

    with pytest.raises(EvidenceNotInPoolError):
        judge_agent(_state(), llm_client)


def test_judge_agent_requires_both_cases_present():
    state = _state().model_copy(update={"bear_case": None})
    llm_client = FakeLLMClient(response=_verdict_citing(BULL_EVIDENCE))

    with pytest.raises(ValueError):
        judge_agent(state, llm_client)
