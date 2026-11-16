
import networkx as nx
import pytest

from app.models import Transfer
from app.services.transit.graph import build_transit_graph


class FakeResult:
    def __init__(self, rows):
        self.rows = rows

    def mappings(self):
        return self

    def all(self):
        return self.rows


class FakeDatabase:
    def __init__(self):
        self.call_count = 0
        self.transfer_query = None

        self.route_stop_rows = [
            {
                "route_id": 1,
                "route_code": "AR-01",
                "route_name": "Route One",
                "stop_id": 1,
                "sequence": 1,
                "destination_board": "Town",
                "stop_name": "Stop A",
                "stop_type": "normal",
                "is_verified": True,
                "longitude": 36.8219,
                "latitude": -3.3869,
            },
            {
                "route_id": 2,
                "route_code": "AR-02",
                "route_name": "Route Two",
                "stop_id": 2,
                "sequence": 1,
                "destination_board": "Market",
                "stop_name": "Stop B",
                "stop_type": "normal",
                "is_verified": True,
                "longitude": 36.825,
                "latitude": -3.390,
            },
        ]

        self.transfer_rows = [
            {
                "id": 10,
                "from_route_id": 1,
                "to_route_id": 2,
                "from_stop_id": 1,
                "to_stop_id": 2,
                "walking_distance_m": 150,
                "is_verified": True,
                "notes": "Verified transfer",
            },
            {
                "id": 11,
                "from_route_id": 1,
                "to_route_id": 2,
                "from_stop_id": 1,
                "to_stop_id": 2,
                "walking_distance_m": 200,
                "is_verified": False,
                "notes": "Unverified transfer",
            },
        ]

    def execute(self, statement):
        self.call_count += 1

        if self.call_count == 1:
            return FakeResult(self.route_stop_rows)

        self.transfer_query = statement

        sql = str(statement.compile(compile_kwargs={"literal_binds": True}))

        if "transfers.is_verified IS true" in sql:
            rows = [
                row for row in self.transfer_rows
                if row["is_verified"]
            ]
        else:
            rows = self.transfer_rows

        return FakeResult(rows)


def get_transfer_edges(graph):
    return [
        data
        for _, _, data in graph.edges(data=True)
        if data["kind"] == "transfer"
    ]


def test_unverified_transfers_are_excluded_by_default():
    db = FakeDatabase()

    graph = build_transit_graph(db)

    transfer_edges = get_transfer_edges(graph)

    assert len(transfer_edges) == 1
    assert transfer_edges[0]["transfer_id"] == 10
    assert transfer_edges[0]["is_verified"] is True

    sql = str(
        db.transfer_query.compile(
            compile_kwargs={"literal_binds": True}
        )
    )
    assert "transfers.is_verified IS true" in sql


def test_unverified_transfers_are_included_when_allowed():
    db = FakeDatabase()

    graph = build_transit_graph(
        db,
        verified_transfers_only=False,
    )

    transfer_edges = get_transfer_edges(graph)

    assert len(transfer_edges) == 2

    transfer_ids = {
        edge["transfer_id"] for edge in transfer_edges
    }

    assert transfer_ids == {10, 11}
