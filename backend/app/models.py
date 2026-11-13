
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column
from geoalchemy2 import Geometry

from app.database import Base


def utc_now():
    return datetime.now(timezone.utc)


class Route(Base):
    __tablename__ = "routes"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(150))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    path: Mapped[object | None] = mapped_column(
        Geometry("LINESTRING", srid=4326, spatial_index=False),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
    )

    __table_args__ = (
        Index("idx_routes_path", "path", postgresql_using="gist"),
    )


class Stop(Base):
    __tablename__ = "stops"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    stop_type: Mapped[str] = mapped_column(String(30), default="informal")

    location: Mapped[object] = mapped_column(
        Geometry("POINT", srid=4326, spatial_index=False)
    )

    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
    )

    __table_args__ = (
        Index("idx_stops_location", "location", postgresql_using="gist"),
    )


class RouteStop(Base):
    __tablename__ = "route_stops"

    id: Mapped[int] = mapped_column(primary_key=True)

    route_id: Mapped[int] = mapped_column(
        ForeignKey("routes.id", ondelete="CASCADE")
    )

    stop_id: Mapped[int] = mapped_column(
        ForeignKey("stops.id", ondelete="RESTRICT")
    )

    sequence: Mapped[int] = mapped_column(Integer)

    destination_board: Mapped[str | None] = mapped_column(
        String(150),
        nullable=True,
    )

    __table_args__ = (
        UniqueConstraint("route_id", "sequence"),
        UniqueConstraint("route_id", "stop_id"),
        CheckConstraint("sequence > 0"),
    )


class Transfer(Base):
    __tablename__ = "transfers"

    id: Mapped[int] = mapped_column(primary_key=True)

    from_route_id: Mapped[int] = mapped_column(
        ForeignKey("routes.id", ondelete="CASCADE")
    )

    to_route_id: Mapped[int] = mapped_column(
        ForeignKey("routes.id", ondelete="CASCADE")
    )

    from_stop_id: Mapped[int] = mapped_column(
        ForeignKey("stops.id", ondelete="RESTRICT")
    )

    to_stop_id: Mapped[int] = mapped_column(
        ForeignKey("stops.id", ondelete="RESTRICT")
    )

    walking_distance_m: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint("walking_distance_m IS NULL OR walking_distance_m >= 0"),
        CheckConstraint("from_route_id <> to_route_id"),
    )


class VehicleVariant(Base):
    __tablename__ = "vehicle_variants"

    id: Mapped[int] = mapped_column(primary_key=True)

    route_id: Mapped[int] = mapped_column(
        ForeignKey("routes.id", ondelete="CASCADE")
    )

    name: Mapped[str] = mapped_column(String(100))
    destination_board: Mapped[str] = mapped_column(String(150))

    image_path: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Fare(Base):
    __tablename__ = "fares"

    id: Mapped[int] = mapped_column(primary_key=True)

    route_id: Mapped[int] = mapped_column(
        ForeignKey("routes.id", ondelete="CASCADE")
    )

    amount_tzs: Mapped[float] = mapped_column(Float)

    effective_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
    )

    effective_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)

    __table_args__ = (
        CheckConstraint("amount_tzs >= 0"),
    )


class JourneyObservation(Base):
    __tablename__ = "journey_observations"

    id: Mapped[int] = mapped_column(primary_key=True)

    route_id: Mapped[int] = mapped_column(
        ForeignKey("routes.id", ondelete="CASCADE")
    )

    departure_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True)
    )

    duration_seconds: Mapped[int] = mapped_column(Integer)

    wait_seconds: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    weekday: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    source: Mapped[str] = mapped_column(String(50), default="field")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint("duration_seconds > 0"),
        CheckConstraint("wait_seconds IS NULL OR wait_seconds >= 0"),
        CheckConstraint("weekday IS NULL OR weekday BETWEEN 0 AND 6"),
    )


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(primary_key=True)

    report_type: Mapped[str] = mapped_column(String(50))
    description: Mapped[str] = mapped_column(Text)

    status: Mapped[str] = mapped_column(String(30), default="pending")

    location: Mapped[object | None] = mapped_column(
        Geometry("POINT", srid=4326, spatial_index=False),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
    )

    __table_args__ = (
        Index("idx_reports_location", "location", postgresql_using="gist"),
    )


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)

    actor: Mapped[str] = mapped_column(String(100))
    action: Mapped[str] = mapped_column(String(100))
    entity_type: Mapped[str] = mapped_column(String(100))

    entity_id: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    details: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
    )
