"""Ticker -> CIK lookup against SEC's public registrant list.

A company can't be researched without a CIK (EDGAR's submissions API is
keyed on it) and the CIK isn't derivable from a ticker, so this mapping is
what makes adding a company by ticker possible at all.

Uses https://www.sec.gov/files/company_tickers.json — free, no API key, and
covers every SEC registrant (~10.4k). Alpha Vantage also reports a CIK, but
this is the authoritative source and costs nothing against the 25/day
Alpha Vantage budget.
"""

from dataclasses import dataclass

import httpx

COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"


class SecTickerLookupError(RuntimeError):
    """SEC's registrant list couldn't be fetched or parsed."""


@dataclass(frozen=True)
class SecTickerRecord:
    ticker: str
    name: str
    cik: str


class SecTickerLookup:
    """Fetches the registrant list once, then answers lookups from memory.

    The mapping is ~10k entries and changes rarely (new registrants), so
    one fetch per process is both sufficient and the polite thing to do
    under SEC's fair-access policy. A long-lived process won't see a
    company that registered after startup — acceptable in V1, and a
    restart picks it up.
    """

    def __init__(self, user_agent: str, http_client: httpx.Client | None = None):
        self._user_agent = user_agent
        self._http = http_client or httpx.Client(timeout=30.0)
        self._by_ticker: dict[str, SecTickerRecord] | None = None

    def get(self, ticker: str) -> SecTickerRecord | None:
        """The registrant for `ticker`, or None if the SEC doesn't list it."""
        return self._mapping().get(ticker.upper())

    def search(self, query: str, limit: int = 10) -> list[SecTickerRecord]:
        """Registrants whose ticker or name matches `query`.

        Exists because people search for "tesla", not "TSLA" — without a
        name search, a company nobody had added by exact ticker was
        effectively unreachable.
        """
        needle = query.strip().lower()
        if not needle:
            return []

        matches = [
            record
            for record in self._mapping().values()
            if needle in record.ticker.lower() or needle in record.name.lower()
        ]
        # Exact ticker first, then ticker prefix, then name matches — so
        # searching "MSFT" doesn't bury Microsoft under companies whose
        # names happen to contain the string.
        matches.sort(
            key=lambda record: (
                record.ticker.lower() != needle,
                not record.ticker.lower().startswith(needle),
                not record.name.lower().startswith(needle),
                len(record.name),
            )
        )
        return matches[:limit]

    def _mapping(self) -> dict[str, SecTickerRecord]:
        if self._by_ticker is None:
            self._by_ticker = self._load()
        return self._by_ticker

    def _load(self) -> dict[str, SecTickerRecord]:
        try:
            response = self._http.get(
                COMPANY_TICKERS_URL, headers={"User-Agent": self._user_agent}
            )
        except httpx.HTTPError as exc:
            raise SecTickerLookupError(f"Could not reach SEC: {exc}") from exc

        if response.status_code != 200:
            raise SecTickerLookupError(
                f"SEC registrant list request failed ({response.status_code})"
            )

        try:
            # Shaped as an object keyed by row index, not a list.
            rows = response.json().values()
        except ValueError as exc:
            raise SecTickerLookupError("SEC registrant list was not valid JSON") from exc

        return {
            row["ticker"].upper(): SecTickerRecord(
                ticker=row["ticker"].upper(),
                name=row["title"],
                # EDGAR's submissions API wants the CIK zero-padded to 10.
                cik=str(row["cik_str"]).zfill(10),
            )
            for row in rows
            if row.get("ticker")
        }
