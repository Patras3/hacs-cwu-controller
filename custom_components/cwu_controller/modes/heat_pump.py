"""Heat Pump mode for CWU Controller.

This mode lets the heat pump control both CWU and floor heating autonomously.
We only monitor what the pump is doing and track energy consumption accordingly.

Key features:
- Both CWU and floor modes are always ON - pump decides what to heat
- Monitor DHW/HC1/HP status to detect what's currently being heated
- Track 3 electric heaters: 1 for CWU (8821), 2 for floor (8402, 8403)
- Send notification when electric heater activates
- Detect potential heater failure (pump says heater on but power is low)
- Energy tracking based on detected heating type

Main state reflects what is being heated:
- pump_idle: nothing being heated
- pump_cwu: CWU being heated (compressor and/or electric)
- pump_floor: Floor being heated (compressor and/or electric)
- pump_both: Both CWU and floor being heated simultaneously
"""

from __future__ import annotations

import logging
from datetime import datetime

from ..const import (
    STATE_PUMP_IDLE,
    STATE_PUMP_CWU,
    STATE_PUMP_FLOOR,
    STATE_PUMP_BOTH,
    STATE_SAFE_MODE,
    BSB_DHW_STATUS_CHARGING,
    BSB_DHW_STATUS_CHARGING_ELECTRIC,
    BSB_HP_COMPRESSOR_ON,
    POWER_ELECTRIC_HEATER_MIN,
    COMPRESSOR_TARGET_CWU,
    COMPRESSOR_TARGET_FLOOR,
    COMPRESSOR_TARGET_IDLE,
    COMPRESSOR_TARGET_DEFROST,
)
from .base import BaseModeHandler

_LOGGER = logging.getLogger(__name__)


class HeatPumpMode(BaseModeHandler):
    """Mode handler for autonomous heat pump control.

    In this mode, the heat pump has full control over what to heat.
    Both CWU and floor heating are enabled, and the pump decides
    based on its internal logic (temperatures, defrost needs, etc.).

    We only:
    - Monitor and map the current heating state
    - Track energy consumption per heating type
    - Send notifications when electric heater activates
    - Alert if electric heater seems broken (low power)
    """

    def __init__(self, coordinator) -> None:
        """Initialize the mode handler."""
        super().__init__(coordinator)
        # Track electric heater activation to avoid duplicate notifications
        self._electric_heater_cwu_notified: bool = False
        self._electric_heater_floor_notified: bool = False
        # Track when we last detected low power during electric heating
        self._low_power_electric_warning_at: datetime | None = None
        self._low_power_warned: bool = False
        # Track last detected states for change detection
        self._last_compressor_target: str = COMPRESSOR_TARGET_IDLE
        self._last_cwu_electric: bool = False
        self._last_floor_electric: bool = False

    def on_mode_enter(self) -> None:
        """Reset notification and warning flags when entering Heat Pump mode.

        This ensures notifications are sent fresh after mode changes,
        even if heaters were already on before the mode switch.
        """
        self._electric_heater_cwu_notified = False
        self._electric_heater_floor_notified = False
        self._low_power_electric_warning_at = None
        self._low_power_warned = False
        _LOGGER.debug("Heat Pump mode entered - notification flags reset")

    async def run_logic(
        self,
        cwu_urgency: int,
        floor_urgency: int,
        cwu_temp: float | None,
        salon_temp: float | None,
    ) -> None:
        """Run control logic for heat pump mode.

        Main job: detect what the pump is currently heating and update state.
        We don't control - just monitor and map states.
        """
        now = datetime.now()

        # Ensure both CWU and floor are enabled on mode entry
        await self._ensure_both_enabled()

        if not self._bsb_lan_data:
            return

        # Get current pump status from BSB-LAN
        dhw_status = self._bsb_lan_data.get("dhw_status", "")
        hp_status = self._bsb_lan_data.get("hp_status", "")
        hc1_status = self._bsb_lan_data.get("hc1_status", "")

        # Get electric heater states
        cwu_electric_on = self._bsb_lan_data.get("electric_heater_cwu_state", "Off").lower() == "on"
        floor_electric_1_on = self._bsb_lan_data.get("electric_heater_floor_1_state", "Off").lower() == "on"
        floor_electric_2_on = self._bsb_lan_data.get("electric_heater_floor_2_state", "Off").lower() == "on"
        floor_electric_on = floor_electric_1_on or floor_electric_2_on

        # Get current power for heater verification
        power = self.coord._get_sensor_value(self.coord.config.get("power_sensor"))

        # Detect compressor target
        compressor_target = self._detect_compressor_target(dhw_status, hp_status, hc1_status)

        # Determine main state based on what's being heated
        new_state = self._determine_main_state(
            compressor_target, cwu_electric_on, floor_electric_on
        )

        # Handle main state transition
        if new_state != self._current_state:
            await self._handle_state_change(
                new_state, compressor_target, cwu_electric_on, floor_electric_on,
                cwu_temp, power
            )

        # Handle heater notifications separately (they have their own state tracking)
        await self._handle_heater_notifications(
            cwu_electric_on, floor_electric_on, cwu_temp, power
        )

        # Check for potential heater failure
        if cwu_electric_on:
            await self._check_heater_power(power, cwu_temp)

    def _detect_compressor_target(
        self,
        dhw_status: str,
        hp_status: str,
        hc1_status: str,
    ) -> str:
        """Detect what the compressor is currently doing.

        Returns:
            COMPRESSOR_TARGET_CWU: Compressor heating CWU
            COMPRESSOR_TARGET_FLOOR: Compressor heating floor
            COMPRESSOR_TARGET_DEFROST: Compressor in defrost mode
            COMPRESSOR_TARGET_IDLE: Compressor not active
        """
        hp_lower = hp_status.lower()

        # Check for defrost first - compressor is running but for defrost, not heating
        if "defrost" in hp_lower:
            return COMPRESSOR_TARGET_DEFROST

        # Check if compressor is actively heating
        compressor_on = BSB_HP_COMPRESSOR_ON.lower() in hp_lower
        if not compressor_on:
            return COMPRESSOR_TARGET_IDLE

        dhw_lower = dhw_status.lower()
        hc1_lower = hc1_status.lower()

        # Check if floor is actively heating (needed for limitation/locked logic)
        floor_heating = any(x in hc1_lower for x in ["heating", "warmer", "comfort"])

        # Check if DHW is in any charging state (including electric)
        dhw_charging = BSB_DHW_STATUS_CHARGING.lower() in dhw_lower

        if dhw_charging:
            # Check if it's paused (limitation/locked)
            is_paused = "limitation" in dhw_lower or "locked" in dhw_lower

            if is_paused:
                # Limitation or Locked - check if we switched to floor
                if floor_heating:
                    # Floor took over, CWU is waiting
                    return COMPRESSOR_TARGET_FLOOR
                else:
                    # Floor not heating, this is just a pause in CWU session
                    return COMPRESSOR_TARGET_CWU
            else:
                # Active charging - check if floor is also heating
                if floor_heating:
                    # Both heating: compressor on floor, electric heater on CWU
                    # (if "electric" in dhw) or compressor prioritizes floor
                    if "electric" in dhw_lower:
                        return COMPRESSOR_TARGET_FLOOR
                    else:
                        return COMPRESSOR_TARGET_CWU
                else:
                    # Only CWU charging, compressor must be on CWU
                    return COMPRESSOR_TARGET_CWU

        # Check if heating floor (when DHW not charging)
        if floor_heating:
            return COMPRESSOR_TARGET_FLOOR

        # Compressor on but unclear target - default to floor
        return COMPRESSOR_TARGET_FLOOR

    def _determine_main_state(
        self,
        compressor_target: str,
        cwu_electric_on: bool,
        floor_electric_on: bool,
    ) -> str:
        """Determine main state based on what's being heated.

        Main state reflects the heating priority/activity:
        - pump_both: Both CWU and floor are being heated (any combination)
        - pump_cwu: Only CWU is being heated
        - pump_floor: Only floor is being heated
        - pump_idle: Nothing is being heated
        """
        cwu_heating = (compressor_target == COMPRESSOR_TARGET_CWU) or cwu_electric_on
        floor_heating = (compressor_target == COMPRESSOR_TARGET_FLOOR) or floor_electric_on

        if cwu_heating and floor_heating:
            return STATE_PUMP_BOTH
        elif cwu_heating:
            return STATE_PUMP_CWU
        elif floor_heating:
            return STATE_PUMP_FLOOR
        else:
            return STATE_PUMP_IDLE

    def _is_cwu_heating_state(self, state: str) -> bool:
        """Check if state indicates CWU is being heated."""
        return state in (STATE_PUMP_CWU, STATE_PUMP_BOTH)

    def _is_floor_heating_state(self, state: str) -> bool:
        """Check if state indicates floor is being heated."""
        return state in (STATE_PUMP_FLOOR, STATE_PUMP_BOTH)

    async def _handle_state_change(
        self,
        new_state: str,
        compressor_target: str,
        cwu_electric_on: bool,
        floor_electric_on: bool,
        cwu_temp: float | None,
        power: float | None,
    ) -> None:
        """Handle transition to new state with logging and session tracking."""
        old_state = self._current_state
        now = datetime.now()

        # Track CWU session start/end for UI
        was_heating_cwu = self._is_cwu_heating_state(old_state)
        will_heat_cwu = self._is_cwu_heating_state(new_state)

        if will_heat_cwu and not was_heating_cwu:
            # Starting CWU heating - begin session
            self.coord._cwu_heating_start = now
            self.coord._cwu_session_start_temp = cwu_temp if cwu_temp is not None else self.coord._last_known_cwu_temp
            self.coord._cwu_session_start_energy_kwh = self.coord._get_energy_meter_value()
            _LOGGER.debug(
                "Heat Pump: CWU session started at %.1f°C",
                self.coord._cwu_session_start_temp or 0
            )
        elif was_heating_cwu and not will_heat_cwu:
            # Stopped CWU heating - end session
            # Save final energy before clearing session (for action history)
            final_cwu_energy = self.coord.session_energy_kwh
            if final_cwu_energy is not None:
                self.coord._last_completed_cwu_session_energy_kwh = final_cwu_energy
            _LOGGER.debug(
                "Heat Pump: CWU session ended (was %.1f°C, now %.1f°C, energy %.3f kWh)",
                self.coord._cwu_session_start_temp or 0,
                cwu_temp or 0,
                final_cwu_energy or 0
            )
            self.coord._cwu_heating_start = None
            self.coord._cwu_session_start_temp = None
            self.coord._cwu_session_start_energy_kwh = None

        # Track Floor session start/end for UI
        was_heating_floor = self._is_floor_heating_state(old_state)
        will_heat_floor = self._is_floor_heating_state(new_state)

        if will_heat_floor and not was_heating_floor:
            # Starting floor heating - begin session
            self.coord._floor_heating_start = now
            self.coord._floor_session_start_energy_kwh = self.coord._get_energy_meter_value()
            _LOGGER.debug("Heat Pump: Floor session started")
        elif was_heating_floor and not will_heat_floor:
            # Stopped floor heating - end session
            # Save final energy before clearing session (for action history)
            final_floor_energy = self.coord.floor_session_energy_kwh
            if final_floor_energy is not None:
                self.coord._last_completed_floor_session_energy_kwh = final_floor_energy
            _LOGGER.debug(
                "Heat Pump: Floor session ended (energy %.3f kWh)",
                final_floor_energy or 0
            )
            self.coord._floor_heating_start = None
            self.coord._floor_session_start_energy_kwh = None

        self._change_state(new_state)

        # Map states to readable names for logging
        state_names = {
            STATE_PUMP_IDLE: "Idle",
            STATE_PUMP_CWU: "CWU",
            STATE_PUMP_FLOOR: "Floor",
            STATE_PUMP_BOTH: "CWU+Floor",
        }
        old_name = state_names.get(old_state, old_state)
        new_name = state_names.get(new_state, new_state)

        # Build detailed reason
        reason_parts = []
        if compressor_target != COMPRESSOR_TARGET_IDLE:
            reason_parts.append(f"Compressor: {compressor_target}")
        if cwu_electric_on:
            reason_parts.append("CWU heater: ON")
        if floor_electric_on:
            reason_parts.append("Floor heater: ON")
        if cwu_temp is not None:
            reason_parts.append(f"CWU: {cwu_temp:.1f}°C")
        if power is not None:
            reason_parts.append(f"Power: {power:.0f}W")

        reason = ", ".join(reason_parts) if reason_parts else "Pump decision"
        self._log_action(f"{old_name} → {new_name}", reason)

    async def _handle_heater_notifications(
        self,
        cwu_electric_on: bool,
        floor_electric_on: bool,
        cwu_temp: float | None,
        power: float | None,
    ) -> None:
        """Handle notifications for electric heater state changes."""
        # CWU heater notification
        if cwu_electric_on and not self._electric_heater_cwu_notified:
            await self._notify_electric_heater_on("CWU", cwu_temp, power)
            self._electric_heater_cwu_notified = True
        elif not cwu_electric_on:
            self._electric_heater_cwu_notified = False
            # Also reset low power warning flag when heater turns off
            self._low_power_warned = False

        # Floor heater notification
        if floor_electric_on and not self._electric_heater_floor_notified:
            await self._notify_electric_heater_on("Floor", cwu_temp, power)
            self._electric_heater_floor_notified = True
        elif not floor_electric_on:
            self._electric_heater_floor_notified = False

    async def _notify_electric_heater_on(
        self,
        heater_type: str,
        cwu_temp: float | None,
        power: float | None,
    ) -> None:
        """Send notification when electric heater activates."""
        power_str = f"{power:.0f}W" if power is not None else "unknown"
        cwu_str = f"{cwu_temp:.1f}°C" if cwu_temp is not None else "unknown"

        await self._async_send_notification(
            f"Electric Heater Active ({heater_type})",
            f"Heat pump switched to electric heater for {heater_type}.\n"
            f"CWU temp: {cwu_str}\n"
            f"Power: {power_str}\n\n"
            f"This is expected when thermodynamic heating cannot meet demand."
        )

    async def _check_heater_power(
        self,
        power: float | None,
        cwu_temp: float | None,
    ) -> None:
        """Check if electric heater power is as expected.

        If pump says heater is on but power is too low, heater might be broken.
        """
        if power is None:
            return

        now = datetime.now()

        if power < POWER_ELECTRIC_HEATER_MIN:
            # Power too low for electric heater
            if self._low_power_electric_warning_at is None:
                self._low_power_electric_warning_at = now

            # Wait at least 2 minutes before warning (avoid false positives during transitions)
            elapsed = (now - self._low_power_electric_warning_at).total_seconds() / 60
            if elapsed >= 2:
                # Only warn once per electric heating session
                if not self._low_power_warned:
                    self._low_power_warned = True
                    cwu_str = f"{cwu_temp:.1f}C" if cwu_temp is not None else "unknown"

                    await self._async_send_notification(
                        "Heater Problem?",
                        f"Heat pump reports electric heater active, but power is low!\n\n"
                        f"Expected: >{POWER_ELECTRIC_HEATER_MIN}W\n"
                        f"Actual: {power:.0f}W\n"
                        f"CWU temp: {cwu_str}\n\n"
                        f"Possible causes:\n"
                        f"- Heater fuse/breaker tripped\n"
                        f"- Heater element failed\n"
                        f"- Sensor issue"
                    )
                    self._log_action(
                        "Heater power warning",
                        f"Expected >{POWER_ELECTRIC_HEATER_MIN}W, got {power:.0f}W"
                    )
        else:
            # Power is OK - reset warning state
            self._low_power_electric_warning_at = None
            self._low_power_warned = False

    async def _ensure_both_enabled(self) -> None:
        """Ensure both CWU and floor heating are enabled.

        Called on every update cycle to maintain pump control mode.
        Only sends commands if current state doesn't match expected.
        """
        if not self._bsb_lan_data:
            return

        cwu_mode = self._bsb_lan_data.get("cwu_mode", "")
        floor_mode = self._bsb_lan_data.get("floor_mode", "")

        cwu_on = cwu_mode.lower() in ("on", "eco", "1")
        floor_on = floor_mode.lower() in ("automatic", "comfort", "1")

        # Only act if something is off
        if not cwu_on:
            _LOGGER.info("Heat Pump mode: CWU was off, turning on")
            await self._async_set_cwu_on()
            self._log_action("CWU enabled", "Heat Pump mode requires both CWU and floor ON")

        if not floor_on:
            _LOGGER.info("Heat Pump mode: Floor was off, turning on")
            await self._async_set_floor_on()
            self._log_action("Floor enabled", "Heat Pump mode requires both CWU and floor ON")
