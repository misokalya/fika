
import pytest

from app.services.routing.mode_config import (
    MODE_CONFIG,
    get_mode_config,
)


@pytest.mark.parametrize(
    "mode, expected",
    [
        (
            "walking",
            {
                "engine": "valhalla",
                "costing": "pedestrian",
                "fare_model": "none",
            },
        ),
        (
            "boda_boda",
            {
                "engine": "valhalla",
                "costing": "motorcycle",
                "fare_model": "boda_estimated",
            },
        ),
        (
            "bajaji",
            {
                "engine": "valhalla",
                "costing": "motorcycle",
                "fare_model": "bajaji_estimated",
            },
        ),
        (
            "taxi",
            {
                "engine": "valhalla",
                "costing": "taxi",
                "fare_model": "taxi_estimated",
            },
        ),
        (
            "dala_dala",
            {
                "engine": "fika_transit",
                "costing": None,
                "fare_model": "dala_dala",
            },
        ),
    ],
)
def test_transport_mode_configuration(mode, expected):
    assert get_mode_config(mode) == expected


def test_boda_boda_and_bajaji_share_routing_profile():
    boda = get_mode_config("boda_boda")
    bajaji = get_mode_config("bajaji")

    assert boda["engine"] == bajaji["engine"]
    assert boda["costing"] == bajaji["costing"]

    # Their fare models must remain distinct.
    assert boda["fare_model"] != bajaji["fare_model"]


def test_dala_dala_does_not_use_valhalla():
    config = get_mode_config("dala_dala")

    assert config["engine"] == "fika_transit"
    assert config["costing"] is None


@pytest.mark.parametrize(
    "mode",
    [
        "",
        "bus",
        "motorcycle",
        "DALA_DALA",
        "Walking",
        "unknown",
    ],
)
def test_unsupported_transport_modes_are_rejected(mode):
    with pytest.raises(
        ValueError,
        match="Unsupported transport mode",
    ):
        get_mode_config(mode)


def test_configuration_contains_only_supported_modes():
    assert set(MODE_CONFIG.keys()) == {
        "walking",
        "boda_boda",
        "bajaji",
        "taxi",
        "dala_dala",
    }


def test_returned_configuration_matches_registered_configuration():
    for mode, config in MODE_CONFIG.items():
        assert get_mode_config(mode) == config
