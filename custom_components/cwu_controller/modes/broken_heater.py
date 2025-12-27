"""Broken heater mode handler for CWU Controller.

This mode handles the scenario where the immersion heater is broken and the
heat pump tries to use it but fails. It includes:
- 3-hour CWU cycle limit with 10-min pause
- Fake heating detection via BSB-LAN
- Anti-oscillation with minimum hold times
- Night floor window (03:00-06:00)
- Max temp detection
- Anti-fighting detection
- Rapid drop detection
- DHW Charged handling
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

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
    CWU_PAUSE_TIME,
    BROKEN_HEATER_FLOOR_WINDOW_START,
    BROKEN_HEATER_FLOOR_WINDOW_END,
    HP_RESTART_MIN_WAIT,
    CWU_RAPID_DROP_WINDOW,
    DHW_CHARGED_REST_TIME,
    CONF_CWU_HYSTERESIS,
    DEFAULT_CWU_HYSTERESIS,
)
from .base import BaseModeHandler

if TYPE_CHECKING:
    from ..coordinator import CWUControllerCoordinator


class BrokenHeaterMode(BaseModeHandler):
    """Broken heater mode - fake heating detection, anti-fighting, etc.

    Strategy:
    - CWU priority almost all day (except 03:00-06:00)
    - Night window 03:00-06:00: floor if CWU is OK
    - Respect HP states (Compressor off time, Defrosting, Overrun)
    - Anti-oscillation via minimum hold times
    - Max temp detection - give pump a break when it can't heat more
    - Rapid CWU drop detection - interrupt floor for hot water emergency
    """

    def __init__(self, coordinator: "CWUControllerCoordinator") -> None:
        """Initialize the broken heater mode handler."""
        super().__init__(coordinator)

    async def run_logic(
        self,
        cwu_urgency: int,
        floor_urgency: int,
        cwu_temp: float | None,
        salon_temp: float | None,
        **kwargs,
    ) -> None:
        """Run control logic for broken heater mode.

        Args:
            cwu_urgency: Current CWU heating urgency level.
            floor_urgency: Current floor heating urgency level.
            cwu_temp: Current CWU temperature.
            salon_temp: Current salon temperature.
            **kwargs: Must include 'fake_heating' (bool).
        """
        fake_heating = kwargs.get("fake_heating", False)
        now = datetime.now()
        current_hour = now.hour

        # =====================================================================
        # Phase 1: Handle fake heating detection (first detection)
        # =====================================================================
        if fake_heating and self.coord._current_state in (STATE_HEATING_CWU, STATE_EMERGENCY_CWU):
            self.coord._change_state(STATE_FAKE_HEATING_DETECTED)
            self.coord._fake_heating_detected_at = now
            self.coord._low_power_start = None  # Reset to prevent duplicate detection
            # Turn off BOTH CWU and floor
            await self.coord._async_set_cwu_off()
            await self.coord._async_set_floor_off()
            await self.coord._async_send_notification(
                "CWU Controller Alert",
                f"Fake heating detected! Pump tried to use broken heater. "
                f"CWU temp: {cwu_temp}°C. Waiting {HP_RESTART_MIN_WAIT} min + HP ready check..."
            )
            self.coord._log_action(
                "Fake heating",
                f"CWU+Floor OFF, CWU at {cwu_temp:.1f}°C, waiting {HP_RESTART_MIN_WAIT}+ min"
                if cwu_temp else f"CWU+Floor OFF, waiting {HP_RESTART_MIN_WAIT}+ min"
            )
            return

        # =====================================================================
        # Phase 2: Handle fake heating recovery (wait + HP ready check)
        # =====================================================================
        if self.coord._current_state == STATE_FAKE_HEATING_DETECTED and self.coord._fake_heating_detected_at:
            elapsed = (now - self.coord._fake_heating_detected_at).total_seconds() / 60

            # Wait minimum time
            if elapsed < HP_RESTART_MIN_WAIT:
                return

            # Check HP status before restarting
            hp_ready, hp_reason = self.coord._is_hp_ready_for_cwu()
            if not hp_ready:
                # Log only every 2 minutes to avoid spam
                if int(elapsed) % 2 == 0:
                    self.coord._log_action(f"Fake heating recovery waiting: {hp_reason}")
                return

            # HP ready - restart CWU
            self.coord._change_state(STATE_FAKE_HEATING_RESTARTING)
            self.coord._log_action("HP ready - restarting CWU after fake heating")
            await self.coord._async_set_floor_off()
            await self.coord._async_set_cwu_on()
            self.coord._low_power_start = None
            self.coord._fake_heating_detected_at = None
            self.coord._change_state(STATE_HEATING_CWU)
            self.coord._cwu_heating_start = now
            self.coord._last_mode_switch = now
            self.coord._reset_max_temp_tracking()
            # Set session start temp
            cwu_start_temp = self.coord._get_cwu_temperature()
            self.coord._cwu_session_start_temp = cwu_start_temp if cwu_start_temp else self.coord._last_known_cwu_temp
            self.coord._log_action(f"CWU restarted after fake heating (temp: {self.coord._cwu_session_start_temp}°C)")
            return

        # =====================================================================
        # Phase 3: Handle pause state (3h limit)
        # =====================================================================
        if self.coord._current_state == STATE_PAUSE:
            if self.coord._is_pause_complete():
                self.coord._pause_start = None
                # Resume CWU heating - start new session
                await self.coord._async_set_cwu_on()
                self.coord._change_state(STATE_HEATING_CWU)
                self.coord._cwu_heating_start = now
                self.coord._last_mode_switch = now
                self.coord._reset_max_temp_tracking()
                cwu_start_temp = self.coord._get_cwu_temperature()
                if cwu_start_temp is None:
                    cwu_start_temp = self.coord._last_known_cwu_temp
                self.coord._cwu_session_start_temp = cwu_start_temp
                self.coord._log_action(f"Pause complete, starting new CWU session (temp: {cwu_start_temp}°C)")
            return

        # =====================================================================
        # Phase 4: Check 3-hour CWU limit
        # =====================================================================
        if self.coord._current_state == STATE_HEATING_CWU and self.coord._should_restart_cwu_cycle():
            self.coord._change_state(STATE_PAUSE)
            self.coord._pause_start = now
            self.coord._cwu_heating_start = None
            await self.coord._async_set_cwu_off()
            await self.coord._async_set_floor_off()
            self.coord._log_action(f"CWU cycle limit reached, pausing for {CWU_PAUSE_TIME} minutes")
            await self.coord._async_send_notification(
                "CWU Controller",
                f"CWU heating paused for {CWU_PAUSE_TIME} min (3h limit). "
                f"CWU: {cwu_temp}°C, Salon: {salon_temp}°C"
            )
            return

        # =====================================================================
        # Phase 5: Rapid drop detection (bath/shower) - highest priority
        # =====================================================================
        drop_detected, drop_amount = self.coord._detect_rapid_drop()
        if drop_detected and self.coord._current_state == STATE_HEATING_FLOOR:
            can_switch, reason = self.coord._can_switch_mode(STATE_HEATING_FLOOR, STATE_EMERGENCY_CWU)
            if can_switch:
                self.coord._log_action(f"Rapid CWU drop {drop_amount:.1f}°C - emergency switch to CWU")
                await self.coord._switch_to_cwu()
                self.coord._change_state(STATE_EMERGENCY_CWU)
                self.coord._cwu_heating_start = now
                self.coord._last_mode_switch = now
                self.coord._reset_max_temp_tracking()
                await self.coord._async_send_notification(
                    "CWU Drop Detected",
                    f"Hot water usage detected ({drop_amount:.1f}°C drop in {CWU_RAPID_DROP_WINDOW}min). "
                    f"Starting emergency CWU heating."
                )
            else:
                self.coord._log_action(f"Rapid drop detected but switch blocked: {reason}")
            return

        # =====================================================================
        # Phase 6: Max temp detection (pump can't heat more)
        # =====================================================================
        if self.coord._current_state in (STATE_HEATING_CWU, STATE_EMERGENCY_CWU):
            if self.coord._detect_max_temp_achieved():
                can_switch, reason = self.coord._can_switch_mode(self.coord._current_state, STATE_HEATING_FLOOR)
                if can_switch:
                    self.coord._log_action(f"Max temp {self.coord._max_temp_achieved}°C reached - switching to floor")
                    await self.coord._switch_to_floor()
                    self.coord._change_state(STATE_HEATING_FLOOR)
                    self.coord._cwu_heating_start = None
                    self.coord._last_mode_switch = now
                    await self.coord._async_send_notification(
                        "CWU Max Temp Reached",
                        f"Pump reached maximum achievable temp: {self.coord._max_temp_achieved}°C. "
                        f"Switching to floor heating."
                    )
                else:
                    self.coord._log_action(f"Max temp reached but switch blocked: {reason}")
                return

        # =====================================================================
        # Phase 7: Night window 03:00-06:00 - floor if CWU OK
        # =====================================================================
        if BROKEN_HEATER_FLOOR_WINDOW_START <= current_hour < BROKEN_HEATER_FLOOR_WINDOW_END:
            if self.coord._is_cwu_temp_acceptable(cwu_temp) and cwu_urgency < URGENCY_CRITICAL:
                if self.coord._current_state != STATE_HEATING_FLOOR:
                    can_switch, reason = self.coord._can_switch_mode(self.coord._current_state, STATE_HEATING_FLOOR)
                    if can_switch:
                        self.coord._log_action(f"Night window: CWU OK ({cwu_temp}°C), switching to floor")
                        await self.coord._switch_to_floor()
                        self.coord._change_state(STATE_HEATING_FLOOR)
                        self.coord._cwu_heating_start = None
                        self.coord._last_mode_switch = now
                return
            # CWU not acceptable in night window - continue to normal logic

        # =====================================================================
        # Phase 8: Emergency handling (critical urgencies)
        # =====================================================================
        if cwu_urgency == URGENCY_CRITICAL and floor_urgency != URGENCY_CRITICAL:
            if self.coord._current_state != STATE_EMERGENCY_CWU:
                can_switch, reason = self.coord._can_switch_mode(self.coord._current_state, STATE_EMERGENCY_CWU)
                if can_switch:
                    await self.coord._switch_to_cwu()
                    self.coord._change_state(STATE_EMERGENCY_CWU)
                    self.coord._cwu_heating_start = now
                    self.coord._last_mode_switch = now
                    self.coord._reset_max_temp_tracking()
                    await self.coord._async_send_notification(
                        "CWU Emergency!",
                        f"CWU critically low: {cwu_temp}°C! Switching to emergency CWU heating."
                    )
                else:
                    self.coord._log_action(f"CWU emergency delayed: {reason}")
            return

        if floor_urgency == URGENCY_CRITICAL and cwu_urgency != URGENCY_CRITICAL:
            if self.coord._current_state != STATE_EMERGENCY_FLOOR:
                can_switch, reason = self.coord._can_switch_mode(self.coord._current_state, STATE_EMERGENCY_FLOOR)
                if can_switch:
                    await self.coord._switch_to_floor()
                    self.coord._change_state(STATE_EMERGENCY_FLOOR)
                    self.coord._cwu_heating_start = None
                    self.coord._last_mode_switch = now
                    await self.coord._async_send_notification(
                        "Floor Emergency!",
                        f"Room too cold: Salon {salon_temp}°C! Switching to floor heating."
                    )
                else:
                    self.coord._log_action(f"Floor emergency delayed: {reason}")
            return

        # Both critical - alternate every 45 minutes (longer than before)
        if cwu_urgency == URGENCY_CRITICAL and floor_urgency == URGENCY_CRITICAL:
            minutes_in_state = (now - self.coord._last_state_change).total_seconds() / 60
            if minutes_in_state >= 45:
                if self.coord._current_state in (STATE_HEATING_CWU, STATE_EMERGENCY_CWU):
                    await self.coord._switch_to_floor()
                    self.coord._change_state(STATE_EMERGENCY_FLOOR)
                    self.coord._last_mode_switch = now
                else:
                    await self.coord._switch_to_cwu()
                    self.coord._change_state(STATE_EMERGENCY_CWU)
                    self.coord._cwu_heating_start = now
                    self.coord._last_mode_switch = now
                    self.coord._reset_max_temp_tracking()
            return

        # =====================================================================
        # Phase 9: Normal operation - CWU priority (daytime)
        # =====================================================================
        target = self.coord._get_target_temp()

        # Currently heating floor - check if should resume CWU
        if self.coord._current_state == STATE_HEATING_FLOOR:
            should_resume = False
            resume_reason = ""

            hysteresis = self.coord.get_config_value(CONF_CWU_HYSTERESIS, DEFAULT_CWU_HYSTERESIS)
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
                can_switch, reason = self.coord._can_switch_mode(STATE_HEATING_FLOOR, STATE_HEATING_CWU)
                if can_switch:
                    self.coord._log_action(f"Resuming CWU: {resume_reason}")
                    await self.coord._switch_to_cwu()
                    self.coord._change_state(STATE_HEATING_CWU)
                    self.coord._cwu_heating_start = now
                    self.coord._last_mode_switch = now
                    self.coord._reset_max_temp_tracking()
                    # Set session start temp
                    cwu_start_temp = self.coord._get_cwu_temperature()
                    self.coord._cwu_session_start_temp = cwu_start_temp if cwu_start_temp else self.coord._last_known_cwu_temp
            return

        # Currently heating CWU - check if should switch to floor
        if self.coord._current_state in (STATE_HEATING_CWU, STATE_EMERGENCY_CWU):
            # Check if pump reports "Charged" (reached target)
            if self.coord._is_pump_charged():
                # DHW Charged rest time - wait before switching to floor
                if self.coord._dhw_charged_at is None:
                    self.coord._dhw_charged_at = now
                    self.coord._log_action(
                        "DHW Charged",
                        f"Pump reports charged at {cwu_temp:.1f}°C, waiting {DHW_CHARGED_REST_TIME}min"
                        if cwu_temp else f"Pump reports charged, waiting {DHW_CHARGED_REST_TIME}min"
                    )

                # Check if rest time elapsed
                elapsed = (now - self.coord._dhw_charged_at).total_seconds() / 60
                if elapsed >= DHW_CHARGED_REST_TIME:
                    can_switch, reason = self.coord._can_switch_mode(self.coord._current_state, STATE_HEATING_FLOOR)
                    if can_switch:
                        await self.coord._switch_to_floor()
                        self.coord._change_state(STATE_HEATING_FLOOR)
                        self.coord._cwu_heating_start = None
                        self.coord._last_mode_switch = now
                        self.coord._dhw_charged_at = None
                        self.coord._log_action(
                            "Switch to floor",
                            f"DHW rest complete ({elapsed:.0f}min), CWU at {cwu_temp:.1f}°C"
                            if cwu_temp else f"DHW rest complete ({elapsed:.0f}min)"
                        )
            else:
                # Not charged anymore - reset
                self.coord._dhw_charged_at = None
            return

        # Idle - start with CWU (priority)
        if self.coord._current_state == STATE_IDLE:
            target = self.coord._get_target_temp()
            cwu_start_temp = self.coord._get_cwu_temperature()
            self.coord._log_action(
                "CWU ON",
                f"CWU {cwu_start_temp:.1f}°C < target {target:.1f}°C" if cwu_start_temp else "Starting CWU heating"
            )
            await self.coord._switch_to_cwu()
            self.coord._change_state(STATE_HEATING_CWU)
            self.coord._cwu_heating_start = now
            self.coord._last_mode_switch = now
            self.coord._reset_max_temp_tracking()
            self.coord._cwu_session_start_temp = cwu_start_temp if cwu_start_temp else self.coord._last_known_cwu_temp
