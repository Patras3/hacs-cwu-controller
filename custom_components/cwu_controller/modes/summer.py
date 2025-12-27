"""Summer mode for CWU Controller.

Placeholder for future summer mode implementation.
Currently defaults to floor heating.
"""

from __future__ import annotations

import logging

from ..const import STATE_HEATING_FLOOR
from .base import BaseModeHandler

_LOGGER = logging.getLogger(__name__)


class SummerMode(BaseModeHandler):
    """Mode handler for summer operation.

    Placeholder implementation - currently just heats floor by default.
    Future features might include:
    - Solar integration
    - Heat only during cheap tariff
    - Minimal heating (only critical)
    """

    async def run_logic(
        self,
        cwu_urgency: int,
        floor_urgency: int,
        cwu_temp: float | None,
        salon_temp: float | None,
    ) -> None:
        """Run control logic for summer mode (placeholder)."""
        _LOGGER.warning("Summer mode is not implemented yet - defaulting to floor heating")

        if self._current_state != STATE_HEATING_FLOOR:
            self._log_action(
                "Summer mode: Not implemented",
                "Defaulting to floor heating"
            )
            await self._switch_to_floor()
            self._change_state(STATE_HEATING_FLOOR)
