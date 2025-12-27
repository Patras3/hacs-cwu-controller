"""Winter mode handler for CWU Controller.

Winter mode features:
- Heat CWU during cheap tariff windows (03:00-06:00, 13:00-15:00, 22:00-24:00)
- No 3-hour session limit (heat until target reached)
- No fake heating detection (pump can use real heater)
- Higher CWU target temperature (+5°C)
- Only heat CWU outside windows if temperature drops significantly
- When not heating water -> heat house
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING

from ..const import (
    STATE_HEATING_CWU,
    STATE_HEATING_FLOOR,
    STATE_EMERGENCY_CWU,
    STATE_EMERGENCY_FLOOR,
    STATE_SAFE_MODE,
    URGENCY_CRITICAL,
)
from .base import BaseModeHandler

if TYPE_CHECKING:
    from ..coordinator import CWUControllerCoordinator

_LOGGER = logging.getLogger(__name__)


class WinterMode(BaseModeHandler):
    """Winter mode - scheduled CWU heating during cheap tariff windows.

    Heating windows: 03:00-06:00, 13:00-15:00, 22:00-24:00

    Features:
    - Higher target temp (+5°C from config), max 55°C
    - No 3h limit (heat until target reached)
    - No fake heating detection (real heater works)
    - Emergency heating outside windows if temp drops critically
    - 3h no-progress timeout protection
    """

    def __init__(self, coordinator: "CWUControllerCoordinator") -> None:
        """Initialize the winter mode handler."""
        super().__init__(coordinator)

    async def run_logic(
        self,
        cwu_urgency: int,
        floor_urgency: int,
        cwu_temp: float | None,
        salon_temp: float | None,
        **kwargs,
    ) -> None:
        """Run control logic for winter mode.

        Args:
            cwu_urgency: Current CWU heating urgency level.
            floor_urgency: Current floor heating urgency level.
            cwu_temp: Current CWU temperature.
            salon_temp: Current salon temperature.
            **kwargs: Additional parameters (not used in winter mode).
        """
        now = datetime.now()
        winter_target = self.coord.get_winter_cwu_target()
        emergency_threshold = self.coord.get_winter_cwu_emergency_threshold()
        is_heating_window = self.coord.is_winter_cwu_heating_window()

        # Emergency handling - critical floor temperature takes priority
        if floor_urgency == URGENCY_CRITICAL:
            if self.coord._current_state != STATE_EMERGENCY_FLOOR:
                await self.coord._switch_to_floor()
                self.coord._change_state(STATE_EMERGENCY_FLOOR)
                await self.coord._async_send_notification(
                    "Floor Emergency!",
                    f"Room critically cold: Salon {salon_temp}°C! Switching to floor heating."
                )
            return

        # Safety check: no progress after 3 hours of CWU heating
        if self.coord._current_state in (STATE_HEATING_CWU, STATE_EMERGENCY_CWU):
            if self.coord._check_winter_cwu_no_progress(cwu_temp):
                start_temp = self.coord._cwu_session_start_temp
                elapsed_hours = (now - self.coord._cwu_heating_start).total_seconds() / 3600 if self.coord._cwu_heating_start else 0
                self.coord._log_action(
                    f"Winter mode: No progress after {elapsed_hours:.1f}h "
                    f"(start: {start_temp}°C, current: {cwu_temp}°C). Resetting to floor."
                )
                await self.coord._async_send_notification(
                    "CWU Heating Problem (Winter Mode)",
                    f"CWU temperature hasn't increased after {elapsed_hours:.1f} hours of heating.\n"
                    f"Started at: {start_temp}°C\n"
                    f"Current: {cwu_temp}°C\n\n"
                    f"Switching to floor heating. Please check the heat pump."
                )
                await self.coord._switch_to_floor()
                self.coord._change_state(STATE_HEATING_FLOOR)
                self.coord._cwu_heating_start = None
                self.coord._cwu_session_start_temp = None
                return

        # Handle CWU heating window (03:00-06:00, 13:00-15:00, 22:00-24:00)
        if is_heating_window:
            # During heating window: heat CWU if below target OR if temp unknown
            # When temp is unknown, enable both floor+CWU and let heat pump decide
            if cwu_temp is None:
                # Temperature unknown - enable both, let pump decide (safe default)
                if self.coord._current_state != STATE_SAFE_MODE:
                    self.coord._log_action(
                        "Winter mode: CWU temp UNKNOWN during heating window - enabling both (pump decides)"
                    )
                    _LOGGER.warning(
                        "CWU temperature unavailable during heating window - enabling both floor+CWU"
                    )
                    await self.coord._enter_safe_mode()
                    self.coord._change_state(STATE_SAFE_MODE)
                return
            elif cwu_temp < winter_target:
                if self.coord._current_state != STATE_HEATING_CWU:
                    await self.coord._switch_to_cwu()
                    self.coord._change_state(STATE_HEATING_CWU)
                    self.coord._cwu_heating_start = now
                    self.coord._log_action(
                        f"Winter mode: Heating window started, CWU {cwu_temp}°C -> target {winter_target}°C"
                    )
                # Continue heating until target reached (no session limit in winter mode)
                return
            else:
                # Target reached during window - switch to floor
                if self.coord._current_state == STATE_HEATING_CWU:
                    self.coord._log_action(
                        f"Winter mode: CWU target reached ({cwu_temp}°C >= {winter_target}°C)"
                    )
                    await self.coord._switch_to_floor()
                    self.coord._change_state(STATE_HEATING_FLOOR)
                    self.coord._cwu_heating_start = None
                return

        # Outside heating window: if temp unknown, enable both (pump decides)
        if cwu_temp is None:
            if self.coord._current_state != STATE_SAFE_MODE:
                self.coord._log_action(
                    "Winter mode: CWU temp UNKNOWN outside window - enabling both (pump decides)"
                )
                _LOGGER.warning(
                    "CWU temperature unavailable outside heating window - enabling both floor+CWU"
                )
                await self.coord._enter_safe_mode()
                self.coord._change_state(STATE_SAFE_MODE)
            return

        # Outside heating window: only heat CWU in emergency (below threshold)
        if cwu_temp < emergency_threshold:
            if self.coord._current_state not in (STATE_HEATING_CWU, STATE_EMERGENCY_CWU):
                await self.coord._switch_to_cwu()
                self.coord._change_state(STATE_EMERGENCY_CWU)
                self.coord._cwu_heating_start = now
                await self.coord._async_send_notification(
                    "CWU Emergency (Winter Mode)",
                    f"CWU dropped to {cwu_temp}°C (below {emergency_threshold}°C threshold). "
                    f"Starting emergency heating outside window."
                )
                self.coord._log_action(
                    f"Winter mode: Emergency CWU heating ({cwu_temp}°C < {emergency_threshold}°C)"
                )
            # If already in emergency heating, continue until buffer temp reached
            return

        # Check if we should exit emergency CWU heating (temp risen above buffer)
        if self.coord._current_state == STATE_EMERGENCY_CWU and cwu_temp is not None:
            buffer_temp = emergency_threshold + 3.0
            if cwu_temp >= buffer_temp:
                self.coord._log_action(
                    f"Winter mode: Emergency CWU complete ({cwu_temp}°C >= {buffer_temp}°C)"
                )
                await self.coord._switch_to_floor()
                self.coord._change_state(STATE_HEATING_FLOOR)
                self.coord._cwu_heating_start = None
                return

        # Currently heating CWU but outside window and above emergency threshold
        if self.coord._current_state in (STATE_HEATING_CWU, STATE_EMERGENCY_CWU):
            # Check if we should continue (during heating window check above already handles this)
            if cwu_temp is not None and cwu_temp >= winter_target:
                self.coord._log_action(
                    f"Winter mode: CWU at target ({cwu_temp}°C), switching to floor"
                )
                await self.coord._switch_to_floor()
                self.coord._change_state(STATE_HEATING_FLOOR)
                self.coord._cwu_heating_start = None
                return

        # Default: heat floor (if not already heating something)
        if self.coord._current_state not in (STATE_HEATING_FLOOR, STATE_HEATING_CWU, STATE_EMERGENCY_CWU, STATE_SAFE_MODE):
            self.coord._log_action("Winter mode: Default to floor heating")
            await self.coord._switch_to_floor()
            self.coord._change_state(STATE_HEATING_FLOOR)
