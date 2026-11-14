
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from geoalchemy2.elements import WKTElement
from geoalchemy2.shape import to_shape

from app.dependencies import get_db
from app.models import Route
from app.schemas import RouteCreate, RouteUpdate, RouteResponse


router = APIRouter(
    prefix="/api/v1/routes",
    tags=["Routes"]
)


def route_to_response(route: Route) -> dict:
    """Convert a SQLAlchemy route, including its PostGIS path, to API data."""

    path = None

    if route.path is not None:
        geometry = to_shape(route.path)
        path = [
            (float(longitude), float(latitude))
            for longitude, latitude in geometry.coords
        ]

    return {
        "id": route.id,
        "code": route.code,
        "name": route.name,
        "description": route.description,
        "is_active": route.is_active,
        "created_at": route.created_at,
        "path": path,
    }


@router.post(
    "",
    response_model=RouteResponse,
    status_code=status.HTTP_201_CREATED
)
def create_route(
    route_data: RouteCreate,
    db: Session = Depends(get_db)
):
    """Create a new public transport route."""

    existing_route = db.query(Route).filter(
        Route.code == route_data.code
    ).first()

    if existing_route:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A route with this code already exists."
        )

    route_values = route_data.model_dump(exclude={"path"})

    if route_data.path is not None:
        coordinates = ", ".join(
            f"{longitude} {latitude}"
            for longitude, latitude in route_data.path
        )

        route_values["path"] = WKTElement(
            f"LINESTRING({coordinates})",
            srid=4326
        )

    route = Route(**route_values)

    try:
        db.add(route)
        db.commit()
        db.refresh(route)

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The route could not be created because of a data conflict."
        )

    return route_to_response(route)


@router.get("", response_model=list[RouteResponse])
def list_routes(
    skip: int = 0,
    limit: int = 100,
    active_only: bool = True,
    db: Session = Depends(get_db)
):
    """List transport routes."""

    if skip < 0 or limit < 1 or limit > 500:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid pagination parameters."
        )

    query = db.query(Route)

    if active_only:
        query = query.filter(Route.is_active.is_(True))

    routes = query.order_by(Route.name).offset(skip).limit(limit).all()

    return [route_to_response(route) for route in routes]


@router.get("/{route_id}", response_model=RouteResponse)
def get_route(
    route_id: int,
    db: Session = Depends(get_db)
):
    """Retrieve a route by its database ID."""

    route = db.query(Route).filter(Route.id == route_id).first()

    if not route:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Route not found."
        )

    return route_to_response(route)


@router.patch("/{route_id}", response_model=RouteResponse)
def update_route(
    route_id: int,
    route_data: RouteUpdate,
    db: Session = Depends(get_db)
):
    """Update an existing route."""

    route = db.query(Route).filter(Route.id == route_id).first()

    if not route:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Route not found."
        )

    updates = route_data.model_dump(exclude_unset=True)

    if "code" in updates and updates["code"] is not None:
        duplicate = db.query(Route).filter(
            Route.code == updates["code"],
            Route.id != route_id
        ).first()

        if duplicate:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Another route already uses this code."
            )

    if "path" in updates:
        coordinates = updates.pop("path")

        if coordinates is None:
            route.path = None
        else:
            coordinate_text = ", ".join(
                f"{longitude} {latitude}"
                for longitude, latitude in coordinates
            )

            route.path = WKTElement(
                f"LINESTRING({coordinate_text})",
                srid=4326
            )

    for field, value in updates.items():
        setattr(route, field, value)

    try:
        db.commit()
        db.refresh(route)

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The route could not be updated because of a data conflict."
        )

    return route_to_response(route)


@router.delete("/{route_id}")
def deactivate_route(
    route_id: int,
    db: Session = Depends(get_db)
):
    """
    Deactivate a route instead of permanently deleting it.

    This preserves historical records and avoids breaking
    relationships with stops, fares and journey observations.
    """

    route = db.query(Route).filter(Route.id == route_id).first()

    if not route:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Route not found."
        )

    route.is_active = False
    db.commit()

    return {
        "message": "Route successfully deactivated.",
        "route_id": route.id
    }
