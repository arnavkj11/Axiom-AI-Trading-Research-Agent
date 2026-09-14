from functools import lru_cache

from app.core.config import settings
from app.filings.edgar_client import EdgarClient
from app.filings.voyage_client import VoyageEmbeddingClient


@lru_cache(maxsize=1)
def get_edgar_client() -> EdgarClient:
    return EdgarClient(user_agent=settings.edgar_user_agent)


@lru_cache(maxsize=1)
def get_voyage_client() -> VoyageEmbeddingClient:
    """One shared client per process — see get_alpha_vantage_client: the
    inter-request pacing this client does is instance state, so a client
    per request would leave concurrent requests unthrottled.
    """
    return VoyageEmbeddingClient(
        api_key=settings.voyage_ai_api_key,
        batch_size=settings.voyage_batch_size,
        min_seconds_between_requests=settings.voyage_min_seconds_between_requests,
    )
