
from datetime import datetime
from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from typing import Annotated, Any


# --------------------------------------------------
# Shared configuration
# --------------------------------------------------

class BaseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --------------------------------------------------
# Geographic coordinate validation
# --------------------------------------------------

# Coordinate order: (longitude, latitude)
Coordinate = tuple[float, float]


def validate_coordinate_pair(coordinate: Coordinate) -> Coordinate:
    longitude, latitude = coordinate

    if not -180 <= longitude <= 180:
        raise ValueError("Longitude must be between -180 and 180.")

    if not -90 <= latitude <= 90:
        raise ValueError("Latitude must be between -90 and 90.")

    return coordinate


# --------------------------------------------------
# ROUTE SCHEMAS
# --------------------------------------------------

class RouteCreate(BaseSchema):
    code: Annotated[str, Field(min_length=1, max_length=50)]
    name: Annotated[str, Field(min_length=2, max_length=150)]
    description: str | None = None
    is_active: bool = True

    # Ordered coordinates defining the route's geographic path.
    # Each coordinate is (longitude, latitude).
    path: list[Coordinate] | None = None

    @field_validator("path")
    @classmethod
    def validate_path(cls, path):
        if path is not None:
            if len(path) < 2:
                raise ValueError("A route path requires at least two coordinates.")

            for coordinate in path:
                validate_coordinate_pair(coordinate)

        return path


class RouteUpdate(BaseSchema):
    code: Annotated[str | None, Field(default=None, min_length=1, max_length=50)]
    name: Annotated[str | None, Field(default=None, min_length=2, max_length=150)]
    description: str | None = None
    is_active: bool | None = None
    path: list[Coordinate] | None = None

    @field_validator("path")
    @classmethod
    def validate_path(cls, path):
        if path is not None:
            if len(path) < 2:
                raise ValueError("A route path requires at least two coordinates.")

            for coordinate in path:
                validate_coordinate_pair(coordinate)

        return path



class RouteResponse(BaseSchema):
    id: int
    code: str
    name: str
    description: str | None
    is_active: bool
    created_at: datetime
    path: list[Coordinate] | None = None


# --------------------------------------------------
# STOP SCHEMAS
# --------------------------------------------------


class StopCreate(BaseSchema):
    name: Annotated[str, Field(min_length=2, max_length=150)]
    description: str | None = None
    stop_type: Annotated[str, Field(min_length=1, max_length=30)] = "informal"

    latitude: float
    longitude: float

    is_verified: bool = False
    is_active: bool = True

    @field_validator("latitude")
    @classmethod
    def validate_latitude(cls, value):
        if not -90 <= value <= 90:
            raise ValueError("Latitude must be between -90 and 90.")
        return value

    @field_validator("longitude")
    @classmethod
    def validate_longitude(cls, value):
        if not -180 <= value <= 180:
            raise ValueError("Longitude must be between -180 and 180.")
        return value


class StopUpdate(BaseSchema):
    name: Annotated[str | None, Field(default=None, min_length=2, max_length=150)]
    description: str | None = None
    stop_type: Annotated[str | None, Field(default=None, min_length=1, max_length=30)]

    latitude: float | None = None
    longitude: float | None = None

    is_verified: bool | None = None
    is_active: bool | None = None

    @field_validator("latitude")
    @classmethod
    def validate_latitude(cls, value):
        if value is not None and not -90 <= value <= 90:
            raise ValueError("Latitude must be between -90 and 90.")
        return value

    @field_validator("longitude")
    @classmethod
    def validate_longitude(cls, value):
        if value is not None and not -180 <= value <= 180:
            raise ValueError("Longitude must be between -180 and 180.")
        return value

    @model_validator(mode="after")
    def validate_location_pair(self):
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError(
                "Latitude and longitude must be provided together."
            )
        return self


class StopResponse(BaseSchema):
    id: int
    name: str
    description: str | None
    stop_type: str
    latitude: float
    longitude: float
    is_verified: bool
    is_active: bool
    created_at: datetime



class RouteStopCreate(BaseSchema):
    stop_id: int = Field(gt=0)
    sequence: int = Field(gt=0)
    destination_board: str | None = Field(default=None, max_length=150)


class RouteStopUpdate(BaseSchema):
    sequence: int | None = Field(default=None, gt=0)
    destination_board: str | None = Field(default=None, max_length=150)


class RouteStopResponse(BaseSchema):
    id: int
    route_id: int
    stop_id: int
    sequence: int
    destination_board: str | None


class TransferCreate(BaseSchema):
    from_route_id: int = Field(gt=0)
    to_route_id: int = Field(gt=0)
    from_stop_id: int = Field(gt=0)
    to_stop_id: int = Field(gt=0)

    walking_distance_m: float | None = Field(default=None, ge=0)
    is_verified: bool = False
    notes: str | None = None

    @model_validator(mode="after")
    def validate_different_routes(self):
        if self.from_route_id == self.to_route_id:
            raise ValueError("A transfer must connect two different routes")
        return self


class TransferUpdate(BaseSchema):
    from_route_id: int | None = Field(default=None, gt=0)
    to_route_id: int | None = Field(default=None, gt=0)
    from_stop_id: int | None = Field(default=None, gt=0)
    to_stop_id: int | None = Field(default=None, gt=0)

    walking_distance_m: float | None = Field(default=None, ge=0)
    is_verified: bool | None = None
    notes: str | None = None


class TransferResponse(BaseSchema):
    id: int
    from_route_id: int
    to_route_id: int
    from_stop_id: int
    to_stop_id: int
    walking_distance_m: float | None
    is_verified: bool
    notes: str | None

# --------------------------------------------------
# JOURNEY SCHEMAS
# --------------------------------------------------

class JourneyPlanRequest(BaseSchema):
    origin_stop_id: int = Field(gt=0)
    destination_stop_id: int = Field(gt=0)
    include_unverified_transfers: bool = False

    @model_validator(mode="after")
    def validate_different_stops(self):
        if self.origin_stop_id == self.destination_stop_id:
            raise ValueError("Origin and destination stops must be different.")
        return self


class JourneyPlanResponse(BaseSchema):
    status: str
    origin_stop_id: int
    destination_stop_id: int
    include_unverified_transfers: bool
    path: dict[str, Any]
    instructions: dict[str, Any]


class CoordinateJourneyPlanRequest(BaseSchema):
    origin_longitude: float = Field(
        ge=-180, le=180, allow_inf_nan=False
    )
    origin_latitude: float = Field(
        ge=-90, le=90, allow_inf_nan=False
    )
    destination_longitude: float = Field(
        ge=-180, le=180, allow_inf_nan=False
    )
    destination_latitude: float = Field(
        ge=-90, le=90, allow_inf_nan=False
    )
    radius_m: float = Field(default=2000, gt=0, le=5000)
    candidate_limit: int = Field(default=10, ge=1, le=50)
    include_unverified_transfers: bool = False
