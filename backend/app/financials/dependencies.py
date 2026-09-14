from functools import lru_cache

from app.core.config import settings
from app.financials.alpha_vantage_client import AlphaVantageClient


@lru_cache(maxsize=1)
def get_alpha_vantage_client() -> AlphaVantageClient:
    """One shared client per process.

    Deliberately cached rather than constructed per request: the client
    throttles itself to stay under Alpha Vantage's free-tier limits, and
    that throttle state lives on the instance. A fresh client per request
    means concurrent requests coordinate not at all — seen live as two
    simultaneous /financials calls bursting 8 requests and both failing.
    """
    return AlphaVantageClient(api_key=settings.alpha_vantage_api_key)
