from fastapi import Depends
from sqlalchemy.orm import Session

from app.agents.llm_client import AnthropicLLMClient
from app.core.config import settings
from app.db.session import get_db
from app.filings.dependencies import get_voyage_client
from app.filings.search import VoyageFilingSearchClient
from app.filings.voyage_client import VoyageEmbeddingClient


def get_llm_client() -> AnthropicLLMClient:
    return AnthropicLLMClient(api_key=settings.anthropic_api_key)


def get_filing_search_client(
    db: Session = Depends(get_db),
    voyage_client: VoyageEmbeddingClient = Depends(get_voyage_client),
) -> VoyageFilingSearchClient:
    return VoyageFilingSearchClient(db=db, voyage_client=voyage_client)
