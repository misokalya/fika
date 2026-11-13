
"""create initial FIKA transport schema

Revision ID: eb45a9746ac9
Revises:
Create Date: 2026-11-14
"""

from alembic import op
import sqlalchemy as sa
import geoalchemy2

revision = "eb45a9746ac9"
down_revision = None
branch_labels = None
depends_on = None

def upgrade() -> None:
    # Routes
    op.create_table(
        "routes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(length=30), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column(
            "path",
            geoalchemy2.types.Geometry(
                geometry_type="LINESTRING",
                srid=4326,
                spatial_index=False,
            ),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.UniqueConstraint("code"),
    )

    op.create_index("ix_routes_code", "routes", ["code"], unique=True)
    op.create_index(
        "idx_routes_path",
        "routes",
        ["path"],
        postgresql_using="gist",
    )

    # Stops
    op.create_table(
        "stops",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("stop_type", sa.String(length=30), nullable=False),
        sa.Column(
            "location",
            geoalchemy2.types.Geometry(
                geometry_type="POINT",
                srid=4326,
                spatial_index=False,
            ),
            nullable=False,
        ),
        sa.Column("is_verified", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
    )

    op.create_index(
        "idx_stops_location",
        "stops",
        ["location"],
        postgresql_using="gist",
    )

    # Route stops
    op.create_table(
        "route_stops",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("route_id", sa.Integer(), nullable=False),
        sa.Column("stop_id", sa.Integer(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("destination_board", sa.String(length=150), nullable=True),
        sa.CheckConstraint("sequence > 0"),
        sa.ForeignKeyConstraint(
            ["route_id"],
            ["routes.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["stop_id"],
            ["stops.id"],
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("route_id", "sequence"),
        sa.UniqueConstraint("route_id", "stop_id"),
    )

    # Transfers
    op.create_table(
        "transfers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("from_route_id", sa.Integer(), nullable=False),
        sa.Column("to_route_id", sa.Integer(), nullable=False),
        sa.Column("from_stop_id", sa.Integer(), nullable=False),
        sa.Column("to_stop_id", sa.Integer(), nullable=False),
        sa.Column("walking_distance_m", sa.Float(), nullable=True),
        sa.Column("is_verified", sa.Boolean(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "walking_distance_m IS NULL OR walking_distance_m >= 0"
        ),
        sa.CheckConstraint("from_route_id <> to_route_id"),
        sa.ForeignKeyConstraint(
            ["from_route_id"],
            ["routes.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["to_route_id"],
            ["routes.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["from_stop_id"],
            ["stops.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["to_stop_id"],
            ["stops.id"],
            ondelete="RESTRICT",
        ),
    )

    # Vehicle variants
    op.create_table(
        "vehicle_variants",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("route_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("destination_board", sa.String(length=150), nullable=False),
        sa.Column("image_path", sa.String(length=255), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["route_id"],
            ["routes.id"],
            ondelete="CASCADE",
        ),
    )

    # Fares
    op.create_table(
        "fares",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("route_id", sa.Integer(), nullable=False),
        sa.Column("amount_tzs", sa.Float(), nullable=False),
        sa.Column(
            "effective_from",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "effective_until",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column("is_verified", sa.Boolean(), nullable=False),
        sa.CheckConstraint("amount_tzs >= 0"),
        sa.ForeignKeyConstraint(
            ["route_id"],
            ["routes.id"],
            ondelete="CASCADE",
        ),
    )

    # Journey observations
    op.create_table(
        "journey_observations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("route_id", sa.Integer(), nullable=False),
        sa.Column(
            "departure_time",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column("duration_seconds", sa.Integer(), nullable=False),
        sa.Column("wait_seconds", sa.Integer(), nullable=True),
        sa.Column("weekday", sa.Integer(), nullable=True),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.CheckConstraint("duration_seconds > 0"),
        sa.CheckConstraint("wait_seconds IS NULL OR wait_seconds >= 0"),
        sa.CheckConstraint("weekday IS NULL OR weekday BETWEEN 0 AND 6"),
        sa.ForeignKeyConstraint(
            ["route_id"],
            ["routes.id"],
            ondelete="CASCADE",
        ),
    )

    # Reports
    op.create_table(
        "reports",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("report_type", sa.String(length=50), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column(
            "location",
            geoalchemy2.types.Geometry(
                geometry_type="POINT",
                srid=4326,
                spatial_index=False,
            ),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
    )

    op.create_index(
        "idx_reports_location",
        "reports",
        ["location"],
        postgresql_using="gist",
    )

    # Audit logs
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("actor", sa.String(length=100), nullable=False),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("entity_type", sa.String(length=100), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=True),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
    )

def downgrade() -> None:
    op.drop_table("audit_logs")

    op.drop_index("idx_reports_location", table_name="reports")
    op.drop_table("reports")

    op.drop_table("journey_observations")
    op.drop_table("fares")
    op.drop_table("vehicle_variants")
    op.drop_table("transfers")
    op.drop_table("route_stops")

    op.drop_index("idx_stops_location", table_name="stops")
    op.drop_table("stops")

    op.drop_index("idx_routes_path", table_name="routes")
    op.drop_index("ix_routes_code", table_name="routes")
    op.drop_table("routes")