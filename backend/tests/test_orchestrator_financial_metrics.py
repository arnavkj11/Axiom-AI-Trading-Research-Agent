from datetime import date

from app.company.models import Company
from app.financials.models import FinancialMetric, MetricName, PeriodType
from app.financials.service import (
    ANNUAL_PERIODS_LIMIT,
    QUARTERLY_PERIODS_LIMIT,
    load_recent_financial_metrics,
)


def _make_company(db_session) -> Company:
    company = Company(ticker="AAPL", name="Apple Inc.", cik="0000320193")
    db_session.add(company)
    db_session.commit()
    return company


def _add_metric(db_session, company, period_end, period_type, metric_name=MetricName.REVENUE, value=1.0):
    db_session.add(
        FinancialMetric(
            company_id=company.id,
            metric_name=metric_name.value,
            period_end=period_end,
            period_type=period_type,
            value=value,
            source="ALPHA_VANTAGE",
        )
    )


def test_load_recent_financial_metrics_caps_annual_periods(db_session):
    # Regression test for a real bug from a live run: AAPL had 1,045
    # historical FinancialMetric rows, all loaded unfiltered into the
    # Fundamental Analyst's prompt (43K input tokens, 25.6s for one call —
    # the single largest cost/latency driver in the whole pipeline).
    company = _make_company(db_session)
    # 8 annual periods, 1 metric each — more than ANNUAL_PERIODS_LIMIT.
    for year in range(2018, 2026):
        _add_metric(db_session, company, date(year, 9, 30), PeriodType.ANNUAL)
    db_session.commit()

    metrics = load_recent_financial_metrics(db_session, company.id)

    assert len(metrics) == ANNUAL_PERIODS_LIMIT
    included_years = {m.period_end.year for m in metrics}
    assert included_years == set(range(2026 - ANNUAL_PERIODS_LIMIT, 2026))


def test_load_recent_financial_metrics_caps_quarterly_periods_independently_of_annual(db_session):
    company = _make_company(db_session)
    for year in range(2018, 2026):
        _add_metric(db_session, company, date(year, 9, 30), PeriodType.ANNUAL)
    # 10 quarters — more than QUARTERLY_PERIODS_LIMIT.
    for i in range(10):
        month = 3 + 3 * (i % 4)
        year = 2024 - (i // 4)
        _add_metric(db_session, company, date(year, month, 28), PeriodType.QUARTERLY)
    db_session.commit()

    metrics = load_recent_financial_metrics(db_session, company.id)

    annual_count = sum(1 for m in metrics if m.period_type == PeriodType.ANNUAL)
    quarterly_count = sum(1 for m in metrics if m.period_type == PeriodType.QUARTERLY)
    assert annual_count == ANNUAL_PERIODS_LIMIT
    assert quarterly_count == QUARTERLY_PERIODS_LIMIT


def test_load_recent_financial_metrics_includes_all_metrics_within_kept_periods(db_session):
    company = _make_company(db_session)
    # Two metrics in the same (most-recent) period should both survive.
    _add_metric(db_session, company, date(2026, 9, 30), PeriodType.ANNUAL, MetricName.REVENUE)
    _add_metric(db_session, company, date(2026, 9, 30), PeriodType.ANNUAL, MetricName.NET_INCOME)
    db_session.commit()

    metrics = load_recent_financial_metrics(db_session, company.id)

    metric_names = {m.metric_name for m in metrics}
    assert metric_names == {MetricName.REVENUE, MetricName.NET_INCOME}


def test_load_recent_financial_metrics_scoped_to_one_company(db_session):
    company_a = _make_company(db_session)
    company_b = Company(ticker="MSFT", name="Microsoft Corp.", cik="0000789019")
    db_session.add(company_b)
    db_session.commit()
    _add_metric(db_session, company_a, date(2026, 9, 30), PeriodType.ANNUAL)
    _add_metric(db_session, company_b, date(2026, 6, 30), PeriodType.ANNUAL)
    db_session.commit()

    metrics = load_recent_financial_metrics(db_session, company_a.id)

    assert len(metrics) == 1
