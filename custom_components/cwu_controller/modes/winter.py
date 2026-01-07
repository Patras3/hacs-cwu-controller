"""Winter mode for CWU Controller.

Scheduled CWU heating during cheap tariff windows.
Uses same temperature targets as broken_heater mode.
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
    CONF_CWU_HYSTERESIS,
    DEFAULT_CWU_HYSTERESIS,
    DHW_CHARGED_REST_TIME,
)
from .base import BaseModeHandler

_LOGGER = logging.getLogger(__name__)


class WinterMode(BaseModeHandler):
    """Mode handler for winter scheduled heating.

    Winter mode features:
    - Heat CWU during cheap tariff windows (03:00-06:00, 13:00-15:00, 22:00-24:00)
    - No 3-hour session limit (heat until target reached)
    - Same CWU target temperature as other modes (no +5°C offset)
    - Hysteresis support (same as broken_heater)
    - Anti-oscillation via minimum hold times
    - DHW Charged handling (wait before switching)
    - Fake heating detection with notification (heater monitoring)
    - Only heat CWU outside windows if temperature drops below min threshold
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
        target = self._get_target_temp()
        min_temp = self._get_min_temp()
        hysteresis = self.get_config_value(CONF_CWU_HYSTERESIS, DEFAULT_CWU_HYSTERESIS)
        is_heating_window = self.coord.is_winter_cwu_heating_window()

        # =====================================================================
        # Phase 1: Heater not working detection (winter mode specific)
        # Detects: "Charging electric" status but power < 2500W for 5+ minutes
        # =====================================================================
        if self._current_state in (STATE_HEATING_CWU, STATE_EMERGENCY_CWU):
            heater_broken = self.coord._detect_heater_not_working()
            if heater_broken:
                # Only send notification once per event
                if self.coord._fake_heating_detected_at is None:
                    self.coord._fake_heating_detected_at = now
                    await self._async_send_notification(
                        "⚠️ Electric Heater Not Working!",
                        f"Pump reports 'Charging electric' but power is too low.\n"
                        f"Expected: >2500W (3.3kW heater)\n"
                        f"CWU temp: {cwu_temp}°C\n\n"
                        f"The heater may be broken! Heating continues with heat pump only..."
                    )
                    self._log_action(
                        "Heater not working",
                        f"'Charging electric' but low power, CWU at {cwu_temp:.1f}°C"
                        if cwu_temp else "'Charging electric' but low power"
                    )
                # Don't return - continue with normal logic
            else:
                # Condition cleared - reset tracking
                if self.coord._fake_heating_detected_at is not None:
                    self.coord._fake_heating_detected_at = None
                    self._log_action(
                        "Heater working",
                        f"Power consumption normal, CWU at {cwu_temp:.1f}°C"
                        if cwu_temp else "Power consumption normal"
                    )

        # =====================================================================
        # Phase 2: Emergency handling - critical floor temperature takes priority
        # =====================================================================
        if floor_urgency == URGENCY_CRITICAL:
            if self._current_state != STATE_EMERGENCY_FLOOR:
                can_switch, reason = self._can_switch_mode(STATE_EMERGENCY_FLOOR)
                if can_switch:
                    await self._switch_to_floor()
                    self._change_state(STATE_EMERGENCY_FLOOR)
                    self.coord._cwu_heating_start = None
                    self.coord._last_mode_switch = now
                    await self._async_send_notification(
                        "Floor Emergency!",
                        f"Room critically cold: Salon {salon_temp}°C! Switching to floor heating."
                    )
                else:
                    _LOGGER.debug("Floor emergency delayed: %s", reason)
            return

        # =====================================================================
        # Phase 3: Safety check - no progress after 3 hours of CWU heating
        # =====================================================================
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
                self.coord._last_mode_switch = now
                return

        # =====================================================================
        # Phase 4: DHW Charged handling (pump reports target reached)
        # =====================================================================
        if self._current_state in (STATE_HEATING_CWU, STATE_EMERGENCY_CWU):
            if self._is_pump_charged():
                # DHW Charged rest time - wait before switching to floor
                if self.coord._dhw_charged_at is None:
                    self.coord._dhw_charged_at = now
                    self._log_action(
                        "DHW Charged",
                        f"Pump reports charged at {cwu_temp:.1f}°C, waiting {DHW_CHARGED_REST_TIME}min"
                        if cwu_temp else f"Pump reports charged, waiting {DHW_CHARGED_REST_TIME}min"
                    )

                # Check if rest time elapsed
                elapsed = (now - self.coord._dhw_charged_at).total_seconds() / 60
                if elapsed >= DHW_CHARGED_REST_TIME:
                    can_switch, reason = self._can_switch_mode(STATE_HEATING_FLOOR)
                    if can_switch:
                        await self._switch_to_floor()
                        self._change_state(STATE_HEATING_FLOOR)
                        self.coord._cwu_heating_start = None
                        self.coord._last_mode_switch = now
                        self.coord._dhw_charged_at = None
                        self._log_action(
                            "Switch to floor",
                            f"DHW rest complete ({elapsed:.0f}min), CWU at {cwu_temp:.1f}°C"
                            if cwu_temp else f"DHW rest complete ({elapsed:.0f}min)"
                        )
                    else:
                        _LOGGER.debug("Floor switch after Charged blocked: %s", reason)
                return
            else:
                # Not charged anymore - reset
                self.coord._dhw_charged_at = None

        # =====================================================================
        # Phase 5: Handle CWU heating window (03:00-06:00, 13:00-15:00, 22:00-24:00)
        # =====================================================================
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

            # Check if we should start CWU heating (with hysteresis)
            if cwu_temp < target - hysteresis:
                if self._current_state not in (STATE_HEATING_CWU, STATE_EMERGENCY_CWU):
                    can_switch, reason = self._can_switch_mode(STATE_HEATING_CWU)
                    if can_switch:
                        await self._switch_to_cwu()
                        self._change_state(STATE_HEATING_CWU)
                        self.coord._cwu_heating_start = now
                        self.coord._cwu_session_start_temp = cwu_temp
                        self.coord._last_mode_switch = now
                        self._log_action(
                            "Heating window CWU",
                            f"CWU {cwu_temp:.1f}°C < threshold {target - hysteresis:.1f}°C (target {target:.0f}°C)"
                        )
                    else:
                        _LOGGER.debug("CWU start blocked: %s", reason)
                # Continue heating until target reached (no session limit in winter mode)
                return

            # CWU temp is OK (above target - hysteresis) - check if we should stop
            if self._current_state in (STATE_HEATING_CWU, STATE_EMERGENCY_CWU):
                # Only stop if we've reached the full target
                if cwu_temp >= target:
                    can_switch, reason = self._can_switch_mode(STATE_HEATING_FLOOR)
                    if can_switch:
                        self._log_action(
                            "Target reached",
                            f"CWU {cwu_temp:.1f}°C >= target {target:.0f}°C"
                        )
                        await self._switch_to_floor()
                        self._change_state(STATE_HEATING_FLOOR)
                        self.coord._cwu_heating_start = None
                        self.coord._last_mode_switch = now
                    else:
                        _LOGGER.debug("Floor switch blocked: %s", reason)
                return

            # CWU is OK during window, heat floor
            if self._current_state != STATE_HEATING_FLOOR:
                can_switch, reason = self._can_switch_mode(STATE_HEATING_FLOOR)
                if can_switch:
                    self._log_action(
                        "Floor (CWU OK in window)",
                        f"CWU {cwu_temp:.1f}°C OK (target {target:.0f}°C)"
                    )
                    await self._switch_to_floor()
                    self._change_state(STATE_HEATING_FLOOR)
                    self.coord._last_mode_switch = now
                else:
                    _LOGGER.debug("Floor switch blocked: %s", reason)
            return

        # =====================================================================
        # Phase 6: Outside heating window - handle unknown temp
        # =====================================================================
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

        # =====================================================================
        # Phase 7: Outside window - emergency CWU if below min threshold
        # =====================================================================
        if cwu_temp < min_temp:
            if self._current_state not in (STATE_HEATING_CWU, STATE_EMERGENCY_CWU):
                can_switch, reason = self._can_switch_mode(STATE_EMERGENCY_CWU)
                if can_switch:
                    await self._switch_to_cwu()
                    self._change_state(STATE_EMERGENCY_CWU)
                    self.coord._cwu_heating_start = now
                    self.coord._cwu_session_start_temp = cwu_temp
                    self.coord._last_mode_switch = now
                    await self._async_send_notification(
                        "CWU Emergency (Winter Mode)",
                        f"CWU dropped to {cwu_temp}°C (below {min_temp}°C threshold). "
                        f"Starting emergency heating outside window."
                    )
                    self._log_action(
                        "Emergency CWU",
                        f"CWU {cwu_temp:.1f}°C < min {min_temp:.0f}°C"
                    )
                else:
                    _LOGGER.debug("Emergency CWU blocked: %s", reason)
            # If already in emergency heating, continue
            return

        # =====================================================================
        # Phase 8: Exit emergency CWU if temp risen above min + buffer
        # =====================================================================
        if self._current_state == STATE_EMERGENCY_CWU:
            buffer_temp = min_temp + 3.0
            if cwu_temp >= buffer_temp:
                can_switch, reason = self._can_switch_mode(STATE_HEATING_FLOOR)
                if can_switch:
                    self._log_action(
                        "Emergency complete",
                        f"CWU {cwu_temp:.1f}°C >= buffer {buffer_temp:.0f}°C"
                    )
                    await self._switch_to_floor()
                    self._change_state(STATE_HEATING_FLOOR)
                    self.coord._cwu_heating_start = None
                    self.coord._last_mode_switch = now
                else:
                    _LOGGER.debug("Floor switch after emergency blocked: %s", reason)
                return

        # =====================================================================
        # Phase 9: Currently heating CWU outside window - check if target reached
        # =====================================================================
        if self._current_state in (STATE_HEATING_CWU, STATE_EMERGENCY_CWU):
            if cwu_temp >= target:
                can_switch, reason = self._can_switch_mode(STATE_HEATING_FLOOR)
                if can_switch:
                    self._log_action(
                        "Switch to floor",
                        f"CWU {cwu_temp:.1f}°C >= target {target:.0f}°C"
                    )
                    await self._switch_to_floor()
                    self._change_state(STATE_HEATING_FLOOR)
                    self.coord._cwu_heating_start = None
                    self.coord._last_mode_switch = now
                else:
                    _LOGGER.debug("Floor switch blocked: %s", reason)
                return

        # =====================================================================
        # Phase 10: Default - heat floor if not already doing something
        # =====================================================================
        if self._current_state not in (STATE_HEATING_FLOOR, STATE_HEATING_CWU, STATE_EMERGENCY_CWU, STATE_SAFE_MODE):
            can_switch, reason = self._can_switch_mode(STATE_HEATING_FLOOR)
            if can_switch:
                self._log_action(
                    "Default to floor",
                    f"From {self._current_state}, CWU {cwu_temp:.1f}°C" if cwu_temp else f"From {self._current_state}"
                )
                await self._switch_to_floor()
                self._change_state(STATE_HEATING_FLOOR)
                self.coord._last_mode_switch = now
            else:
                _LOGGER.debug("Default floor switch blocked: %s", reason)
