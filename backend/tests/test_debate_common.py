from datetime import date

import pytest

from app.agents.debate_common import (
    EvidenceNotInPoolError,
    collect_available_evidence,
    collect_available_findings,
    collect_full_debate_evidence_pool,
    collect_rebuttal_evidence_pool,
    resolve_case_evidence_against_pool,
)
from app.agents.schemas import (
    BearCase,
    BullCase,
    FilingChunkEvidence,
    FinancialMetricEvidence,
    FilingAnalysis,
    Finding,
    FundamentalAnalysis,
    ScenarioValuation,
    Stance,
    ValuationOutput,
    ValuationOutputEvidence,
)
from app.financials.models import MetricName
from app.research.models import ResearchRunStatus
from app.research.schemas import ResearchState


def _metric_evidence(metric_id=1) -> FinancialMetricEvidence:
    return FinancialMetricEvidence(
        metric_id=metric_id,
        metric_name=MetricName.OPERATING_MARGIN,
        period_end=date(2026, 6, 30),
        value=0.34,
    )


def _chunk_evidence(chunk_id=1) -> FilingChunkEvidence:
    return FilingChunkEvidence(
        chunk_id=chunk_id,
        filing_id=1,
        accession_number="0000320193-26-000012",
        section="Item 1A. Risk Factors",
        quote="We face significant competition.",
    )


def _valuation_evidence() -> ValuationOutputEvidence:
    return ValuationOutputEvidence(
        research_run_id=1,
        function_name="run_dcf",
        output_field="scenarios.base.fair_value_per_share",
        value=142.5,
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
                Finding(claim="Margin expanded", importance=0.8, evidence=[_metric_evidence(1)])
            ],
            risks=[Finding(claim="Rising costs", importance=0.6, evidence=[_metric_evidence(2)])],
        ),
        filing_analysis=FilingAnalysis(
            stance=Stance.NEUTRAL,
            confidence=0.6,
            findings=[
                Finding(claim="New risk disclosed", importance=0.6, evidence=[_chunk_evidence(1)])
            ],
        ),
        valuation_output=ValuationOutput(
            method="dcf_scenario",
            scenarios=[
                ScenarioValuation(scenario="base", fair_value_per_share=142.5, assumptions={})
            ],
            evidence=[_valuation_evidence()],
            commentary="Base case looks reasonable.",
        ),
    )


def test_collect_available_findings_includes_fundamental_and_filing_findings_and_risks():
    findings = collect_available_findings(_state())
    claims = {f.claim for f in findings}
    assert claims == {"Margin expanded", "Rising costs", "New risk disclosed"}


def test_collect_available_findings_handles_missing_upstream_analyses():
    state = ResearchState(
        research_run_id=1,
        company_id=7,
        ticker="AAPL",
        research_date=date(2026, 9, 6),
    )
    assert collect_available_findings(state) == []


def test_collect_available_evidence_includes_finding_evidence_and_valuation_evidence():
    evidence = collect_available_evidence(_state())
    assert _metric_evidence(1) in evidence
    assert _metric_evidence(2) in evidence
    assert _chunk_evidence(1) in evidence
    assert _valuation_evidence() in evidence
    assert len(evidence) == 4


def test_resolve_case_evidence_against_pool_passes_when_evidence_matches_pool():
    pool = [_metric_evidence(1)]
    findings = [Finding(claim="Reused claim", importance=0.7, evidence=[_metric_evidence(1)])]

    resolved = resolve_case_evidence_against_pool(findings, pool)

    assert resolved[0].evidence == [_metric_evidence(1)]


def test_resolve_case_evidence_against_pool_rejects_evidence_not_in_pool():
    pool = [_metric_evidence(1)]
    fabricated = Finding(claim="Made up claim", importance=0.7, evidence=[_metric_evidence(999)])

    with pytest.raises(EvidenceNotInPoolError):
        resolve_case_evidence_against_pool([fabricated], pool)


def test_resolve_case_evidence_against_pool_rejects_evidence_with_altered_identity_field():
    # metric_id is the identity field for FinancialMetricEvidence — an
    # evidence item with a metric_id absent from the pool is a real
    # mismatch (not the kind of harmless retyping this fix accommodates).
    pool = [_metric_evidence(1)]
    altered_identity = _metric_evidence(2)  # different metric_id -> not in pool
    finding = Finding(claim="Altered claim", importance=0.7, evidence=[altered_identity])

    with pytest.raises(EvidenceNotInPoolError):
        resolve_case_evidence_against_pool([finding], pool)


def test_resolve_case_evidence_against_pool_canonicalizes_whitespace_drift_in_free_text_fields():
    # The real bug this fixes: a live run had Bear re-cite a FilingChunkEvidence
    # whose `section` text had different whitespace than what Filing Analyst
    # originally produced (models don't always reproduce text byte-for-byte,
    # even when told to copy verbatim), and the old exact-equality check
    # rejected it as fabricated even though the chunk_id/filing_id/
    # accession_number identity was completely correct.
    canonical = _chunk_evidence(1)
    pool = [canonical]
    retyped_with_whitespace_drift = canonical.model_copy(
        update={"section": "Item 1A.    Risk Factors", "quote": "We  face significant   competition."}
    )
    finding = Finding(
        claim="New competitive risk", importance=0.7, evidence=[retyped_with_whitespace_drift]
    )

    resolved = resolve_case_evidence_against_pool([finding], pool)

    # Resolved evidence is replaced with the pool's canonical object, not
    # the model's retyped copy — the evidence trail always matches the
    # DB-backed source exactly.
    assert resolved[0].evidence == [canonical]
    assert resolved[0].evidence[0].section == "Item 1A. Risk Factors"


def test_resolve_case_evidence_against_pool_canonicalizes_valuation_output_evidence():
    canonical = _valuation_evidence()
    pool = [canonical]
    retyped = canonical.model_copy(update={"assumptions": {"growth_rate": 0.08}})
    finding = Finding(claim="Base case is reasonable", importance=0.7, evidence=[retyped])

    resolved = resolve_case_evidence_against_pool([finding], pool)

    assert resolved[0].evidence == [canonical]


def _bear_evidence() -> FinancialMetricEvidence:
    return _metric_evidence(3)


def _state_with_debate() -> ResearchState:
    state = _state()
    bull_rebuttal_evidence = _metric_evidence(4)
    bear_rebuttal_evidence = _metric_evidence(5)
    return state.model_copy(
        update={
            "bull_case": BullCase(
                thesis="Margins are expanding.",
                confidence=0.75,
                findings=[
                    Finding(claim="Margin expanded", importance=0.8, evidence=[_metric_evidence(1)])
                ],
                rebuttal="Bear overstates cost pressure.",
                rebuttal_findings=[
                    Finding(
                        claim="Cost pressure is transitory",
                        importance=0.7,
                        evidence=[bull_rebuttal_evidence],
                    )
                ],
            ),
            "bear_case": BearCase(
                thesis="Competitive pressure is rising.",
                confidence=0.6,
                findings=[
                    Finding(claim="New competitor entered", importance=0.7, evidence=[_bear_evidence()])
                ],
                rebuttal="Margin expansion won't survive new competition.",
                rebuttal_findings=[
                    Finding(
                        claim="Competitor is undercutting on price",
                        importance=0.7,
                        evidence=[bear_rebuttal_evidence],
                    )
                ],
            ),
        }
    )


def test_collect_rebuttal_evidence_pool_includes_original_pool_and_both_sides_opening_findings():
    state = _state().model_copy(
        update={
            "bull_case": BullCase(
                thesis="Margins are expanding.",
                confidence=0.75,
                findings=[
                    Finding(claim="Margin expanded", importance=0.8, evidence=[_metric_evidence(1)])
                ],
            ),
            "bear_case": BearCase(
                thesis="Competitive pressure is rising.",
                confidence=0.6,
                findings=[
                    Finding(claim="New competitor entered", importance=0.7, evidence=[_bear_evidence()])
                ],
            ),
        }
    )

    pool = collect_rebuttal_evidence_pool(state)

    assert _metric_evidence(1) in pool  # from the original upstream pool (fundamental)
    assert _valuation_evidence() in pool  # from the original upstream pool (valuation)
    assert _bear_evidence() in pool  # from the opposing side's (bear's) opening findings


def test_collect_full_debate_evidence_pool_includes_both_sides_findings_and_rebuttal_findings():
    state = _state_with_debate()

    pool = collect_full_debate_evidence_pool(state)

    assert _metric_evidence(1) in pool  # bull opening finding
    assert _bear_evidence() in pool  # bear opening finding
    assert _metric_evidence(4) in pool  # bull rebuttal finding
    assert _metric_evidence(5) in pool  # bear rebuttal finding


def test_full_debate_evidence_pool_validates_a_verdict_citing_only_a_rebuttal_finding():
    # The most likely place for a subtle pool-construction bug: evidence
    # that exists ONLY inside a rebuttal_findings list (never in the
    # opening findings) must still validate successfully against the
    # widened pool the Judge uses.
    state = _state_with_debate()
    pool = collect_full_debate_evidence_pool(state)

    rebuttal_only_evidence = _metric_evidence(5)  # only ever appears in bear's rebuttal_findings
    verdict_findings = [
        Finding(
            claim="Competitor's price undercutting is a genuine near-term risk",
            importance=0.9,
            evidence=[rebuttal_only_evidence],
        )
    ]

    resolve_case_evidence_against_pool(verdict_findings, pool)  # should not raise
