"""Tests for fetching the current share price.

A DCF fair value only becomes actionable next to what the stock actually
trades at, so this is the input that turns "is this a good business?" into
"is this a good investment?".
"""

from datetime import date

import httpx
import pytest

from app.financials.alpha_vantage_client import AlphaVantageClient, AlphaVantageError

GLOBAL_QUOTE_PAYLOAD = {
    "Global Quote": {
        "01. symbol": "AAPL",
        "05. price": "180.4200",
        "07. latest trading day": "2026-09-08",
        "09. change": "1.2300",
        "10. change percent": "0.6871%",
    }
}


def _client_with_response(payload: dict, status_code: int = 200) -> AlphaVantageClient:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json=payload)

    return AlphaVantageClient(
        api_key="test-key", http_client=httpx.Client(transport=httpx.MockTransport(handler))
    )


def test_parses_the_current_price_and_its_trading_day():
    quote = _client_with_response(GLOBAL_QUOTE_PAYLOAD).get_quote("AAPL")

    assert quote is not None
    assert quote.price == 180.42
    assert quote.as_of == date(2026, 9, 8)


def test_returns_none_when_alpha_vantage_knows_no_such_symbol():
    # Alpha Vantage answers an unknown symbol with an empty object rather
    # than an error, so "no quote" has to be distinguished from "failure".
    quote = _client_with_response({"Global Quote": {}}).get_quote("ZZZZ")

    assert quote is None


def test_rate_limit_response_still_raises():
    # Distinct from "no such symbol": the caller should be able to tell a
    # missing quote from a throttled one.
    client = _client_with_response({"Note": "call frequency limit reached"})

    with pytest.raises(AlphaVantageError):
        client.get_quote("AAPL")
