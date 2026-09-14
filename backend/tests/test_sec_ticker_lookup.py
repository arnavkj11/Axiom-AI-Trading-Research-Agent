"""Tests for the SEC ticker -> CIK lookup.

This is what makes a company addable at all: the CIK is required to pull
filings from EDGAR, and it isn't derivable from the ticker without this
mapping.
"""

import httpx
import pytest

from app.company.sec_lookup import SecTickerLookup, SecTickerLookupError

# Shaped like the real https://www.sec.gov/files/company_tickers.json —
# an object keyed by row index, not a list.
SAMPLE_PAYLOAD = {
    "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
    "1": {"cik_str": 1318605, "ticker": "TSLA", "title": "Tesla, Inc."},
    "2": {"cik_str": 789019, "ticker": "MSFT", "title": "Microsoft Corp"},
}


class _FakeTransport(httpx.BaseTransport):
    def __init__(self, payload=None, status_code=200, count_calls=None):
        self._payload = SAMPLE_PAYLOAD if payload is None else payload
        self._status_code = status_code
        self.calls = count_calls if count_calls is not None else []

    def handle_request(self, request):
        self.calls.append(str(request.url))
        return httpx.Response(
            self._status_code, json=self._payload, request=request
        )


def _lookup(**kwargs) -> tuple[SecTickerLookup, _FakeTransport]:
    transport = _FakeTransport(**kwargs)
    client = httpx.Client(transport=transport)
    return SecTickerLookup(user_agent="Axiom Test (test@example.com)", http_client=client), transport


def test_finds_a_company_by_ticker():
    lookup, _ = _lookup()

    record = lookup.get("TSLA")

    assert record is not None
    assert record.ticker == "TSLA"
    assert record.name == "Tesla, Inc."
    # Zero-padded to 10 digits, the form EDGAR's submissions API expects.
    assert record.cik == "0001318605"


def test_ticker_matching_is_case_insensitive():
    lookup, _ = _lookup()

    assert lookup.get("tsla") is not None
    assert lookup.get("TSLA") == lookup.get("tsla")


def test_returns_none_for_a_ticker_the_sec_does_not_list():
    lookup, _ = _lookup()

    assert lookup.get("NOTAREALTICKER") is None


def test_mapping_is_fetched_once_and_reused():
    # 10k+ registrants over the wire; refetching per lookup would be
    # wasteful and rude to SEC's fair-access policy.
    lookup, transport = _lookup()

    lookup.get("AAPL")
    lookup.get("TSLA")
    lookup.get("MSFT")

    assert len(transport.calls) == 1


def test_identifies_itself_to_the_sec():
    # SEC's fair-access policy requires an identifying User-Agent.
    lookup, _ = _lookup()
    captured = {}

    def capture(request):
        captured["user_agent"] = request.headers.get("User-Agent")
        return httpx.Response(200, json=SAMPLE_PAYLOAD, request=request)

    lookup = SecTickerLookup(
        user_agent="Axiom Test (test@example.com)",
        http_client=httpx.Client(transport=httpx.MockTransport(capture)),
    )
    lookup.get("AAPL")

    assert captured["user_agent"] == "Axiom Test (test@example.com)"


def test_raises_a_clear_error_when_sec_is_unreachable():
    lookup, _ = _lookup(status_code=503)

    with pytest.raises(SecTickerLookupError):
        lookup.get("AAPL")


def test_search_finds_a_company_by_name_not_just_ticker():
    # The case that motivated this: searching "tesla" should surface TSLA.
    # A user looking for a company generally knows its name, not its ticker.
    lookup, _ = _lookup()

    matches = lookup.search("tesla")

    assert [m.ticker for m in matches] == ["TSLA"]


def test_search_finds_a_company_by_ticker():
    lookup, _ = _lookup()

    matches = lookup.search("tsla")

    assert [m.ticker for m in matches] == ["TSLA"]


def test_search_ranks_exact_ticker_matches_first():
    # "MSFT" the ticker should outrank a company whose *name* merely
    # contains the string.
    lookup, _ = _lookup(
        payload={
            "0": {"cik_str": 1, "ticker": "XMSFT", "title": "Not Microsoft Holdings"},
            "1": {"cik_str": 789019, "ticker": "MSFT", "title": "Microsoft Corp"},
        }
    )

    matches = lookup.search("MSFT")

    assert matches[0].ticker == "MSFT"


def test_search_returns_nothing_for_gibberish():
    lookup, _ = _lookup()

    assert lookup.search("zzzzqqqq") == []


def test_search_caps_how_many_matches_it_returns():
    payload = {
        str(i): {"cik_str": i, "ticker": f"BNK{i}", "title": f"Bank Holding {i}"}
        for i in range(50)
    }
    lookup, _ = _lookup(payload=payload)

    assert len(lookup.search("bank", limit=5)) == 5
