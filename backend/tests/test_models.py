from datetime import date

from app.company.models import Company
from app.research.models import ResearchRun, ResearchRunStatus


def test_company_created_at_and_updated_at_populated_by_db(db_session):
    company = Company(ticker="AAPL", name="Apple Inc.")
    db_session.add(company)
    db_session.commit()
    db_session.refresh(company)

    assert company.created_at is not None
    assert company.updated_at is not None


def test_research_run_defaults_to_pending_status_and_todays_date(db_session):
    company = Company(ticker="AAPL", name="Apple Inc.")
    db_session.add(company)
    db_session.commit()

    run = ResearchRun(company_id=company.id)
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)

    assert run.status == ResearchRunStatus.PENDING
    assert run.research_date == date.today()
    assert run.started_at is None
    assert run.completed_at is None
