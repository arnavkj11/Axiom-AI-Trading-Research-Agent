from datetime import date

import pytest

from app.agents.bear import bear_analyst
from app.agents.debate_common import EvidenceNotInPoolError
from app.agents.schemas import (
    BearCase,
    FilingAnalysis,
    FilingChunkEvidence,
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

RISK_EVIDENCE = FinancialMetricEvidence(
    metric_id=2, metric_name=MetricName.DEBT, period_end=date(2026, 6, 30), value=500.0
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
            findings=[],
            risks=[Finding(claim="Debt is rising", importance=0.7, evidence=[RISK_EVIDENCE])],
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


def _bear_case_citing(evidence) -> BearCase:
    return BearCase(
        thesis="Rising leverage undermines the bull case.",
        confidence=0.65,
        findings=[Finding(claim="Debt is rising", importance=0.7, evidence=[evidence])],
    )


def test_bear_analyst_returns_state_update_with_llm_output():
    llm_client = FakeLLMClient(response=_bear_case_citing(RISK_EVIDENCE))

    result = bear_analyst(_state(), llm_client)

    assert result == {"bear_case": _bear_case_citing(RISK_EVIDENCE)}


def test_bear_analyst_requests_bear_case_output_model():
    llm_client = FakeLLMClient(response=_bear_case_citing(RISK_EVIDENCE))

    bear_analyst(_state(), llm_client)

    assert llm_client.calls[0]["output_model"] is BearCase


def test_bear_analyst_prompt_includes_upstream_findings_and_valuation():
    llm_client = FakeLLMClient(response=_bear_case_citing(RISK_EVIDENCE))

    bear_analyst(_state(), llm_client)

    prompt = llm_client.calls[0]["user_message"]
    assert "Debt is rising" in prompt
    assert "dcf_scenario" in prompt


def test_bear_analyst_rejects_case_citing_evidence_not_produced_upstream():
    llm_client = FakeLLMClient(response=_bear_case_citing(OTHER_EVIDENCE))

    with pytest.raises(EvidenceNotInPoolError):
        bear_analyst(_state(), llm_client)


def test_bear_analyst_clears_rebuttal_fields_even_if_the_model_populated_them():
    # See the mirrored bull.py regression test for the real-run context.
    case_with_premature_rebuttal = _bear_case_citing(RISK_EVIDENCE).model_copy(
        update={
            "rebuttal": "I anticipate the bull case will argue...",
            "rebuttal_findings": [
                Finding(claim="Pre-empting a rebuttal", importance=0.6, evidence=[RISK_EVIDENCE])
            ],
        }
    )
    llm_client = FakeLLMClient(response=case_with_premature_rebuttal)

    result = bear_analyst(_state(), llm_client)

    assert result["bear_case"].rebuttal is None
    assert result["bear_case"].rebuttal_findings == []


def test_bear_analyst_accepts_reciting_filing_evidence_with_whitespace_drift():
    # Regression test for a real failure from a live end-to-end run:
    # Filing Analyst cited a chunk with section="Item 1A.    Risk Factors"
    # (real filing-text whitespace), and when Bear re-cited that same
    # chunk_id, the model retyped the section/quote text with different
    # whitespace. The old exact-equality check rejected this as
    # fabrication even though chunk_id/filing_id/accession_number were
    # all correct.
    canonical_evidence = FilingChunkEvidence(
        chunk_id=519,
        filing_id=14,
        accession_number="0000320193-26-000020",
        section="Item 1A.    Risk Factors",
        quote="The Company is experiencing a period of supply constraints...",
    )
    state = _state().model_copy(
        update={
            "filing_analysis": FilingAnalysis(
                stance=Stance.NEUTRAL,
                confidence=0.5,
                findings=[
                    Finding(
                        claim="Supply constraints disclosed",
                        importance=0.7,
                        evidence=[canonical_evidence],
                    )
                ],
            )
        }
    )
    retyped_evidence = canonical_evidence.model_copy(
        update={
            "section": "Item 1A. Risk Factors",
            "quote": "The Company is experiencing a period of supply constraints...",
        }
    )
    llm_client = FakeLLMClient(response=_bear_case_citing(retyped_evidence))

    result = bear_analyst(state, llm_client)

    # Accepted, and canonicalized back to Filing Analyst's exact evidence —
    # not left as the model's retyped copy.
    assert result["bear_case"].findings[0].evidence[0] == canonical_evidence
