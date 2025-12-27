"""Base class for CWU Controller mode handlers."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..coordinator import CWUControllerCoordinator


class BaseModeHandler(ABC):
    """Abstract base class for operating mode handlers.

    Each mode handler implements the control logic for a specific operating mode.
    The handler has access to the coordinator for state, BSB-LAN data, and control methods.
    """

    def __init__(self, coordinator: "CWUControllerCoordinator") -> None:
        """Initialize the mode handler.

        Args:
            coordinator: The CWU Controller coordinator instance.
        """
        self.coord = coordinator

    @abstractmethod
    async def run_logic(
        self,
        cwu_urgency: int,
        floor_urgency: int,
        cwu_temp: float | None,
        salon_temp: float | None,
        **kwargs,
    ) -> None:
        """Run the control logic for this mode.

        Args:
            cwu_urgency: Current CWU heating urgency level.
            floor_urgency: Current floor heating urgency level.
            cwu_temp: Current CWU temperature (None if unavailable).
            salon_temp: Current salon temperature (None if unavailable).
            **kwargs: Additional mode-specific parameters.
        """
        raise NotImplementedError
