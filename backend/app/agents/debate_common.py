"""Shared helpers for Bull and Bear (CLAUDE.md: each "builds the strongest
evidence-backed case from the preliminary thesis and the other agents'
findings" — they argue from existing evidence, they don't gather new
evidence themselves).

Both agents are given the pool of Findings/Evidence the Fundamental,
Filing, and Valuation agents already produced and validated, and must
cite only from that pool — resolve_case_evidence_against_pool rejects
any case citing evidence that wasn't actually produced upstream.
"""

from pydantic import BaseModel, Field

from app.agents.schemas import (
    Evidence,
    FilingChunkEvidence,
    FinancialMetricEvidence,
    Finding,
    ValuationOutput,
    ValuationOutputEvidence,
)
from app.research.schemas import ResearchState


class EvidenceNotInPoolError(RuntimeError):
    """A Bull/Bear/Judge finding cited Evidence that wasn't produced upstream."""


class RebuttalAlreadyRecordedError(RuntimeError):
    """A rebuttal node ran against a case that already has a recorded rebuttal.

    The graph has no edge that should ever trigger this twice — this is a
    defense-in-depth guard, not the primary mechanism enforcing the
    one-rebuttal-round cap (CLAUDE.md Rule 5). See bull_rebuttal.py /
    bear_rebuttal.py.
    """


class RebuttalResponse(BaseModel):
    """What a rebuttal node's LLM call produces — just the delta to record,
    never a full BullCase/BearCase (thesis/findings are never regenerated).
    """

    rebuttal: str
    rebuttal_findings: list[Finding] = Field(default_factory=list)


def collect_available_findings(state: ResearchState) -> list[Finding]:
    findings: list[Finding] = []
    if state.fundamental_analysis is not None:
        findings.extend(state.fundamental_analysis.findings)
        findings.extend(state.fundamental_analysis.risks)
    if state.filing_analysis is not None:
        findings.extend(state.filing_analysis.findings)
        findings.extend(state.filing_analysis.risks)
    return findings


def collect_available_evidence(state: ResearchState) -> list[Evidence]:
    evidence: list[Evidence] = []
    for finding in collect_available_findings(state):
        evidence.extend(finding.evidence)
    if state.valuation_output is not None:
        evidence.extend(state.valuation_output.evidence)
    return evidence


def collect_rebuttal_evidence_pool(state: ResearchState) -> list[Evidence]:
    """The pool a rebuttal node may cite from: the original upstream pool,
    plus BOTH sides' opening findings — the rebutting side's own (so Bull
    can re-cite its own opening evidence) and the opponent's (so Bull can
    cite the exact evidence Bear used while rebutting it). Not
    rebuttal_findings — neither side has rebutted yet when this runs.
    """
    pool = collect_available_evidence(state)
    if state.bull_case is not None:
        for finding in state.bull_case.findings:
            pool.extend(finding.evidence)
    if state.bear_case is not None:
        for finding in state.bear_case.findings:
            pool.extend(finding.evidence)
    return pool


def collect_full_debate_evidence_pool(state: ResearchState) -> list[Evidence]:
    """The pool the Judge may cite from: the original upstream pool, plus
    both sides' opening findings AND rebuttal_findings.
    """
    pool = collect_available_evidence(state)
    if state.bull_case is not None:
        for finding in state.bull_case.findings + state.bull_case.rebuttal_findings:
            pool.extend(finding.evidence)
    if state.bear_case is not None:
        for finding in state.bear_case.findings + state.bear_case.rebuttal_findings:
            pool.extend(finding.evidence)
    return pool


def _evidence_identity(evidence: Evidence) -> tuple:
    """The real-world "primary key" fields for each Evidence variant —
    the ones tied to an actual DB row / retrieved chunk / computed value,
    as opposed to free-text fields (quote, section) or duplicated
    descriptive fields (metric_name, period_end, value, assumptions) that
    the model may retype with cosmetic differences even when asked to
    copy verbatim.
    """
    if isinstance(evidence, FinancialMetricEvidence):
        return ("financial_metric", evidence.metric_id)
    if isinstance(evidence, FilingChunkEvidence):
        return ("filing_chunk", evidence.chunk_id)
    if isinstance(evidence, ValuationOutputEvidence):
        return ("valuation_output", evidence.research_run_id, evidence.function_name, evidence.output_field)
    raise TypeError(f"unrecognized evidence type: {type(evidence)!r}")


def resolve_case_evidence_against_pool(
    findings: list[Finding], pool: list[Evidence]
) -> list[Finding]:
    """Validates every Finding's evidence against the pool by identity —
    not exact field equality — and replaces each citation with the
    pool's canonical object, so the evidence trail in the final output
    always matches the DB-backed source exactly, never an LLM-retyped
    copy of it. Raises EvidenceNotInPoolError if a citation's identity
    isn't found in the pool at all (real fabrication, not cosmetic
    retyping).
    """
    pool_by_identity = {_evidence_identity(evidence): evidence for evidence in pool}
    resolved_findings: list[Finding] = []
    for finding in findings:
        resolved_evidence: list[Evidence] = []
        for evidence in finding.evidence:
            canonical = pool_by_identity.get(_evidence_identity(evidence))
            if canonical is None:
                raise EvidenceNotInPoolError(
                    f"cited evidence {evidence!r} was not produced by an upstream agent"
                )
            resolved_evidence.append(canonical)
        resolved_findings.append(finding.model_copy(update={"evidence": resolved_evidence}))
    return resolved_findings


def format_available_findings(findings: list[Finding]) -> str:
    lines = []
    for i, finding in enumerate(findings, start=1):
        lines.append(f"{i}. claim: {finding.claim} (importance={finding.importance})")
        for evidence in finding.evidence:
            lines.append(f"   evidence: {evidence.model_dump_json()}")
    return "\n".join(lines)


def format_available_valuation(valuation_output: ValuationOutput | None) -> str:
    """Renders valuation for the debate agents (Bull, Bear, Judge).

    Includes the market price and each scenario's upside, because that
    comparison — not the fair value alone — is what makes a case an
    investment argument rather than a business description. When no quote
    was available, say so explicitly rather than omitting it, so the model
    doesn't assume a price it was never given.
    """
    if valuation_output is None:
        return "(no valuation output available)"
    lines = [f"Valuation method: {valuation_output.method}", f"Commentary: {valuation_output.commentary}"]

    if valuation_output.current_price is not None:
        lines.append(f"Current market price: ${valuation_output.current_price:.2f}")
    else:
        lines.append(
            "Current market price: unknown (no quote available) — do not assume "
            "a price or claim the stock is cheap or expensive."
        )

    for scenario in valuation_output.scenarios:
        line = f"  {scenario.scenario}: fair_value_per_share={scenario.fair_value_per_share}"
        if scenario.upside_pct is not None:
            direction = "above" if scenario.upside_pct >= 0 else "below"
            line += (
                f", upside_pct={scenario.upside_pct:.4f} "
                f"({abs(scenario.upside_pct):.1%} {direction} the market price)"
            )
        lines.append(line)

    for evidence in valuation_output.evidence:
        lines.append(f"  evidence: {evidence.model_dump_json()}")
    return "\n".join(lines)
