
import networkx as nx

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Route, RouteStop, Stop, Transfer


def build_transit_graph(
    db: Session,
    verified_transfers_only: bool = True,
) -> nx.MultiDiGraph:
    """
    Build the FIKA dala-dala transit graph from PostgreSQL.

    Nodes represent stops.
    Ride edges connect consecutive stops on a route.
    Transfer edges connect stops belonging to different routes.

    The graph represents network topology, not estimated travel time.
    """

    graph = nx.MultiDiGraph()

    # ---------------------------------------------------------
    # 1. Load active route stops and their geographic locations
    # ---------------------------------------------------------

    statement = (
        select(
            RouteStop.route_id,
            Route.code.label("route_code"),
            Route.name.label("route_name"),
            RouteStop.stop_id,
            RouteStop.sequence,
            RouteStop.destination_board,
            Stop.name.label("stop_name"),
            Stop.stop_type,
            Stop.is_verified,
            func.ST_X(Stop.location).label("longitude"),
            func.ST_Y(Stop.location).label("latitude"),
        )
        .join(Route, RouteStop.route_id == Route.id)
        .join(Stop, RouteStop.stop_id == Stop.id)
        .where(
            Route.is_active.is_(True),
            Stop.is_active.is_(True),
        )
        .order_by(
            RouteStop.route_id,
            RouteStop.sequence,
        )
    )

    rows = db.execute(statement).mappings().all()

    # Group stops by route so we can connect consecutive stops.
    routes = {}

    for row in rows:
        stop_id = row["stop_id"]

        # Add each physical stop only once.
        if not graph.has_node(stop_id):
            graph.add_node(
                stop_id,
                name=row["stop_name"],
                stop_type=row["stop_type"],
                is_verified=row["is_verified"],
                longitude=row["longitude"],
                latitude=row["latitude"],
            )

        routes.setdefault(row["route_id"], []).append(row)

    # ---------------------------------------------------------
    # 2. Connect consecutive stops along each dala-dala route
    # ---------------------------------------------------------

    for route_id, route_stops in routes.items():

        for current, following in zip(
            route_stops,
            route_stops[1:],
        ):
            graph.add_edge(
                current["stop_id"],
                following["stop_id"],
                kind="ride",
                weight=1,
                route_id=route_id,
                route_code=current["route_code"],
                route_name=current["route_name"],
                sequence_from=current["sequence"],
                sequence_to=following["sequence"],
                destination_board=current["destination_board"],
            )

    # ---------------------------------------------------------
    # 3. Load valid transfers between active routes
    # ---------------------------------------------------------

    transfer_statement = (
        select(Transfer)
        .join(
            Route,
            Transfer.from_route_id == Route.id,
        )
        .where(Route.is_active.is_(True))
        .join(
            Route,
            Transfer.to_route_id == Route.id,
            isouter=False,
        )
    )

    # Use explicit aliases to validate both routes and stops.
    from_route = Route.__table__.alias("from_route")
    to_route = Route.__table__.alias("to_route")
    from_stop = Stop.__table__.alias("from_stop")
    to_stop = Stop.__table__.alias("to_stop")

    transfer_statement = (
        select(
            Transfer.id,
            Transfer.from_route_id,
            Transfer.to_route_id,
            Transfer.from_stop_id,
            Transfer.to_stop_id,
            Transfer.walking_distance_m,
            Transfer.is_verified,
            Transfer.notes,
        )
        .join(
            from_route,
            Transfer.from_route_id == from_route.c.id,
        )
        .join(
            to_route,
            Transfer.to_route_id == to_route.c.id,
        )
        .join(
            from_stop,
            Transfer.from_stop_id == from_stop.c.id,
        )
        .join(
            to_stop,
            Transfer.to_stop_id == to_stop.c.id,
        )
        .where(
            from_route.c.is_active.is_(True),
            to_route.c.is_active.is_(True),
            from_stop.c.is_active.is_(True),
            to_stop.c.is_active.is_(True),
        )
    )

    if verified_transfers_only:
        transfer_statement = transfer_statement.where(
            Transfer.is_verified.is_(True)
        )

    transfers = db.execute(
        transfer_statement
    ).mappings().all()

    for transfer in transfers:

        from_stop_id = transfer["from_stop_id"]
        to_stop_id = transfer["to_stop_id"]

        # Only connect stops already present in the transit graph.
        if (
            from_stop_id not in graph
            or to_stop_id not in graph
        ):
            continue

        graph.add_edge(
            from_stop_id,
            to_stop_id,
            kind="transfer",
            weight=1,
            transfer_id=transfer["id"],
            from_route_id=transfer["from_route_id"],
            to_route_id=transfer["to_route_id"],
            walking_distance_m=transfer["walking_distance_m"],
            is_verified=transfer["is_verified"],
            notes=transfer["notes"],
        )

    return graph
