"""remove duplicate route code index

Revision ID: c2397ed7af93
Revises: fa6a1d2a98f3
Create Date: 2026-11-17 20:55:45.935553

"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "c2397ed7af93"
down_revision: Union[str, Sequence[str], None] = "fa6a1d2a98f3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Remove the redundant unique index on routes.code."""
    op.drop_index("ix_routes_code", table_name="routes")


def downgrade() -> None:
    """Restore the redundant index if this migration is rolled back."""
    op.create_index(
        "ix_routes_code",
        "routes",
        ["code"],
        unique=True,
    )