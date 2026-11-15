def generate_journey_instructions(graph, path_result):
    """
    Generate passenger-friendly instructions from a transit path.

    Groups consecutive ride edges on the same route into a single ride step.
    Transfer edges are represented as separate transfer steps.

    Unverified transfer distances are explicitly identified as estimates.
    """

    steps = []
    connections = path_result["connections"]

    current_ride = None

    def finish_ride():
        nonlocal current_ride

        if current_ride is not None:
            current_ride["step_number"] = len(steps) + 1
            current_ride["instruction"] = (
                f"Board {current_ride['route_code']} displaying "
                f"'{current_ride['destination_board']}'."
            )

            steps.append(current_ride)
            current_ride = None

    for connection in connections:

        if connection["kind"] == "ride":

            route_id = connection["route_id"]

            if current_ride is None:
                current_ride = {
                    "type": "ride",
                    "route_id": route_id,
                    "route_code": connection["route_code"],
                    "route_name": connection["route_name"],
                    "destination_board": connection.get(
                        "destination_board"
                    ),
                    "boarding_stop": {
                        "id": connection["from_stop_id"],
                        "name": graph.nodes[
                            connection["from_stop_id"]
                        ]["name"],
                    },
                    "alighting_stop": {
                        "id": connection["to_stop_id"],
                        "name": graph.nodes[
                            connection["to_stop_id"]
                        ]["name"],
                    },
                    "stop_ids": [
                        connection["from_stop_id"],
                        connection["to_stop_id"],
                    ],
                }

            elif current_ride["route_id"] == route_id:
                current_ride["alighting_stop"] = {
                    "id": connection["to_stop_id"],
                    "name": graph.nodes[
                        connection["to_stop_id"]
                    ]["name"],
                }

                current_ride["stop_ids"].append(
                    connection["to_stop_id"]
                )

            else:
                finish_ride()

                current_ride = {
                    "type": "ride",
                    "route_id": route_id,
                    "route_code": connection["route_code"],
                    "route_name": connection["route_name"],
                    "destination_board": connection.get(
                        "destination_board"
                    ),
                    "boarding_stop": {
                        "id": connection["from_stop_id"],
                        "name": graph.nodes[
                            connection["from_stop_id"]
                        ]["name"],
                    },
                    "alighting_stop": {
                        "id": connection["to_stop_id"],
                        "name": graph.nodes[
                            connection["to_stop_id"]
                        ]["name"],
                    },
                    "stop_ids": [
                        connection["from_stop_id"],
                        connection["to_stop_id"],
                    ],
                }

        elif connection["kind"] == "transfer":

            finish_ride()

            from_stop_id = connection["from_stop_id"]
            to_stop_id = connection["to_stop_id"]

            walking_distance = connection.get("walking_distance_m")
            is_verified = connection.get("is_verified", False)

            verification_note = (
                ""
                if is_verified
                else " (unverified estimate)"
            )

            if walking_distance is not None:
                instruction = (
                    f"Transfer from "
                    f"{graph.nodes[from_stop_id]['name']} to "
                    f"{graph.nodes[to_stop_id]['name']}. "
                    f"Recorded walking distance: "
                    f"{walking_distance:.0f} m"
                    f"{verification_note}."
                )
            else:
                instruction = (
                    f"Transfer from "
                    f"{graph.nodes[from_stop_id]['name']} to "
                    f"{graph.nodes[to_stop_id]['name']}"
                    f"{verification_note}."
                )

            steps.append({
                "step_number": len(steps) + 1,
                "type": "transfer",
                "transfer_id": connection.get("transfer_id"),
                "from_stop": {
                    "id": from_stop_id,
                    "name": graph.nodes[from_stop_id]["name"],
                },
                "to_stop": {
                    "id": to_stop_id,
                    "name": graph.nodes[to_stop_id]["name"],
                },
                "walking_distance_m": walking_distance,
                "is_verified": is_verified,
                "notes": connection.get("notes"),
                "instruction": instruction,
            })

    finish_ride()

    ride_steps = sum(
        1 for step in steps if step["type"] == "ride"
    )

    transfer_steps = sum(
        1 for step in steps if step["type"] == "transfer"
    )

    return {
        "origin_stop_id": path_result["origin_stop_id"],
        "destination_stop_id": path_result["destination_stop_id"],
        "steps": steps,
        "total_steps": len(steps),
        "ride_steps": ride_steps,
        "transfer_steps": transfer_steps,
    }