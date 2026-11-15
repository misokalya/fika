
import math
import os
from typing import Any

import httpx

from app.services.routing.base import RoutingProvider


class ValhallaRoutingError(Exception):
    """Raised when Valhalla cannot calculate a route."""


class ValhallaProvider(RoutingProvider):
    """
    Asynchronous routing adapter for the Valhalla API.
    """

    def __init__(
        self,
        base_url: str | None = None,
        timeout: float = 15.0,
    ):
        self.base_url = (
            base_url
            or os.getenv(
                "VALHALLA_BASE_URL",
                "https://valhalla1.openstreetmap.de",
            )
        ).rstrip("/")

        self.timeout = timeout

    @staticmethod
    def _validate_coordinates(
        coordinates: tuple[float, float],
        name: str,
    ) -> None:
        if len(coordinates) != 2:
            raise ValueError(
                f"{name} must contain longitude and latitude."
            )

        longitude, latitude = coordinates

        if not (
            math.isfinite(longitude)
            and math.isfinite(latitude)
        ):
            raise ValueError(
                f"{name} contains invalid coordinates."
            )

        if not -180 <= longitude <= 180:
            raise ValueError(
                f"{name} longitude must be between -180 and 180."
            )

        if not -90 <= latitude <= 90:
            raise ValueError(
                f"{name} latitude must be between -90 and 90."
            )

    async def get_route(
        self,
        origin: tuple[float, float],
        destination: tuple[float, float],
        costing: str,
    ) -> dict[str, Any]:

        self._validate_coordinates(origin, "Origin")
        self._validate_coordinates(destination, "Destination")

        if not costing:
            raise ValueError("A Valhalla costing profile is required.")

        origin_lon, origin_lat = origin
        destination_lon, destination_lat = destination

        payload = {
            "locations": [
                {
                    "lat": origin_lat,
                    "lon": origin_lon,
                },
                {
                    "lat": destination_lat,
                    "lon": destination_lon,
                },
            ],
            "costing": costing,
            "units": "kilometers",
            "language": "en-US",
        }

        try:
            async with httpx.AsyncClient(
                timeout=self.timeout
            ) as client:

                response = await client.post(
                    f"{self.base_url}/route",
                    json=payload,
                )

                response.raise_for_status()

                data = response.json()

        except httpx.TimeoutException as exc:
            raise ValhallaRoutingError(
                "Valhalla request timed out."
            ) from exc

        except httpx.HTTPStatusError as exc:
            raise ValhallaRoutingError(
                f"Valhalla returned HTTP "
                f"{exc.response.status_code}."
            ) from exc

        except httpx.RequestError as exc:
            raise ValhallaRoutingError(
                f"Could not connect to Valhalla: {exc}"
            ) from exc

        except ValueError as exc:
            raise ValhallaRoutingError(
                "Valhalla returned an invalid JSON response."
            ) from exc

        try:
            trip = data["trip"]
            leg = trip["legs"][0]
            summary = leg["summary"]

            distance_km = float(summary["length"])
            duration_seconds = float(summary["time"])

            if (
                not math.isfinite(distance_km)
                or not math.isfinite(duration_seconds)
                or distance_km < 0
                or duration_seconds < 0
            ):
                raise ValueError("Invalid route measurements.")

            return {
                "provider": "valhalla",
                "costing": costing,
                "distance_km": distance_km,
                "duration_seconds": duration_seconds,
                "duration_minutes": round(
                    duration_seconds / 60, 2
                ),
                "cost": summary.get("cost"),
                "geometry": leg.get("shape"),
                "maneuvers": leg.get("maneuvers", []),
            }

        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise ValhallaRoutingError(
                "Valhalla returned an unexpected route structure."
            ) from exc
