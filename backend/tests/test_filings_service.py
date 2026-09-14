import pytest

from app.company.models import Company
from app.filings.models import FilingChunk, FilingStatus
from app.filings.service import sync_company_filings
from tests.fakes import FakeEdgarClient, FakeVoyageClient


def _make_company(db_session, cik="0000320193"):
    company = Company(ticker="AAPL", name="Apple Inc.", cik=cik)
    db_session.add(company)
    db_session.commit()
    return company


def test_applies_v1_scope_limits_per_form_type(db_session):
    company = _make_company(db_session)
    edgar = FakeEdgarClient()
    voyage = FakeVoyageClient()

    filings = sync_company_filings(db_session, company, edgar, voyage)

    by_type = {}
    for f in filings:
        by_type[f.form_type] = by_type.get(f.form_type, 0) + 1
    assert by_type == {"10-K": 1, "10-Q": 4, "8-K": 8}


def test_chunks_and_embeds_each_new_filing(db_session):
    company = _make_company(db_session)
    edgar = FakeEdgarClient()
    voyage = FakeVoyageClient()

    filings = sync_company_filings(db_session, company, edgar, voyage)

    assert all(f.status == FilingStatus.EMBEDDED for f in filings)
    chunks = db_session.query(FilingChunk).filter(
        FilingChunk.filing_id.in_([f.id for f in filings])
    ).all()
    assert len(chunks) > 0
    assert all(c.embedding is not None for c in chunks)
    assert all(c.filing_date is not None and c.published_at is not None for c in chunks)


def test_second_sync_does_not_refetch_already_embedded_filings(db_session):
    company = _make_company(db_session)
    edgar = FakeEdgarClient()
    voyage = FakeVoyageClient()

    sync_company_filings(db_session, company, edgar, voyage)
    documents_fetched_first_pass = len(edgar.document_calls)

    sync_company_filings(db_session, company, edgar, voyage)

    assert documents_fetched_first_pass == 13  # 1 + 4 + 8
    assert len(edgar.document_calls) == documents_fetched_first_pass  # no new fetches
    assert edgar.calls == 2  # still re-lists filings each sync to check for new ones


def test_a_failed_filing_does_not_block_the_others(db_session):
    company = _make_company(db_session)
    edgar = FakeEdgarClient(raise_on_document={"0000320193-24-10K0"})
    voyage = FakeVoyageClient()

    filings = sync_company_filings(db_session, company, edgar, voyage)

    failed = next(f for f in filings if f.accession_number == "0000320193-24-10K0")
    others = [f for f in filings if f.accession_number != "0000320193-24-10K0"]
    assert failed.status == FilingStatus.FAILED
    assert all(f.status == FilingStatus.EMBEDDED for f in others)


def test_raises_clear_error_when_company_has_no_cik(db_session):
    company = Company(ticker="NOCIK", name="No Cik Inc.", cik=None)
    db_session.add(company)
    db_session.commit()

    with pytest.raises(ValueError, match="CIK"):
        sync_company_filings(db_session, company, FakeEdgarClient(), FakeVoyageClient())
