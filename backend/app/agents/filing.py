"""Filing Analyst agent — a LangGraph node.

Retrieves the most relevant SEC filing chunks for a fixed set of research
topics via pgvector similarity search, then reasons over only that
retrieved text. Every FilingChunkEvidence citation is checked against the
chunks actually retrieved before the result is accepted — the LLM cannot
fabricate a chunk_id or attach a real chunk_id to the wrong filing.
"""

from typing import Protocol

from app.agents.schemas import EvidenceType, FilingAnalysis
from app.filings.search import FilingChunkResult
from app.research.schemas import ResearchState

# V1-trimmed set of full_vision.md's Filing Analyst responsibilities
# (risk changes, management tone, revenue/customer concentration).
RETRIEVAL_TOPICS = [
    "risk factors and material risks to the business",
    "management discussion, business outlook, and strategic changes",
    "revenue drivers and customer concentration",
]
TOP_K_PER_TOPIC = 5

SYSTEM_PROMPT = """You are Axiom's Filing Analyst agent, part of a multi-agent equity \
research platform.

Analyze the SEC filing excerpts provided below: new or changed risks, management tone, \
customer concentration, litigation, strategic changes, and material events.

Every finding with importance >= 0.5 MUST cite at least one piece of evidence with \
evidence_type "filing_chunk", using the exact chunk_id, filing_id, accession_number, \
and section of one of the excerpts given. Never invent a chunk_id or attach an \
excerpt's fields to the wrong chunk_id. The quote field must be an excerpt actually \
drawn from that chunk's text. Do not make claims that aren't grounded in the provided \
excerpts."""


class FilingSearchClient(Protocol):
    def search(
        self, *, company_id: int, query: str, top_k: int
    ) -> list[FilingChunkResult]: ...


class LLMClient(Protocol):
    def generate_structured(
        self, *, system: str, user_message: str, output_model: type[FilingAnalysis]
    ) -> FilingAnalysis: ...


class FilingEvidenceMismatchError(RuntimeError):
    """A FilingChunkEvidence citation didn't match a chunk that was actually retrieved."""


def filing_analyst(
    state: ResearchState, filing_search_client: FilingSearchClient, llm_client: LLMClient
) -> dict:
    """LangGraph node: returns a partial state update with filing_analysis set."""
    chunks = _retrieve_chunks(state, filing_search_client)
    analysis = llm_client.generate_structured(
        system=SYSTEM_PROMPT,
        user_message=_build_user_message(state, chunks),
        output_model=FilingAnalysis,
    )
    _validate_evidence_matches_retrieved_chunks(analysis, chunks)
    return {"filing_analysis": analysis}


def _retrieve_chunks(
    state: ResearchState, filing_search_client: FilingSearchClient
) -> list[FilingChunkResult]:
    seen_chunk_ids: set[int] = set()
    chunks: list[FilingChunkResult] = []
    for topic in RETRIEVAL_TOPICS:
        for chunk in filing_search_client.search(
            company_id=state.company_id, query=topic, top_k=TOP_K_PER_TOPIC
        ):
            if chunk.chunk_id in seen_chunk_ids:
                continue
            seen_chunk_ids.add(chunk.chunk_id)
            chunks.append(chunk)
    return chunks


def _build_user_message(state: ResearchState, chunks: list[FilingChunkResult]) -> str:
    lines = [f"Company: {state.ticker}", "", "Filing excerpts (cite by chunk_id):"]
    for chunk in chunks:
        lines.append(
            f"- chunk_id={chunk.chunk_id} filing_id={chunk.filing_id} "
            f"accession_number={chunk.accession_number} section={chunk.section!r}\n"
            f"  text: {chunk.text}"
        )
    return "\n".join(lines)


def _validate_evidence_matches_retrieved_chunks(
    analysis: FilingAnalysis, chunks: list[FilingChunkResult]
) -> None:
    chunks_by_id = {chunk.chunk_id: chunk for chunk in chunks}
    for finding in analysis.findings + analysis.risks:
        for evidence in finding.evidence:
            if evidence.evidence_type != EvidenceType.FILING_CHUNK:
                continue
            chunk = chunks_by_id.get(evidence.chunk_id)
            if chunk is None:
                raise FilingEvidenceMismatchError(
                    f"cited chunk_id={evidence.chunk_id} was never retrieved"
                )
            if (
                chunk.filing_id != evidence.filing_id
                or chunk.accession_number != evidence.accession_number
            ):
                raise FilingEvidenceMismatchError(
                    f"evidence for chunk_id={evidence.chunk_id} doesn't match the "
                    f"retrieved chunk's filing_id/accession_number"
                )
