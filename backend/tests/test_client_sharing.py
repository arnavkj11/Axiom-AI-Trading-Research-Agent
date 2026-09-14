"""The rate-limited API clients must be shared across requests.

AlphaVantageClient throttles itself to stay under the free tier's limits,
but that state lives on the instance — so handing every request a fresh
client silently disables the throttle between concurrent requests. Seen
live: a page that fetched /financials twice at once (React StrictMode's
dev double-effect) burst 8 requests at Alpha Vantage and got both
responses rejected, surfacing as 502s.
"""

from app.company.dependencies import get_sec_ticker_lookup
from app.filings.dependencies import get_voyage_client
from app.financials.dependencies import get_alpha_vantage_client


def test_alpha_vantage_client_is_shared_so_throttling_actually_applies():
    assert get_alpha_vantage_client() is get_alpha_vantage_client()


def test_voyage_client_is_shared_so_throttling_actually_applies():
    # Same reasoning: VoyageEmbeddingClient paces itself against Voyage's
    # rate limit using instance state.
    assert get_voyage_client() is get_voyage_client()


def test_sec_ticker_lookup_is_shared_so_the_registrant_list_is_fetched_once():
    assert get_sec_ticker_lookup() is get_sec_ticker_lookup()
