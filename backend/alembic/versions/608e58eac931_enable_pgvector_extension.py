"""enable pgvector extension

Revision ID: 608e58eac931
Revises: aa01b9376b50
Create Date: 2026-09-06 22:03:28.223855

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '608e58eac931'
down_revision: Union[str, Sequence[str], None] = 'aa01b9376b50'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP EXTENSION IF EXISTS vector")
