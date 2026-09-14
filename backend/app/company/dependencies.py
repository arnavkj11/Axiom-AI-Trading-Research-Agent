from functools import lru_cache

from app.company.sec_lookup import SecTickerLookup
from app.core.config import settings


@lru_cache(maxsize=1)
def _shared_lookup() -> SecTickerLookup:
    # Cached so the ~10k-entry SEC registrant list is fetched once per
    # process rather than once per request (SecTickerLookup caches the
    # mapping on the instance, so a fresh instance per request would
    # refetch every time).
    return SecTickerLookup(user_agent=settings.edgar_user_agent)


def get_sec_ticker_lookup() -> SecTickerLookup:
    return _shared_lookup()
