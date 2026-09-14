"""API tests for triggering and polling research runs.

Starlette's TestClient runs BackgroundTasks to completion before handing
back the response, so a POST here synchronously drives the whole
seven-agent graph — no polling or sleeps needed to observe the terminal
state.
"""

from datetime import date

import pytest
from sqlalchemy.orm import sessionmaker

from app.agents.debate_common import RebuttalAlreadyRecordedError, RebuttalResponse
from app.agents.dependencies import get_llm_client
from app.company.models import Company
from app.financials.models import FinancialMetric, MetricName, PeriodType
from app.main import app
from app.research.dependencies import get_filing_search_client_factory, get_session_factory
from app.research.models import ResearchRun, ResearchRunStatus
from tests.fakes import (
    FILING_CHUNK,
    FakeFilingSearchClient,
    RoutingFakeLLMClient,
    all_agent_responses,
    bull_case,
    judge_verdict,
)


@pytest.fixture()
def company(db_session) -> Company:
    company = Company(ticker="AAPL", name="Apple Inc.", cik="0000320193")
    db_session.add(company)
    db_session.flush()
    db_session.add_all(
        [
            FinancialMetric(
                company_id=company.id,
                metric_name=MetricName.FREE_CASH_FLOW.value,
                period_end=date(2026, 6, 30),
                period_type=PeriodType.ANNUAL,
                value=100.0,
                source="ALPHA_VANTAGE",
            ),
            FinancialMetric(
                company_id=company.id,
                metric_name=MetricName.SHARE_COUNT.value,
                period_end=date(2026, 6, 30),
                period_type=PeriodType.ANNUAL,
                value=1000.0,
                source="ALPHA_VANTAGE",
            ),
        ]
    )
    db_session.commit()
    return company


@pytest.fixture()
def pipeline(db_session):
    """Points the background task's dependencies at the test database and
    fake agents. Returns a setter so a test can swap in an LLM client that
    fails partway through the pipeline.
    """
    session_factory = sessionmaker(bind=db_session.get_bind())
    app.dependency_overrides[get_session_factory] = lambda: session_factory
    app.dependency_overrides[get_filing_search_client_factory] = lambda: (
        lambda db: FakeFilingSearchClient(default=[FILING_CHUNK])
    )

    def use_llm_client(llm_client):
        app.dependency_overrides[get_llm_client] = lambda: llm_client

    use_llm_client(RoutingFakeLLMClient(all_agent_responses()))
    yield use_llm_client
    app.dependency_overrides.clear()


def _run_row(db_session, run_id: int) -> ResearchRun:
    # The background task committed on its own session; expire the test
    # session's identity map so we read the row back rather than a stale
    # cached copy. (Production gets a fresh session per request.)
    db_session.expire_all()
    return db_session.get(ResearchRun, run_id)


def test_post_research_creates_pending_run_and_returns_its_id(client, company, pipeline):
    response = client.post(f"/companies/{company.ticker}/research")

    assert response.status_code == 202
    body = response.json()
    assert body["ticker"] == "AAPL"
    # The response is serialized before background tasks run, so the
    # caller always sees the run at its starting status.
    assert body["status"] == ResearchRunStatus.PENDING.value
    assert isinstance(body["research_run_id"], int)


def test_post_research_returns_404_for_unknown_ticker(client, pipeline):
    response = client.post("/companies/NOPE/research")

    assert response.status_code == 404


def test_completed_run_reports_complete_with_the_full_report(client, db_session, company, pipeline):
    run_id = client.post(f"/companies/{company.ticker}/research").json()["research_run_id"]

    response = client.get(f"/research/{run_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == ResearchRunStatus.COMPLETE.value
    assert body["error"] is None
    report = body["report"]
    assert report["judge_verdict"]["conviction"] == judge_verdict().conviction
    assert report["judge_verdict"]["synthesis"] == judge_verdict().synthesis
    assert report["bull_case"]["thesis"] == bull_case().thesis
    assert report["fundamental_analysis"] is not None
    assert report["filing_analysis"] is not None
    assert report["valuation_output"] is not None
    assert report["bear_case"] is not None


def test_status_endpoint_returns_only_the_status(client, company, pipeline):
    run_id = client.post(f"/companies/{company.ticker}/research").json()["research_run_id"]

    response = client.get(f"/research/{run_id}/status")

    assert response.status_code == 200
    assert response.json() == {
        "research_run_id": run_id,
        "status": ResearchRunStatus.COMPLETE.value,
    }


def test_get_research_returns_404_for_unknown_run_id(client):
    assert client.get("/research/4242").status_code == 404
    assert client.get("/research/4242/status").status_code == 404


def test_agent_failure_marks_the_run_failed_rather_than_leaving_it_running(
    client, db_session, company, pipeline
):
    # The Judge's LLM call blows up midway through the pipeline.
    pipeline(
        RoutingFakeLLMClient(
            all_agent_responses(),
            raise_on={type(judge_verdict()): RuntimeError("anthropic overloaded_error")},
        )
    )

    run_id = client.post(f"/companies/{company.ticker}/research").json()["research_run_id"]

    run = _run_row(db_session, run_id)
    assert run.status == ResearchRunStatus.FAILED
    assert run.status != ResearchRunStatus.RUNNING
    assert "anthropic overloaded_error" in run.error
    assert run.completed_at is not None

    body = client.get(f"/research/{run_id}").json()
    assert body["status"] == ResearchRunStatus.FAILED.value
    assert "anthropic overloaded_error" in body["error"]


def test_rebuttal_already_recorded_error_is_named_in_the_stored_error(
    client, db_session, company, pipeline
):
    # The one-rebuttal-round cap (CLAUDE.md Rule 5) is an architectural
    # invariant, so its violation gets an explicit test rather than only
    # generic coverage via the LLM-failure case above.
    #
    # The exception is raised from the rebuttal node's LLM call rather than
    # by tripping the guard organically, because the graph can't actually
    # reach that guard: bull_analyst already forces rebuttal=None on the
    # opening case (bull.py), so a BullCase arriving at bull_rebuttal with
    # a rebuttal set is unreachable through the real pipeline. The guard's
    # own trigger condition is unit-tested directly in test_orchestrator.py
    # ("test_rebuttal_node_itself_refuses_a_second_round..."); what this
    # test covers is the seam that one doesn't — that when the error does
    # fire mid-graph, the background task records it as FAILED with the
    # type named, instead of stranding the run in RUNNING.
    pipeline(
        RoutingFakeLLMClient(
            all_agent_responses(),
            raise_on={
                RebuttalResponse: RebuttalAlreadyRecordedError(
                    "bull_case already has a recorded rebuttal"
                )
            },
        )
    )

    run_id = client.post(f"/companies/{company.ticker}/research").json()["research_run_id"]

    run = _run_row(db_session, run_id)
    assert run.status == ResearchRunStatus.FAILED
    assert "RebuttalAlreadyRecordedError" in run.error
    assert "already has a recorded rebuttal" in run.error


def test_failed_run_still_exposes_the_agent_outputs_that_did_finish(
    client, db_session, company, pipeline
):
    pipeline(
        RoutingFakeLLMClient(
            all_agent_responses(),
            raise_on={type(judge_verdict()): RuntimeError("judge exploded")},
        )
    )

    run_id = client.post(f"/companies/{company.ticker}/research").json()["research_run_id"]

    body = client.get(f"/research/{run_id}").json()
    assert body["status"] == ResearchRunStatus.FAILED.value
    # Terminal state, so the report is populated even though the run failed
    # — the agents that completed before the Judge are still worth showing.
    assert body["report"] is not None
    assert body["report"]["judge_verdict"] is None


def test_report_is_null_while_a_run_is_still_pending(client, db_session, company):
    # No pipeline fixture here: nothing kicks the run past PENDING, so this
    # is the pre-terminal shape a polling frontend sees.
    run = ResearchRun(company_id=company.id, research_date=date(2026, 9, 7))
    db_session.add(run)
    db_session.commit()

    body = client.get(f"/research/{run.id}").json()

    assert body["status"] == ResearchRunStatus.PENDING.value
    assert body["report"] is None


def test_unknown_ticker_creates_no_research_run(client, db_session, pipeline):
    client.post("/companies/NOPE/research")

    assert db_session.query(ResearchRun).count() == 0


def test_rebuttal_response_type_is_what_the_debate_nodes_request():
    # Guards the raise_on keys used above: if the rebuttal nodes ever stop
    # requesting RebuttalResponse, the failure-path tests would silently
    # stop simulating a mid-debate failure.
    assert RebuttalResponse in all_agent_responses()
