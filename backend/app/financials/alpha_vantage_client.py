import time
from dataclasses import dataclass
from datetime import date, datetime

import httpx

from app.financials.models import PeriodType

BASE_URL = "https://www.alphavantage.co/query"
MIN_SECONDS_BETWEEN_REQUESTS = 2.0


class AlphaVantageError(RuntimeError):
    """Alpha Vantage returned an error or rate-limit response instead of data."""


@dataclass
class IncomeStatementPeriod:
    period_end: date
    period_type: PeriodType
    revenue: float | None
    gross_profit: float | None
    operating_income: float | None
    net_income: float | None


@dataclass
class CashFlowPeriod:
    period_end: date
    period_type: PeriodType
    operating_cash_flow: float | None
    capex: float | None


@dataclass
class BalanceSheetPeriod:
    period_end: date
    period_type: PeriodType
    debt: float | None
    cash: float | None
    share_count: float | None


@dataclass
class EarningsPeriod:
    period_end: date
    period_type: PeriodType
    eps: float | None


@dataclass
class Quote:
    """A share price and the trading day it's from.

    Timestamped because reports are persisted and reopened later — a price
    shown without its as-of date reads as current when it may be weeks old.
    """

    price: float
    as_of: date


@dataclass
class CompanyOverview:
    """Descriptive fields only — the SEC registrant list is the source of
    truth for ticker/name/CIK, so this fills in what it doesn't carry.
    """

    exchange: str | None
    sector: str | None
    industry: str | None


def _to_float(raw: str | None) -> float | None:
    if raw is None or raw == "None":
        return None
    return float(raw)


def _to_date(raw: str) -> date:
    return datetime.strptime(raw, "%Y-%m-%d").date()


def _titleize(raw: str | None) -> str | None:
    # Alpha Vantage returns these SHOUTED ("CONSUMER CYCLICAL"); the UI
    # shows them verbatim alongside the company name.
    return raw.title() if raw else None


class AlphaVantageClient:
    """Thin wrapper around Alpha Vantage's fundamentals endpoints.

    CAVEAT: Alpha Vantage's free tier serves restated financials — the
    numbers as currently reported, not what was known as of `period_end`.
    Fine for V1 (point-in-time cutoff enforcement is a later phase) but
    don't treat these values as historically accurate for as-of-date
    research without revisiting this.
    """

    def __init__(self, api_key: str, http_client: httpx.Client | None = None):
        self._api_key = api_key
        self._http = http_client or httpx.Client(timeout=30.0)
        self._last_request_at: float | None = None

    def _throttle(self) -> None:
        # Free-tier Alpha Vantage rejects bursts faster than 1 req/sec; a
        # single financials fetch fires 4 sequential requests, so without
        # this the second call fails almost every time.
        if self._last_request_at is None:
            return
        elapsed = time.monotonic() - self._last_request_at
        remaining = MIN_SECONDS_BETWEEN_REQUESTS - elapsed
        if remaining > 0:
            time.sleep(remaining)

    def _get(self, function: str, symbol: str) -> dict:
        self._throttle()
        self._last_request_at = time.monotonic()
        response = self._http.get(
            BASE_URL, params={"function": function, "symbol": symbol, "apikey": self._api_key}
        )
        response.raise_for_status()
        data = response.json()
        if "Note" in data:
            raise AlphaVantageError(data["Note"])
        if "Information" in data:
            raise AlphaVantageError(data["Information"])
        if "Error Message" in data:
            raise AlphaVantageError(data["Error Message"])
        return data

    def _parse_periods(self, function, symbol, annual_key, quarterly_key, parser):
        data = self._get(function, symbol)
        return [
            *(parser(r, PeriodType.ANNUAL) for r in data.get(annual_key, [])),
            *(parser(r, PeriodType.QUARTERLY) for r in data.get(quarterly_key, [])),
        ]

    def get_quote(self, symbol: str) -> Quote | None:
        """Latest share price, or None if Alpha Vantage lists no such symbol.

        Deliberately the latest daily quote rather than anything intraday:
        the DCF horizon is years, so sub-daily precision would add cost and
        false precision without changing a verdict.

        Costs one of the free tier's 25 daily requests.
        """
        data = self._get("GLOBAL_QUOTE", symbol).get("Global Quote") or {}
        price = _to_float(data.get("05. price"))
        trading_day = data.get("07. latest trading day")
        if price is None or not trading_day:
            return None
        return Quote(price=price, as_of=_to_date(trading_day))

    def get_company_overview(self, symbol: str) -> CompanyOverview | None:
        """Descriptive company fields, or None if Alpha Vantage has no
        entry for the symbol (it answers with an empty object rather than
        an error for unknown tickers).

        Costs one of the free tier's 25 daily requests.
        """
        data = self._get("OVERVIEW", symbol)
        if not data or not data.get("Symbol"):
            return None
        return CompanyOverview(
            exchange=data.get("Exchange") or None,
            sector=_titleize(data.get("Sector")),
            industry=_titleize(data.get("Industry")),
        )

    def get_income_statement(self, symbol: str) -> list[IncomeStatementPeriod]:
        return self._parse_periods(
            "INCOME_STATEMENT",
            symbol,
            "annualReports",
            "quarterlyReports",
            self._parse_income_report,
        )

    def get_cash_flow(self, symbol: str) -> list[CashFlowPeriod]:
        return self._parse_periods(
            "CASH_FLOW", symbol, "annualReports", "quarterlyReports", self._parse_cash_flow_report
        )

    def get_balance_sheet(self, symbol: str) -> list[BalanceSheetPeriod]:
        return self._parse_periods(
            "BALANCE_SHEET",
            symbol,
            "annualReports",
            "quarterlyReports",
            self._parse_balance_sheet_report,
        )

    def get_earnings(self, symbol: str) -> list[EarningsPeriod]:
        return self._parse_periods(
            "EARNINGS", symbol, "annualEarnings", "quarterlyEarnings", self._parse_earnings_report
        )

    @staticmethod
    def _parse_income_report(report: dict, period_type: PeriodType) -> IncomeStatementPeriod:
        return IncomeStatementPeriod(
            period_end=_to_date(report["fiscalDateEnding"]),
            period_type=period_type,
            revenue=_to_float(report.get("totalRevenue")),
            gross_profit=_to_float(report.get("grossProfit")),
            operating_income=_to_float(report.get("operatingIncome")),
            net_income=_to_float(report.get("netIncome")),
        )

    @staticmethod
    def _parse_cash_flow_report(report: dict, period_type: PeriodType) -> CashFlowPeriod:
        return CashFlowPeriod(
            period_end=_to_date(report["fiscalDateEnding"]),
            period_type=period_type,
            operating_cash_flow=_to_float(report.get("operatingCashflow")),
            capex=_to_float(report.get("capitalExpenditures")),
        )

    @staticmethod
    def _parse_balance_sheet_report(report: dict, period_type: PeriodType) -> BalanceSheetPeriod:
        return BalanceSheetPeriod(
            period_end=_to_date(report["fiscalDateEnding"]),
            period_type=period_type,
            debt=_to_float(report.get("shortLongTermDebtTotal")),
            cash=_to_float(report.get("cashAndCashEquivalentsAtCarryingValue")),
            share_count=_to_float(report.get("commonStockSharesOutstanding")),
        )

    @staticmethod
    def _parse_earnings_report(report: dict, period_type: PeriodType) -> EarningsPeriod:
        return EarningsPeriod(
            period_end=_to_date(report["fiscalDateEnding"]),
            period_type=period_type,
            eps=_to_float(report.get("reportedEPS")),
        )
