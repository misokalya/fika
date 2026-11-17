
"""add segment journey observations

Revision ID: 76b12b7aba8d
Revises: eb45a9746ac9
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "76b12b7aba8d"
down_revision: Union[str, Sequence[str], None] = "eb45a9746ac9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add nullable segment endpoints to preserve existing observations.
    op.add_column(
        "journey_observations",
        sa.Column("from_stop_id", sa.Integer(), nullable=True),
    )

    op.add_column(
        "journey_observations",
        sa.Column("to_stop_id", sa.Integer(), nullable=True),
    )

    # Existing records receive False.
    op.add_column(
        "journey_observations",
        sa.Column(
            "is_verified",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )

    # Explicitly named foreign keys.
    op.create_foreign_key(
        "fk_journey_observations_from_stop",
        "journey_observations",
        "stops",
        ["from_stop_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    op.create_foreign_key(
        "fk_journey_observations_to_stop",
        "journey_observations",
        "stops",
        ["to_stop_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    # Segment endpoints must either both be present or both be absent.
    op.create_check_constraint(
        "ck_journey_observations_segment_pair",
        "journey_observations",
        """
        (from_stop_id IS NULL AND to_stop_id IS NULL)
        OR
        (from_stop_id IS NOT NULL AND to_stop_id IS NOT NULL)
        """,
    )

    # A journey segment cannot begin and end at the same stop.
    op.create_check_constraint(
        "ck_journey_observations_different_stops",
        "journey_observations",
        "from_stop_id IS NULL OR from_stop_id <> to_stop_id",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_journey_observations_different_stops",
        "journey_observations",
        type_="check",
    )

    op.drop_constraint(
        "ck_journey_observations_segment_pair",
        "journey_observations",
        type_="check",
    )

    op.drop_constraint(
        "fk_journey_observations_to_stop",
        "journey_observations",
        type_="foreignkey",
    )

    op.drop_constraint(
        "fk_journey_observations_from_stop",
        "journey_observations",
        type_="foreignkey",
    )

    op.drop_column("journey_observations", "is_verified")
    op.drop_column("journey_observations", "to_stop_id")
    op.drop_column("journey_observations", "from_stop_id")
