from datetime import date

import pytest

from app.agents.bull import bull_analyst
from app.agents.debate_common import EvidenceNotInPoolError
from app.agents.schemas import (
    BullCase,
    FilingAnalysis,
    FinancialMetricEvidence,
    Finding,
    FundamentalAnalysis,
    ScenarioValuation,
    Stance,
    ValuationOutput,
)
from app.financials.models import MetricName
from app.research.models import ResearchRunStatus
from app.research.schemas import ResearchState
from tests.fakes import FakeLLMClient

MARGIN_EVIDENCE = FinancialMetricEvidence(
    metric_id=1, metric_name=MetricName.OPERATING_MARGIN, period_end=date(2026, 6, 30), value=0.34
)
OTHER_EVIDENCE = FinancialMetricEvidence(
    metric_id=999, metric_name=MetricName.REVENUE_GROWTH, period_end=date(2026, 6, 30), value=0.5
)


def _state() -> ResearchState:
    return ResearchState(
        research_run_id=1,
        company_id=7,
        ticker="AAPL",
        research_date=date(2026, 9, 6),
        status=ResearchRunStatus.RUNNING,
        fundamental_analysis=FundamentalAnalysis(
            stance=Stance.BULLISH,
            confidence=0.8,
            findings=[
                Finding(claim="Margin expanded", importance=0.8, evidence=[MARGIN_EVIDENCE])
            ],
        ),
        filing_analysis=FilingAnalysis(stance=Stance.NEUTRAL, confidence=0.5, findings=[]),
        valuation_output=ValuationOutput(
            method="dcf_scenario",
            scenarios=[
                ScenarioValuation(scenario="base", fair_value_per_share=142.5, assumptions={})
            ],
            evidence=[],
            commentary="Reasonable base case.",
        ),
    )


def _bull_case_citing(evidence) -> BullCase:
    return BullCase(
        thesis="Margins are expanding faster than the market expects.",
        confidence=0.75,
        findings=[Finding(claim="Margin expanded", importance=0.8, evidence=[evidence])],
    )


def test_bull_analyst_returns_state_update_with_llm_output():
    llm_client = FakeLLMClient(response=_bull_case_citing(MARGIN_EVIDENCE))

    result = bull_analyst(_state(), llm_client)

    assert result == {"bull_case": _bull_case_citing(MARGIN_EVIDENCE)}


def test_bull_analyst_requests_bull_case_output_model():
    llm_client = FakeLLMClient(response=_bull_case_citing(MARGIN_EVIDENCE))

    bull_analyst(_state(), llm_client)

    assert llm_client.calls[0]["output_model"] is BullCase


def test_bull_analyst_prompt_includes_upstream_findings_and_valuation():
    llm_client = FakeLLMClient(response=_bull_case_citing(MARGIN_EVIDENCE))

    bull_analyst(_state(), llm_client)

    prompt = llm_client.calls[0]["user_message"]
    assert "Margin expanded" in prompt
    assert "dcf_scenario" in prompt


def test_bull_analyst_rejects_case_citing_evidence_not_produced_upstream():
    llm_client = FakeLLMClient(response=_bull_case_citing(OTHER_EVIDENCE))

    with pytest.raises(EvidenceNotInPoolError):
        bull_analyst(_state(), llm_client)


def test_bull_analyst_clears_rebuttal_fields_even_if_the_model_populated_them():
    # Regression test for a real failure from a live run: nothing in
    # BullCase's schema or the opening-case system prompt tells the model
    # that rebuttal/rebuttal_findings belong to a later step, so a real
    # Sonnet response filled them in on the OPENING case. bull_rebuttal's
    # RebuttalAlreadyRecordedError guard then (correctly) refused to
    # overwrite what looked like an already-recorded rebuttal, killing the
    # whole run. Fix: the opening case can never legitimately carry a
    # rebuttal yet, so bull_analyst enforces that in Python rather than
    # trusting the model to leave the fields empty.
    case_with_premature_rebuttal = _bull_case_citing(MARGIN_EVIDENCE).model_copy(
        update={
            "rebuttal": "I anticipate the bear case will focus on...",
            "rebuttal_findings": [
                Finding(claim="Pre-empting a rebuttal", importance=0.6, evidence=[MARGIN_EVIDENCE])
            ],
        }
    )
    llm_client = FakeLLMClient(response=case_with_premature_rebuttal)

    result = bull_analyst(_state(), llm_client)

    assert result["bull_case"].rebuttal is None
    assert result["bull_case"].rebuttal_findings == []
