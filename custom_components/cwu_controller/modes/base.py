"""Base class for CWU Controller operating modes."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import TYPE_CHECKING

from ..notifications import async_send_notification

if TYPE_CHECKING:
    from ..coordinator import CWUControllerCoordinator

_LOGGER = logging.getLogger(__name__)


class BaseModeHandler(ABC):
    """Base class for operating mode handlers.

    Mode handlers implement the control logic for different operating scenarios.
    They have access to the coordinator for state management and device control.
    """

    def __init__(self, coordinator: "CWUControllerCoordinator") -> None:
        """Initialize the mode handler.

        Args:
            coordinator: The parent coordinator instance
        """
        self.coord = coordinator

    @property
    def name(self) -> str:
        """Return the mode name for logging."""
        return self.__class__.__name__

    @abstractmethod
    async def run_logic(
        self,
        cwu_urgency: int,
        floor_urgency: int,
        cwu_temp: float | None,
        salon_temp: float | None,
    ) -> None:
        """Run the mode-specific control logic.

        This is the main entry point called by the coordinator each update cycle.

        Args:
            cwu_urgency: CWU heating urgency level (0-4)
            floor_urgency: Floor heating urgency level (0-4)
            cwu_temp: Current CWU temperature (may be None)
            salon_temp: Current living room temperature (may be None)
        """
        raise NotImplementedError

    def on_mode_enter(self) -> None:
        """Called when this mode becomes active.

        Override in subclasses to reset mode-specific state.
        This is called by the coordinator when operating mode changes.
        """
        pass

    # =========================================================================
    # Helper methods - shortcuts to coordinator methods
    # =========================================================================

    def _log_action(self, action: str, reasoning: str = "") -> None:
        """Log an action with reasoning."""
        self.coord._log_action(action, reasoning)

    def _change_state(self, new_state: str) -> None:
        """Change the controller state."""
        self.coord._change_state(new_state)

    async def _switch_to_cwu(self) -> None:
        """Switch to CWU heating."""
        await self.coord._switch_to_cwu()

    async def _switch_to_floor(self) -> None:
        """Switch to floor heating."""
        await self.coord._switch_to_floor()

    async def _async_set_cwu_on(self) -> bool:
        """Turn on CWU heating."""
        return await self.coord._async_set_cwu_on()

    async def _async_set_cwu_off(self) -> bool:
        """Turn off CWU heating."""
        return await self.coord._async_set_cwu_off()

    async def _async_set_floor_on(self) -> bool:
        """Turn on floor heating."""
        return await self.coord._async_set_floor_on()

    async def _async_set_floor_off(self) -> bool:
        """Turn off floor heating."""
        return await self.coord._async_set_floor_off()

    async def _async_send_notification(self, title: str, message: str) -> None:
        """Send a notification."""
        await async_send_notification(self.coord, title, message)

    async def _enter_safe_mode(self) -> None:
        """Enter safe mode."""
        await self.coord._enter_safe_mode()

    def _is_hp_ready_for_cwu(self) -> tuple[bool, str]:
        """Check if heat pump is ready for CWU heating."""
        return self.coord._is_hp_ready_for_cwu()

    def _detect_rapid_drop(self) -> tuple[bool, float]:
        """Detect rapid CWU temperature drop."""
        return self.coord._detect_rapid_drop()

    def _is_pump_charged(self) -> bool:
        """Check if pump reports CWU is charged."""
        return self.coord._is_pump_charged()

    def _reset_max_temp_tracking(self) -> None:
        """Reset max temperature tracking data."""
        self.coord._reset_max_temp_tracking()

    def _can_switch_mode(self, to_state: str) -> tuple[bool, str]:
        """Check if mode switching is allowed (anti-oscillation).

        Args:
            to_state: Target state to switch to
        """
        return self.coord._can_switch_mode(self._current_state, to_state)

    def get_config_value(self, key: str, default: float) -> float:
        """Get a configuration value."""
        return self.coord.get_config_value(key, default)

    def _get_target_temp(self) -> float:
        """Get target CWU temperature."""
        return self.coord._get_target_temp()

    def _get_min_temp(self) -> float:
        """Get minimum CWU temperature."""
        return self.coord._get_min_temp()

    def _get_critical_temp(self) -> float:
        """Get critical CWU temperature."""
        return self.coord._get_critical_temp()

    # =========================================================================
    # Property accessors for coordinator state
    # =========================================================================

    @property
    def _current_state(self) -> str:
        """Get current controller state."""
        return self.coord._current_state

    @property
    def _bsb_lan_data(self) -> dict:
        """Get BSB-LAN data."""
        return self.coord._bsb_lan_data

    @property
    def now(self) -> datetime:
        """Get current datetime."""
        return datetime.now()
