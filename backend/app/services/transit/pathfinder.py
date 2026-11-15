
import networkx as nx


class TransitPathNotFoundError(Exception):
    """Raised when no transit path exists between two stops."""


def find_transit_path(
    graph: nx.MultiDiGraph,
    origin_stop_id: int,
    destination_stop_id: int,
) -> dict:
    """
    Find a directed path between two stops in the FIKA transit graph.

    This version uses edge weights for structural pathfinding.
    It does not calculate real journey time or fare.
    """

    if origin_stop_id not in graph:
        raise ValueError(
            f"Origin stop {origin_stop_id} does not exist in the graph."
        )

    if destination_stop_id not in graph:
        raise ValueError(
            f"Destination stop {destination_stop_id} does not exist in the graph."
        )

    try:
        stop_path = nx.shortest_path(
            graph,
            source=origin_stop_id,
            target=destination_stop_id,
            weight="weight",
        )

    except nx.NetworkXNoPath as exc:
        raise TransitPathNotFoundError(
            f"No transit path exists from stop "
            f"{origin_stop_id} to stop {destination_stop_id}."
        ) from exc

    connections = []

    for from_stop, to_stop in zip(stop_path, stop_path[1:]):
        edge_options = graph.get_edge_data(from_stop, to_stop)

        if not edge_options:
            raise TransitPathNotFoundError(
                f"Missing connection between stops "
                f"{from_stop} and {to_stop}."
            )

        # Select the lowest-weight connection if parallel edges exist.
        edge_data = min(
            edge_options.values(),
            key=lambda edge: edge.get("weight", 1),
        )

        connections.append({
            "from_stop_id": from_stop,
            "to_stop_id": to_stop,
            **edge_data,
        })

    return {
        "origin_stop_id": origin_stop_id,
        "destination_stop_id": destination_stop_id,
        "stops": stop_path,
        "connections": connections,
        "total_connections": len(connections),
        "ride_connections": sum(
            edge["kind"] == "ride" for edge in connections
        ),
        "transfer_connections": sum(
            edge["kind"] == "transfer" for edge in connections
        ),
    }
