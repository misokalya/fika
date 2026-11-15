
MODE_CONFIG = {
    "walking": {
        "engine": "valhalla",
        "costing": "pedestrian",
        "fare_model": "none",
    },
    "boda_boda": {
        "engine": "valhalla",
        "costing": "motorcycle",
        "fare_model": "boda_estimated",
    },
    "bajaji": {
        "engine": "valhalla",
        "costing": "motorcycle",
        "fare_model": "bajaji_estimated",
    },
    "taxi": {
        "engine": "valhalla",
        "costing": "taxi",
        "fare_model": "taxi_estimated",
    },
    "dala_dala": {
        "engine": "fika_transit",
        "costing": None,
        "fare_model": "dala_dala",
    },
}


def get_mode_config(mode: str) -> dict:
    """
    Return routing configuration for a FIKA transport mode.
    """
    config = MODE_CONFIG.get(mode)

    if config is None:
        raise ValueError(f"Unsupported transport mode: {mode}")

    return config
