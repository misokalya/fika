
from abc import ABC, abstractmethod
from typing import Any


class RoutingProvider(ABC):
    """
    Base interface for external road and pedestrian routing providers.
    """

    @abstractmethod
    async def get_route(
        self,
        origin: tuple[float, float],
        destination: tuple[float, float],
        costing: str,
    ) -> dict[str, Any]:
        """
        Calculate a route between two coordinates.

        Coordinates use (longitude, latitude).
        """
        raise NotImplementedError
