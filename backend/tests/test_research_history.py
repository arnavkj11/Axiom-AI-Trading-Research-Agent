"""Listing past research runs.

Runs were fully persisted but unreachable: the only route to a report was
GET /research/{id}, and nothing told you what ids existed. This is the
index that makes stored history findable.

Summaries only — a list must not carry six JSONB blobs per row.
"""

from datetime import date, datetime, timezone

import pytest

from app.agents.schemas import (
    BullCase,
    Finding,
    FinancialMetricEvidence,
    FundamentalAnalysis,
    JudgeVerdict,
    Stance,
)
from app.company.models import Company
from app.financials.models import MetricName
from app.research.models import ResearchRun, ResearchRunStatus
from app.research.schemas import ResearchState
from app.research.service import save_research_state

EVIDENCE = FinancialMetricEvidence(
    metric_id=1, metric_name=MetricName.OPERATING_MARGIN, period_end=date(2026, 6, 30), value=0.34
)


@pytest.fixture()
def companies(db_session) -> dict[str, Company]:
    made = {}
    for ticker, name in (("AAPL", "Apple Inc."), ("NVDA", "NVIDIA Corp")):
        company = Company(ticker=ticker, name=name, cik=f"000{len(made)}")
        db_session.add(company)
        made[ticker] = company
    db_session.commit()
    return made


def _run(db_session, company: Company, research_date: date) -> ResearchRun:
    run = ResearchRun(company_id=company.id, research_date=research_date)
    db_session.add(run)
    db_session.commit()
    return run


def _complete(db_session, run: ResearchRun, company: Company, *, stance, conviction):
    state = ResearchState(
        research_run_id=run.id,
        company_id=company.id,
        ticker=company.ticker,
        research_date=run.research_date,
        fundamental_analysis=FundamentalAnalysis(
            stance=stance, confidence=0.8, findings=[]
        ),
        bull_case=BullCase(thesis="Up.", confidence=0.7, findings=[]),
        judge_verdict=JudgeVerdict(
            stance=stance,
            conviction=conviction,
            synthesis="Weighed.",
            bull_summary="b",
            bear_summary="b",
            rebuttal_summary="r",
            key_findings=[
                Finding(claim="Margin expanded", importance=0.9, evidence=[EVIDENCE])
            ],
        ),
    )
    save_research_state(db_session, state)


def test_lists_runs_for_one_company(client, db_session, companies):
    apple_run = _run(db_session, companies["AAPL"], date(2026, 9, 7))
    _complete(db_session, apple_run, companies["AAPL"], stance=Stance.BULLISH, conviction=64)
    nvda_run = _run(db_session, companies["NVDA"], date(2026, 9, 8))
    _complete(db_session, nvda_run, companies["NVDA"], stance=Stance.NEUTRAL, conviction=58)

    runs = client.get("/research", params={"ticker": "AAPL"}).json()["runs"]

    assert [r["research_run_id"] for r in runs] == [apple_run.id]
    assert runs[0]["ticker"] == "AAPL"


def test_ticker_filter_is_case_insensitive(client, db_session, companies):
    run = _run(db_session, companies["AAPL"], date(2026, 9, 7))
    _complete(db_session, run, companies["AAPL"], stance=Stance.BULLISH, conviction=64)

    assert len(client.get("/research", params={"ticker": "aapl"}).json()["runs"]) == 1


def test_lists_every_company_when_no_ticker_given(client, db_session, companies):
    _run(db_session, companies["AAPL"], date(2026, 9, 7))
    _run(db_session, companies["NVDA"], date(2026, 9, 8))

    runs = client.get("/research").json()["runs"]

    assert {r["ticker"] for r in runs} == {"AAPL", "NVDA"}


def test_newest_run_comes_first(client, db_session, companies):
    older = _run(db_session, companies["AAPL"], date(2026, 9, 1))
    newer = _run(db_session, companies["AAPL"], date(2026, 9, 8))

    runs = client.get("/research", params={"ticker": "AAPL"}).json()["runs"]

    assert [r["research_run_id"] for r in runs] == [newer.id, older.id]


def test_summary_carries_the_verdict_headline(client, db_session, companies):
    # So the history reads as "NEUTRAL 58" rather than a row of opaque ids.
    run = _run(db_session, companies["NVDA"], date(2026, 9, 8))
    _complete(db_session, run, companies["NVDA"], stance=Stance.NEUTRAL, conviction=58)

    summary = client.get("/research", params={"ticker": "NVDA"}).json()["runs"][0]

    assert summary["stance"] == "NEUTRAL"
    assert summary["conviction"] == 58
    assert summary["status"] == ResearchRunStatus.COMPLETE.value
    assert summary["has_report"] is True


def test_summary_omits_the_full_report(client, db_session, companies):
    # A history list must not ship six JSONB blobs per row.
    run = _run(db_session, companies["AAPL"], date(2026, 9, 7))
    _complete(db_session, run, companies["AAPL"], stance=Stance.BULLISH, conviction=64)

    summary = client.get("/research", params={"ticker": "AAPL"}).json()["runs"][0]

    assert "report" not in summary
    assert "judge_verdict" not in summary


def test_run_with_no_stored_outputs_is_flagged_as_reportless(client, db_session, companies):
    # Runs predating the persistence layer are COMPLETE but stored nothing.
    # Flagging them stops the UI linking to a page that renders empty.
    run = _run(db_session, companies["AAPL"], date(2026, 9, 1))
    run.status = ResearchRunStatus.COMPLETE
    run.completed_at = datetime.now(timezone.utc)
    db_session.commit()

    summary = client.get("/research", params={"ticker": "AAPL"}).json()["runs"][0]

    assert summary["has_report"] is False
    assert summary["stance"] is None


def test_failed_run_carries_its_error(client, db_session, companies):
    # A billing failure should be readable from the list, without opening it.
    run = _run(db_session, companies["AAPL"], date(2026, 9, 8))
    run.status = ResearchRunStatus.FAILED
    run.error = "BadRequestError: credit balance is too low"
    db_session.commit()

    summary = client.get("/research", params={"ticker": "AAPL"}).json()["runs"][0]

    assert summary["status"] == ResearchRunStatus.FAILED.value
    assert "credit balance" in summary["error"]


def test_partial_run_keeps_what_it_stored(client, db_session, companies):
    # Failed midway: some agent outputs landed, the verdict never did.
    run = _run(db_session, companies["AAPL"], date(2026, 9, 8))
    state = ResearchState(
        research_run_id=run.id,
        company_id=companies["AAPL"].id,
        ticker="AAPL",
        research_date=run.research_date,
        fundamental_analysis=FundamentalAnalysis(
            stance=Stance.BULLISH, confidence=0.8, findings=[]
        ),
        error="judge timed out",
    )
    save_research_state(db_session, state)

    summary = client.get("/research", params={"ticker": "AAPL"}).json()["runs"][0]

    assert summary["status"] == ResearchRunStatus.FAILED.value
    assert summary["has_report"] is True  # partial work is still worth opening
    assert summary["stance"] is None


def test_limit_caps_the_listing(client, db_session, companies):
    for day in range(1, 6):
        _run(db_session, companies["AAPL"], date(2026, 9, day))

    runs = client.get("/research", params={"ticker": "AAPL", "limit": 3}).json()["runs"]

    assert len(runs) == 3


def test_unknown_ticker_is_rejected(client, db_session, companies):
    assert client.get("/research", params={"ticker": "ZZZZ"}).status_code == 404


def test_company_with_no_runs_lists_nothing(client, db_session, companies):
    assert client.get("/research", params={"ticker": "NVDA"}).json()["runs"] == []
