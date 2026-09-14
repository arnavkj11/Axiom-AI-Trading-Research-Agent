"""Dependencies for running research in the background.

Both of these hand back a *factory* rather than a ready-made object, for
one reason: a research run executes in a FastAPI BackgroundTask, which
starts after the request has finished and after get_db's `finally` has
already closed the request's Session. Anything bound to that Session is
unusable by then, so the task builds its own.
"""

from collections.abc import Callable

from fastapi import Depends
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.filings.dependencies import get_voyage_client
from app.filings.search import VoyageFilingSearchClient
from app.filings.voyage_client import VoyageEmbeddingClient


def get_session_factory() -> Callable[[], Session]:
    """The session factory a background research run opens its own session
    from. Overridden in tests to point at the test database.
    """
    return SessionLocal


def get_filing_search_client_factory(
    voyage_client: VoyageEmbeddingClient = Depends(get_voyage_client),
) -> Callable[[Session], VoyageFilingSearchClient]:
    """Builds a Filing Analyst search client against whichever Session the
    background task opened, since VoyageFilingSearchClient binds to one.
    """
    return lambda db: VoyageFilingSearchClient(db=db, voyage_client=voyage_client)
