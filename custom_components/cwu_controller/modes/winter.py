"""Winter mode for CWU Controller.

Scheduled CWU heating during cheap tariff windows with higher target temperature.
"""

from __future__ import annotations

import logging
from datetime import datetime

from ..const import (
    STATE_HEATING_CWU,
    STATE_HEATING_FLOOR,
    STATE_EMERGENCY_CWU,
    STATE_EMERGENCY_FLOOR,
    STATE_SAFE_MODE,
    URGENCY_CRITICAL,
)
from .base import BaseModeHandler

_LOGGER = logging.getLogger(__name__)


class WinterMode(BaseModeHandler):
    """Mode handler for winter scheduled heating.

    Winter mode features:
    - Heat CWU during cheap tariff windows (03:00-06:00, 13:00-15:00, 22:00-24:00)
    - No 3-hour session limit (heat until target reached)
    - No fake heating detection (pump can use real heater)
    - Higher CWU target temperature (+5°C from config)
    - Only heat CWU outside windows if temperature drops significantly
    - When not heating water -> heat house
    """

    async def run_logic(
        self,
        cwu_urgency: int,
        floor_urgency: int,
        cwu_temp: float | None,
        salon_temp: float | None,
    ) -> None:
        """Run control logic for winter mode."""
        now = datetime.now()
        winter_target = self.coord.get_winter_cwu_target()
        emergency_threshold = self.coord.get_winter_cwu_emergency_threshold()
        is_heating_window = self.coord.is_winter_cwu_heating_window()

        # Emergency handling - critical floor temperature takes priority
        if floor_urgency == URGENCY_CRITICAL:
            if self._current_state != STATE_EMERGENCY_FLOOR:
                await self._switch_to_floor()
                self._change_state(STATE_EMERGENCY_FLOOR)
                await self._async_send_notification(
                    "Floor Emergency!",
                    f"Room critically cold: Salon {salon_temp}°C! Switching to floor heating."
                )
            return

        # Safety check: no progress after 3 hours of CWU heating
        if self._current_state in (STATE_HEATING_CWU, STATE_EMERGENCY_CWU):
            if self.coord._check_winter_cwu_no_progress(cwu_temp):
                start_temp = self.coord._cwu_session_start_temp
                elapsed_hours = (now - self.coord._cwu_heating_start).total_seconds() / 3600 if self.coord._cwu_heating_start else 0
                self._log_action(
                    "No progress timeout",
                    f"After {elapsed_hours:.1f}h (start: {start_temp}°C → {cwu_temp}°C)"
                )
                await self._async_send_notification(
                    "CWU Heating Problem (Winter Mode)",
                    f"CWU temperature hasn't increased after {elapsed_hours:.1f} hours of heating.\n"
                    f"Started at: {start_temp}°C\n"
                    f"Current: {cwu_temp}°C\n\n"
                    f"Switching to floor heating. Please check the heat pump."
                )
                await self._switch_to_floor()
                self._change_state(STATE_HEATING_FLOOR)
                self.coord._cwu_heating_start = None
                self.coord._cwu_session_start_temp = None
                return

        # Handle CWU heating window (03:00-06:00, 13:00-15:00, 22:00-24:00)
        if is_heating_window:
            # During heating window: heat CWU if below target OR if temp unknown
            if cwu_temp is None:
                # Temperature unknown - enable both, let pump decide (safe default)
                if self._current_state != STATE_SAFE_MODE:
                    self._log_action(
                        "Safe mode",
                        "CWU temp unknown during heating window"
                    )
                    _LOGGER.warning(
                        "CWU temperature unavailable during heating window - enabling both floor+CWU"
                    )
                    await self._enter_safe_mode()
                    self._change_state(STATE_SAFE_MODE)
                return
            elif cwu_temp < winter_target:
                if self._current_state != STATE_HEATING_CWU:
                    await self._switch_to_cwu()
                    self._change_state(STATE_HEATING_CWU)
                    self.coord._cwu_heating_start = now
                    self.coord._cwu_session_start_temp = cwu_temp
                    self._log_action(
                        "Heating window CWU",
                        f"CWU {cwu_temp:.1f}°C → target {winter_target:.0f}°C"
                    )
                # Continue heating until target reached (no session limit in winter mode)
                return
            else:
                # Target reached during window - switch to floor
                if self._current_state == STATE_HEATING_CWU:
                    self._log_action(
                        "Target reached",
                        f"CWU {cwu_temp:.1f}°C >= target {winter_target:.0f}°C"
                    )
                    await self._switch_to_floor()
                    self._change_state(STATE_HEATING_FLOOR)
                    self.coord._cwu_heating_start = None
                return

        # Outside heating window: if temp unknown, enable both (pump decides)
        if cwu_temp is None:
            if self._current_state != STATE_SAFE_MODE:
                self._log_action(
                    "Safe mode",
                    "CWU temp unknown outside window"
                )
                _LOGGER.warning(
                    "CWU temperature unavailable outside heating window - enabling both floor+CWU"
                )
                await self._enter_safe_mode()
                self._change_state(STATE_SAFE_MODE)
            return

        # Outside heating window: only heat CWU in emergency (below threshold)
        if cwu_temp < emergency_threshold:
            if self._current_state not in (STATE_HEATING_CWU, STATE_EMERGENCY_CWU):
                await self._switch_to_cwu()
                self._change_state(STATE_EMERGENCY_CWU)
                self.coord._cwu_heating_start = now
                self.coord._cwu_session_start_temp = cwu_temp
                await self._async_send_notification(
                    "CWU Emergency (Winter Mode)",
                    f"CWU dropped to {cwu_temp}°C (below {emergency_threshold}°C threshold). "
                    f"Starting emergency heating outside window."
                )
                self._log_action(
                    "Emergency CWU",
                    f"CWU {cwu_temp:.1f}°C < threshold {emergency_threshold:.0f}°C"
                )
            # If already in emergency heating, continue until buffer temp reached
            return

        # Check if we should exit emergency CWU heating (temp risen above buffer)
        if self._current_state == STATE_EMERGENCY_CWU and cwu_temp is not None:
            buffer_temp = emergency_threshold + 3.0
            if cwu_temp >= buffer_temp:
                self._log_action(
                    "Emergency complete",
                    f"CWU {cwu_temp:.1f}°C >= buffer {buffer_temp:.0f}°C"
                )
                await self._switch_to_floor()
                self._change_state(STATE_HEATING_FLOOR)
                self.coord._cwu_heating_start = None
                return

        # Currently heating CWU but outside window and above emergency threshold
        if self._current_state in (STATE_HEATING_CWU, STATE_EMERGENCY_CWU):
            if cwu_temp is not None and cwu_temp >= winter_target:
                self._log_action(
                    "Switch to floor",
                    f"CWU {cwu_temp:.1f}°C >= target {winter_target:.0f}°C"
                )
                await self._switch_to_floor()
                self._change_state(STATE_HEATING_FLOOR)
                self.coord._cwu_heating_start = None
                return

        # Default: heat floor (if not already heating something)
        if self._current_state not in (STATE_HEATING_FLOOR, STATE_HEATING_CWU, STATE_EMERGENCY_CWU, STATE_SAFE_MODE):
            self._log_action(
                "Default to floor",
                f"From {self._current_state}, CWU {cwu_temp:.1f}°C" if cwu_temp else f"From {self._current_state}"
            )
            await self._switch_to_floor()
            self._change_state(STATE_HEATING_FLOOR)
