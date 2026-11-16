def rank_journeys(journeys: list[dict]) -> list[dict]:
    """
    Rank using measurable walking information.

    Journeys with unavailable total walking duration are
    placed after journeys with a known duration.
    """
    return sorted(
        journeys,
        key=lambda journey: (
            journey["metrics"]["total_walking_duration_seconds"]
            is None,
            journey["metrics"]["total_walking_duration_seconds"]
            if journey["metrics"]["total_walking_duration_seconds"]
            is not None
            else float("inf"),
            journey["metrics"]["transfer_count"],
            journey["metrics"]["total_walking_distance_m"],
        ),
    )