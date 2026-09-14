import pytest

from app.financials.calculations import (
    free_cash_flow,
    gross_margin,
    operating_margin,
    revenue_growth,
)


def test_gross_margin_divides_gross_profit_by_revenue():
    assert gross_margin(revenue=200.0, gross_profit=80.0) == 0.4


def test_gross_margin_returns_none_when_revenue_is_zero():
    assert gross_margin(revenue=0.0, gross_profit=80.0) is None


def test_gross_margin_returns_none_when_gross_profit_is_none():
    assert gross_margin(revenue=200.0, gross_profit=None) is None


def test_operating_margin_divides_operating_income_by_revenue():
    assert operating_margin(revenue=200.0, operating_income=30.0) == 0.15


def test_operating_margin_returns_none_when_revenue_is_zero():
    assert operating_margin(revenue=0.0, operating_income=30.0) is None


def test_free_cash_flow_adds_capex_to_operating_cash_flow():
    # Alpha Vantage reports capitalExpenditures as a negative outflow.
    assert free_cash_flow(operating_cash_flow=100.0, capex=-40.0) == 60.0


def test_free_cash_flow_returns_none_when_operating_cash_flow_missing():
    assert free_cash_flow(operating_cash_flow=None, capex=-40.0) is None


def test_free_cash_flow_returns_none_when_capex_missing():
    assert free_cash_flow(operating_cash_flow=100.0, capex=None) is None


def test_revenue_growth_computes_year_over_year_change():
    assert revenue_growth(current_revenue=110.0, previous_revenue=100.0) == pytest.approx(0.1)


def test_revenue_growth_returns_none_when_previous_revenue_is_zero():
    assert revenue_growth(current_revenue=110.0, previous_revenue=0.0) is None


def test_revenue_growth_returns_none_when_current_revenue_missing():
    assert revenue_growth(current_revenue=None, previous_revenue=100.0) is None
