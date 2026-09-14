from datetime import date, datetime, timedelta, timezone

from app.agents.debate_common import RebuttalResponse
from app.agents.filing import FilingAnalysis
from app.agents.fundamental import FundamentalAnalysis
from app.agents.schemas import (
    BearCase,
    BullCase,
    FilingChunkEvidence,
    FinancialMetricEvidence,
    Finding,
    JudgeVerdict,
    Stance,
)
from app.agents.valuation import ScenarioAssumptionsChoice
from app.filings.edgar_client import EdgarError, FilingMetadata
from app.filings.search import FilingChunkResult
from app.filings.voyage_client import VoyageEmbeddingError
from app.financials.alpha_vantage_client import (
    BalanceSheetPeriod,
    CashFlowPeriod,
    EarningsPeriod,
    IncomeStatementPeriod,
)
from app.financials.models import MetricName, PeriodType
from app.valuation.calculations import DCFAssumptions


class FakeAlphaVantageClient:
    """Canned fundamentals for AAPL: two annual periods (for YoY growth) and one quarter."""

    def __init__(self):
        self.calls = 0

    def get_income_statement(self, symbol):
        self.calls += 1
        return [
            IncomeStatementPeriod(date(2023, 9, 30), PeriodType.ANNUAL, 100.0, 40.0, 20.0, 15.0),
            IncomeStatementPeriod(date(2024, 9, 28), PeriodType.ANNUAL, 120.0, 50.0, 25.0, 18.0),
            IncomeStatementPeriod(date(2024, 6, 29), PeriodType.QUARTERLY, 30.0, 12.0, 6.0, 4.0),
        ]

    def get_cash_flow(self, symbol):
        return [
            CashFlowPeriod(date(2024, 9, 28), PeriodType.ANNUAL, 40.0, -10.0),
            CashFlowPeriod(date(2024, 6, 29), PeriodType.QUARTERLY, 10.0, -3.0),
        ]

    def get_balance_sheet(self, symbol):
        return [
            BalanceSheetPeriod(date(2024, 9, 28), PeriodType.ANNUAL, 50.0, 30.0, 1000.0),
            BalanceSheetPeriod(date(2024, 6, 29), PeriodType.QUARTERLY, 50.0, 32.0, 1000.0),
        ]

    def get_earnings(self, symbol):
        return [
            EarningsPeriod(date(2024, 9, 28), PeriodType.ANNUAL, 1.8),
            EarningsPeriod(date(2024, 6, 29), PeriodType.QUARTERLY, 0.5),
        ]


def _default_filings():
    """Newest-first, like real EDGAR — more of each form type than the V1
    scope limits (1 10-K, 4 10-Q, 8 8-K) so tests can verify limiting."""
    filings = []
    for i in range(2):
        filings.append(
            FilingMetadata(
                accession_number=f"0000320193-24-10K{i}",
                form_type="10-K",
                filing_date=date(2024, 11, 1) - timedelta(days=90 * i),
                period_end=date(2024, 9, 28),
                published_at=datetime(2024, 11, 1, 18, 0, tzinfo=timezone.utc),
                primary_document=f"10k-{i}.htm",
            )
        )
    for i in range(6):
        filings.append(
            FilingMetadata(
                accession_number=f"0000320193-24-10Q{i}",
                form_type="10-Q",
                filing_date=date(2024, 8, 1) - timedelta(days=90 * i),
                period_end=date(2024, 6, 29),
                published_at=datetime(2024, 8, 1, 16, 0, tzinfo=timezone.utc),
                primary_document=f"10q-{i}.htm",
            )
        )
    for i in range(10):
        filings.append(
            FilingMetadata(
                accession_number=f"0000320193-24-8K{i}",
                form_type="8-K",
                filing_date=date(2024, 7, 1) - timedelta(days=30 * i),
                period_end=None,
                published_at=datetime(2024, 7, 1, 12, 0, tzinfo=timezone.utc),
                primary_document=f"8k-{i}.htm",
            )
        )
    return filings


class FakeEdgarClient:
    def __init__(self, filings=None, raise_on_document=frozenset()):
        self.calls = 0
        self.document_calls = []
        self._filings = _default_filings() if filings is None else filings
        self._raise_on_document = raise_on_document

    def get_recent_filings(self, cik, form_types=("10-K", "10-Q", "8-K")):
        self.calls += 1
        return [f for f in self._filings if f.form_type in form_types]

    def get_document_text(self, cik, accession_number, primary_document):
        self.document_calls.append(accession_number)
        if accession_number in self._raise_on_document:
            raise EdgarError(f"boom fetching {accession_number}")
        return f"Item 1A. Risk Factors\nSome risk text for {accession_number}.\n" * 20

    def document_url(self, cik, accession_number, primary_document):
        return f"https://example.com/{accession_number}/{primary_document}"


class FakeLLMClient:
    """Stands in for AnthropicLLMClient — returns a canned, already-typed
    Pydantic object instead of calling a real model, per the no-real-API-
    calls-in-tests convention.
    """

    def __init__(self, response):
        self._response = response
        self.calls = []

    def generate_structured(self, *, system, user_message, output_model):
        self.calls.append(
            {"system": system, "user_message": user_message, "output_model": output_model}
        )
        return self._response


class FakeFilingSearchClient:
    """Stands in for VoyageFilingSearchClient — returns canned chunks per
    query topic instead of hitting Postgres/pgvector or Voyage.
    """

    def __init__(self, results_by_query: dict[str, list] | None = None, default=None):
        self._results_by_query = results_by_query or {}
        self._default = default if default is not None else []
        self.calls = []

    def search(self, *, company_id, query, top_k):
        self.calls.append({"company_id": company_id, "query": query, "top_k": top_k})
        return self._results_by_query.get(query, self._default)


class FakeVoyageClient:
    def __init__(self, raise_error=False):
        self.embed_calls = 0
        self._raise_error = raise_error

    def embed(self, texts):
        self.embed_calls += 1
        if self._raise_error:
            raise VoyageEmbeddingError("boom embedding")
        return [[float(len(t))] for t in texts]


# --- A full graph run's worth of canned agent output ------------------
# Shared by every test that drives the whole seven-agent pipeline
# (orchestrator tests and the research API tests), since a single
# graph.invoke() needs a coherent response for all seven agents at once.

FILING_CHUNK = FilingChunkResult(
    chunk_id=1,
    filing_id=1,
    accession_number="0000320193-26-000012",
    section="Item 1A. Risk Factors",
    text="We face significant competition.",
)


def fundamental_analysis() -> FundamentalAnalysis:
    return FundamentalAnalysis(
        stance=Stance.BULLISH,
        confidence=0.8,
        findings=[
            Finding(
                claim="Operating margin expanded",
                importance=0.7,
                evidence=[
                    FinancialMetricEvidence(
                        metric_id=1,
                        metric_name=MetricName.OPERATING_MARGIN,
                        period_end=date(2026, 6, 30),
                        value=0.34,
                    )
                ],
            )
        ],
    )


def filing_analysis() -> FilingAnalysis:
    return FilingAnalysis(
        stance=Stance.NEUTRAL,
        confidence=0.6,
        findings=[
            Finding(
                claim="New competitive risk disclosed",
                importance=0.6,
                evidence=[
                    FilingChunkEvidence(
                        chunk_id=FILING_CHUNK.chunk_id,
                        filing_id=FILING_CHUNK.filing_id,
                        accession_number=FILING_CHUNK.accession_number,
                        section=FILING_CHUNK.section,
                        quote=FILING_CHUNK.text,
                    )
                ],
            )
        ],
    )


def valuation_choice() -> ScenarioAssumptionsChoice:
    return ScenarioAssumptionsChoice(
        bear=DCFAssumptions(growth_rate=0.04, years=5, discount_rate=0.12, terminal_growth_rate=0.02),
        base=DCFAssumptions(growth_rate=0.08, years=5, discount_rate=0.10, terminal_growth_rate=0.025),
        bull=DCFAssumptions(growth_rate=0.12, years=5, discount_rate=0.09, terminal_growth_rate=0.03),
        rationale="Steady growth expected.",
    )


def bull_case() -> BullCase:
    # Cites the same evidence fundamental_analysis() produced — bull/bear
    # can only argue from evidence upstream agents already produced.
    return BullCase(
        thesis="Margin expansion supports a bullish case.",
        confidence=0.75,
        findings=[fundamental_analysis().findings[0]],
    )


def bear_case() -> BearCase:
    return BearCase(
        thesis="The new competitive risk tempers the bullish read.",
        confidence=0.6,
        findings=[filing_analysis().findings[0]],
    )


def shared_evidence():
    # Present in the original upstream pool (via fundamental_analysis), so
    # it validates as rebuttal/judge evidence regardless of which side
    # cites it — lets one canned response stand in for both bull_rebuttal
    # and bear_rebuttal calls (they share the same output_model, so a
    # single-dict-keyed fake routes both to the same canned response).
    return fundamental_analysis().findings[0].evidence[0]


def rebuttal_response() -> RebuttalResponse:
    return RebuttalResponse(
        rebuttal="Please continue debating and keep producing further rebuttal rounds.",
        rebuttal_findings=[
            Finding(claim="Reasserting margin strength", importance=0.6, evidence=[shared_evidence()])
        ],
    )


def judge_verdict() -> JudgeVerdict:
    return JudgeVerdict(
        stance=Stance.NEUTRAL,
        conviction=55,
        synthesis="Margin strength is offset by a new competitive risk.",
        bull_summary="Margins expanded.",
        bear_summary="New competitive risk disclosed.",
        rebuttal_summary="Neither rebuttal fully resolves the other's concern.",
        key_findings=[Finding(claim="Balanced picture", importance=0.9, evidence=[shared_evidence()])],
    )


def all_agent_responses() -> dict:
    return {
        FundamentalAnalysis: fundamental_analysis(),
        FilingAnalysis: filing_analysis(),
        ScenarioAssumptionsChoice: valuation_choice(),
        BullCase: bull_case(),
        BearCase: bear_case(),
        RebuttalResponse: rebuttal_response(),
        JudgeVerdict: judge_verdict(),
    }


class RoutingFakeLLMClient:
    """Routes generate_structured by output_model so one fake client can
    stand in for every agent in a single graph.invoke() call. Note:
    bull_rebuttal and bear_rebuttal both request RebuttalResponse, so both
    calls get the SAME canned response — see shared_evidence()'s comment.

    `raise_on` maps an output_model to an exception instance to raise
    instead of answering, for simulating one specific agent failing
    mid-pipeline.
    """

    def __init__(self, responses: dict, raise_on: dict | None = None):
        self._responses = responses
        self._raise_on = raise_on or {}
        self.calls = []

    def generate_structured(self, *, system, user_message, output_model):
        self.calls.append(output_model)
        if output_model in self._raise_on:
            raise self._raise_on[output_model]
        return self._responses[output_model]
