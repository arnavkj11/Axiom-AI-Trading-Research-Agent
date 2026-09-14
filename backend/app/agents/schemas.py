"""Shared Pydantic contracts for the research agent pipeline (CLAUDE.md's
"agents reason, Python calculates, every material claim cites evidence"
rule).

No agent communicates in free-form prose across the LangGraph boundary —
every input/output is one of the models below.
"""

from datetime import date
from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator

from app.financials.models import MetricName

# Findings at or above this importance must carry at least one Evidence
# reference (CLAUDE.md: "Every Finding with meaningful importance must
# carry at least one evidence reference").
MATERIALITY_THRESHOLD = 0.5


class EvidenceType(str, Enum):
    FINANCIAL_METRIC = "financial_metric"
    FILING_CHUNK = "filing_chunk"
    VALUATION_OUTPUT = "valuation_output"


class FinancialMetricEvidence(BaseModel):
    """Cites one row in financial_metrics by primary key."""

    evidence_type: Literal[EvidenceType.FINANCIAL_METRIC] = EvidenceType.FINANCIAL_METRIC
    metric_id: int
    metric_name: MetricName
    period_end: date
    value: float


class FilingChunkEvidence(BaseModel):
    """Cites one row in filing_chunks (and its parent filing) by primary key."""

    evidence_type: Literal[EvidenceType.FILING_CHUNK] = EvidenceType.FILING_CHUNK
    chunk_id: int
    filing_id: int
    accession_number: str
    section: str | None = None
    quote: str


class ValuationOutputEvidence(BaseModel):
    """Cites a field of a deterministic valuation function's output.

    Valuation outputs aren't persisted as their own DB rows in V1, so this
    self-describes the source instead of pointing at a foreign key:
    research_run_id + function_name + output_field + a value snapshot.
    """

    evidence_type: Literal[EvidenceType.VALUATION_OUTPUT] = EvidenceType.VALUATION_OUTPUT
    research_run_id: int
    function_name: str
    output_field: str
    value: float
    assumptions: dict[str, float] = Field(default_factory=dict)


Evidence = Annotated[
    FinancialMetricEvidence | FilingChunkEvidence | ValuationOutputEvidence,
    Field(discriminator="evidence_type"),
]


class Finding(BaseModel):
    claim: str
    importance: float = Field(ge=0, le=1)
    evidence: list[Evidence] = Field(default_factory=list)

    @model_validator(mode="after")
    def _require_evidence_when_material(self) -> "Finding":
        if self.importance >= MATERIALITY_THRESHOLD and not self.evidence:
            raise ValueError(
                f"findings with importance >= {MATERIALITY_THRESHOLD} must cite at least one Evidence"
            )
        return self


class Stance(str, Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"


class FundamentalAnalysis(BaseModel):
    stance: Stance
    confidence: float = Field(ge=0, le=1)
    findings: list[Finding]
    risks: list[Finding] = Field(default_factory=list)


class FilingAnalysis(BaseModel):
    stance: Stance
    confidence: float = Field(ge=0, le=1)
    findings: list[Finding]
    risks: list[Finding] = Field(default_factory=list)


class ScenarioValuation(BaseModel):
    scenario: Literal["bear", "base", "bull"]
    fair_value_per_share: float
    assumptions: dict[str, float]
    # (fair_value - price) / price. None when no quote was available —
    # never guessed, since this is the number an investment decision turns
    # on. Computed in Python; the model never derives it (CLAUDE.md Rule 1).
    upside_pct: float | None = None


class ValuationOutput(BaseModel):
    method: str
    scenarios: list[ScenarioValuation]
    current_price: float | None = None
    evidence: list[Evidence] = Field(default_factory=list)
    commentary: str


class BullCase(BaseModel):
    thesis: str
    confidence: float = Field(ge=0, le=1)
    findings: list[Finding]
    rebuttal: str | None = None
    rebuttal_findings: list[Finding] = Field(default_factory=list)


class BearCase(BaseModel):
    thesis: str
    confidence: float = Field(ge=0, le=1)
    findings: list[Finding]
    rebuttal: str | None = None
    rebuttal_findings: list[Finding] = Field(default_factory=list)


class JudgeVerdict(BaseModel):
    stance: Stance
    conviction: int = Field(ge=0, le=100)
    synthesis: str
    bull_summary: str
    bear_summary: str
    rebuttal_summary: str
    key_findings: list[Finding] = Field(default_factory=list)
    risks: list[Finding] = Field(default_factory=list)
    catalysts: list[Finding] = Field(default_factory=list)
