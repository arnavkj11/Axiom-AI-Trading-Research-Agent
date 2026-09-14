from dataclasses import dataclass
from datetime import date, datetime, timezone

import httpx
from bs4 import BeautifulSoup

SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
ARCHIVES_URL = (
    "https://www.sec.gov/Archives/edgar/data/{cik_no_zeros}/{accession_no_dashes}/{document}"
)


class EdgarError(RuntimeError):
    """EDGAR returned a non-2xx response."""


@dataclass
class FilingMetadata:
    accession_number: str
    form_type: str
    filing_date: date
    period_end: date | None
    published_at: datetime
    primary_document: str


def _to_date(raw: str) -> date | None:
    if not raw:
        return None
    return datetime.strptime(raw, "%Y-%m-%d").date()


def _to_datetime(raw: str) -> datetime:
    # EDGAR's acceptanceDateTime looks like "2024-11-01T18:05:00.000Z".
    return datetime.strptime(raw, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)


class EdgarClient:
    """Fetches filing metadata and documents from SEC EDGAR.

    SEC's fair-access policy requires every request to carry an identifying
    User-Agent (name + contact email) or requests get blocked.
    """

    def __init__(self, user_agent: str, http_client: httpx.Client | None = None):
        self._user_agent = user_agent
        self._http = http_client or httpx.Client(timeout=30.0)

    def _headers(self) -> dict[str, str]:
        return {"User-Agent": self._user_agent}

    def get_recent_filings(
        self, cik: str, form_types: tuple[str, ...] = ("10-K", "10-Q", "8-K")
    ) -> list[FilingMetadata]:
        url = SUBMISSIONS_URL.format(cik=cik.zfill(10))
        response = self._http.get(url, headers=self._headers())
        if response.status_code != 200:
            raise EdgarError(
                f"EDGAR submissions request failed ({response.status_code}) for CIK {cik}"
            )
        recent = response.json()["filings"]["recent"]

        filings = []
        for i, form in enumerate(recent["form"]):
            if form not in form_types:
                continue
            filings.append(
                FilingMetadata(
                    accession_number=recent["accessionNumber"][i],
                    form_type=form,
                    filing_date=_to_date(recent["filingDate"][i]),
                    period_end=_to_date(recent["reportDate"][i]),
                    published_at=_to_datetime(recent["acceptanceDateTime"][i]),
                    primary_document=recent["primaryDocument"][i],
                )
            )
        return filings

    def document_url(self, cik: str, accession_number: str, primary_document: str) -> str:
        return ARCHIVES_URL.format(
            cik_no_zeros=str(int(cik)),
            accession_no_dashes=accession_number.replace("-", ""),
            document=primary_document,
        )

    def get_document_text(self, cik: str, accession_number: str, primary_document: str) -> str:
        url = self.document_url(cik, accession_number, primary_document)
        response = self._http.get(url, headers=self._headers())
        if response.status_code != 200:
            raise EdgarError(
                f"EDGAR document request failed ({response.status_code}) for {accession_number}"
            )
        # Pass raw bytes, not response.text — httpx's own encoding guess
        # produces mojibake on filings that declare their charset only in
        # an HTML meta tag (not the Content-Type header). BeautifulSoup's
        # UnicodeDammit sniffs those correctly.
        soup = BeautifulSoup(response.content, "html.parser")
        return soup.get_text(separator="\n")
