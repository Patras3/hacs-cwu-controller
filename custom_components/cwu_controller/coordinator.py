"""Data coordinator for CWU Controller."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.components.water_heater import SERVICE_SET_OPERATION_MODE
from homeassistant.components.climate import SERVICE_TURN_ON, SERVICE_TURN_OFF

from .const import (
    DOMAIN,
    UPDATE_INTERVAL,
    STATE_IDLE,
    STATE_HEATING_CWU,
    STATE_HEATING_FLOOR,
    STATE_PAUSE,
    STATE_EMERGENCY_CWU,
    STATE_EMERGENCY_FLOOR,
    STATE_FAKE_HEATING_DETECTED,
    URGENCY_NONE,
    URGENCY_LOW,
    URGENCY_MEDIUM,
    URGENCY_HIGH,
    URGENCY_CRITICAL,
    POWER_IDLE_THRESHOLD,
    POWER_THERMODYNAMIC_MIN,
    CWU_MAX_HEATING_TIME,
    CWU_PAUSE_TIME,
    FAKE_HEATING_DETECTION_TIME,
    SENSOR_UNAVAILABLE_GRACE,
    EVENING_PREP_HOUR,
    BATH_TIME_HOUR,
    WH_MODE_OFF,
    WH_MODE_HEAT_PUMP,
    WH_MODE_PERFORMANCE,
    CLIMATE_OFF,
    CLIMATE_AUTO,
    CLIMATE_HEAT,
    DEFAULT_CWU_TARGET_TEMP,
    DEFAULT_CWU_MIN_TEMP,
    DEFAULT_CWU_CRITICAL_TEMP,
    DEFAULT_SALON_TARGET_TEMP,
    DEFAULT_SALON_MIN_TEMP,
    DEFAULT_BEDROOM_MIN_TEMP,
)

_LOGGER = logging.getLogger(__name__)


class CWUControllerCoordinator(DataUpdateCoordinator):
    """Coordinator for CWU Controller."""

    def __init__(self, hass: HomeAssistant, config: dict[str, Any]) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=UPDATE_INTERVAL),
        )
        self.config = config
        self.hass = hass

        # State tracking
        self._current_state = STATE_IDLE
        self._previous_state = STATE_IDLE
        self._enabled = True
        self._manual_override = False
        self._manual_override_until: datetime | None = None

        # Timing tracking
        self._cwu_heating_start: datetime | None = None
        self._pause_start: datetime | None = None
        self._low_power_start: datetime | None = None
        self._last_state_change: datetime = datetime.now()

        # Sensor tracking
        self._last_known_cwu_temp: float | None = None
        self._last_known_salon_temp: float | None = None
        self._cwu_temp_unavailable_since: datetime | None = None
        self._last_cwu_temp_for_trend: float | None = None
        self._last_cwu_temp_time: datetime | None = None

        # History for UI
        self._state_history: list[dict] = []
        self._action_history: list[dict] = []

        # Power tracking for trend analysis
        self._recent_power_readings: list[tuple[datetime, float]] = []

    @property
    def current_state(self) -> str:
        """Return current controller state."""
        return self._current_state

    @property
    def is_enabled(self) -> bool:
        """Return if controller is enabled."""
        return self._enabled

    @property
    def state_history(self) -> list[dict]:
        """Return state history."""
        return self._state_history[-100:]  # Last 100 entries

    @property
    def action_history(self) -> list[dict]:
        """Return action history."""
        return self._action_history[-100:]  # Last 100 entries

    def _get_sensor_value(self, entity_id: str | None, default: float | None = None) -> float | None:
        """Get sensor value with fallback handling."""
        if not entity_id:
            return default

        state = self.hass.states.get(entity_id)
        if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return default

        try:
            return float(state.state)
        except (ValueError, TypeError):
            return default

    def _get_entity_state(self, entity_id: str | None) -> str | None:
        """Get entity state."""
        if not entity_id:
            return None

        state = self.hass.states.get(entity_id)
        if state is None:
            return None
        return state.state

    def _calculate_cwu_urgency(self, cwu_temp: float | None, current_hour: int) -> int:
        """Calculate CWU heating urgency."""
        if cwu_temp is None:
            # Sensor unavailable - assume medium urgency
            return URGENCY_MEDIUM

        target = self.config.get("cwu_target_temp", DEFAULT_CWU_TARGET_TEMP)
        min_temp = self.config.get("cwu_min_temp", DEFAULT_CWU_MIN_TEMP)
        critical = self.config.get("cwu_critical_temp", DEFAULT_CWU_CRITICAL_TEMP)

        # Evening/bath time - more aggressive
        if current_hour >= BATH_TIME_HOUR:
            if cwu_temp < critical:
                return URGENCY_CRITICAL
            if cwu_temp < min_temp:
                return URGENCY_HIGH
            if cwu_temp < target:
                return URGENCY_MEDIUM
            return URGENCY_NONE

        # Afternoon - prepare for evening
        if current_hour >= EVENING_PREP_HOUR:
            if cwu_temp < critical:
                return URGENCY_HIGH
            if cwu_temp < min_temp:
                return URGENCY_MEDIUM
            if cwu_temp < target:
                return URGENCY_LOW
            return URGENCY_NONE

        # Morning/daytime - more relaxed
        if cwu_temp < critical:
            return URGENCY_MEDIUM
        if cwu_temp < min_temp:
            return URGENCY_LOW
        return URGENCY_NONE

    def _calculate_floor_urgency(
        self,
        salon_temp: float | None,
        bedroom_temp: float | None,
        kids_temp: float | None
    ) -> int:
        """Calculate floor heating urgency."""
        target = self.config.get("salon_target_temp", DEFAULT_SALON_TARGET_TEMP)
        min_salon = self.config.get("salon_min_temp", DEFAULT_SALON_MIN_TEMP)
        min_bedroom = self.config.get("bedroom_min_temp", DEFAULT_BEDROOM_MIN_TEMP)

        # Check bedroom temperatures first (safety)
        for temp in [bedroom_temp, kids_temp]:
            if temp is not None and temp < min_bedroom - 1:  # Below 18°C
                return URGENCY_CRITICAL

        if salon_temp is None:
            return URGENCY_MEDIUM

        if salon_temp < min_salon - 2:  # Below 19°C
            return URGENCY_CRITICAL
        if salon_temp < min_salon:  # Below 21°C
            return URGENCY_HIGH
        if salon_temp < target:  # Below 22°C
            return URGENCY_MEDIUM
        if salon_temp < target + 0.5:  # Below 22.5°C
            return URGENCY_LOW
        return URGENCY_NONE

    def _detect_fake_heating(self, power: float | None, wh_state: str | None) -> bool:
        """Detect if pump thinks it's heating but using broken heater."""
        if power is None or wh_state is None:
            return False

        # Water heater should be in an active mode
        if wh_state not in (WH_MODE_HEAT_PUMP, WH_MODE_PERFORMANCE):
            return False

        # Power should be very low (< 10W means waiting for heater)
        if power >= POWER_IDLE_THRESHOLD:
            # Reset low power tracking
            self._low_power_start = None
            return False

        # Track how long power has been low
        now = datetime.now()
        if self._low_power_start is None:
            self._low_power_start = now
            return False

        minutes_low = (now - self._low_power_start).total_seconds() / 60
        return minutes_low >= FAKE_HEATING_DETECTION_TIME

    def _should_restart_cwu_cycle(self) -> bool:
        """Check if we need to restart CWU cycle due to 3h limit."""
        if self._cwu_heating_start is None:
            return False

        elapsed = (datetime.now() - self._cwu_heating_start).total_seconds() / 60
        return elapsed >= CWU_MAX_HEATING_TIME

    def _is_pause_complete(self) -> bool:
        """Check if pause period is complete."""
        if self._pause_start is None:
            return True

        elapsed = (datetime.now() - self._pause_start).total_seconds() / 60
        return elapsed >= CWU_PAUSE_TIME

    async def _async_set_water_heater_mode(self, mode: str) -> bool:
        """Set water heater operation mode."""
        entity_id = self.config.get("water_heater")
        if not entity_id:
            return False

        try:
            await self.hass.services.async_call(
                "water_heater",
                SERVICE_SET_OPERATION_MODE,
                {"entity_id": entity_id, "operation_mode": mode},
                blocking=True,
            )
            self._log_action(f"Set water heater to {mode}")
            return True
        except Exception as e:
            _LOGGER.error("Failed to set water heater mode: %s", e)
            return False

    async def _async_set_climate(self, turn_on: bool) -> bool:
        """Turn climate on or off."""
        entity_id = self.config.get("climate")
        if not entity_id:
            return False

        try:
            service = SERVICE_TURN_ON if turn_on else SERVICE_TURN_OFF
            await self.hass.services.async_call(
                "climate",
                service,
                {"entity_id": entity_id},
                blocking=True,
            )
            self._log_action(f"Climate {'ON' if turn_on else 'OFF'}")
            return True
        except Exception as e:
            _LOGGER.error("Failed to control climate: %s", e)
            return False

    async def _async_send_notification(self, title: str, message: str) -> None:
        """Send notification."""
        notify_service = self.config.get("notify_service")
        if not notify_service:
            return

        try:
            service_domain, service_name = notify_service.split(".", 1)
            await self.hass.services.async_call(
                service_domain,
                service_name,
                {"title": title, "message": message},
                blocking=False,
            )
        except Exception as e:
            _LOGGER.warning("Failed to send notification: %s", e)

    def _log_action(self, action: str) -> None:
        """Log an action to history."""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "action": action,
            "state": self._current_state,
        }
        self._action_history.append(entry)
        _LOGGER.info("CWU Controller: %s", action)

    def _change_state(self, new_state: str) -> None:
        """Change controller state."""
        if new_state != self._current_state:
            self._previous_state = self._current_state
            self._current_state = new_state
            self._last_state_change = datetime.now()

            entry = {
                "timestamp": datetime.now().isoformat(),
                "from_state": self._previous_state,
                "to_state": new_state,
            }
            self._state_history.append(entry)
            _LOGGER.info("CWU Controller state: %s -> %s", self._previous_state, new_state)

    async def async_enable(self) -> None:
        """Enable the controller."""
        self._enabled = True
        self._manual_override = False
        self._log_action("Controller enabled")

    async def async_disable(self) -> None:
        """Disable the controller."""
        self._enabled = False
        self._log_action("Controller disabled")

    async def async_force_cwu(self, duration_minutes: int = 60) -> None:
        """Force CWU heating for specified duration."""
        self._manual_override = True
        self._manual_override_until = datetime.now() + timedelta(minutes=duration_minutes)

        await self._async_set_climate(False)
        await asyncio.sleep(1)
        await self._async_set_water_heater_mode(WH_MODE_HEAT_PUMP)

        self._change_state(STATE_HEATING_CWU)
        self._cwu_heating_start = datetime.now()
        self._log_action(f"Force CWU for {duration_minutes} minutes")

    async def async_force_floor(self, duration_minutes: int = 60) -> None:
        """Force floor heating for specified duration."""
        self._manual_override = True
        self._manual_override_until = datetime.now() + timedelta(minutes=duration_minutes)

        await self._async_set_water_heater_mode(WH_MODE_OFF)
        await asyncio.sleep(1)
        await self._async_set_climate(True)

        self._change_state(STATE_HEATING_FLOOR)
        self._log_action(f"Force floor heating for {duration_minutes} minutes")

    async def async_test_cwu_on(self) -> None:
        """Test action: turn on CWU."""
        await self._async_set_water_heater_mode(WH_MODE_HEAT_PUMP)
        await self._async_send_notification("CWU Controller Test", "CWU turned ON (heat_pump mode)")

    async def async_test_cwu_off(self) -> None:
        """Test action: turn off CWU."""
        await self._async_set_water_heater_mode(WH_MODE_OFF)
        await self._async_send_notification("CWU Controller Test", "CWU turned OFF")

    async def async_test_floor_on(self) -> None:
        """Test action: turn on floor heating."""
        await self._async_set_climate(True)
        await self._async_send_notification("CWU Controller Test", "Floor heating turned ON")

    async def async_test_floor_off(self) -> None:
        """Test action: turn off floor heating."""
        await self._async_set_climate(False)
        await self._async_send_notification("CWU Controller Test", "Floor heating turned OFF")

    async def _async_update_data(self) -> dict[str, Any]:
        """Update data and run control logic."""
        now = datetime.now()
        current_hour = now.hour

        # Get sensor values
        cwu_temp = self._get_sensor_value(self.config.get("cwu_temp_sensor"))
        salon_temp = self._get_sensor_value(self.config.get("salon_temp_sensor"))
        bedroom_temp = self._get_sensor_value(self.config.get("bedroom_temp_sensor"))
        kids_temp = self._get_sensor_value(self.config.get("kids_room_temp_sensor"))
        power = self._get_sensor_value(self.config.get("power_sensor"))
        pump_input = self._get_sensor_value(self.config.get("pump_input_temp"))
        pump_output = self._get_sensor_value(self.config.get("pump_output_temp"))

        wh_state = self._get_entity_state(self.config.get("water_heater"))
        climate_state = self._get_entity_state(self.config.get("climate"))

        # Track CWU temp for trend analysis
        if cwu_temp is not None:
            self._last_known_cwu_temp = cwu_temp
            self._cwu_temp_unavailable_since = None
        elif self._cwu_temp_unavailable_since is None:
            self._cwu_temp_unavailable_since = now

        if salon_temp is not None:
            self._last_known_salon_temp = salon_temp

        # Track power readings
        if power is not None:
            self._recent_power_readings.append((now, power))
            # Keep only last 10 minutes of readings
            cutoff = now - timedelta(minutes=10)
            self._recent_power_readings = [
                (t, p) for t, p in self._recent_power_readings if t > cutoff
            ]

        # Calculate urgencies
        cwu_urgency = self._calculate_cwu_urgency(
            cwu_temp if cwu_temp is not None else self._last_known_cwu_temp,
            current_hour
        )
        floor_urgency = self._calculate_floor_urgency(
            salon_temp if salon_temp is not None else self._last_known_salon_temp,
            bedroom_temp,
            kids_temp
        )

        # Detect fake heating
        fake_heating = self._detect_fake_heating(power, wh_state)

        # Calculate average power
        avg_power = 0.0
        if self._recent_power_readings:
            avg_power = sum(p for _, p in self._recent_power_readings) / len(self._recent_power_readings)

        # Prepare data for entities
        data = {
            "cwu_temp": cwu_temp,
            "salon_temp": salon_temp,
            "bedroom_temp": bedroom_temp,
            "kids_temp": kids_temp,
            "power": power,
            "avg_power": avg_power,
            "pump_input": pump_input,
            "pump_output": pump_output,
            "wh_state": wh_state,
            "climate_state": climate_state,
            "controller_state": self._current_state,
            "cwu_urgency": cwu_urgency,
            "floor_urgency": floor_urgency,
            "fake_heating": fake_heating,
            "enabled": self._enabled,
            "manual_override": self._manual_override,
            "cwu_heating_minutes": 0,
            "state_history": self._state_history[-20:],
            "action_history": self._action_history[-20:],
        }

        if self._cwu_heating_start:
            data["cwu_heating_minutes"] = (now - self._cwu_heating_start).total_seconds() / 60

        # Skip control logic if disabled
        if not self._enabled:
            return data

        # Check manual override expiry
        if self._manual_override and self._manual_override_until:
            if now > self._manual_override_until:
                self._manual_override = False
                self._manual_override_until = None
                self._log_action("Manual override expired")

        if self._manual_override:
            return data

        # Control logic
        await self._run_control_logic(
            cwu_urgency,
            floor_urgency,
            fake_heating,
            cwu_temp,
            salon_temp,
            power,
            wh_state,
            climate_state,
        )

        data["controller_state"] = self._current_state
        return data

    async def _run_control_logic(
        self,
        cwu_urgency: int,
        floor_urgency: int,
        fake_heating: bool,
        cwu_temp: float | None,
        salon_temp: float | None,
        power: float | None,
        wh_state: str | None,
        climate_state: str | None,
    ) -> None:
        """Run the main control logic."""

        # Handle fake heating detection
        if fake_heating and self._current_state == STATE_HEATING_CWU:
            self._change_state(STATE_FAKE_HEATING_DETECTED)
            await self._async_send_notification(
                "CWU Controller Alert",
                f"Fake heating detected! Power < 10W for {FAKE_HEATING_DETECTION_TIME}+ minutes. "
                f"CWU temp: {cwu_temp}°C. Restarting cycle..."
            )
            # Try to restart by turning off and on
            await self._async_set_water_heater_mode(WH_MODE_OFF)
            await asyncio.sleep(2)
            await self._async_set_water_heater_mode(WH_MODE_HEAT_PUMP)
            self._low_power_start = None
            self._change_state(STATE_HEATING_CWU)
            return

        # Handle pause state
        if self._current_state == STATE_PAUSE:
            if self._is_pause_complete():
                self._pause_start = None
                # Resume CWU heating
                await self._async_set_water_heater_mode(WH_MODE_HEAT_PUMP)
                self._change_state(STATE_HEATING_CWU)
                self._cwu_heating_start = datetime.now()
                self._log_action("Pause complete, resuming CWU heating")
            return

        # Check 3-hour CWU limit
        if self._current_state == STATE_HEATING_CWU and self._should_restart_cwu_cycle():
            self._change_state(STATE_PAUSE)
            self._pause_start = datetime.now()
            self._cwu_heating_start = None
            await self._async_set_water_heater_mode(WH_MODE_OFF)
            await self._async_set_climate(False)
            self._log_action(f"CWU cycle limit reached, pausing for {CWU_PAUSE_TIME} minutes")
            await self._async_send_notification(
                "CWU Controller",
                f"CWU heating paused for {CWU_PAUSE_TIME} min (3h limit). "
                f"CWU: {cwu_temp}°C, Salon: {salon_temp}°C"
            )
            return

        # Emergency handling
        if cwu_urgency == URGENCY_CRITICAL and floor_urgency != URGENCY_CRITICAL:
            if self._current_state != STATE_EMERGENCY_CWU:
                await self._switch_to_cwu()
                self._change_state(STATE_EMERGENCY_CWU)
                await self._async_send_notification(
                    "CWU Emergency!",
                    f"CWU critically low: {cwu_temp}°C! Switching to CWU heating."
                )
            return

        if floor_urgency == URGENCY_CRITICAL and cwu_urgency != URGENCY_CRITICAL:
            if self._current_state != STATE_EMERGENCY_FLOOR:
                await self._switch_to_floor()
                self._change_state(STATE_EMERGENCY_FLOOR)
                await self._async_send_notification(
                    "Floor Emergency!",
                    f"Room too cold: Salon {salon_temp}°C! Switching to floor heating."
                )
            return

        # Both critical - alternate every 30 minutes
        if cwu_urgency == URGENCY_CRITICAL and floor_urgency == URGENCY_CRITICAL:
            minutes_in_state = (datetime.now() - self._last_state_change).total_seconds() / 60
            if minutes_in_state >= 30:
                if self._current_state in (STATE_HEATING_CWU, STATE_EMERGENCY_CWU):
                    await self._switch_to_floor()
                    self._change_state(STATE_EMERGENCY_FLOOR)
                else:
                    await self._switch_to_cwu()
                    self._change_state(STATE_EMERGENCY_CWU)
            return

        # Normal decision logic
        if cwu_urgency >= URGENCY_HIGH and floor_urgency <= URGENCY_LOW:
            # CWU needs attention, floor is fine
            if self._current_state != STATE_HEATING_CWU:
                await self._switch_to_cwu()
                self._change_state(STATE_HEATING_CWU)
                self._cwu_heating_start = datetime.now()
            return

        if floor_urgency >= URGENCY_HIGH and cwu_urgency <= URGENCY_LOW:
            # Floor needs attention, CWU is fine
            if self._current_state != STATE_HEATING_FLOOR:
                await self._switch_to_floor()
                self._change_state(STATE_HEATING_FLOOR)
                self._cwu_heating_start = None
            return

        # Medium urgencies - prefer CWU if approaching evening
        if cwu_urgency >= URGENCY_MEDIUM and datetime.now().hour >= EVENING_PREP_HOUR:
            if self._current_state != STATE_HEATING_CWU:
                await self._switch_to_cwu()
                self._change_state(STATE_HEATING_CWU)
                self._cwu_heating_start = datetime.now()
            return

        # Default: floor heating (keep house warm)
        if self._current_state not in (STATE_HEATING_FLOOR, STATE_IDLE):
            # Check if CWU is at target before switching to floor
            target = self.config.get("cwu_target_temp", DEFAULT_CWU_TARGET_TEMP)
            if cwu_temp is not None and cwu_temp >= target:
                await self._switch_to_floor()
                self._change_state(STATE_HEATING_FLOOR)
                self._cwu_heating_start = None
        elif self._current_state == STATE_IDLE:
            # Start with floor heating by default
            await self._switch_to_floor()
            self._change_state(STATE_HEATING_FLOOR)

    async def _switch_to_cwu(self) -> None:
        """Switch to CWU heating mode."""
        # First turn off floor heating
        await self._async_set_climate(False)
        await asyncio.sleep(1)
        # Then enable CWU
        await self._async_set_water_heater_mode(WH_MODE_HEAT_PUMP)
        self._log_action("Switched to CWU heating")

    async def _switch_to_floor(self) -> None:
        """Switch to floor heating mode."""
        # First turn off CWU
        await self._async_set_water_heater_mode(WH_MODE_OFF)
        await asyncio.sleep(1)
        # Then enable floor heating
        await self._async_set_climate(True)
        self._log_action("Switched to floor heating")
