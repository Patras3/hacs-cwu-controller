"""Heat Pump mode for CWU Controller.

This mode lets the heat pump control both CWU and floor heating autonomously.
We only monitor what the pump is doing and track energy consumption accordingly.

Key features:
- Both CWU and floor modes are always ON - pump decides what to heat
- Monitor DHW/HC1/HP status to detect what's currently being heated
- Send notification when electric heater activates
- Detect potential heater failure (pump says heater on but power is low)
- Energy tracking based on detected heating type
"""

from __future__ import annotations

import logging
from datetime import datetime

from ..const import (
    STATE_PUMP_IDLE,
    STATE_PUMP_HEATING_CWU,
    STATE_PUMP_HEATING_FLOOR,
    STATE_PUMP_HEATING_CWU_ELECTRIC,
    STATE_SAFE_MODE,
    BSB_DHW_STATUS_CHARGING,
    BSB_DHW_STATUS_CHARGING_ELECTRIC,
    BSB_HP_COMPRESSOR_ON,
    POWER_ELECTRIC_HEATER_MIN,
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
        self._electric_heater_notified: bool = False
        # Track when we last detected low power during electric heating
        self._low_power_electric_warning_at: datetime | None = None

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

        # Get current pump status from BSB-LAN
        dhw_status = self._bsb_lan_data.get("dhw_status", "") if self._bsb_lan_data else ""
        hp_status = self._bsb_lan_data.get("hp_status", "") if self._bsb_lan_data else ""
        hc1_status = self._bsb_lan_data.get("hc1_status", "") if self._bsb_lan_data else ""

        # Get current power for heater verification
        power = self.coord._get_sensor_value(self.coord.config.get("power_sensor"))

        # Detect current heating state based on BSB-LAN status
        new_state = self._detect_heating_state(dhw_status, hp_status, hc1_status, power)

        # Handle state transitions and notifications
        if new_state != self._current_state:
            await self._handle_state_change(new_state, cwu_temp, power)

        # Check for potential heater failure (pump says electric but power is low)
        if new_state == STATE_PUMP_HEATING_CWU_ELECTRIC:
            await self._check_heater_power(power, cwu_temp)

    def _detect_heating_state(
        self,
        dhw_status: str,
        hp_status: str,
        hc1_status: str,
        power: float | None,
    ) -> str:
        """Detect current heating state from BSB-LAN status.

        Returns the appropriate state based on what the pump is doing.
        """
        dhw_lower = dhw_status.lower()
        hp_lower = hp_status.lower()
        hc1_lower = hc1_status.lower()

        # Check for electric heater CWU heating first (highest priority for detection)
        if BSB_DHW_STATUS_CHARGING_ELECTRIC.lower() in dhw_lower:
            return STATE_PUMP_HEATING_CWU_ELECTRIC

        # Check for thermodynamic CWU heating
        if BSB_DHW_STATUS_CHARGING.lower() in dhw_lower:
            # Verify compressor is actually running for thermodynamic heating
            if BSB_HP_COMPRESSOR_ON.lower() in hp_lower:
                return STATE_PUMP_HEATING_CWU

        # Check for floor heating
        # HC1 status indicates floor heating circuit activity
        # Common values: "Off", "Heating", "Cooling", etc.
        if "heating" in hc1_lower or "heat" in hc1_lower:
            return STATE_PUMP_HEATING_FLOOR

        # Also check if compressor is running for floor (when DHW not charging)
        if BSB_HP_COMPRESSOR_ON.lower() in hp_lower:
            # Compressor running but not for DHW - likely floor
            if "charging" not in dhw_lower:
                return STATE_PUMP_HEATING_FLOOR

        # Nothing actively heating
        return STATE_PUMP_IDLE

    async def _handle_state_change(
        self,
        new_state: str,
        cwu_temp: float | None,
        power: float | None,
    ) -> None:
        """Handle transition to new state with logging and notifications."""
        old_state = self._current_state
        self._change_state(new_state)

        # Map old and new states to readable names for logging
        state_names = {
            STATE_PUMP_IDLE: "Idle",
            STATE_PUMP_HEATING_CWU: "CWU (thermodynamic)",
            STATE_PUMP_HEATING_FLOOR: "Floor",
            STATE_PUMP_HEATING_CWU_ELECTRIC: "CWU (electric heater)",
        }
        old_name = state_names.get(old_state, old_state)
        new_name = state_names.get(new_state, new_state)

        # Log the state change
        reason_parts = []
        if cwu_temp is not None:
            reason_parts.append(f"CWU: {cwu_temp:.1f}C")
        if power is not None:
            reason_parts.append(f"Power: {power:.0f}W")
        reason = ", ".join(reason_parts) if reason_parts else "Pump decision"

        self._log_action(f"{old_name} -> {new_name}", reason)

        # Special handling for electric heater activation
        if new_state == STATE_PUMP_HEATING_CWU_ELECTRIC and old_state != STATE_PUMP_HEATING_CWU_ELECTRIC:
            await self._notify_electric_heater_on(cwu_temp, power)
            self._electric_heater_notified = True
        elif new_state != STATE_PUMP_HEATING_CWU_ELECTRIC:
            self._electric_heater_notified = False
            self._low_power_electric_warning_at = None

    async def _notify_electric_heater_on(
        self,
        cwu_temp: float | None,
        power: float | None,
    ) -> None:
        """Send notification when electric heater activates."""
        power_str = f"{power:.0f}W" if power is not None else "unknown"
        cwu_str = f"{cwu_temp:.1f}C" if cwu_temp is not None else "unknown"

        await self._async_send_notification(
            "Electric Heater Active",
            f"Heat pump switched to electric heater for CWU.\n"
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
                if not getattr(self, '_low_power_warned', False):
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
