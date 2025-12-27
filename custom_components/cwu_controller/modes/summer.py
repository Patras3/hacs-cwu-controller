"""Summer mode handler for CWU Controller.

Summer mode is a placeholder - not yet implemented.
Currently defaults to floor heating only.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from ..const import STATE_HEATING_FLOOR
from .base import BaseModeHandler

if TYPE_CHECKING:
    from ..coordinator import CWUControllerCoordinator


class SummerMode(BaseModeHandler):
    """Summer mode - placeholder, not yet implemented.

    Currently just enables floor heating and lets the pump handle CWU.
    Future implementation could include:
    - CWU heating during solar hours
    - Minimal floor heating
    - Smart scheduling based on weather
    """

    def __init__(self, coordinator: "CWUControllerCoordinator") -> None:
        """Initialize the summer mode handler."""
        super().__init__(coordinator)

    async def run_logic(
        self,
        cwu_urgency: int,
        floor_urgency: int,
        cwu_temp: float | None,
        salon_temp: float | None,
        **kwargs,
    ) -> None:
        """Run control logic for summer mode.

        Currently just switches to floor heating as a placeholder.

        Args:
            cwu_urgency: Current CWU heating urgency level (not used yet).
            floor_urgency: Current floor heating urgency level (not used yet).
            cwu_temp: Current CWU temperature (not used yet).
            salon_temp: Current salon temperature (not used yet).
            **kwargs: Additional parameters (not used yet).
        """
        # Summer mode not implemented yet - default to floor heating
        if self.coord._current_state != STATE_HEATING_FLOOR:
            self.coord._log_action("Summer mode not implemented - using floor heating")
            await self.coord._switch_to_floor()
            self.coord._change_state(STATE_HEATING_FLOOR)
