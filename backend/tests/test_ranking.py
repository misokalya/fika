from app.services.journey.ranking import rank_journeys


def make_journey(duration, transfers, distance):
    return {
        "metrics": {
            "total_walking_duration_seconds": duration,
            "transfer_count": transfers,
            "total_walking_distance_m": distance,
        }
    }


def test_journeys_are_ranked_by_walking_duration():
    journeys = [
        make_journey(600, 0, 500),
        make_journey(200, 1, 200),
        make_journey(400, 0, 300),
    ]

    ranked = rank_journeys(journeys)

    durations = [
        journey["metrics"]["total_walking_duration_seconds"]
        for journey in ranked
    ]

    assert durations == [200, 400, 600]


def test_unknown_walking_duration_is_ranked_last():
    journeys = [
        make_journey(None, 0, 100),
        make_journey(300, 1, 200),
        make_journey(600, 0, 500),
    ]

    ranked = rank_journeys(journeys)

    durations = [
        journey["metrics"]["total_walking_duration_seconds"]
        for journey in ranked
    ]

    assert durations == [300, 600, None]


def test_transfer_count_breaks_duration_ties():
    journeys = [
        make_journey(300, 2, 100),
        make_journey(300, 0, 500),
        make_journey(300, 1, 200),
    ]

    ranked = rank_journeys(journeys)

    transfers = [
        journey["metrics"]["transfer_count"]
        for journey in ranked
    ]

    assert transfers == [0, 1, 2]


def test_walking_distance_breaks_remaining_ties():
    journeys = [
        make_journey(300, 1, 500),
        make_journey(300, 1, 100),
        make_journey(300, 1, 300),
    ]

    ranked = rank_journeys(journeys)

    distances = [
        journey["metrics"]["total_walking_distance_m"]
        for journey in ranked
    ]

    assert distances == [100, 300, 500]