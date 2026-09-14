from datetime import date

import pytest

from app.agents.filing import FilingEvidenceMismatchError, RETRIEVAL_TOPICS, filing_analyst
from app.agents.schemas import FilingAnalysis, FilingChunkEvidence, Finding, Stance
from app.filings.search import FilingChunkResult
from app.research.models import ResearchRunStatus
from app.research.schemas import ResearchState
from tests.fakes import FakeFilingSearchClient, FakeLLMClient

CHUNK_A = FilingChunkResult(
    chunk_id=201,
    filing_id=10,
    accession_number="0000320193-26-000012",
    section="Item 1A. Risk Factors",
    text="We face significant competition from other manufacturers.",
)
CHUNK_B = FilingChunkResult(
    chunk_id=202,
    filing_id=10,
    accession_number="0000320193-26-000012",
    section="Item 7. MD&A",
    text="Revenue growth was primarily driven by services and wearables.",
)


def _state() -> ResearchState:
    return ResearchState(
        research_run_id=1,
        company_id=7,
        ticker="AAPL",
        research_date=date(2026, 9, 6),
        status=ResearchRunStatus.FILING_RUNNING,
    )


def _analysis_citing(chunk: FilingChunkResult) -> FilingAnalysis:
    return FilingAnalysis(
        stance=Stance.NEUTRAL,
        confidence=0.6,
        findings=[
            Finding(
                claim="New competitive risk disclosed",
                importance=0.7,
                evidence=[
                    FilingChunkEvidence(
                        chunk_id=chunk.chunk_id,
                        filing_id=chunk.filing_id,
                        accession_number=chunk.accession_number,
                        section=chunk.section,
                        quote=chunk.text,
                    )
                ],
            )
        ],
    )


def test_filing_analyst_returns_state_update_with_llm_output():
    search_client = FakeFilingSearchClient(default=[CHUNK_A])
    llm_client = FakeLLMClient(response=_analysis_citing(CHUNK_A))

    result = filing_analyst(_state(), search_client, llm_client)

    assert result == {"filing_analysis": _analysis_citing(CHUNK_A)}


def test_filing_analyst_requests_filing_analysis_output_model():
    search_client = FakeFilingSearchClient(default=[CHUNK_A])
    llm_client = FakeLLMClient(response=_analysis_citing(CHUNK_A))

    filing_analyst(_state(), search_client, llm_client)

    assert llm_client.calls[0]["output_model"] is FilingAnalysis


def test_filing_analyst_searches_once_per_retrieval_topic():
    search_client = FakeFilingSearchClient(default=[CHUNK_A])
    llm_client = FakeLLMClient(response=_analysis_citing(CHUNK_A))

    filing_analyst(_state(), search_client, llm_client)

    queried_topics = {call["query"] for call in search_client.calls}
    assert queried_topics == set(RETRIEVAL_TOPICS)
    assert all(call["company_id"] == 7 for call in search_client.calls)


def test_filing_analyst_dedupes_chunks_returned_by_multiple_topics():
    search_client = FakeFilingSearchClient(
        results_by_query={topic: [CHUNK_A] for topic in RETRIEVAL_TOPICS}
    )
    llm_client = FakeLLMClient(response=_analysis_citing(CHUNK_A))

    filing_analyst(_state(), search_client, llm_client)

    prompt = llm_client.calls[0]["user_message"]
    assert prompt.count(f"chunk_id={CHUNK_A.chunk_id}") == 1


def test_filing_analyst_prompt_includes_retrieved_chunk_ids_and_text():
    search_client = FakeFilingSearchClient(default=[CHUNK_A, CHUNK_B])
    llm_client = FakeLLMClient(response=_analysis_citing(CHUNK_A))

    filing_analyst(_state(), search_client, llm_client)

    prompt = llm_client.calls[0]["user_message"]
    assert f"chunk_id={CHUNK_A.chunk_id}" in prompt
    assert CHUNK_A.text in prompt
    assert f"chunk_id={CHUNK_B.chunk_id}" in prompt
    assert CHUNK_B.text in prompt


def test_filing_analyst_rejects_evidence_citing_a_chunk_that_was_never_retrieved():
    search_client = FakeFilingSearchClient(default=[CHUNK_A])
    llm_client = FakeLLMClient(response=_analysis_citing(CHUNK_B))  # not retrieved

    with pytest.raises(FilingEvidenceMismatchError):
        filing_analyst(_state(), search_client, llm_client)


def test_filing_analyst_rejects_evidence_with_mismatched_filing_metadata():
    search_client = FakeFilingSearchClient(default=[CHUNK_A])
    mismatched = FilingAnalysis(
        stance=Stance.NEUTRAL,
        confidence=0.6,
        findings=[
            Finding(
                claim="New competitive risk disclosed",
                importance=0.7,
                evidence=[
                    FilingChunkEvidence(
                        chunk_id=CHUNK_A.chunk_id,
                        filing_id=999,  # doesn't match CHUNK_A.filing_id
                        accession_number=CHUNK_A.accession_number,
                        section=CHUNK_A.section,
                        quote=CHUNK_A.text,
                    )
                ],
            )
        ],
    )
    llm_client = FakeLLMClient(response=mismatched)

    with pytest.raises(FilingEvidenceMismatchError):
        filing_analyst(_state(), search_client, llm_client)
