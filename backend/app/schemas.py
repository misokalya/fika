
from datetime import datetime
from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


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

