import pytest
from pydantic import ValidationError

from app.agents.schemas import (
    BearCase,
    BullCase,
    FinancialMetricEvidence,
    Finding,
)
from app.financials.models import MetricName


def _metric_evidence() -> FinancialMetricEvidence:
    return FinancialMetricEvidence(
        metric_id=1,
        metric_name=MetricName.OPERATING_MARGIN,
        period_end="2026-06-30",
        value=0.342,
    )


def test_finding_rejects_material_importance_without_evidence():
    with pytest.raises(ValidationError):
        Finding(claim="Operating margin expanded year-over-year", importance=0.88, evidence=[])


def test_finding_allows_low_importance_without_evidence():
    finding = Finding(claim="Minor, immaterial observation", importance=0.1, evidence=[])
    assert finding.evidence == []


def test_finding_allows_material_importance_with_evidence():
    finding = Finding(
        claim="Operating margin expanded year-over-year",
        importance=0.88,
        evidence=[_metric_evidence()],
    )
    assert finding.evidence[0].metric_id == 1


def test_evidence_discriminated_union_rejects_mismatched_type_and_fields():
    # evidence_type says financial_metric, but the payload carries filing_chunk
    # fields instead of the required metric_id/metric_name/period_end/value.
    with pytest.raises(ValidationError):
        Finding(
            claim="New litigation risk disclosed",
            importance=0.9,
            evidence=[
                {
                    "evidence_type": "financial_metric",
                    "chunk_id": 42,
                    "filing_id": 7,
                    "accession_number": "0000320193-26-000012",
                    "quote": "The Company is subject to litigation...",
                }
            ],
        )


def test_bull_case_rebuttal_defaults_to_none_pre_debate():
    bull = BullCase(
        thesis="Strong secular growth with expanding margins.",
        confidence=0.75,
        findings=[],
    )
    assert bull.rebuttal is None
    assert bull.rebuttal_findings == []


def test_bear_case_rebuttal_defaults_to_none_pre_debate():
    bear = BearCase(
        thesis="Growth is decelerating faster than the market expects.",
        confidence=0.6,
        findings=[],
    )
    assert bear.rebuttal is None
    assert bear.rebuttal_findings == []
