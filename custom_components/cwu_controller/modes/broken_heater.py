"""Broken heater mode for CWU Controller.

This mode handles the scenario where the immersion heater is broken
and the heat pump tries to use it unsuccessfully.
"""

from __future__ import annotations

import logging
from datetime import datetime

from ..const import (
    STATE_IDLE,
    STATE_HEATING_CWU,
    STATE_HEATING_FLOOR,
    STATE_PAUSE,
    STATE_EMERGENCY_CWU,
    STATE_EMERGENCY_FLOOR,
    STATE_FAKE_HEATING_DETECTED,
    STATE_FAKE_HEATING_RESTARTING,
    URGENCY_CRITICAL,
    URGENCY_HIGH,
    CWU_MAX_HEATING_TIME,
    CWU_PAUSE_TIME,
    CWU_RAPID_DROP_THRESHOLD,
    CWU_RAPID_DROP_WINDOW,
    HP_RESTART_MIN_WAIT,
    DHW_CHARGED_REST_TIME,
    BROKEN_HEATER_FLOOR_WINDOW_START,
    BROKEN_HEATER_FLOOR_WINDOW_END,
    CONF_CWU_HYSTERESIS,
    DEFAULT_CWU_HYSTERESIS,
)
from .base import BaseModeHandler

_LOGGER = logging.getLogger(__name__)


class BrokenHeaterMode(BaseModeHandler):
    """Mode handler for broken heater scenario.

    Strategy:
    - CWU priority almost all day (except 03:00-06:00)
    - Night window 03:00-06:00: floor if CWU is OK
    - Respect HP states (Compressor off time, Defrosting, Overrun)
    - Anti-oscillation via minimum hold times
    - Max temp detection - give pump a break when it can't heat more
    - Rapid CWU drop detection - interrupt floor for hot water emergency
    - Fake heating detection - pump tries broken electric heater
    """

    async def run_logic(
        self,
        cwu_urgency: int,
        floor_urgency: int,
        cwu_temp: float | None,
        salon_temp: float | None,
    ) -> None:
        """Run control logic for broken heater mode."""
        # Check for fake heating using heat pump status
        fake_heating = self.coord._detect_fake_heating_bsb()

        await self._run_broken_heater_logic(
            cwu_urgency=cwu_urgency,
            floor_urgency=floor_urgency,
            fake_heating=fake_heating,
            cwu_temp=cwu_temp,
            salon_temp=salon_temp,
        )

    async def _run_broken_heater_logic(
        self,
        cwu_urgency: int,
        floor_urgency: int,
        fake_heating: bool,
        cwu_temp: float | None,
        salon_temp: float | None,
    ) -> None:
        """Run the main broken heater control logic."""
        now = datetime.now()
        current_hour = now.hour

        # =====================================================================
        # Phase 1: Handle fake heating detection (first detection)
        # =====================================================================
        if fake_heating and self._current_state in (STATE_HEATING_CWU, STATE_EMERGENCY_CWU):
            self._change_state(STATE_FAKE_HEATING_DETECTED)
            self.coord._fake_heating_detected_at = now
            self.coord._low_power_start = None  # Reset to prevent duplicate detection
            # Turn off BOTH CWU and floor
            await self._async_set_cwu_off()
            await self._async_set_floor_off()
            await self._async_send_notification(
                "CWU Controller Alert",
                f"Fake heating detected! Pump tried to use broken heater. "
                f"CWU temp: {cwu_temp}°C. Waiting {HP_RESTART_MIN_WAIT} min + HP ready check..."
            )
            self._log_action(
                "Fake heating",
                f"CWU+Floor OFF, CWU at {cwu_temp:.1f}°C, waiting {HP_RESTART_MIN_WAIT}+ min"
                if cwu_temp else f"CWU+Floor OFF, waiting {HP_RESTART_MIN_WAIT}+ min"
            )
            return

        # =====================================================================
        # Phase 2: Handle fake heating recovery (wait + HP ready check)
        # =====================================================================
        if self._current_state == STATE_FAKE_HEATING_DETECTED and self.coord._fake_heating_detected_at:
            elapsed = (now - self.coord._fake_heating_detected_at).total_seconds() / 60

            # Wait minimum time
            if elapsed < HP_RESTART_MIN_WAIT:
                return

            # Check HP status before restarting
            hp_ready, hp_reason = self._is_hp_ready_for_cwu()
            if not hp_ready:
                # Log only every 2 minutes to avoid spam
                if int(elapsed) % 2 == 0:
                    _LOGGER.debug("Fake heating recovery waiting: %s (%.1f min elapsed)", hp_reason, elapsed)
                return

            # HP ready - restart CWU
            self._change_state(STATE_FAKE_HEATING_RESTARTING)
            await self._async_set_floor_off()
            await self._async_set_cwu_on()
            self.coord._low_power_start = None
            self.coord._fake_heating_detected_at = None
            self._change_state(STATE_HEATING_CWU)
            self.coord._cwu_heating_start = now
            self.coord._last_mode_switch = now
            self._reset_max_temp_tracking()
            # Set session start temp
            cwu_start_temp = self.coord._get_cwu_temperature()
            self.coord._cwu_session_start_temp = cwu_start_temp if cwu_start_temp else self.coord._last_known_cwu_temp
            self._log_action(
                "CWU restarted after fake heating",
                f"HP ready after {elapsed:.1f} min wait, starting at {self.coord._cwu_session_start_temp:.1f}°C"
                if self.coord._cwu_session_start_temp else f"HP ready after {elapsed:.1f} min wait"
            )
            return

        # =====================================================================
        # Phase 3: Handle pause state (3h limit)
        # =====================================================================
        if self._current_state == STATE_PAUSE:
            if self.coord._is_pause_complete():
                self.coord._pause_start = None
                # Resume CWU heating - start new session
                await self._async_set_cwu_on()
                self._change_state(STATE_HEATING_CWU)
                self.coord._cwu_heating_start = now
                self.coord._last_mode_switch = now
                self._reset_max_temp_tracking()
                cwu_start_temp = self.coord._get_cwu_temperature()
                if cwu_start_temp is None:
                    cwu_start_temp = self.coord._last_known_cwu_temp
                self.coord._cwu_session_start_temp = cwu_start_temp
                self._log_action(
                    "Pause complete - new CWU session",
                    f"Starting at {cwu_start_temp:.1f}°C after {CWU_PAUSE_TIME} min pause"
                    if cwu_start_temp else f"Starting after {CWU_PAUSE_TIME} min pause"
                )
            return

        # =====================================================================
        # Phase 4: Check 3-hour CWU limit
        # =====================================================================
        if self._current_state == STATE_HEATING_CWU and self.coord._should_restart_cwu_cycle():
            self._change_state(STATE_PAUSE)
            self.coord._pause_start = now
            self.coord._cwu_heating_start = None
            await self._async_set_cwu_off()
            await self._async_set_floor_off()
            self._log_action(
                "CWU cycle limit reached - pause",
                f"CWU at {cwu_temp:.1f}°C after {CWU_MAX_HEATING_TIME} min, pausing for {CWU_PAUSE_TIME} min"
                if cwu_temp else f"Pausing for {CWU_PAUSE_TIME} min after {CWU_MAX_HEATING_TIME} min heating"
            )
            await self._async_send_notification(
                "CWU Controller",
                f"CWU heating paused for {CWU_PAUSE_TIME} min (3h limit). "
                f"CWU: {cwu_temp}°C, Salon: {salon_temp}°C"
            )
            return

        # =====================================================================
        # Phase 5: Rapid drop detection (bath/shower) - highest priority
        # =====================================================================
        drop_detected, drop_amount = self._detect_rapid_drop()
        if drop_detected and self._current_state == STATE_HEATING_FLOOR:
            can_switch, reason = self._can_switch_mode(STATE_EMERGENCY_CWU)
            if can_switch:
                self._log_action(
                    "Rapid CWU drop - emergency CWU",
                    f"{drop_amount:.1f}°C drop in {CWU_RAPID_DROP_WINDOW} min (threshold: {CWU_RAPID_DROP_THRESHOLD}°C)"
                )
                await self._switch_to_cwu()
                self._change_state(STATE_EMERGENCY_CWU)
                self.coord._cwu_heating_start = now
                self.coord._last_mode_switch = now
                self._reset_max_temp_tracking()
                await self._async_send_notification(
                    "CWU Drop Detected",
                    f"Hot water usage detected ({drop_amount:.1f}°C drop in {CWU_RAPID_DROP_WINDOW}min). "
                    f"Starting emergency CWU heating."
                )
            else:
                _LOGGER.debug("Rapid drop detected but switch blocked: %s", reason)
            return

        # =====================================================================
        # Phase 6: Max temp detection (pump can't heat more)
        # =====================================================================
        if self._current_state in (STATE_HEATING_CWU, STATE_EMERGENCY_CWU):
            if self.coord._detect_max_temp_achieved():
                can_switch, reason = self._can_switch_mode(STATE_HEATING_FLOOR)
                if can_switch:
                    self._log_action(
                        "Max temp reached - switch to floor",
                        f"CWU at {self.coord._max_temp_achieved:.1f}°C, pump cannot heat higher"
                    )
                    await self._switch_to_floor()
                    self._change_state(STATE_HEATING_FLOOR)
                    self.coord._cwu_heating_start = None
                    self.coord._last_mode_switch = now
                    await self._async_send_notification(
                        "CWU Max Temp Reached",
                        f"Pump reached maximum achievable temp: {self.coord._max_temp_achieved}°C. "
                        f"Switching to floor heating."
                    )
                else:
                    _LOGGER.debug("Max temp reached but switch blocked: %s", reason)
                return

        # =====================================================================
        # Phase 7: Night window 03:00-06:00 - floor if CWU OK
        # =====================================================================
        if BROKEN_HEATER_FLOOR_WINDOW_START <= current_hour < BROKEN_HEATER_FLOOR_WINDOW_END:
            if self.coord._is_cwu_temp_acceptable(cwu_temp) and cwu_urgency < URGENCY_CRITICAL:
                if self._current_state != STATE_HEATING_FLOOR:
                    can_switch, reason = self._can_switch_mode(STATE_HEATING_FLOOR)
                    if can_switch:
                        min_temp = self._get_min_temp()
                        self._log_action(
                            "Night window - switch to floor",
                            f"CWU OK at {cwu_temp:.1f}°C >= {min_temp:.0f}°C, {BROKEN_HEATER_FLOOR_WINDOW_START}:00-{BROKEN_HEATER_FLOOR_WINDOW_END}:00 window"
                        )
                        await self._switch_to_floor()
                        self._change_state(STATE_HEATING_FLOOR)
                        self.coord._cwu_heating_start = None
                        self.coord._last_mode_switch = now
                    else:
                        _LOGGER.debug("Night window floor switch blocked: %s", reason)
                return
            # CWU not acceptable in night window - continue to normal logic

        # =====================================================================
        # Phase 8: Emergency handling (critical urgencies)
        # =====================================================================
        if cwu_urgency == URGENCY_CRITICAL and floor_urgency != URGENCY_CRITICAL:
            if self._current_state != STATE_EMERGENCY_CWU:
                can_switch, reason = self._can_switch_mode(STATE_EMERGENCY_CWU)
                if can_switch:
                    critical_temp = self._get_critical_temp()
                    self._log_action(
                        "CWU Emergency - switch to CWU",
                        f"CWU critically low: {cwu_temp:.1f}°C < {critical_temp:.0f}°C"
                    )
                    await self._switch_to_cwu()
                    self._change_state(STATE_EMERGENCY_CWU)
                    self.coord._cwu_heating_start = now
                    self.coord._last_mode_switch = now
                    self._reset_max_temp_tracking()
                    await self._async_send_notification(
                        "CWU Emergency!",
                        f"CWU critically low: {cwu_temp}°C! Switching to emergency CWU heating."
                    )
                else:
                    _LOGGER.debug("CWU emergency delayed: %s", reason)
            return

        if floor_urgency == URGENCY_CRITICAL and cwu_urgency != URGENCY_CRITICAL:
            if self._current_state != STATE_EMERGENCY_FLOOR:
                can_switch, reason = self._can_switch_mode(STATE_EMERGENCY_FLOOR)
                if can_switch:
                    self._log_action(
                        "Floor Emergency - switch to floor",
                        f"Room critically cold: Salon {salon_temp:.1f}°C"
                    )
                    await self._switch_to_floor()
                    self._change_state(STATE_EMERGENCY_FLOOR)
                    self.coord._cwu_heating_start = None
                    self.coord._last_mode_switch = now
                    await self._async_send_notification(
                        "Floor Emergency!",
                        f"Room too cold: Salon {salon_temp}°C! Switching to floor heating."
                    )
                else:
                    _LOGGER.debug("Floor emergency delayed: %s", reason)
            return

        # Both critical - alternate every 45 minutes
        if cwu_urgency == URGENCY_CRITICAL and floor_urgency == URGENCY_CRITICAL:
            minutes_in_state = (now - self.coord._last_state_change).total_seconds() / 60
            if minutes_in_state >= 45:
                if self._current_state in (STATE_HEATING_CWU, STATE_EMERGENCY_CWU):
                    await self._switch_to_floor()
                    self._change_state(STATE_EMERGENCY_FLOOR)
                    self.coord._last_mode_switch = now
                else:
                    await self._switch_to_cwu()
                    self._change_state(STATE_EMERGENCY_CWU)
                    self.coord._cwu_heating_start = now
                    self.coord._last_mode_switch = now
                    self._reset_max_temp_tracking()
            return

        # =====================================================================
        # Phase 9: Normal operation - CWU priority (daytime)
        # =====================================================================
        target = self._get_target_temp()

        # Currently heating floor - check if should resume CWU
        if self._current_state == STATE_HEATING_FLOOR:
            should_resume = False
            resume_reason = ""

            hysteresis = self.get_config_value(CONF_CWU_HYSTERESIS, DEFAULT_CWU_HYSTERESIS)
            if cwu_temp is not None and cwu_temp < target - hysteresis:
                should_resume = True
                resume_reason = f"temp {cwu_temp:.1f}°C < target-{hysteresis:.0f} ({target - hysteresis:.1f}°C)"
            elif cwu_urgency >= URGENCY_HIGH:
                should_resume = True
                resume_reason = f"urgency HIGH ({cwu_urgency})"
            elif not self.coord._is_cwu_temp_acceptable(cwu_temp):
                should_resume = True
                resume_reason = f"temp {cwu_temp}°C not acceptable"

            if should_resume:
                can_switch, reason = self._can_switch_mode(STATE_HEATING_CWU)
                if can_switch:
                    self._log_action("Resuming CWU", resume_reason)
                    await self._switch_to_cwu()
                    self._change_state(STATE_HEATING_CWU)
                    self.coord._cwu_heating_start = now
                    self.coord._last_mode_switch = now
                    self._reset_max_temp_tracking()
                    # Set session start temp
                    cwu_start_temp = self.coord._get_cwu_temperature()
                    self.coord._cwu_session_start_temp = cwu_start_temp if cwu_start_temp else self.coord._last_known_cwu_temp
                else:
                    _LOGGER.debug("CWU resume blocked: %s", reason)
            return

        # Currently heating CWU - check if should switch to floor
        if self._current_state in (STATE_HEATING_CWU, STATE_EMERGENCY_CWU):
            # Check if pump reports "Charged" (reached target)
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
                        _LOGGER.debug(f"Floor switch after Charged blocked: {reason}")
            else:
                # Not charged anymore - reset
                self.coord._dhw_charged_at = None
            return

        # Idle - start CWU only if temp is below target - hysteresis
        if self._current_state == STATE_IDLE:
            target = self._get_target_temp()
            hysteresis = self.get_config_value(CONF_CWU_HYSTERESIS, DEFAULT_CWU_HYSTERESIS)
            cwu_start_temp = self.coord._get_cwu_temperature()

            # Only start if temp is below threshold (respects hysteresis)
            if cwu_start_temp is not None and cwu_start_temp >= target - hysteresis:
                # Temp is OK, stay idle
                _LOGGER.debug(
                    f"Idle: CWU {cwu_start_temp:.1f}°C >= threshold {target - hysteresis:.1f}°C, staying idle"
                )
                return

            self._log_action(
                "CWU ON",
                f"CWU {cwu_start_temp:.1f}°C < threshold {target - hysteresis:.1f}°C"
                if cwu_start_temp else "Starting CWU heating (no temp data)"
            )
            await self._switch_to_cwu()
            self._change_state(STATE_HEATING_CWU)
            self.coord._cwu_heating_start = now
            self.coord._last_mode_switch = now
            self._reset_max_temp_tracking()
            self.coord._cwu_session_start_temp = cwu_start_temp if cwu_start_temp else self.coord._last_known_cwu_temp
