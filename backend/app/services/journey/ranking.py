
def rank_journeys(journeys: list[dict]) -> list[dict]:
    """
    Rank journeys using measurable information only.

    Priority:
    1. Lowest combined walking time.
    2. Fewest dala-dala transfers.
    3. Lowest combined walking distance.

    Transit duration and fare are not included because they
    are not yet reliably estimated.
    """

    return sorted(
        journeys,
        key=lambda journey: (
            journey["metrics"]["total_walking_duration_seconds"],
            journey["metrics"]["transfer_count"],
            journey["metrics"]["total_walking_distance_m"],
        ),
    )
