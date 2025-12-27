"""Data coordinator for CWU Controller."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN, EVENT_HOMEASSISTANT_STOP
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
    STATE_FAKE_HEATING_RESTARTING,
    STATE_SAFE_MODE,
    URGENCY_NONE,
    URGENCY_LOW,
    URGENCY_MEDIUM,
    URGENCY_HIGH,
    URGENCY_CRITICAL,
    POWER_IDLE_THRESHOLD,
    POWER_SPIKE_THRESHOLD,
    POWER_THERMODYNAMIC_MIN,
    CWU_MAX_HEATING_TIME,
    CWU_PAUSE_TIME,
    FAKE_HEATING_DETECTION_TIME,
    FAKE_HEATING_RESTART_WAIT,
    SENSOR_UNAVAILABLE_GRACE,
    EVENING_PREP_HOUR,
    BATH_TIME_HOUR,
    DEFAULT_CWU_TARGET_TEMP,
    DEFAULT_CWU_MIN_TEMP,
    DEFAULT_CWU_CRITICAL_TEMP,
    DEFAULT_SALON_TARGET_TEMP,
    DEFAULT_SALON_MIN_TEMP,
    DEFAULT_BEDROOM_MIN_TEMP,
    CONF_CWU_HYSTERESIS,
    DEFAULT_CWU_HYSTERESIS,
    # Mode constants
    MODE_BROKEN_HEATER,
    MODE_WINTER,
    MODE_SUMMER,
    CONF_OPERATING_MODE,
    CONF_WORKDAY_SENSOR,
    # Tariff constants
    CONF_TARIFF_EXPENSIVE_RATE,
    CONF_TARIFF_CHEAP_RATE,
    TARIFF_EXPENSIVE_RATE,
    TARIFF_CHEAP_RATE,
    TARIFF_CHEAP_WINDOWS,
    # Winter mode settings
    WINTER_CWU_HEATING_WINDOWS,
    WINTER_CWU_TARGET_OFFSET,
    WINTER_CWU_EMERGENCY_OFFSET,
    WINTER_CWU_MAX_TEMP,
    WINTER_CWU_NO_PROGRESS_TIMEOUT,
    WINTER_CWU_MIN_TEMP_INCREASE,
    # Energy tracking
    CONF_ENERGY_SENSOR,
    DEFAULT_ENERGY_SENSOR,
    ENERGY_TRACKING_INTERVAL,
    ENERGY_DELTA_ANOMALY_THRESHOLD,
    # BSB-LAN
    CONF_BSB_LAN_HOST,
    DEFAULT_BSB_LAN_HOST,
    BSB_LAN_PARAM_CWU_MODE,
    BSB_LAN_PARAM_FLOOR_MODE,
    BSB_CWU_MODE_OFF,
    BSB_CWU_MODE_ON,
    BSB_FLOOR_MODE_PROTECTION,
    BSB_FLOOR_MODE_AUTOMATIC,
    BSB_DHW_STATUS_CHARGING,
    BSB_DHW_STATUS_CHARGING_ELECTRIC,
    BSB_HP_COMPRESSOR_ON,
    BSB_HP_OFF_TIME_ACTIVE,
    CONTROL_SOURCE_BSB_LAN,
    CONTROL_SOURCE_HA_CLOUD,
    BSB_FAKE_HEATING_DETECTION_TIME,
    BSB_LAN_STATE_VERIFY_INTERVAL,
    BSB_LAN_UNAVAILABLE_TIMEOUT,
    SAFE_MODE_WATER_HEATER,
    SAFE_MODE_CLIMATE,
    SAFE_MODE_DELAY,
    # Broken heater mode refactored constants
    BROKEN_HEATER_FLOOR_WINDOW_START,
    BROKEN_HEATER_FLOOR_WINDOW_END,
    MIN_CWU_HEATING_TIME,
    MIN_FLOOR_HEATING_TIME,
    MAX_TEMP_DETECTION_WINDOW,
    MAX_TEMP_FLOW_STAGNATION,
    MAX_TEMP_ELECTRIC_FALLBACK_COUNT,
    MAX_TEMP_ACCEPTABLE_DROP,
    MAX_TEMP_CRITICAL_THRESHOLD,
    MAX_TEMP_FIGHTING_WINDOW,
    MAX_TEMP_FIGHTING_PROGRESS,
    MAX_TEMP_FIGHTING_THRESHOLD,
    MAX_TEMP_FIGHTING_ELECTRIC_COUNT,
    CWU_RAPID_DROP_THRESHOLD,
    CWU_RAPID_DROP_WINDOW,
    HP_RESTART_MIN_WAIT,
    HP_STATUS_DEFROSTING,
    HP_STATUS_OVERRUN,
    DHW_STATUS_CHARGED,
    DHW_CHARGED_REST_TIME,
    MANUAL_HEAT_TO_MIN_TEMP,
    MANUAL_HEAT_TO_MAX_TEMP,
    CONF_CWU_TARGET_TEMP,
    CONF_CWU_MIN_TEMP,
    CONF_CWU_CRITICAL_TEMP,
    CONF_SALON_TARGET_TEMP,
    CONF_SALON_MIN_TEMP,
    CONF_BEDROOM_MIN_TEMP,
)
from .bsb_lan import BSBLanClient
from .modes import BrokenHeaterMode, WinterMode, SummerMode
from . import tariff
from .energy import EnergyTracker
from .notifications import async_send_notification, async_check_and_send_daily_report

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
        self._fake_heating_detected_at: datetime | None = None
        self._last_state_change: datetime = datetime.now()

        # Transition lock - prevent race conditions during mode switches
        self._transition_in_progress: bool = False

        # Sensor tracking
        self._last_known_cwu_temp: float | None = None
        self._last_known_salon_temp: float | None = None
        self._last_cwu_temp_for_trend: float | None = None
        self._last_cwu_temp_time: datetime | None = None

        # CWU Session tracking (for UI)
        self._cwu_session_start_temp: float | None = None

        # Action history for UI (state history is tracked by HA natively)
        self._action_history: list[dict] = []

        # Power tracking for trend analysis
        self._recent_power_readings: list[tuple[datetime, float]] = []

        # First run flag - detect current state on startup
        self._first_run: bool = True

        # Operating mode
        self._operating_mode: str = config.get(CONF_OPERATING_MODE, MODE_BROKEN_HEATER)

        # BSB-LAN client for direct heat pump control
        bsb_host = config.get(CONF_BSB_LAN_HOST, DEFAULT_BSB_LAN_HOST)
        self._bsb_client = BSBLanClient(bsb_host)

        # BSB-LAN cached data (updated every coordinator update)
        self._bsb_lan_data: dict[str, Any] = {}
        self._bsb_lan_last_update: datetime | None = None  # Last successful BSB-LAN fetch

        # Control source tracking (cloud used only in safe mode)
        self._control_source: str = CONTROL_SOURCE_BSB_LAN

        # BSB-LAN fake heating detection
        self._bsb_dhw_charging_no_compressor_since: datetime | None = None

        # Anti-oscillation: last mode switch timestamp
        self._last_mode_switch: datetime | None = None

        # Max temp detection (pompa nie daje rady więcej)
        self._max_temp_achieved: float | None = None  # Najwyższa osiągnięta temp
        self._max_temp_at: datetime | None = None  # Kiedy zaczęliśmy sprawdzać
        self._electric_fallback_count: int = 0  # Ile razy "Charging electric"
        self._flow_temp_at_max_check: float | None = None  # Flow temp na początku okna

        # Anti-fighting tracking (rolling window - avoid fighting for last few degrees)
        self._cwu_temp_history_fighting: list[tuple[datetime, float]] = []  # Rolling 60min history
        self._electric_fallback_history: list[datetime] = []  # Timestamps of electric fallback events

        # Rapid drop detection (pobór CWU - kąpiel)
        self._cwu_temp_history_bsb: list[tuple[datetime, float]] = []  # Historia temp BSB 8830

        # HP wait for ready (po fake heating)
        self._hp_waiting_for_ready: bool = False
        self._hp_waiting_since: datetime | None = None

        # Energy tracking - delegated to EnergyTracker
        self._energy_tracker = EnergyTracker(
            hass,
            get_meter_value=lambda: self._get_energy_meter_value(),
            get_current_state=lambda: self._current_state,
            is_cheap_tariff=lambda: self.is_cheap_tariff(),
        )

        # State verification - periodically check pump state matches expected
        self._last_state_verify: datetime | None = None

        # BSB-LAN unavailability tracking for safe mode
        self._bsb_lan_unavailable_since: datetime | None = None

        # DHW Charged handling - rest time before switching to floor
        self._dhw_charged_at: datetime | None = None

        # Manual heat-to feature - one-time heating to specific temp
        self._manual_heat_to_target: float | None = None
        self._manual_heat_to_original_target: float | None = None
        self._manual_heat_to_active: bool = False

        # Config overrides from number entities (runtime changes)
        self._config_overrides: dict[str, float] = {}

        # Mode handlers - each mode has its own handler class
        self._mode_handlers = {
            MODE_BROKEN_HEATER: BrokenHeaterMode(self),
            MODE_WINTER: WinterMode(self),
            MODE_SUMMER: SummerMode(self),
        }

        # Register shutdown handler to save data
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, self._async_save_on_shutdown)

    @property
    def current_state(self) -> str:
        """Return current controller state."""
        return self._current_state

    @property
    def is_enabled(self) -> bool:
        """Return if controller is enabled."""
        return self._enabled

    @property
    def action_history(self) -> list[dict]:
        """Return action history (today + yesterday)."""
        return self._action_history

    @property
    def operating_mode(self) -> str:
        """Return current operating mode."""
        return self._operating_mode

    @property
    def energy_today(self) -> dict[str, float]:
        """Return today's energy consumption in kWh."""
        data = self._energy_tracker.energy_today
        data["total_cheap"] = data["cwu_cheap"] + data["floor_cheap"]
        data["total_expensive"] = data["cwu_expensive"] + data["floor_expensive"]
        return data

    @property
    def energy_yesterday(self) -> dict[str, float]:
        """Return yesterday's energy consumption in kWh."""
        data = self._energy_tracker.energy_yesterday
        data["total_cheap"] = data["cwu_cheap"] + data["floor_cheap"]
        data["total_expensive"] = data["cwu_expensive"] + data["floor_expensive"]
        return data

    @property
    def bsb_lan_data(self) -> dict[str, Any]:
        """Return cached BSB-LAN data."""
        return self._bsb_lan_data

    @property
    def bsb_lan_available(self) -> bool:
        """Return if BSB-LAN is available."""
        return self._bsb_client.is_available

    @property
    def control_source(self) -> str:
        """Return current control source (cloud only used in safe mode)."""
        return self._control_source

    async def async_load_energy_data(self) -> None:
        """Load persisted energy data from storage."""
        await self._energy_tracker.async_load()

    async def async_save_energy_data(self) -> None:
        """Save energy data to persistent storage."""
        await self._energy_tracker.async_save()

    async def _async_save_on_shutdown(self, event) -> None:
        """Save energy data when Home Assistant is stopping."""
        _LOGGER.info("Home Assistant stopping - saving energy data...")
        await self._energy_tracker.async_save()

    async def _maybe_save_energy_data(self) -> None:
        """Save energy data if enough time has passed since last save."""
        await self._energy_tracker.async_maybe_save()

    def get_tariff_cheap_rate(self) -> float:
        """Get configured cheap tariff rate (zł/kWh)."""
        return self.config.get(CONF_TARIFF_CHEAP_RATE, TARIFF_CHEAP_RATE)

    def get_tariff_expensive_rate(self) -> float:
        """Get configured expensive tariff rate (zł/kWh)."""
        return self.config.get(CONF_TARIFF_EXPENSIVE_RATE, TARIFF_EXPENSIVE_RATE)

    def _get_workday_state(self) -> str | None:
        """Get workday sensor state for tariff calculation."""
        workday_sensor = self.config.get(CONF_WORKDAY_SENSOR)
        if workday_sensor:
            state = self._get_entity_state(workday_sensor)
            if state is not None and state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                return state
        return None

    def is_cheap_tariff(self, dt: datetime | None = None) -> bool:
        """Check if current time is in cheap tariff window (G12w)."""
        return tariff.is_cheap_tariff(dt, self._get_workday_state())

    def get_current_tariff_rate(self, dt: datetime | None = None) -> float:
        """Get current electricity rate in zł/kWh."""
        return tariff.get_current_tariff_rate(
            self.get_tariff_cheap_rate(),
            self.get_tariff_expensive_rate(),
            dt,
            self._get_workday_state(),
        )

    def is_winter_cwu_heating_window(self, dt: datetime | None = None) -> bool:
        """Check if current time is in winter mode CWU heating window."""
        return tariff.is_winter_cwu_heating_window(dt)

    def get_winter_cwu_target(self) -> float:
        """Get CWU target temperature for winter mode."""
        base_target = self.config.get("cwu_target_temp", DEFAULT_CWU_TARGET_TEMP)
        return tariff.get_winter_cwu_target(base_target)

    def get_winter_cwu_emergency_threshold(self) -> float:
        """Get temperature below which CWU heating is forced outside windows."""
        base_target = self.config.get("cwu_target_temp", DEFAULT_CWU_TARGET_TEMP)
        return tariff.get_winter_cwu_emergency_threshold(base_target)

    async def async_set_operating_mode(self, mode: str) -> None:
        """Set operating mode."""
        if mode not in (MODE_BROKEN_HEATER, MODE_WINTER, MODE_SUMMER):
            _LOGGER.warning("Invalid operating mode: %s", mode)
            return

        old_mode = self._operating_mode
        self._operating_mode = mode
        self._log_action(f"Operating mode changed: {old_mode} -> {mode}", "User selected new operating mode")

        # Reset state when changing modes
        self._change_state(STATE_IDLE)
        self._cwu_heating_start = None
        self._cwu_session_start_temp = None
        self._pause_start = None
        self._low_power_start = None
        self._fake_heating_detected_at = None

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

    def _detect_initial_state(
        self,
        wh_state: str | None,
        climate_state: str | None,
        power: float | None,
        cwu_temp: float | None,
    ) -> None:
        """Detect initial state after HA restart based on device states."""
        _LOGGER.info("CWU Controller: Detecting initial state after startup...")

        # Check if CWU heating is active (BSB CWU mode "On" with power)
        # wh_state is now BSB cwu_mode like "On", "Off", etc.
        cwu_mode_active = wh_state and wh_state.lower() == "on"
        cwu_active = cwu_mode_active and power is not None and power > POWER_IDLE_THRESHOLD

        # Check if floor heating is active (BSB floor mode "Automatic" or "Comfort")
        # climate_state is now BSB floor_mode like "Automatic", "Protection", etc.
        floor_active = climate_state and climate_state.lower() in ("automatic", "comfort")

        if cwu_active:
            self._current_state = STATE_HEATING_CWU
            self._cwu_heating_start = datetime.now()  # Approximate - we don't know exact start
            self._cwu_session_start_temp = cwu_temp  # Current temp as start (approximate)
            self._log_action(
                f"Detected CWU heating in progress after restart (temp: {cwu_temp}°C)",
                f"BSB CWU mode ON, power {power:.0f}W > {POWER_IDLE_THRESHOLD}W"
            )
            _LOGGER.info("CWU Controller: Detected active CWU heating, resuming tracking")

        elif floor_active:
            self._current_state = STATE_HEATING_FLOOR
            self._log_action(
                "Detected floor heating in progress after restart",
                f"BSB floor mode: {climate_state}"
            )
            _LOGGER.info("CWU Controller: Detected active floor heating")

        else:
            self._current_state = STATE_IDLE
            self._log_action(
                "Started in idle state after restart",
                f"No active heating detected (CWU mode: {wh_state}, Floor mode: {climate_state})"
            )
            _LOGGER.info("CWU Controller: Starting in idle state")

    def _get_min_temp(self) -> float:
        """Get CWU min temperature (with runtime overrides)."""
        return self.get_config_value(CONF_CWU_MIN_TEMP, DEFAULT_CWU_MIN_TEMP)

    def _get_critical_temp(self) -> float:
        """Get CWU critical temperature (with runtime overrides)."""
        return self.get_config_value(CONF_CWU_CRITICAL_TEMP, DEFAULT_CWU_CRITICAL_TEMP)

    def _calculate_cwu_urgency(self, cwu_temp: float | None, current_hour: int) -> int:
        """Calculate CWU heating urgency."""
        if cwu_temp is None:
            # BSB-LAN unavailable - assume medium urgency
            return URGENCY_MEDIUM

        # Get thresholds from config (no offsets - single source)
        target = self._get_target_temp()
        min_temp = self._get_min_temp()
        critical = self._get_critical_temp()

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
        """Detect if pump thinks it's heating but not actually heating CWU.

        Detects fake heating when:
        - Water heater is in active mode (BSB CWU mode "On")
        - CWU heating has been active for at least FAKE_HEATING_DETECTION_TIME
        - No power spike >= POWER_SPIKE_THRESHOLD (200W) in the last 10 minutes

        This catches both scenarios:
        1. Power < 10W (pump waiting for broken immersion heater)
        2. Power ~50W (pump running but compressor not heating CWU)
        """
        if power is None or wh_state is None:
            return False

        # Water heater should be in an active mode (BSB mode "On")
        if not wh_state or wh_state.lower() != "on":
            return False

        # Need to be in CWU heating state for at least FAKE_HEATING_DETECTION_TIME
        if self._cwu_heating_start is None:
            return False

        now = datetime.now()
        minutes_heating = (now - self._cwu_heating_start).total_seconds() / 60
        if minutes_heating < FAKE_HEATING_DETECTION_TIME:
            return False

        # Check if there was any power spike above threshold in recent readings
        if not self._recent_power_readings:
            return False

        # Get readings from last FAKE_HEATING_DETECTION_TIME minutes
        cutoff = now - timedelta(minutes=FAKE_HEATING_DETECTION_TIME)
        recent_readings = [p for t, p in self._recent_power_readings if t > cutoff]

        if not recent_readings:
            return False

        max_power = max(recent_readings)

        # Fake heating if max power is below spike threshold (no real heating detected)
        return max_power < POWER_SPIKE_THRESHOLD

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

    def _check_winter_cwu_no_progress(self, current_temp: float | None) -> bool:
        """Check if winter mode CWU heating has made no progress after timeout.

        Returns True if:
        - Heating has been active for WINTER_CWU_NO_PROGRESS_TIMEOUT minutes
        - Temperature has not increased by at least WINTER_CWU_MIN_TEMP_INCREASE
        """
        if self._cwu_heating_start is None:
            return False
        if self._cwu_session_start_temp is None:
            return False
        if current_temp is None:
            # Can't check progress without current temp - don't trigger reset
            return False

        elapsed = (datetime.now() - self._cwu_heating_start).total_seconds() / 60
        if elapsed < WINTER_CWU_NO_PROGRESS_TIMEOUT:
            return False

        # Check if temperature has increased sufficiently
        temp_increase = current_temp - self._cwu_session_start_temp
        return temp_increase < WINTER_CWU_MIN_TEMP_INCREASE

    # -------------------------------------------------------------------------
    # Safe mode cloud methods (used ONLY when BSB-LAN unavailable 15+ minutes)
    # -------------------------------------------------------------------------

    async def _async_safe_mode_cwu_on(self) -> bool:
        """Turn CWU on via cloud (safe mode only).

        Always sends command even if already on (cloud state unreliable).
        """
        try:
            await self.hass.services.async_call(
                "water_heater",
                SERVICE_SET_OPERATION_MODE,
                {"entity_id": SAFE_MODE_WATER_HEATER, "operation_mode": "heat_pump"},
                blocking=True,
            )
            _LOGGER.debug("Safe mode: CWU ON (cloud)")
            return True
        except Exception as e:
            _LOGGER.error("Safe mode CWU ON failed: %s", e)
            return False

    async def _async_safe_mode_floor_on(self) -> bool:
        """Turn floor on via cloud (safe mode only).

        Always sends command even if already on (cloud state unreliable).
        """
        try:
            await self.hass.services.async_call(
                "climate",
                SERVICE_TURN_ON,
                {"entity_id": SAFE_MODE_CLIMATE},
                blocking=True,
            )
            _LOGGER.debug("Safe mode: Floor ON (cloud)")
            return True
        except Exception as e:
            _LOGGER.error("Safe mode Floor ON failed: %s", e)
            return False

    # -------------------------------------------------------------------------
    # Heat pump control methods
    # -------------------------------------------------------------------------

    async def _async_set_cwu_on(self) -> bool:
        """Turn CWU heating on with verification.

        Note: This is a low-level function. Caller should log the decision.
        """
        if not self._bsb_client.is_available:
            _LOGGER.warning("BSB-LAN unavailable - CWU ON skipped")
            return False

        success, msg = await self._bsb_client.async_write_and_verify(
            BSB_LAN_PARAM_CWU_MODE, BSB_CWU_MODE_ON
        )
        if success:
            _LOGGER.debug("CWU ON success")
        else:
            _LOGGER.error("CWU ON failed: %s", msg)
            self._log_action("Control error", f"CWU ON failed: {msg}")
        return success

    async def _async_set_cwu_off(self) -> bool:
        """Turn CWU heating off with verification.

        Note: This is a low-level function. Caller should log the decision.
        """
        if not self._bsb_client.is_available:
            _LOGGER.warning("BSB-LAN unavailable - CWU OFF skipped")
            return False

        success, msg = await self._bsb_client.async_write_and_verify(
            BSB_LAN_PARAM_CWU_MODE, BSB_CWU_MODE_OFF
        )
        if success:
            _LOGGER.debug("CWU OFF success")
        else:
            _LOGGER.error("CWU OFF failed: %s", msg)
            self._log_action("Control error", f"CWU OFF failed: {msg}")
        return success

    async def _async_set_floor_on(self) -> bool:
        """Turn floor heating on with verification.

        Note: This is a low-level function. Caller should log the decision.
        """
        if not self._bsb_client.is_available:
            _LOGGER.warning("BSB-LAN unavailable - Floor ON skipped")
            return False

        success, msg = await self._bsb_client.async_write_and_verify(
            BSB_LAN_PARAM_FLOOR_MODE, BSB_FLOOR_MODE_AUTOMATIC
        )
        if success:
            _LOGGER.debug("Floor ON success")
        else:
            _LOGGER.error("Floor ON failed: %s", msg)
            self._log_action("Control error", f"Floor ON failed: {msg}")
        return success

    async def _async_set_floor_off(self) -> bool:
        """Turn floor heating off with verification.

        Note: This is a low-level function. Caller should log the decision.
        """
        if not self._bsb_client.is_available:
            _LOGGER.warning("BSB-LAN unavailable - Floor OFF skipped")
            return False

        success, msg = await self._bsb_client.async_write_and_verify(
            BSB_LAN_PARAM_FLOOR_MODE, BSB_FLOOR_MODE_PROTECTION
        )
        if success:
            _LOGGER.debug("Floor OFF success")
        else:
            _LOGGER.error("Floor OFF failed: %s", msg)
            self._log_action("Control error", f"Floor OFF failed: {msg}")
        return success

    # -------------------------------------------------------------------------
    # Data fetching and temperature methods
    # -------------------------------------------------------------------------

    async def _async_refresh_bsb_lan_data(self) -> None:
        """Refresh BSB-LAN data for control decisions and sensors.

        On failure, keeps previous data (stale data is better than no data).
        Tracks last successful update time for staleness detection.
        After 15 min without fresh data, control logic will enter safe mode.
        """
        raw_data = await self._bsb_client.async_read_parameters()
        if not raw_data:
            # Keep old data - stale data is better than None values
            # Control logic checks _bsb_lan_last_update for staleness
            _LOGGER.debug("BSB-LAN refresh failed - keeping previous data")
            return

        # Update timestamp on successful fetch
        self._bsb_lan_last_update = datetime.now()

        self._bsb_lan_data = {
            "floor_mode": raw_data.get("700", {}).get("desc", "---"),
            "cwu_mode": raw_data.get("1600", {}).get("desc", "---"),
            "cwu_target_setpoint": self._parse_bsb_value(raw_data.get("1610", {})),
            "hc1_status": raw_data.get("8000", {}).get("desc", "---"),
            "dhw_status": raw_data.get("8003", {}).get("desc", "---"),
            "hp_status": raw_data.get("8006", {}).get("desc", "---"),
            "flow_temp": self._parse_bsb_value(raw_data.get("8412", {})),
            "return_temp": self._parse_bsb_value(raw_data.get("8410", {})),
            "cwu_temp": self._parse_bsb_value(raw_data.get("8830", {})),
            "outside_temp": self._parse_bsb_value(raw_data.get("8700", {})),
        }

        # Calculate delta T
        if self._bsb_lan_data["flow_temp"] is not None and self._bsb_lan_data["return_temp"] is not None:
            self._bsb_lan_data["delta_t"] = self._bsb_lan_data["flow_temp"] - self._bsb_lan_data["return_temp"]
        else:
            self._bsb_lan_data["delta_t"] = None

    def _get_cwu_temperature(self) -> float | None:
        """Get CWU temperature.

        Returns None if unavailable - triggers safe mode after timeout.
        """
        if self._bsb_lan_data:
            return self._bsb_lan_data.get("cwu_temp")
        return None

    def _detect_fake_heating_bsb(self) -> bool:
        """Detect fake heating using heat pump status.

        Fake heating detected when:
        1. DHW status shows "Charging electric" = broken heater scenario
        2. DHW status shows "Charging" but compressor not running for 10+ minutes
           EXCEPT when compressor is in mandatory off time ("off time min active")
        """
        if not self._bsb_lan_data:
            return False

        dhw_status = self._bsb_lan_data.get("dhw_status", "")
        hp_status = self._bsb_lan_data.get("hp_status", "")

        # Immediate detection: electric heater is charging (broken heater mode)
        if BSB_DHW_STATUS_CHARGING_ELECTRIC.lower() in dhw_status.lower():
            _LOGGER.debug("Detected electric heater charging (broken heater), DHW status: %s", dhw_status)
            return True

        # DHW charging but compressor not running
        dhw_charging = BSB_DHW_STATUS_CHARGING.lower() in dhw_status.lower()
        compressor_running = BSB_HP_COMPRESSOR_ON.lower() in hp_status.lower()
        # Compressor in mandatory minimum off time - this is NOT fake heating
        compressor_off_time = BSB_HP_OFF_TIME_ACTIVE.lower() in hp_status.lower()

        if dhw_charging and not compressor_running:
            # If compressor is in mandatory off time, this is normal - reset tracking
            if compressor_off_time:
                if self._bsb_dhw_charging_no_compressor_since is not None:
                    _LOGGER.debug("Compressor in mandatory off time - not fake heating, HP status: %s", hp_status)
                self._bsb_dhw_charging_no_compressor_since = None
                return False

            # Start tracking
            if self._bsb_dhw_charging_no_compressor_since is None:
                self._bsb_dhw_charging_no_compressor_since = datetime.now()

            # Check if threshold reached
            elapsed = (datetime.now() - self._bsb_dhw_charging_no_compressor_since).total_seconds() / 60
            if elapsed >= BSB_FAKE_HEATING_DETECTION_TIME:
                _LOGGER.debug("DHW charging but no compressor for %.1f min (threshold: %d min)", elapsed, BSB_FAKE_HEATING_DETECTION_TIME)
                return True
        else:
            # Reset tracking
            self._bsb_dhw_charging_no_compressor_since = None

        return False

    # -------------------------------------------------------------------------
    # State Verification - ensure pump state matches expected
    # -------------------------------------------------------------------------

    async def _verify_pump_state(self) -> None:
        """Verify pump state matches expected and fix if needed.

        Called periodically (every 5 minutes) to ensure the heat pump
        is in the correct state. This catches cases where:
        - BSB-LAN command was sent but pump didn't respond
        - Someone manually changed pump settings
        - Network issues caused command to be lost
        """
        now = datetime.now()

        # Skip if not enough time passed since last verify
        if self._last_state_verify is not None:
            minutes_since_verify = (now - self._last_state_verify).total_seconds() / 60
            if minutes_since_verify < BSB_LAN_STATE_VERIFY_INTERVAL:
                return

        # Skip if BSB-LAN not available or no data
        if not self._bsb_client.is_available or not self._bsb_lan_data:
            return

        # Skip if controller is disabled or in manual override
        if not self._enabled or self._manual_override:
            return

        # Skip if transition is in progress (states are changing)
        if self._transition_in_progress:
            return

        self._last_state_verify = now

        # Get current BSB-LAN state
        actual_cwu_mode = self._bsb_lan_data.get("cwu_mode", "")
        actual_floor_mode = self._bsb_lan_data.get("floor_mode", "")

        # Determine expected state based on current controller state
        expected_cwu_on, expected_floor_on = self._get_expected_pump_state()

        # Compare and fix if needed
        cwu_mismatch = False
        floor_mismatch = False

        # CWU: "On" or "Eco" means on, "Off" means off
        actual_cwu_on = actual_cwu_mode.lower() in ("on", "eco", "1")
        if expected_cwu_on != actual_cwu_on:
            cwu_mismatch = True

        # Floor: "Automatic" means on, "Protection" means off
        actual_floor_on = actual_floor_mode.lower() in ("automatic", "1")
        if expected_floor_on != actual_floor_on:
            floor_mismatch = True

        if cwu_mismatch or floor_mismatch:
            _LOGGER.warning(
                "Pump state mismatch detected! State: %s, "
                "Expected: CWU=%s Floor=%s, Actual: CWU=%s Floor=%s",
                self._current_state,
                "ON" if expected_cwu_on else "OFF",
                "ON" if expected_floor_on else "OFF",
                actual_cwu_mode,
                actual_floor_mode,
            )

            # Fix the state
            if cwu_mismatch:
                if expected_cwu_on:
                    await self._async_set_cwu_on()
                    self._log_action(
                        "State verify: Fixed CWU → ON",
                        f"Expected ON for state {self._current_state}, was {actual_cwu_mode}"
                    )
                else:
                    await self._async_set_cwu_off()
                    self._log_action(
                        "State verify: Fixed CWU → OFF",
                        f"Expected OFF for state {self._current_state}, was {actual_cwu_mode}"
                    )

            if floor_mismatch:
                if expected_floor_on:
                    await self._async_set_floor_on()
                    self._log_action(
                        "State verify: Fixed Floor → ON",
                        f"Expected ON for state {self._current_state}, was {actual_floor_mode}"
                    )
                else:
                    await self._async_set_floor_off()
                    self._log_action(
                        "State verify: Fixed Floor → OFF",
                        f"Expected OFF for state {self._current_state}, was {actual_floor_mode}"
                    )

    def _get_expected_pump_state(self) -> tuple[bool, bool]:
        """Get expected CWU and Floor state based on current controller state.

        Returns:
            Tuple of (cwu_should_be_on, floor_should_be_on)
        """
        state = self._current_state

        if state in (STATE_HEATING_CWU, STATE_EMERGENCY_CWU):
            # CWU heating: CWU on, floor off
            return (True, False)

        if state in (STATE_HEATING_FLOOR, STATE_EMERGENCY_FLOOR):
            # Floor heating: CWU off, floor on
            return (False, True)

        if state == STATE_SAFE_MODE:
            # Safe mode: both on (pump decides)
            return (True, True)

        if state in (STATE_IDLE, STATE_PAUSE, STATE_FAKE_HEATING_DETECTED):
            # Idle/pause/fake heating detected: both off
            return (False, False)

        if state == STATE_FAKE_HEATING_RESTARTING:
            # Restarting after fake heating: CWU on, floor off
            return (True, False)

        # Default: both off
        return (False, False)


    def _cleanup_old_history(self) -> None:
        """Remove history entries older than yesterday."""
        today = datetime.now().date()
        yesterday = today - timedelta(days=1)

        def is_recent(entry: dict) -> bool:
            try:
                entry_date = datetime.fromisoformat(entry["timestamp"]).date()
                return entry_date >= yesterday
            except (KeyError, ValueError):
                return False

        self._action_history = [e for e in self._action_history if is_recent(e)]

    def _log_action(self, action: str, reasoning: str = "") -> None:
        """Log an action to history with optional reasoning.

        Args:
            action: Short action description (e.g., "CWU ON", "Switch to floor")
            reasoning: Specific reasoning at this decision point
        """
        entry = {
            "timestamp": datetime.now().isoformat(),
            "action": action,
            "state": self._current_state,
            "reasoning": reasoning,
        }
        self._action_history.append(entry)
        self._cleanup_old_history()
        if reasoning:
            _LOGGER.info("CWU Controller: %s (%s)", action, reasoning)
        else:
            _LOGGER.info("CWU Controller: %s", action)

    def _change_state(self, new_state: str) -> None:
        """Change controller state."""
        if new_state != self._current_state:
            self._previous_state = self._current_state
            self._current_state = new_state
            self._last_state_change = datetime.now()
            self._cleanup_old_history()
            _LOGGER.info("CWU Controller state: %s -> %s", self._previous_state, new_state)

    def _get_energy_meter_value(self) -> float | None:
        """Get current value from energy meter sensor (kWh)."""
        energy_sensor = self.config.get(CONF_ENERGY_SENSOR, DEFAULT_ENERGY_SENSOR)
        return self._get_sensor_value(energy_sensor)


    async def async_enable(self) -> None:
        """Enable the controller."""
        self._enabled = True
        self._manual_override = False
        self._log_action("Controller enabled", "User toggled enable switch")

    async def async_disable(self) -> None:
        """Disable the controller and enter safe mode (heat pump takes control)."""
        self._enabled = False

        # Enter safe mode - turn on both floor and CWU, let heat pump decide
        await self._async_set_floor_on()
        _LOGGER.debug("Disable: Floor heating enabled, waiting 60s...")
        await asyncio.sleep(60)
        await self._async_set_cwu_on()
        self._log_action("Controller disabled - safe mode active", "User toggled enable switch, heat pump takes control")

    async def async_force_cwu(self, duration_minutes: int = 60) -> None:
        """Force CWU heating for specified duration."""
        self._manual_override = True
        self._manual_override_until = datetime.now() + timedelta(minutes=duration_minutes)

        # First turn off everything with delays between commands
        _LOGGER.debug("Force CWU: Stopping CWU")
        await self._async_set_cwu_off()
        await asyncio.sleep(30)

        _LOGGER.debug("Force CWU: Stopping floor heating")
        await self._async_set_floor_off()

        # Wait for pump to settle
        _LOGGER.debug("Force CWU: Waiting 60s for pump to settle")
        await asyncio.sleep(60)

        # Now enable CWU
        await self._async_set_cwu_on()

        self._change_state(STATE_HEATING_CWU)
        self._cwu_heating_start = datetime.now()
        # Set session start temp for UI tracking (BSB-LAN preferred)
        cwu_temp = self._get_cwu_temperature()
        self._cwu_session_start_temp = cwu_temp if cwu_temp is not None else self._last_known_cwu_temp
        self._log_action("Force CWU", f"Manual override for {duration_minutes} min")

    async def async_force_floor(self, duration_minutes: int = 60) -> None:
        """Force floor heating for specified duration."""
        self._manual_override = True
        self._manual_override_until = datetime.now() + timedelta(minutes=duration_minutes)

        # First turn off everything with delays between commands
        _LOGGER.debug("Force Floor: Stopping CWU")
        await self._async_set_cwu_off()
        await asyncio.sleep(30)

        _LOGGER.debug("Force Floor: Stopping floor heating")
        await self._async_set_floor_off()

        # Wait for pump to settle
        _LOGGER.debug("Force Floor: Waiting 60s for pump to settle")
        await asyncio.sleep(60)

        # Now enable floor heating
        await self._async_set_floor_on()

        self._change_state(STATE_HEATING_FLOOR)
        self._log_action("Force Floor", f"Manual override for {duration_minutes} min")

    async def async_force_auto(self) -> None:
        """Cancel manual override and let controller decide from scratch."""
        self._manual_override = False
        self._manual_override_until = None
        self._manual_heat_to_active = False
        self._manual_heat_to_target = None
        self._change_state(STATE_IDLE)
        self._cwu_heating_start = None
        self._cwu_session_start_temp = None
        self._log_action("Manual override cancelled", "Switching to auto mode")
        # Next coordinator update will run control logic and decide

    async def async_heat_to_temp(self, target_temp: float) -> None:
        """Heat CWU to specific temperature, then return to AUTO.

        Args:
            target_temp: Target temperature in °C (36-55)
        """
        if target_temp < MANUAL_HEAT_TO_MIN_TEMP or target_temp > MANUAL_HEAT_TO_MAX_TEMP:
            _LOGGER.warning(
                "Heat-to target %s°C out of range (%s-%s°C)",
                target_temp, MANUAL_HEAT_TO_MIN_TEMP, MANUAL_HEAT_TO_MAX_TEMP
            )
            return

        cwu_temp = self._get_cwu_temperature()

        # Store original target for restoration
        self._manual_heat_to_original_target = self.get_config_value(
            CONF_CWU_TARGET_TEMP, DEFAULT_CWU_TARGET_TEMP
        )
        self._manual_heat_to_target = target_temp
        self._manual_heat_to_active = True
        self._manual_override = True

        # Sync target to BSB-LAN
        await self._bsb_client.async_set_cwu_target_temp(target_temp)

        # Start CWU heating
        await self._async_set_floor_off()
        await asyncio.sleep(30)
        await self._async_set_cwu_on()

        self._change_state(STATE_HEATING_CWU)
        self._cwu_heating_start = datetime.now()
        self._cwu_session_start_temp = cwu_temp
        self._log_action(
            "Heat-to started",
            f"Target {target_temp:.0f}°C, current {cwu_temp:.1f}°C" if cwu_temp else f"Target {target_temp:.0f}°C"
        )

    def get_config_value(self, key: str, default: float) -> float:
        """Get config value with runtime overrides.

        Args:
            key: Config key (e.g., CONF_CWU_TARGET_TEMP)
            default: Default value if not set

        Returns:
            Current value (override or config or default)
        """
        if key in self._config_overrides:
            return self._config_overrides[key]
        return self.config.get(key, default)

    async def async_set_config_value(self, key: str, value: float) -> None:
        """Set config override value (from number entities).

        Args:
            key: Config key to override
            value: New value
        """
        self._config_overrides[key] = value
        _LOGGER.info("Config override: %s = %s", key, value)

        # Sync CWU target to BSB-LAN if changed
        if key == CONF_CWU_TARGET_TEMP:
            await self._bsb_client.async_set_cwu_target_temp(value)

    @property
    def manual_heat_to_active(self) -> bool:
        """Return if manual heat-to is active."""
        return self._manual_heat_to_active

    @property
    def manual_heat_to_target(self) -> float | None:
        """Return manual heat-to target temperature."""
        return self._manual_heat_to_target

    @property
    def last_reasoning(self) -> str:
        """Return reasoning from last action."""
        if self._action_history:
            return self._action_history[-1].get("reasoning", "")
        return ""

    async def async_test_cwu_on(self) -> None:
        """Test action: turn on CWU."""
        success = await self._async_set_cwu_on()
        status = "CWU turned ON" if success else "CWU ON failed (unavailable)"
        await async_send_notification(self, "CWU Controller Test", status)

    async def async_test_cwu_off(self) -> None:
        """Test action: turn off CWU."""
        success = await self._async_set_cwu_off()
        status = "CWU turned OFF" if success else "CWU OFF failed (unavailable)"
        await async_send_notification(self, "CWU Controller Test", status)

    async def async_test_floor_on(self) -> None:
        """Test action: turn on floor heating."""
        success = await self._async_set_floor_on()
        status = "Floor heating turned ON" if success else "Floor ON failed (unavailable)"
        await async_send_notification(self, "CWU Controller Test", status)

    async def async_test_floor_off(self) -> None:
        """Test action: turn off floor heating."""
        success = await self._async_set_floor_off()
        status = "Floor heating turned OFF" if success else "Floor OFF failed (unavailable)"
        await async_send_notification(self, "CWU Controller Test", status)

    def _parse_bsb_value(self, data: dict) -> float | None:
        """Parse BSB-LAN value from response."""
        try:
            value = data.get("value")
            if value is not None:
                return float(value)
        except (ValueError, TypeError):
            pass
        return None

    async def _async_update_data(self) -> dict[str, Any]:
        """Update data and run control logic."""
        now = datetime.now()
        current_hour = now.hour

        # Fetch heat pump data
        await self._async_refresh_bsb_lan_data()

        # Get CWU temperature
        cwu_temp = self._get_cwu_temperature()

        # Get other sensor values
        salon_temp = self._get_sensor_value(self.config.get("salon_temp_sensor"))
        bedroom_temp = self._get_sensor_value(self.config.get("bedroom_temp_sensor"))
        kids_temp = self._get_sensor_value(self.config.get("kids_room_temp_sensor"))
        power = self._get_sensor_value(self.config.get("power_sensor"))
        pump_input = self._get_sensor_value(self.config.get("pump_input_temp"))
        pump_output = self._get_sensor_value(self.config.get("pump_output_temp"))

        # Get CWU and floor modes from heat pump data
        wh_state = self._bsb_lan_data.get("cwu_mode") if self._bsb_lan_data else None
        climate_state = self._bsb_lan_data.get("floor_mode") if self._bsb_lan_data else None

        # First run - detect current state from actual device states
        if self._first_run:
            self._first_run = False
            self._detect_initial_state(wh_state, climate_state, power, cwu_temp)

        # Track CWU temp for trend analysis
        if cwu_temp is not None:
            self._last_known_cwu_temp = cwu_temp

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

        # Detect fake heating (only in broken_heater mode)
        # Use status-based detection with power-based fallback
        fake_heating = False
        if self._operating_mode == MODE_BROKEN_HEATER:
            if self._bsb_lan_data:
                fake_heating = self._detect_fake_heating_bsb()
            else:
                # Fallback to power-based detection
                fake_heating = self._detect_fake_heating(power, wh_state)

        # Update energy tracking
        self._energy_tracker.update()

        # Periodically save energy data (every 5 minutes)
        await self._maybe_save_energy_data()

        # Check for daily report
        await async_check_and_send_daily_report(self)

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
            "manual_override_until": self._manual_override_until.isoformat() if self._manual_override_until else None,
            "cwu_heating_minutes": 0,
            "action_history": self._action_history[-20:],
            "cwu_target_temp": self._get_target_temp(),
            "cwu_min_temp": self._get_min_temp(),
            "cwu_critical_temp": self._get_critical_temp(),
            "salon_target_temp": self.config.get("salon_target_temp", DEFAULT_SALON_TARGET_TEMP),
            # Manual heat-to feature
            "manual_heat_to_active": self._manual_heat_to_active,
            "manual_heat_to_target": self._manual_heat_to_target,
            "dhw_charged_at": self._dhw_charged_at.isoformat() if self._dhw_charged_at else None,
            # CWU Session data
            "cwu_session_start_time": self._cwu_heating_start.isoformat() if self._cwu_heating_start else None,
            "cwu_session_start_temp": self._cwu_session_start_temp,
            # Fake heating recovery data
            "fake_heating_restart_in": None,
            # Operating mode
            "operating_mode": self._operating_mode,
            # Tariff information
            "is_cheap_tariff": self.is_cheap_tariff(),
            "current_tariff_rate": self.get_current_tariff_rate(),
            "is_cwu_heating_window": self.is_winter_cwu_heating_window() if self._operating_mode == MODE_WINTER else False,
            # Winter mode specific
            "winter_cwu_target": self.get_winter_cwu_target() if self._operating_mode == MODE_WINTER else None,
            "winter_cwu_emergency_threshold": self.get_winter_cwu_emergency_threshold() if self._operating_mode == MODE_WINTER else None,
            # Energy tracking (using property for calculated values)
            "energy_today_cwu_kwh": self.energy_today["cwu"],
            "energy_today_cwu_cheap_kwh": self.energy_today["cwu_cheap"],
            "energy_today_cwu_expensive_kwh": self.energy_today["cwu_expensive"],
            "energy_today_floor_kwh": self.energy_today["floor"],
            "energy_today_floor_cheap_kwh": self.energy_today["floor_cheap"],
            "energy_today_floor_expensive_kwh": self.energy_today["floor_expensive"],
            "energy_today_total_kwh": self.energy_today["total"],
            "energy_today_total_cheap_kwh": self.energy_today["total_cheap"],
            "energy_today_total_expensive_kwh": self.energy_today["total_expensive"],
            "energy_yesterday_cwu_kwh": self.energy_yesterday["cwu"],
            "energy_yesterday_cwu_cheap_kwh": self.energy_yesterday["cwu_cheap"],
            "energy_yesterday_cwu_expensive_kwh": self.energy_yesterday["cwu_expensive"],
            "energy_yesterday_floor_kwh": self.energy_yesterday["floor"],
            "energy_yesterday_floor_cheap_kwh": self.energy_yesterday["floor_cheap"],
            "energy_yesterday_floor_expensive_kwh": self.energy_yesterday["floor_expensive"],
            "energy_yesterday_total_kwh": self.energy_yesterday["total"],
            "energy_yesterday_total_cheap_kwh": self.energy_yesterday["total_cheap"],
            "energy_yesterday_total_expensive_kwh": self.energy_yesterday["total_expensive"],
            # Cost calculations (accurate based on actual tariff usage)
            "cost_today_cwu_estimate": (
                self.energy_today["cwu_cheap"] * self.get_tariff_cheap_rate() +
                self.energy_today["cwu_expensive"] * self.get_tariff_expensive_rate()
            ),
            "cost_today_floor_estimate": (
                self.energy_today["floor_cheap"] * self.get_tariff_cheap_rate() +
                self.energy_today["floor_expensive"] * self.get_tariff_expensive_rate()
            ),
            "cost_today_estimate": (
                self.energy_today["total_cheap"] * self.get_tariff_cheap_rate() +
                self.energy_today["total_expensive"] * self.get_tariff_expensive_rate()
            ),
            "cost_yesterday_cwu_estimate": (
                self.energy_yesterday["cwu_cheap"] * self.get_tariff_cheap_rate() +
                self.energy_yesterday["cwu_expensive"] * self.get_tariff_expensive_rate()
            ),
            "cost_yesterday_floor_estimate": (
                self.energy_yesterday["floor_cheap"] * self.get_tariff_cheap_rate() +
                self.energy_yesterday["floor_expensive"] * self.get_tariff_expensive_rate()
            ),
            "cost_yesterday_estimate": (
                self.energy_yesterday["total_cheap"] * self.get_tariff_cheap_rate() +
                self.energy_yesterday["total_expensive"] * self.get_tariff_expensive_rate()
            ),
            # Tariff rates (for sensors)
            "tariff_cheap_rate": self.get_tariff_cheap_rate(),
            "tariff_expensive_rate": self.get_tariff_expensive_rate(),
            # BSB-LAN data
            "bsb_lan": self._bsb_lan_data,
            "bsb_lan_available": self._bsb_client.is_available,
            "control_source": self._control_source,
            # Anti-oscillation data (broken_heater mode)
            "last_mode_switch": self._last_mode_switch.isoformat() if self._last_mode_switch else None,
            "hold_time_remaining": self._get_hold_time_remaining(),
            "can_switch_to_cwu": self._can_switch_mode(self._current_state, STATE_HEATING_CWU)[0] if self._operating_mode == MODE_BROKEN_HEATER else True,
            "can_switch_to_floor": self._can_switch_mode(self._current_state, STATE_HEATING_FLOOR)[0] if self._operating_mode == MODE_BROKEN_HEATER else True,
            "switch_blocked_reason": self._get_switch_blocked_reason(),
            # HP status (broken_heater mode)
            "hp_ready": self._is_hp_ready_for_cwu()[0] if self._operating_mode == MODE_BROKEN_HEATER else True,
            "hp_ready_reason": self._is_hp_ready_for_cwu()[1] if self._operating_mode == MODE_BROKEN_HEATER else "OK",
            # Max temp tracking (broken_heater mode)
            "max_temp_achieved": self._max_temp_achieved,
            "electric_fallback_count": self._electric_fallback_count,
            "max_temp_detected": self._max_temp_achieved is not None,
            # Night floor window (broken_heater mode)
            "is_night_floor_window": BROKEN_HEATER_FLOOR_WINDOW_START <= now.hour < BROKEN_HEATER_FLOOR_WINDOW_END if self._operating_mode == MODE_BROKEN_HEATER else False,
        }

        if self._fake_heating_detected_at:
            elapsed = (now - self._fake_heating_detected_at).total_seconds() / 60
            remaining = max(0, FAKE_HEATING_RESTART_WAIT - elapsed)
            data["fake_heating_restart_in"] = round(remaining, 1)

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
                self._log_action("Manual override expired", "Timer reached, returning to auto mode")

        # Handle fake heating even in manual CWU mode
        # (don't switch to floor, just restart CWU after wait period)
        if self._manual_override and self._current_state == STATE_HEATING_CWU:
            if fake_heating:
                self._change_state(STATE_FAKE_HEATING_DETECTED)
                self._fake_heating_detected_at = datetime.now()
                # Stop all heating
                await self._async_set_cwu_off()
                await self._async_set_floor_off()
                await async_send_notification(self,
                    "CWU Controller Alert (Manual Mode)",
                    f"Fake heating detected! Pump trying electric heater (broken). "
                    f"CWU temp: {cwu_temp}°C. Waiting {HP_RESTART_MIN_WAIT}+ min for HP ready..."
                )
                self._log_action(
                    "Manual mode: Fake heating detected",
                    f"CWU {cwu_temp:.1f}°C, all OFF, waiting {HP_RESTART_MIN_WAIT}+ min for HP ready"
                    if cwu_temp else f"All OFF, waiting {HP_RESTART_MIN_WAIT}+ min for HP ready"
                )

        # Handle fake heating restart in manual mode (with HP ready check)
        if self._manual_override and self._current_state == STATE_FAKE_HEATING_DETECTED:
            if self._fake_heating_detected_at:
                elapsed = (now - self._fake_heating_detected_at).total_seconds() / 60

                # Wait minimum time before checking HP
                if elapsed < HP_RESTART_MIN_WAIT:
                    return data  # Still waiting

                # Check if HP is ready
                hp_ready, hp_reason = self._is_hp_ready_for_cwu()
                if not hp_ready:
                    # Log every 2 minutes while waiting
                    if int(elapsed) % 2 == 0 and int(elapsed) != int(elapsed - 1):
                        _LOGGER.debug("Manual mode: Waiting for HP ready - %s (%.1f min elapsed)", hp_reason, elapsed)
                    return data  # Keep waiting

                # HP ready - restart CWU
                await self._async_set_cwu_on()
                self._fake_heating_detected_at = None
                self._change_state(STATE_HEATING_CWU)
                self._cwu_heating_start = now  # Reset heating start for next detection
                self._last_mode_switch = now  # For anti-oscillation
                self._reset_max_temp_tracking()  # Reset max temp for new session
                cwu_temp_now = self._get_cwu_temperature()
                self._log_action(
                    "Manual mode: CWU restarted after fake heating",
                    f"HP ready after {elapsed:.1f} min wait, CWU at {cwu_temp_now:.1f}°C" if cwu_temp_now else f"HP ready after {elapsed:.1f} min wait"
                )

        # Check heat-to completion (manual heating to specific temp)
        if self._manual_heat_to_active and cwu_temp is not None:
            if cwu_temp >= self._manual_heat_to_target:
                # Target reached - restore original target and return to AUTO
                if self._manual_heat_to_original_target:
                    await self._bsb_client.async_set_cwu_target_temp(self._manual_heat_to_original_target)

                self._log_action(
                    "Heat-to complete",
                    f"Reached {cwu_temp:.1f}°C (target {self._manual_heat_to_target:.0f}°C)"
                )

                # Reset and return to AUTO
                self._manual_heat_to_active = False
                self._manual_heat_to_target = None
                self._manual_override = False
                self._manual_override_until = None
                self._change_state(STATE_IDLE)
                # Next update will run control logic

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

        # Periodic state verification (every 5 minutes)
        # Ensures pump state matches expected, fixes if needed
        await self._verify_pump_state()

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
        """Run the main control logic - routes to mode-specific logic."""

        # Skip control logic if a transition is in progress
        if self._transition_in_progress:
            return

        # Handle safe mode - BSB-LAN unavailable
        if self._current_state == STATE_SAFE_MODE:
            # Check if BSB-LAN recovered
            if self._bsb_client.is_available and cwu_temp is not None:
                self._log_action(
                    "BSB-LAN recovered - exiting safe mode",
                    f"CWU: {cwu_temp:.1f}°C, Salon: {salon_temp:.1f}°C, resuming BSB-LAN control"
                    if salon_temp else f"CWU: {cwu_temp:.1f}°C, resuming BSB-LAN control"
                )
                await async_send_notification(self,
                    "CWU Controller Recovered",
                    f"BSB-LAN connection restored.\n"
                    f"CWU: {cwu_temp}°C, Salon: {salon_temp}°C\n"
                    f"Resuming normal BSB-LAN control."
                )
                self._bsb_lan_unavailable_since = None
                self._control_source = CONTROL_SOURCE_BSB_LAN
                self._change_state(STATE_IDLE)
                # Continue to normal control logic below
            else:
                # Still in safe mode, nothing to do
                return

        # Check BSB-LAN data freshness for safe mode
        # We keep stale data on failure (stale data is better than None),
        # but after 15 min without fresh data, enter safe mode and clear data.
        data_stale_minutes = 0.0
        if self._bsb_lan_last_update is not None:
            data_stale_minutes = (datetime.now() - self._bsb_lan_last_update).total_seconds() / 60

        # Check if data is too stale (no fresh data for 15+ minutes)
        if self._bsb_lan_last_update is None or data_stale_minutes >= BSB_LAN_UNAVAILABLE_TIMEOUT:
            if self._bsb_lan_last_update is None:
                # Never had data - can't make decisions
                _LOGGER.warning("BSB-LAN: No data yet - waiting for first successful fetch")
                return

            # Data is too stale - enter safe mode
            self._log_action(
                "Entering safe mode",
                f"BSB-LAN data stale for {data_stale_minutes:.0f} min (threshold: {BSB_LAN_UNAVAILABLE_TIMEOUT} min)"
            )
            await async_send_notification(self,
                "CWU Controller - Safe Mode",
                f"BSB-LAN data has been stale for {data_stale_minutes:.0f} minutes.\n\n"
                f"Entering safe mode - using cloud control as backup.\n"
                f"CWU and floor heating will be turned on via cloud.\n"
                f"Normal BSB-LAN control will resume when connection recovers."
            )
            # Clear stale data
            self._bsb_lan_data = {}
            await self._enter_safe_mode()
            self._change_state(STATE_SAFE_MODE)
            return

        # Data is fresh enough - continue with cached data
        # Clear any previous unavailable state if we have fresh data
        if self._bsb_lan_unavailable_since is not None and data_stale_minutes < 2:
            self._log_action(
                "BSB-LAN connection restored",
                f"Data fresh ({data_stale_minutes:.1f} min old), resuming normal control"
            )
            self._bsb_lan_unavailable_since = None
            self._control_source = CONTROL_SOURCE_BSB_LAN

        # Route to mode handler
        handler = self._mode_handlers.get(self._operating_mode)
        if handler:
            await handler.run_logic(cwu_urgency, floor_urgency, cwu_temp, salon_temp)
        else:
            _LOGGER.error("Unknown operating mode: %s, falling back to broken_heater", self._operating_mode)
            await self._mode_handlers[MODE_BROKEN_HEATER].run_logic(
                cwu_urgency, floor_urgency, cwu_temp, salon_temp
            )

    # =========================================================================
    # BROKEN HEATER MODE - Helper Methods (Refactored)
    # =========================================================================

    def _is_hp_ready_for_cwu(self) -> tuple[bool, str]:
        """Check if heat pump is ready to start CWU heating.

        Returns False during:
        - Compressor off time min active (mandatory rest)
        - Defrosting active
        - Overrun active (pump circulation)
        """
        if not self._bsb_lan_data:
            # BSB-LAN unavailable - assume ready (fallback mode)
            return (True, "BSB unavailable, assuming ready")

        hp_status = self._bsb_lan_data.get("hp_status", "")
        dhw_status = self._bsb_lan_data.get("dhw_status", "")

        # Compressor mandatory rest period
        if BSB_HP_OFF_TIME_ACTIVE.lower() in hp_status.lower():
            return (False, "HP: Compressor off time")

        # Defrosting
        if HP_STATUS_DEFROSTING.lower() in hp_status.lower():
            return (False, "HP: Defrosting")

        # Overrun (pump circulation after heating)
        if HP_STATUS_OVERRUN.lower() in hp_status.lower():
            return (False, "HP: Overrun")
        if HP_STATUS_OVERRUN.lower() in dhw_status.lower():
            return (False, "DHW: Overrun")

        return (True, "HP ready")

    def _can_switch_mode(self, from_state: str, to_state: str) -> tuple[bool, str]:
        """Check if mode switch is allowed (anti-oscillation + HP check).

        Returns:
            Tuple of (allowed: bool, reason: str)
        """
        now = datetime.now()

        # Check minimum hold times
        if self._last_mode_switch is not None:
            elapsed = (now - self._last_mode_switch).total_seconds() / 60

            if from_state in (STATE_HEATING_CWU, STATE_EMERGENCY_CWU) and elapsed < MIN_CWU_HEATING_TIME:
                return (False, f"CWU hold: {MIN_CWU_HEATING_TIME - elapsed:.0f}min left")

            if from_state in (STATE_HEATING_FLOOR, STATE_EMERGENCY_FLOOR) and elapsed < MIN_FLOOR_HEATING_TIME:
                return (False, f"Floor hold: {MIN_FLOOR_HEATING_TIME - elapsed:.0f}min left")

        # HP check before switching TO CWU
        if to_state in (STATE_HEATING_CWU, STATE_EMERGENCY_CWU):
            hp_ready, hp_reason = self._is_hp_ready_for_cwu()
            if not hp_ready:
                return (False, hp_reason)

        return (True, "OK")

    def _get_hold_time_remaining(self) -> float:
        """Get remaining hold time in minutes before mode switch is allowed.

        Returns:
            Remaining minutes (0 if no hold active)
        """
        if self._last_mode_switch is None:
            return 0.0

        elapsed = (datetime.now() - self._last_mode_switch).total_seconds() / 60

        # Check which hold time applies based on current state
        if self._current_state in (STATE_HEATING_CWU, STATE_EMERGENCY_CWU):
            remaining = MIN_CWU_HEATING_TIME - elapsed
        elif self._current_state in (STATE_HEATING_FLOOR, STATE_EMERGENCY_FLOOR):
            remaining = MIN_FLOOR_HEATING_TIME - elapsed
        else:
            return 0.0

        return max(0.0, remaining)

    def _get_switch_blocked_reason(self) -> str:
        """Get reason why mode switch is blocked (or empty if not blocked).

        Returns:
            Reason string (empty if switch is allowed)
        """
        # Check hold time first
        hold_remaining = self._get_hold_time_remaining()
        if hold_remaining > 0:
            if self._current_state in (STATE_HEATING_CWU, STATE_EMERGENCY_CWU):
                return f"CWU hold: {hold_remaining:.0f}min left"
            elif self._current_state in (STATE_HEATING_FLOOR, STATE_EMERGENCY_FLOOR):
                return f"Floor hold: {hold_remaining:.0f}min left"

        # Check HP status if trying to switch to CWU
        hp_ready, hp_reason = self._is_hp_ready_for_cwu()
        if not hp_ready:
            return hp_reason

        return ""

    def _detect_max_temp_achieved(self) -> bool:
        """Detect if pump reached max temp for current outside temperature.

        Criteria (any of these triggers max temp detection):
        1. Flow temp (8412) not rising significantly for 30 min + electric fallback 2+ times
        2. Anti-fighting (rolling 60min window): within 5°C of target AND either:
           - <2°C progress in last 60 min, OR
           - 2+ electric fallback events in last 60 min

        Returns True if max temp detected (should switch to floor).
        """
        if not self._bsb_lan_data:
            return False

        flow_temp = self._bsb_lan_data.get("flow_temp")
        dhw_status = self._bsb_lan_data.get("dhw_status", "")
        cwu_temp = self._bsb_lan_data.get("cwu_temp")
        target_temp = self._get_target_temp()
        now = datetime.now()
        cutoff = now - timedelta(minutes=MAX_TEMP_FIGHTING_WINDOW)

        # Track electric fallback events with timestamps
        if "electric" in dhw_status.lower():
            # Avoid duplicate entries within same minute
            if not self._electric_fallback_history or \
               (now - self._electric_fallback_history[-1]).total_seconds() > 60:
                self._electric_fallback_history.append(now)
                self._electric_fallback_count += 1
                _LOGGER.debug(f"Electric fallback count: {self._electric_fallback_count}")

        # Prune old electric fallback history (keep only last 60 min)
        self._electric_fallback_history = [
            t for t in self._electric_fallback_history if t > cutoff
        ]

        # Track CWU temp history for rolling window (anti-fighting)
        if cwu_temp is not None:
            self._cwu_temp_history_fighting.append((now, cwu_temp))
            # Prune old entries (keep 70 min to have buffer)
            prune_cutoff = now - timedelta(minutes=70)
            self._cwu_temp_history_fighting = [
                (t, temp) for t, temp in self._cwu_temp_history_fighting if t > prune_cutoff
            ]

        # Initialize flow temp tracking (for original electric fallback detection)
        if self._flow_temp_at_max_check is None:
            self._flow_temp_at_max_check = flow_temp
            self._max_temp_at = now
            return False

        if flow_temp is None or self._flow_temp_at_max_check is None:
            return False

        flow_rise = flow_temp - self._flow_temp_at_max_check
        elapsed = (now - self._max_temp_at).total_seconds() / 60 if self._max_temp_at else 0

        # Check 1: Electric fallback + flow stagnation (original logic - 30 min window)
        if elapsed >= MAX_TEMP_DETECTION_WINDOW:
            if flow_rise < MAX_TEMP_FLOW_STAGNATION and self._electric_fallback_count >= MAX_TEMP_ELECTRIC_FALLBACK_COUNT:
                # Max reached via electric fallback
                self._max_temp_achieved = cwu_temp
                self._log_action(
                    "Max temp detected",
                    f"Flow stagnant +{flow_rise:.1f}°C, electric x{self._electric_fallback_count}, CWU={cwu_temp:.1f}°C"
                )
                return True

            # Reset for next window
            self._flow_temp_at_max_check = flow_temp
            self._max_temp_at = now
            self._electric_fallback_count = 0

        # Check 2: Anti-fighting (rolling 60 min window)
        if cwu_temp is not None:
            distance_to_target = target_temp - cwu_temp

            # Only check if within threshold of target
            if 0 <= distance_to_target <= MAX_TEMP_FIGHTING_THRESHOLD:
                # Get temp from ~60 min ago
                old_temps = [(t, temp) for t, temp in self._cwu_temp_history_fighting if t <= cutoff]

                if old_temps:
                    # Use the oldest entry within our window
                    oldest_time, oldest_temp = min(old_temps, key=lambda x: x[0])
                    window_progress = cwu_temp - oldest_temp
                    window_elapsed = (now - oldest_time).total_seconds() / 60

                    # Count electric events in last 60 min
                    electric_in_window = len(self._electric_fallback_history)

                    # Fighting conditions:
                    # A) Slow progress: <2°C in 60 min
                    slow_progress = window_progress < MAX_TEMP_FIGHTING_PROGRESS and window_elapsed >= MAX_TEMP_FIGHTING_WINDOW

                    # B) Electric heater keeps activating: 2+ times in 60 min
                    electric_fighting = electric_in_window >= MAX_TEMP_FIGHTING_ELECTRIC_COUNT

                    if slow_progress or electric_fighting:
                        self._max_temp_achieved = cwu_temp
                        reason_parts = []
                        if slow_progress:
                            reason_parts.append(f"progress +{window_progress:.1f}°C/{window_elapsed:.0f}min")
                        if electric_fighting:
                            reason_parts.append(f"electric fallback x{electric_in_window}/60min")
                        self._log_action(
                            "Anti-fighting: stop",
                            f"CWU {cwu_temp:.1f}°C (target {target_temp:.1f}°C, -{distance_to_target:.1f}°C), {', '.join(reason_parts)}"
                        )
                        return True

        return False

    def _is_cwu_temp_acceptable(self, cwu_temp: float | None) -> bool:
        """Check if current CWU temp is acceptable.

        If we achieved max (e.g. 45°C), drop to 40°C is OK.
        But if max was 38°C, drop to 33°C is NOT acceptable.
        """
        if cwu_temp is None:
            return False

        # Absolute minimum threshold
        if cwu_temp < MAX_TEMP_CRITICAL_THRESHOLD:
            return False

        # If we have recorded max
        if self._max_temp_achieved is not None:
            drop = self._max_temp_achieved - cwu_temp
            if drop <= MAX_TEMP_ACCEPTABLE_DROP:  # <= 5°C from max
                return True
            return False

        # No max recorded - use standard target with hysteresis
        target = self._get_target_temp()
        hysteresis = self.get_config_value(CONF_CWU_HYSTERESIS, DEFAULT_CWU_HYSTERESIS)
        return cwu_temp >= target - hysteresis

    def _detect_rapid_drop(self) -> tuple[bool, float]:
        """Detect rapid CWU temperature drop (hot water usage / bath).

        Uses BSB 8830 (bottom of tank) for fast detection.
        Skips detection if already heating CWU (pointless to detect when already acting).

        Returns:
            Tuple of (drop_detected: bool, drop_amount: float)
        """
        # Skip if already heating CWU - we're already doing what rapid drop would trigger
        if self._current_state in (STATE_HEATING_CWU, STATE_EMERGENCY_CWU):
            return (False, 0.0)

        if not self._bsb_lan_data:
            return (False, 0.0)

        cwu_temp = self._bsb_lan_data.get("cwu_temp")
        if cwu_temp is None:
            return (False, 0.0)

        now = datetime.now()
        self._cwu_temp_history_bsb.append((now, cwu_temp))

        # Keep only last CWU_RAPID_DROP_WINDOW minutes
        cutoff = now - timedelta(minutes=CWU_RAPID_DROP_WINDOW)
        self._cwu_temp_history_bsb = [(t, temp) for t, temp in self._cwu_temp_history_bsb if t > cutoff]

        if len(self._cwu_temp_history_bsb) < 2:
            return (False, 0.0)

        # Get max temp in window
        max_temp = max(temp for _, temp in self._cwu_temp_history_bsb)
        drop = max_temp - cwu_temp

        if drop >= CWU_RAPID_DROP_THRESHOLD:  # >= 5°C
            self._log_action(
                "Rapid CWU drop",
                f"{max_temp:.1f}→{cwu_temp:.1f}°C ({drop:.1f}°C drop in {CWU_RAPID_DROP_WINDOW}min)"
            )
            return (True, drop)

        return (False, drop)

    def _is_pump_charged(self) -> bool:
        """Check if pump reports CWU is charged (reached target).

        DHW status contains 'Charged' when pump finished heating.
        """
        if not self._bsb_lan_data:
            return False

        dhw_status = self._bsb_lan_data.get("dhw_status", "")
        return DHW_STATUS_CHARGED in dhw_status.lower()

    def _get_target_temp(self) -> float:
        """Get CWU target temperature (with runtime overrides)."""
        return self.get_config_value(CONF_CWU_TARGET_TEMP, DEFAULT_CWU_TARGET_TEMP)

    def _reset_max_temp_tracking(self) -> None:
        """Reset max temp tracking for new CWU session."""
        self._max_temp_achieved = None
        self._max_temp_at = None
        self._electric_fallback_count = 0
        self._flow_temp_at_max_check = None
        # Reset anti-fighting rolling window history
        self._cwu_temp_history_fighting.clear()
        self._electric_fallback_history.clear()

    async def _switch_to_cwu(self) -> None:
        """Switch to CWU heating mode with proper delays.

        Note: Caller should log the decision with reasoning before calling.
        """
        if self._transition_in_progress:
            _LOGGER.debug("Switch to CWU skipped - transition in progress")
            return

        self._transition_in_progress = True
        try:
            # First turn off floor heating
            await self._async_set_floor_off()
            await asyncio.sleep(60)  # Wait 1 minute for pump to settle

            # Then enable CWU
            await self._async_set_cwu_on()
        finally:
            self._transition_in_progress = False

        # Track session start - get current temp
        cwu_temp = self._get_cwu_temperature()
        if cwu_temp is None:
            cwu_temp = self._last_known_cwu_temp
        self._cwu_session_start_temp = cwu_temp

        # Clear rapid drop history - will start fresh when we stop heating
        self._cwu_temp_history_bsb.clear()

    async def _switch_to_floor(self) -> None:
        """Switch to floor heating mode with proper delays.

        Note: Caller should log the decision with reasoning before calling.
        """
        if self._transition_in_progress:
            _LOGGER.debug("Switch to floor skipped - transition in progress")
            return

        self._transition_in_progress = True
        try:
            # First turn off CWU
            await self._async_set_cwu_off()
            await asyncio.sleep(60)  # Wait 1 minute for pump to settle

            # Then enable floor heating
            await self._async_set_floor_on()

            # Clear CWU session
            self._cwu_session_start_temp = None
        finally:
            self._transition_in_progress = False

    async def _enter_safe_mode(self) -> None:
        """Enter safe mode - use cloud as last resort.

        Called when BSB-LAN has been unavailable for 15 minutes.
        Uses cloud entities to turn on both CWU and floor heating.
        Always sends commands even if devices appear on (cloud state unreliable).
        """
        if self._transition_in_progress:
            _LOGGER.debug("Enter safe mode skipped - transition in progress")
            return

        self._transition_in_progress = True
        try:
            self._control_source = CONTROL_SOURCE_HA_CLOUD

            # Turn on CWU via cloud (always send command)
            await self._async_safe_mode_cwu_on()
            _LOGGER.debug("Safe mode: CWU enabled via cloud, waiting %ds before floor...", SAFE_MODE_DELAY)

            # Wait 2 minutes before enabling floor
            await asyncio.sleep(SAFE_MODE_DELAY)

            # Turn on floor via cloud (always send command)
            await self._async_safe_mode_floor_on()

            self._log_action(
                "Safe mode active",
                "BSB-LAN unavailable, CWU+Floor ON via cloud, heat pump in control"
            )
        finally:
            self._transition_in_progress = False
