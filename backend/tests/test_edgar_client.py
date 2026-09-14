from datetime import date, datetime, timezone

import httpx
import pytest

from app.filings.edgar_client import EdgarClient, EdgarError

SUBMISSIONS_PAYLOAD = {
    "cik": "320193",
    "filings": {
        "recent": {
            "accessionNumber": [
                "0000320193-24-000123",
                "0000320193-24-000045",
                "0001140361-23-012345",
            ],
            "filingDate": ["2024-11-01", "2024-08-01", "2023-01-15"],
            "reportDate": ["2024-09-28", "2024-06-29", ""],
            "acceptanceDateTime": [
                "2024-11-01T18:05:00.000Z",
                "2024-08-01T16:30:00.000Z",
                "2023-01-15T20:00:00.000Z",
            ],
            "form": ["10-K", "10-Q", "4"],
            "primaryDocument": ["aapl-20240928.htm", "aapl-20240629.htm", "xslF345X03.xml"],
        }
    },
}


def _client_with_json(payload: dict, expected_headers: dict | None = None) -> EdgarClient:
    def handler(request: httpx.Request) -> httpx.Response:
        if expected_headers:
            for key, value in expected_headers.items():
                assert request.headers[key] == value
        return httpx.Response(200, json=payload)

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    return EdgarClient(user_agent="Axiom test@example.com", http_client=http_client)


def test_get_recent_filings_sends_required_user_agent_header():
    client = _client_with_json(
        SUBMISSIONS_PAYLOAD, expected_headers={"User-Agent": "Axiom test@example.com"}
    )

    client.get_recent_filings("0000320193")


def test_get_recent_filings_filters_to_requested_form_types():
    client = _client_with_json(SUBMISSIONS_PAYLOAD)

    filings = client.get_recent_filings("0000320193", form_types=("10-K", "10-Q", "8-K"))

    assert {f.form_type for f in filings} == {"10-K", "10-Q"}
    assert len(filings) == 2


def test_get_recent_filings_parses_dates_correctly():
    client = _client_with_json(SUBMISSIONS_PAYLOAD)

    filings = client.get_recent_filings("0000320193", form_types=("10-K",))

    ten_k = filings[0]
    assert ten_k.accession_number == "0000320193-24-000123"
    assert ten_k.filing_date == date(2024, 11, 1)
    assert ten_k.period_end == date(2024, 9, 28)
    assert ten_k.published_at == datetime(2024, 11, 1, 18, 5, 0, tzinfo=timezone.utc)
    assert ten_k.primary_document == "aapl-20240928.htm"


def test_get_recent_filings_raises_on_non_200():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, text="forbidden")

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = EdgarClient(user_agent="Axiom test@example.com", http_client=http_client)

    with pytest.raises(EdgarError):
        client.get_recent_filings("0000320193")


def test_get_document_text_strips_html_to_plain_text():
    html = "<html><body><p>Item 1A. Risk Factors</p><p>We face risks.</p></body></html>"

    def handler(request: httpx.Request) -> httpx.Response:
        assert "320193/000032019324000123/aapl-20240928.htm" in str(request.url)
        return httpx.Response(200, text=html)

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = EdgarClient(user_agent="Axiom test@example.com", http_client=http_client)

    text = client.get_document_text("0000320193", "0000320193-24-000123", "aapl-20240928.htm")

    assert "Item 1A. Risk Factors" in text
    assert "We face risks." in text
    assert "<p>" not in text


def test_get_document_text_decodes_non_utf8_content_correctly():
    # cp1252-encoded right single quote (0x92), no charset in the header —
    # matches real EDGAR filings encountered live, where relying on
    # httpx's own encoding guess (via response.text) produced mojibake
    # ("Management�s Discussion") instead of "Management's Discussion".
    html_bytes = "<html><body><p>Management’s Discussion</p></body></html>".encode("cp1252")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=html_bytes, headers={"content-type": "text/html"})

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = EdgarClient(user_agent="Axiom test@example.com", http_client=http_client)

    text = client.get_document_text("0000320193", "0000320193-24-000123", "aapl-20240928.htm")

    assert "Management’s Discussion" in text
    assert "�" not in text
