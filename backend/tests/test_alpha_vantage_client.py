from datetime import date

import httpx
import pytest

from app.financials.alpha_vantage_client import AlphaVantageClient, AlphaVantageError
from app.financials.models import PeriodType


def _client_with_response(payload: dict, status_code: int = 200) -> AlphaVantageClient:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json=payload)

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    return AlphaVantageClient(api_key="test-key", http_client=http_client)


def test_get_income_statement_parses_annual_and_quarterly_reports():
    payload = {
        "annualReports": [
            {
                "fiscalDateEnding": "2024-09-28",
                "totalRevenue": "391035000000",
                "grossProfit": "180683000000",
                "operatingIncome": "123216000000",
                "netIncome": "93736000000",
            }
        ],
        "quarterlyReports": [
            {
                "fiscalDateEnding": "2024-06-29",
                "totalRevenue": "85777000000",
                "grossProfit": "39678000000",
                "operatingIncome": "25352000000",
                "netIncome": "21448000000",
            }
        ],
    }
    client = _client_with_response(payload)

    periods = client.get_income_statement("AAPL")

    annual = next(p for p in periods if p.period_type == PeriodType.ANNUAL)
    quarterly = next(p for p in periods if p.period_type == PeriodType.QUARTERLY)
    assert annual.period_end == date(2024, 9, 28)
    assert annual.revenue == 391035000000.0
    assert annual.gross_profit == 180683000000.0
    assert quarterly.period_end == date(2024, 6, 29)
    assert quarterly.revenue == 85777000000.0


def test_get_income_statement_treats_none_string_as_missing():
    payload = {
        "annualReports": [
            {
                "fiscalDateEnding": "2024-09-28",
                "totalRevenue": "None",
                "grossProfit": "None",
                "operatingIncome": "None",
                "netIncome": "None",
            }
        ],
        "quarterlyReports": [],
    }
    client = _client_with_response(payload)

    periods = client.get_income_statement("AAPL")

    assert periods[0].revenue is None


def test_raises_on_rate_limit_note():
    payload = {"Note": "Thank you for using Alpha Vantage! Our standard API call frequency is ..."}
    client = _client_with_response(payload)

    with pytest.raises(AlphaVantageError):
        client.get_income_statement("AAPL")


def test_raises_on_invalid_symbol_error_message():
    payload = {"Error Message": "Invalid API call."}
    client = _client_with_response(payload)

    with pytest.raises(AlphaVantageError):
        client.get_income_statement("NOTATICKER")


def test_get_cash_flow_parses_capex_and_operating_cash_flow():
    payload = {
        "annualReports": [
            {
                "fiscalDateEnding": "2024-09-28",
                "operatingCashflow": "118254000000",
                "capitalExpenditures": "-9447000000",
            }
        ],
        "quarterlyReports": [],
    }
    client = _client_with_response(payload)

    periods = client.get_cash_flow("AAPL")

    assert periods[0].operating_cash_flow == 118254000000.0
    assert periods[0].capex == -9447000000.0


def test_get_balance_sheet_parses_debt_cash_and_share_count():
    payload = {
        "annualReports": [
            {
                "fiscalDateEnding": "2024-09-28",
                "shortLongTermDebtTotal": "106629000000",
                "cashAndCashEquivalentsAtCarryingValue": "29943000000",
                "commonStockSharesOutstanding": "15116786000",
            }
        ],
        "quarterlyReports": [],
    }
    client = _client_with_response(payload)

    periods = client.get_balance_sheet("AAPL")

    assert periods[0].debt == 106629000000.0
    assert periods[0].cash == 29943000000.0
    assert periods[0].share_count == 15116786000.0


def test_get_earnings_parses_reported_eps():
    payload = {
        "annualEarnings": [{"fiscalDateEnding": "2024-09-28", "reportedEPS": "6.11"}],
        "quarterlyEarnings": [{"fiscalDateEnding": "2024-06-29", "reportedEPS": "1.4"}],
    }
    client = _client_with_response(payload)

    periods = client.get_earnings("AAPL")

    annual = next(p for p in periods if p.period_type == PeriodType.ANNUAL)
    assert annual.eps == 6.11


def test_throttles_between_consecutive_requests(monkeypatch):
    sleep_calls = []
    monkeypatch.setattr("app.financials.alpha_vantage_client.time.sleep", sleep_calls.append)
    payload = {"annualReports": [], "quarterlyReports": []}
    client = _client_with_response(payload)

    client.get_income_statement("AAPL")
    client.get_cash_flow("AAPL")

    assert len(sleep_calls) == 1
    assert sleep_calls[0] > 0


def test_does_not_throttle_the_first_request(monkeypatch):
    sleep_calls = []
    monkeypatch.setattr("app.financials.alpha_vantage_client.time.sleep", sleep_calls.append)
    payload = {"annualReports": [], "quarterlyReports": []}
    client = _client_with_response(payload)

    client.get_income_statement("AAPL")

    assert not sleep_calls
