"""Import every domain model so Base.metadata is complete.

Anything that needs the full schema — Alembic autogenerate,
metadata.create_all() in tests — should import Base from here, not from
app.db.base directly. Domain model modules import Base from app.db.base
(never from here), which keeps this a one-way dependency and avoids a
circular import between db.base and the domain packages.
"""

# pylint: disable=unused-import
from app.company.models import Company  # noqa: F401
from app.db.base import Base
from app.filings.models import Filing, FilingChunk  # noqa: F401
from app.financials.models import FinancialMetric  # noqa: F401
from app.research.models import ResearchRun  # noqa: F401
# pylint: enable=unused-import

__all__ = ["Base"]
