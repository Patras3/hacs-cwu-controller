"""Data coordinator for CWU Controller."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.storage import Store
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

_LOGGER = logging.getLogger(__name__)

# Storage configuration
STORAGE_VERSION = 1
STORAGE_KEY = f"{DOMAIN}_energy_data"
ENERGY_SAVE_INTERVAL = 300  # Save every 5 minutes


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

        # History for UI
        self._state_history: list[dict] = []
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

        # Control source tracking (bsb_lan or ha_cloud)
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

        # Rapid drop detection (pobór CWU - kąpiel)
        self._cwu_temp_history_bsb: list[tuple[datetime, float]] = []  # Historia temp BSB 8830

        # HP wait for ready (po fake heating)
        self._hp_waiting_for_ready: bool = False
        self._hp_waiting_since: datetime | None = None

        # Energy tracking (kWh accumulated) - split by tariff type
        # Today's accumulated energy
        self._energy_cwu_cheap_today: float = 0.0
        self._energy_cwu_expensive_today: float = 0.0
        self._energy_floor_cheap_today: float = 0.0
        self._energy_floor_expensive_today: float = 0.0
        # Yesterday's accumulated energy
        self._energy_cwu_cheap_yesterday: float = 0.0
        self._energy_cwu_expensive_yesterday: float = 0.0
        self._energy_floor_cheap_yesterday: float = 0.0
        self._energy_floor_expensive_yesterday: float = 0.0

        # Energy meter tracking state (for delta calculation)
        self._last_meter_reading: float | None = None  # Last energy meter value (kWh)
        self._last_meter_time: datetime | None = None  # When we took the last reading
        self._last_meter_state: str | None = None  # Controller state at last reading
        self._last_meter_tariff_cheap: bool | None = None  # Was it cheap tariff at last reading
        self._meter_tracking_date: datetime | None = None  # Date of current tracking period

        self._last_daily_report_date: datetime | None = None

        # Persistence - data will be loaded async after init
        self._store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._last_energy_save: datetime | None = None
        self._energy_data_loaded: bool = False

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
    def state_history(self) -> list[dict]:
        """Return state history (today + yesterday)."""
        return self._state_history

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
        cwu_total = self._energy_cwu_cheap_today + self._energy_cwu_expensive_today
        floor_total = self._energy_floor_cheap_today + self._energy_floor_expensive_today
        return {
            "cwu": cwu_total,
            "cwu_cheap": self._energy_cwu_cheap_today,
            "cwu_expensive": self._energy_cwu_expensive_today,
            "floor": floor_total,
            "floor_cheap": self._energy_floor_cheap_today,
            "floor_expensive": self._energy_floor_expensive_today,
            "total": cwu_total + floor_total,
            "total_cheap": self._energy_cwu_cheap_today + self._energy_floor_cheap_today,
            "total_expensive": self._energy_cwu_expensive_today + self._energy_floor_expensive_today,
        }

    @property
    def energy_yesterday(self) -> dict[str, float]:
        """Return yesterday's energy consumption in kWh."""
        cwu_total = self._energy_cwu_cheap_yesterday + self._energy_cwu_expensive_yesterday
        floor_total = self._energy_floor_cheap_yesterday + self._energy_floor_expensive_yesterday
        return {
            "cwu": cwu_total,
            "cwu_cheap": self._energy_cwu_cheap_yesterday,
            "cwu_expensive": self._energy_cwu_expensive_yesterday,
            "floor": floor_total,
            "floor_cheap": self._energy_floor_cheap_yesterday,
            "floor_expensive": self._energy_floor_expensive_yesterday,
            "total": cwu_total + floor_total,
            "total_cheap": self._energy_cwu_cheap_yesterday + self._energy_floor_cheap_yesterday,
            "total_expensive": self._energy_cwu_expensive_yesterday + self._energy_floor_expensive_yesterday,
        }

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
        """Return current control source (bsb_lan or ha_cloud)."""
        return self._control_source

    async def async_load_energy_data(self) -> None:
        """Load persisted energy data from storage.

        Handles multiple scenarios:
        1. Same day restart: restore all values including meter tracking state
        2. Day changed since last save: move today's data to yesterday, reset today
        3. Data older than yesterday: start completely fresh
        4. Handle gap energy on restart based on state continuity
        """
        try:
            data = await self._store.async_load()
            if data is None:
                _LOGGER.info("No stored energy data found, starting fresh")
                self._energy_data_loaded = True
                return

            # Get stored date to check for day rollover
            stored_date_str = data.get("date")
            today = datetime.now().date()

            if stored_date_str:
                stored_date = datetime.fromisoformat(stored_date_str).date()

                if stored_date == today:
                    # Same day - restore today's values
                    self._energy_cwu_cheap_today = data.get("cwu_cheap_today", 0.0)
                    self._energy_cwu_expensive_today = data.get("cwu_expensive_today", 0.0)
                    self._energy_floor_cheap_today = data.get("floor_cheap_today", 0.0)
                    self._energy_floor_expensive_today = data.get("floor_expensive_today", 0.0)
                    self._energy_cwu_cheap_yesterday = data.get("cwu_cheap_yesterday", 0.0)
                    self._energy_cwu_expensive_yesterday = data.get("cwu_expensive_yesterday", 0.0)
                    self._energy_floor_cheap_yesterday = data.get("floor_cheap_yesterday", 0.0)
                    self._energy_floor_expensive_yesterday = data.get("floor_expensive_yesterday", 0.0)
                    _LOGGER.info(
                        "Loaded energy data for today: CWU %.2f kWh, Floor %.2f kWh",
                        self.energy_today["cwu"],
                        self.energy_today["floor"]
                    )
                elif stored_date == today - timedelta(days=1):
                    # Stored data is from yesterday - move to yesterday, reset today
                    self._energy_cwu_cheap_yesterday = data.get("cwu_cheap_today", 0.0)
                    self._energy_cwu_expensive_yesterday = data.get("cwu_expensive_today", 0.0)
                    self._energy_floor_cheap_yesterday = data.get("floor_cheap_today", 0.0)
                    self._energy_floor_expensive_yesterday = data.get("floor_expensive_today", 0.0)
                    # Today starts fresh
                    self._energy_cwu_cheap_today = 0.0
                    self._energy_cwu_expensive_today = 0.0
                    self._energy_floor_cheap_today = 0.0
                    self._energy_floor_expensive_today = 0.0
                    _LOGGER.info(
                        "Day changed since last save. Yesterday: CWU %.2f kWh, Floor %.2f kWh",
                        self.energy_yesterday["cwu"],
                        self.energy_yesterday["floor"]
                    )
                else:
                    # Data is older than yesterday - reset everything
                    _LOGGER.info("Stored energy data is too old (%s), starting fresh", stored_date)

            # Restore meter tracking state for gap energy calculation on restart
            # This allows us to attribute energy consumed during shutdown
            last_meter = data.get("last_meter_reading")
            if last_meter is not None:
                self._last_meter_reading = last_meter
            last_meter_time_str = data.get("last_meter_time")
            if last_meter_time_str:
                self._last_meter_time = datetime.fromisoformat(last_meter_time_str)
            self._last_meter_state = data.get("last_meter_state")
            self._last_meter_tariff_cheap = data.get("last_meter_tariff_cheap")
            meter_date_str = data.get("meter_tracking_date")
            if meter_date_str:
                self._meter_tracking_date = datetime.fromisoformat(meter_date_str)

            _LOGGER.debug(
                "Loaded meter tracking state: reading=%.3f, state=%s, cheap=%s",
                self._last_meter_reading or 0,
                self._last_meter_state,
                self._last_meter_tariff_cheap
            )

            # Restore daily report date if available
            report_date_str = data.get("last_daily_report_date")
            if report_date_str:
                self._last_daily_report_date = datetime.fromisoformat(report_date_str)

            self._energy_data_loaded = True

        except Exception as e:
            _LOGGER.error("Failed to load energy data: %s", e)
            self._energy_data_loaded = True  # Mark as loaded to prevent blocking

    async def async_save_energy_data(self) -> None:
        """Save energy data to persistent storage.

        Saves:
        - Accumulated energy by type and tariff
        - Meter tracking state for restart gap calculation
        - Daily report date
        """
        try:
            data = {
                # Date for day rollover detection
                "date": datetime.now().date().isoformat(),
                # Today's accumulated energy (kWh)
                "cwu_cheap_today": self._energy_cwu_cheap_today,
                "cwu_expensive_today": self._energy_cwu_expensive_today,
                "floor_cheap_today": self._energy_floor_cheap_today,
                "floor_expensive_today": self._energy_floor_expensive_today,
                # Yesterday's accumulated energy (kWh)
                "cwu_cheap_yesterday": self._energy_cwu_cheap_yesterday,
                "cwu_expensive_yesterday": self._energy_cwu_expensive_yesterday,
                "floor_cheap_yesterday": self._energy_floor_cheap_yesterday,
                "floor_expensive_yesterday": self._energy_floor_expensive_yesterday,
                # Meter tracking state for restart gap calculation
                "last_meter_reading": self._last_meter_reading,
                "last_meter_time": self._last_meter_time.isoformat() if self._last_meter_time else None,
                "last_meter_state": self._last_meter_state,
                "last_meter_tariff_cheap": self._last_meter_tariff_cheap,
                "meter_tracking_date": self._meter_tracking_date.isoformat() if self._meter_tracking_date else None,
                # Daily report tracking
                "last_daily_report_date": self._last_daily_report_date.isoformat() if self._last_daily_report_date else None,
            }
            await self._store.async_save(data)
            self._last_energy_save = datetime.now()
            _LOGGER.debug(
                "Energy data saved: CWU %.3f kWh, Floor %.3f kWh, Meter %.3f kWh",
                self.energy_today["cwu"],
                self.energy_today["floor"],
                self._last_meter_reading or 0
            )
        except Exception as e:
            _LOGGER.error("Failed to save energy data: %s", e)

    async def _async_save_on_shutdown(self, event) -> None:
        """Save energy data when Home Assistant is stopping."""
        _LOGGER.info("Home Assistant stopping - saving energy data...")
        await self.async_save_energy_data()

    async def _maybe_save_energy_data(self) -> None:
        """Save energy data if enough time has passed since last save."""
        now = datetime.now()
        if self._last_energy_save is None:
            # First save after startup
            await self.async_save_energy_data()
            return

        seconds_since_save = (now - self._last_energy_save).total_seconds()
        if seconds_since_save >= ENERGY_SAVE_INTERVAL:
            await self.async_save_energy_data()

    def get_tariff_cheap_rate(self) -> float:
        """Get configured cheap tariff rate (zł/kWh)."""
        return self.config.get(CONF_TARIFF_CHEAP_RATE, TARIFF_CHEAP_RATE)

    def get_tariff_expensive_rate(self) -> float:
        """Get configured expensive tariff rate (zł/kWh)."""
        return self.config.get(CONF_TARIFF_EXPENSIVE_RATE, TARIFF_EXPENSIVE_RATE)

    def is_cheap_tariff(self, dt: datetime | None = None) -> bool:
        """Check if current time is in cheap tariff window (G12w).

        Uses workday sensor (binary_sensor.workday_sensor from python-holidays).
        If workday sensor is "off", it means today is a weekend or holiday = cheap tariff.
        Requires workday sensor to be configured for holiday detection.
        """
        if dt is None:
            dt = datetime.now()

        # Check workday sensor (required for holiday detection)
        workday_sensor = self.config.get(CONF_WORKDAY_SENSOR)
        if workday_sensor:
            workday_state = self._get_entity_state(workday_sensor)
            if workday_state is not None and workday_state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                # workday_sensor: "on" = workday, "off" = weekend/holiday
                if workday_state == "off":
                    # Not a workday = weekend or holiday = cheap all day
                    return True
                # It's a workday - check time windows below
            # If sensor unavailable, fall back to weekend check only

        # Weekends are always cheap (fallback if workday sensor unavailable)
        if dt.weekday() >= 5:  # Saturday = 5, Sunday = 6
            return True

        # Check time windows (applies to workdays)
        current_hour = dt.hour
        for start_hour, end_hour in TARIFF_CHEAP_WINDOWS:
            if start_hour <= current_hour < end_hour:
                return True

        return False

    def get_current_tariff_rate(self, dt: datetime | None = None) -> float:
        """Get current electricity rate in zł/kWh."""
        if self.is_cheap_tariff(dt):
            return self.get_tariff_cheap_rate()
        return self.get_tariff_expensive_rate()

    def is_winter_cwu_heating_window(self, dt: datetime | None = None) -> bool:
        """Check if current time is in winter mode CWU heating window."""
        if dt is None:
            dt = datetime.now()

        current_hour = dt.hour
        for start_hour, end_hour in WINTER_CWU_HEATING_WINDOWS:
            if start_hour <= current_hour < end_hour:
                return True
        return False

    def get_winter_cwu_target(self) -> float:
        """Get CWU target temperature for winter mode.

        Applies winter offset (+5°C), capped at WINTER_CWU_MAX_TEMP (55°C).
        """
        base_target = self.config.get("cwu_target_temp", DEFAULT_CWU_TARGET_TEMP)
        target = base_target + WINTER_CWU_TARGET_OFFSET
        return min(target, WINTER_CWU_MAX_TEMP)

    def get_winter_cwu_emergency_threshold(self) -> float:
        """Get temperature below which CWU heating is forced outside windows."""
        return self.get_winter_cwu_target() - WINTER_CWU_EMERGENCY_OFFSET

    async def async_set_operating_mode(self, mode: str) -> None:
        """Set operating mode."""
        if mode not in (MODE_BROKEN_HEATER, MODE_WINTER, MODE_SUMMER):
            _LOGGER.warning("Invalid operating mode: %s", mode)
            return

        old_mode = self._operating_mode
        self._operating_mode = mode
        self._log_action(f"Operating mode changed: {old_mode} -> {mode}")

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
            self._log_action(f"Detected CWU heating in progress after restart (temp: {cwu_temp}°C)")
            _LOGGER.info("CWU Controller: Detected active CWU heating, resuming tracking")

        elif floor_active:
            self._current_state = STATE_HEATING_FLOOR
            self._log_action("Detected floor heating in progress after restart")
            _LOGGER.info("CWU Controller: Detected active floor heating")

        else:
            self._current_state = STATE_IDLE
            self._log_action("Started in idle state after restart")
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
            self._log_action("Safe mode: CWU ON (cloud)")
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
            self._log_action("Safe mode: Floor ON (cloud)")
            return True
        except Exception as e:
            _LOGGER.error("Safe mode Floor ON failed: %s", e)
            return False

    # -------------------------------------------------------------------------
    # Control methods - BSB-LAN only (no fallback in normal operation)
    # -------------------------------------------------------------------------

    async def _async_set_cwu_on(self) -> bool:
        """Turn CWU heating on via BSB-LAN."""
        if not self._bsb_client.is_available:
            _LOGGER.warning("BSB-LAN unavailable - CWU ON skipped")
            return False

        success = await self._bsb_client.async_set_cwu_mode(BSB_CWU_MODE_ON)
        if success:
            self._control_source = CONTROL_SOURCE_BSB_LAN
            self._log_action("CWU ON")
        else:
            _LOGGER.error("BSB-LAN CWU ON failed")
        return success

    async def _async_set_cwu_off(self) -> bool:
        """Turn CWU heating off via BSB-LAN."""
        if not self._bsb_client.is_available:
            _LOGGER.warning("BSB-LAN unavailable - CWU OFF skipped")
            return False

        success = await self._bsb_client.async_set_cwu_mode(BSB_CWU_MODE_OFF)
        if success:
            self._control_source = CONTROL_SOURCE_BSB_LAN
            self._log_action("CWU OFF")
        else:
            _LOGGER.error("BSB-LAN CWU OFF failed")
        return success

    async def _async_set_floor_on(self) -> bool:
        """Turn floor heating on via BSB-LAN."""
        if not self._bsb_client.is_available:
            _LOGGER.warning("BSB-LAN unavailable - Floor ON skipped")
            return False

        success = await self._bsb_client.async_set_floor_mode(BSB_FLOOR_MODE_AUTOMATIC)
        if success:
            self._control_source = CONTROL_SOURCE_BSB_LAN
            self._log_action("Floor ON")
        else:
            _LOGGER.error("BSB-LAN Floor ON failed")
        return success

    async def _async_set_floor_off(self) -> bool:
        """Turn floor heating off via BSB-LAN."""
        if not self._bsb_client.is_available:
            _LOGGER.warning("BSB-LAN unavailable - Floor OFF skipped")
            return False

        success = await self._bsb_client.async_set_floor_mode(BSB_FLOOR_MODE_PROTECTION)
        if success:
            self._control_source = CONTROL_SOURCE_BSB_LAN
            self._log_action("Floor OFF")
        else:
            _LOGGER.error("BSB-LAN Floor OFF failed")
        return success

    # -------------------------------------------------------------------------
    # BSB-LAN data fetching and temperature methods
    # -------------------------------------------------------------------------

    async def _async_refresh_bsb_lan_data(self) -> None:
        """Refresh BSB-LAN data for control decisions and sensors."""
        raw_data = await self._bsb_client.async_read_parameters()
        if not raw_data:
            self._bsb_lan_data = {}
            return

        self._bsb_lan_data = {
            "floor_mode": raw_data.get("700", {}).get("desc", "---"),
            "cwu_mode": raw_data.get("1600", {}).get("desc", "---"),
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
        """Get CWU temperature from BSB-LAN exclusively.

        BSB-LAN parameter 8830 is the only source.
        Returns None if BSB-LAN unavailable - triggers safe mode after timeout.
        """
        if self._bsb_lan_data:
            return self._bsb_lan_data.get("cwu_temp")
        return None

    def _detect_fake_heating_bsb(self) -> bool:
        """Detect fake heating using BSB-LAN status (more accurate).

        Fake heating detected when:
        1. DHW status shows "Charging electric" = broken heater scenario
        2. DHW status shows "Charging" but compressor not running for 5+ minutes
           EXCEPT when compressor is in mandatory off time ("off time min active")
        """
        if not self._bsb_lan_data:
            return False

        dhw_status = self._bsb_lan_data.get("dhw_status", "")
        hp_status = self._bsb_lan_data.get("hp_status", "")

        # Immediate detection: electric heater is charging (broken heater mode)
        if BSB_DHW_STATUS_CHARGING_ELECTRIC.lower() in dhw_status.lower():
            self._log_action("BSB-LAN: Detected electric heater charging (broken heater)")
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
                    self._log_action("BSB-LAN: Compressor in mandatory off time - not fake heating")
                self._bsb_dhw_charging_no_compressor_since = None
                return False

            # Start tracking
            if self._bsb_dhw_charging_no_compressor_since is None:
                self._bsb_dhw_charging_no_compressor_since = datetime.now()

            # Check if threshold reached
            elapsed = (datetime.now() - self._bsb_dhw_charging_no_compressor_since).total_seconds() / 60
            if elapsed >= BSB_FAKE_HEATING_DETECTION_TIME:
                self._log_action(f"BSB-LAN: DHW charging but no compressor for {elapsed:.1f} min")
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
                    self._log_action("State verify: Fixed CWU → ON")
                else:
                    await self._async_set_cwu_off()
                    self._log_action("State verify: Fixed CWU → OFF")

            if floor_mismatch:
                if expected_floor_on:
                    await self._async_set_floor_on()
                    self._log_action("State verify: Fixed Floor → ON")
                else:
                    await self._async_set_floor_off()
                    self._log_action("State verify: Fixed Floor → OFF")

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

        self._state_history = [e for e in self._state_history if is_recent(e)]
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

            entry = {
                "timestamp": datetime.now().isoformat(),
                "from_state": self._previous_state,
                "to_state": new_state,
            }
            self._state_history.append(entry)
            self._cleanup_old_history()
            _LOGGER.info("CWU Controller state: %s -> %s", self._previous_state, new_state)

    def _get_energy_meter_value(self) -> float | None:
        """Get current value from energy meter sensor (kWh)."""
        energy_sensor = self.config.get(CONF_ENERGY_SENSOR, DEFAULT_ENERGY_SENSOR)
        return self._get_sensor_value(energy_sensor)

    def _is_heating_state(self, state: str | None) -> bool:
        """Check if given state is an active heating state."""
        if state is None:
            return False
        return state in (
            STATE_HEATING_CWU, STATE_EMERGENCY_CWU,
            STATE_FAKE_HEATING_DETECTED, STATE_FAKE_HEATING_RESTARTING,
            STATE_HEATING_FLOOR, STATE_EMERGENCY_FLOOR,
            STATE_SAFE_MODE  # Safe mode also heats
        )

    def _is_cwu_state(self, state: str | None) -> bool:
        """Check if given state is a CWU heating state."""
        if state is None:
            return False
        return state in (
            STATE_HEATING_CWU, STATE_EMERGENCY_CWU,
            STATE_FAKE_HEATING_DETECTED, STATE_FAKE_HEATING_RESTARTING
        )

    def _is_floor_state(self, state: str | None) -> bool:
        """Check if given state is a floor heating state."""
        if state is None:
            return False
        return state in (STATE_HEATING_FLOOR, STATE_EMERGENCY_FLOOR)

    def _attribute_energy(self, kwh: float, state: str, is_cheap: bool) -> None:
        """Attribute energy consumption to the appropriate counter.

        Args:
            kwh: Energy in kWh to attribute
            state: Controller state that consumed this energy
            is_cheap: Whether this was during cheap tariff
        """
        if kwh <= 0:
            return

        if self._is_cwu_state(state):
            if is_cheap:
                self._energy_cwu_cheap_today += kwh
            else:
                self._energy_cwu_expensive_today += kwh
            _LOGGER.debug(
                "Attributed %.4f kWh to CWU (%s tariff)",
                kwh, "cheap" if is_cheap else "expensive"
            )
        elif self._is_floor_state(state):
            if is_cheap:
                self._energy_floor_cheap_today += kwh
            else:
                self._energy_floor_expensive_today += kwh
            _LOGGER.debug(
                "Attributed %.4f kWh to Floor (%s tariff)",
                kwh, "cheap" if is_cheap else "expensive"
            )
        elif state == STATE_SAFE_MODE:
            # Safe mode - split 50/50 between CWU and floor (both are on)
            half_kwh = kwh / 2
            if is_cheap:
                self._energy_cwu_cheap_today += half_kwh
                self._energy_floor_cheap_today += half_kwh
            else:
                self._energy_cwu_expensive_today += half_kwh
                self._energy_floor_expensive_today += half_kwh
            _LOGGER.debug(
                "Attributed %.4f kWh to Safe Mode (50/50 split, %s tariff)",
                kwh, "cheap" if is_cheap else "expensive"
            )

    def _handle_day_rollover(self, now: datetime) -> bool:
        """Handle day rollover for energy tracking.

        Returns True if day rollover occurred.
        """
        if self._meter_tracking_date is None:
            self._meter_tracking_date = now
            return False

        if now.date() != self._meter_tracking_date.date():
            # New day - move today's stats to yesterday and reset
            self._energy_cwu_cheap_yesterday = self._energy_cwu_cheap_today
            self._energy_cwu_expensive_yesterday = self._energy_cwu_expensive_today
            self._energy_floor_cheap_yesterday = self._energy_floor_cheap_today
            self._energy_floor_expensive_yesterday = self._energy_floor_expensive_today
            self._energy_cwu_cheap_today = 0.0
            self._energy_cwu_expensive_today = 0.0
            self._energy_floor_cheap_today = 0.0
            self._energy_floor_expensive_today = 0.0

            _LOGGER.info(
                "Energy tracking day rollover - Yesterday CWU: %.2f kWh, Floor: %.2f kWh",
                self.energy_yesterday["cwu"],
                self.energy_yesterday["floor"]
            )
            # Force immediate save after day rollover
            self._last_energy_save = None
            self._meter_tracking_date = now
            return True

        return False

    def _update_energy_tracking(self) -> None:
        """Update energy consumption tracking using energy meter delta.

        Uses the total energy meter sensor to calculate actual consumption.
        This is more accurate than integrating power readings because:
        1. Energy meter is already integrated by the device
        2. No accumulation of rounding errors
        3. Works even if some updates are missed

        Tracks energy separately for:
        - CWU cheap/expensive tariff
        - Floor cheap/expensive tariff

        Handles:
        - Day rollover (midnight)
        - State changes (only attribute when state is consistent)
        - Restart gaps (attribute if state matches)
        - Meter resets/anomalies (detect and skip)

        Called every UPDATE_INTERVAL (60 seconds) by the coordinator.
        """
        # Safety check: don't track energy until persisted data is loaded
        # This prevents double-counting if _async_update_data runs before load completes
        if not self._energy_data_loaded:
            _LOGGER.debug("Energy tracking skipped - waiting for persisted data to load")
            return

        now = datetime.now()

        # Handle day rollover
        self._handle_day_rollover(now)

        # Get current energy meter reading
        current_meter = self._get_energy_meter_value()
        if current_meter is None:
            _LOGGER.debug("Energy meter unavailable, skipping tracking")
            return

        # Determine current tariff
        is_cheap = self.is_cheap_tariff(now)
        current_state = self._current_state

        # First reading ever - just store and return
        if self._last_meter_reading is None:
            self._last_meter_reading = current_meter
            self._last_meter_time = now
            self._last_meter_state = current_state
            self._last_meter_tariff_cheap = is_cheap
            _LOGGER.info(
                "Energy meter tracking initialized: %.3f kWh, state=%s",
                current_meter, current_state
            )
            return

        # Calculate delta since last reading
        delta_kwh = current_meter - self._last_meter_reading

        # Sanity checks
        if delta_kwh < 0:
            # Meter went backwards - possible reset or sensor error
            _LOGGER.warning(
                "Energy meter went backwards (%.3f -> %.3f), resetting tracking",
                self._last_meter_reading, current_meter
            )
            self._last_meter_reading = current_meter
            self._last_meter_time = now
            self._last_meter_state = current_state
            self._last_meter_tariff_cheap = is_cheap
            return

        if delta_kwh > ENERGY_DELTA_ANOMALY_THRESHOLD:
            time_diff = (now - self._last_meter_time).total_seconds() / 3600 if self._last_meter_time else 0
            _LOGGER.warning(
                "Unusually large energy delta: %.3f kWh in %.2f hours (threshold: %.1f kWh). "
                "This might indicate a meter issue or long gap. Skipping attribution.",
                delta_kwh, time_diff, ENERGY_DELTA_ANOMALY_THRESHOLD
            )
            self._last_meter_reading = current_meter
            self._last_meter_time = now
            self._last_meter_state = current_state
            self._last_meter_tariff_cheap = is_cheap
            return

        # Attribute energy based on state consistency
        if delta_kwh > 0:
            # Check if state is consistent (same as last reading)
            if self._is_heating_state(current_state):
                if current_state == self._last_meter_state:
                    # State is consistent - attribute all delta to this state
                    # Use current tariff for attribution (more accurate than averaging)
                    self._attribute_energy(delta_kwh, current_state, is_cheap)
                elif self._last_meter_state is None:
                    # First attribution after startup - use current state
                    self._attribute_energy(delta_kwh, current_state, is_cheap)
                else:
                    # State changed since last reading
                    # We could try to split, but for simplicity we attribute to current state
                    # since most energy is typically consumed at the end of heating
                    _LOGGER.debug(
                        "State changed (%s -> %s) during tracking interval, "
                        "attributing %.4f kWh to current state",
                        self._last_meter_state, current_state, delta_kwh
                    )
                    self._attribute_energy(delta_kwh, current_state, is_cheap)
            else:
                # Not in heating state - check if we were heating before
                if self._is_heating_state(self._last_meter_state):
                    # Just stopped heating - attribute remaining delta to previous state
                    # Use previous tariff since energy was consumed then
                    prev_cheap = self._last_meter_tariff_cheap if self._last_meter_tariff_cheap is not None else is_cheap
                    _LOGGER.debug(
                        "Heating stopped, attributing final %.4f kWh to %s",
                        delta_kwh, self._last_meter_state
                    )
                    self._attribute_energy(delta_kwh, self._last_meter_state, prev_cheap)
                else:
                    # Idle delta - this is standby power, don't attribute to heating
                    _LOGGER.debug(
                        "Idle energy delta: %.4f kWh (standby power, not attributed)",
                        delta_kwh
                    )

        # Update tracking state
        self._last_meter_reading = current_meter
        self._last_meter_time = now
        self._last_meter_state = current_state
        self._last_meter_tariff_cheap = is_cheap

    async def _check_and_send_daily_report(self) -> None:
        """Check if it's time to send daily report and send it."""
        now = datetime.now()

        # Send report between 00:05 and 00:15
        if not (now.hour == 0 and 5 <= now.minute <= 15):
            return

        # Check if we already sent report today
        if self._last_daily_report_date is not None:
            if self._last_daily_report_date.date() == now.date():
                return

        # Get yesterday's energy data (already in kWh from property)
        energy = self.energy_yesterday
        cwu_kwh = energy["cwu"]
        floor_kwh = energy["floor"]
        total_kwh = energy["total"]

        if total_kwh < 0.1:
            # Don't send report if essentially no consumption
            self._last_daily_report_date = now
            return

        # Calculate accurate costs based on tariff split (using configurable rates)
        cheap_rate = self.get_tariff_cheap_rate()
        expensive_rate = self.get_tariff_expensive_rate()

        cwu_cost = (energy["cwu_cheap"] * cheap_rate +
                    energy["cwu_expensive"] * expensive_rate)
        floor_cost = (energy["floor_cheap"] * cheap_rate +
                      energy["floor_expensive"] * expensive_rate)
        total_cost = cwu_cost + floor_cost

        # Calculate savings vs all-expensive rate
        total_if_expensive = total_kwh * expensive_rate
        savings = total_if_expensive - total_cost

        message = (
            f"📊 Daily Energy Report (yesterday)\n\n"
            f"🚿 CWU: {cwu_kwh:.2f} kWh ({cwu_cost:.2f} zł)\n"
            f"   ├ Cheap: {energy['cwu_cheap']:.2f} kWh\n"
            f"   └ Expensive: {energy['cwu_expensive']:.2f} kWh\n\n"
            f"🏠 Floor: {floor_kwh:.2f} kWh ({floor_cost:.2f} zł)\n"
            f"   ├ Cheap: {energy['floor_cheap']:.2f} kWh\n"
            f"   └ Expensive: {energy['floor_expensive']:.2f} kWh\n\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📈 Total: {total_kwh:.2f} kWh ({total_cost:.2f} zł)\n"
            f"💰 Saved: {savings:.2f} zł vs expensive rate\n\n"
            f"💡 Mode: {self._operating_mode.replace('_', ' ').title()}"
        )

        await self._async_send_notification("CWU Controller Daily Report", message)
        self._last_daily_report_date = now
        _LOGGER.info("Daily energy report sent: CWU %.2f kWh, Floor %.2f kWh, Cost %.2f zł",
                     cwu_kwh, floor_kwh, total_cost)

    async def async_enable(self) -> None:
        """Enable the controller."""
        self._enabled = True
        self._manual_override = False
        self._log_action("Controller enabled")

    async def async_disable(self) -> None:
        """Disable the controller and enter safe mode (heat pump takes control)."""
        self._enabled = False
        self._log_action("Controller disabled - entering safe mode")

        # Enter safe mode - turn on both floor and CWU, let heat pump decide
        await self._async_set_floor_on()
        self._log_action("Floor heating enabled, waiting 60s...")
        await asyncio.sleep(60)
        await self._async_set_cwu_on()
        self._log_action("Safe mode active - heat pump in control")

    async def async_force_cwu(self, duration_minutes: int = 60) -> None:
        """Force CWU heating for specified duration."""
        self._manual_override = True
        self._manual_override_until = datetime.now() + timedelta(minutes=duration_minutes)

        # First turn off everything with delays between commands
        self._log_action("Force CWU: Stopping CWU...")
        await self._async_set_cwu_off()
        self._log_action("Waiting 30s...")
        await asyncio.sleep(30)

        self._log_action("Force CWU: Stopping floor heating...")
        await self._async_set_floor_off()

        # Wait for pump to settle
        self._log_action("Waiting 60s for pump to settle...")
        await asyncio.sleep(60)

        # Now enable CWU
        await self._async_set_cwu_on()

        self._change_state(STATE_HEATING_CWU)
        self._cwu_heating_start = datetime.now()
        # Set session start temp for UI tracking (BSB-LAN preferred)
        cwu_temp = self._get_cwu_temperature()
        self._cwu_session_start_temp = cwu_temp if cwu_temp is not None else self._last_known_cwu_temp
        self._log_action(f"Force CWU for {duration_minutes} minutes")

    async def async_force_floor(self, duration_minutes: int = 60) -> None:
        """Force floor heating for specified duration."""
        self._manual_override = True
        self._manual_override_until = datetime.now() + timedelta(minutes=duration_minutes)

        # First turn off everything with delays between commands
        self._log_action("Force Floor: Stopping CWU...")
        await self._async_set_cwu_off()
        self._log_action("Waiting 30s...")
        await asyncio.sleep(30)

        self._log_action("Force Floor: Stopping floor heating...")
        await self._async_set_floor_off()

        # Wait for pump to settle
        self._log_action("Waiting 60s for pump to settle...")
        await asyncio.sleep(60)

        # Now enable floor heating
        await self._async_set_floor_on()

        self._change_state(STATE_HEATING_FLOOR)
        self._log_action(f"Force floor heating for {duration_minutes} minutes")

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
        """Test action: turn on CWU via BSB-LAN."""
        success = await self._async_set_cwu_on()
        status = "CWU turned ON via BSB-LAN" if success else "CWU ON failed (BSB-LAN unavailable)"
        await self._async_send_notification("CWU Controller Test", status)

    async def async_test_cwu_off(self) -> None:
        """Test action: turn off CWU via BSB-LAN."""
        success = await self._async_set_cwu_off()
        status = "CWU turned OFF via BSB-LAN" if success else "CWU OFF failed (BSB-LAN unavailable)"
        await self._async_send_notification("CWU Controller Test", status)

    async def async_test_floor_on(self) -> None:
        """Test action: turn on floor heating via BSB-LAN."""
        success = await self._async_set_floor_on()
        status = "Floor heating turned ON via BSB-LAN" if success else "Floor ON failed (BSB-LAN unavailable)"
        await self._async_send_notification("CWU Controller Test", status)

    async def async_test_floor_off(self) -> None:
        """Test action: turn off floor heating via BSB-LAN."""
        success = await self._async_set_floor_off()
        status = "Floor heating turned OFF via BSB-LAN" if success else "Floor OFF failed (BSB-LAN unavailable)"
        await self._async_send_notification("CWU Controller Test", status)

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

        # Fetch BSB-LAN data first (primary data source)
        await self._async_refresh_bsb_lan_data()

        # Get CWU temperature (BSB-LAN only)
        cwu_temp = self._get_cwu_temperature()

        # Get other sensor values
        salon_temp = self._get_sensor_value(self.config.get("salon_temp_sensor"))
        bedroom_temp = self._get_sensor_value(self.config.get("bedroom_temp_sensor"))
        kids_temp = self._get_sensor_value(self.config.get("kids_room_temp_sensor"))
        power = self._get_sensor_value(self.config.get("power_sensor"))
        pump_input = self._get_sensor_value(self.config.get("pump_input_temp"))
        pump_output = self._get_sensor_value(self.config.get("pump_output_temp"))

        # Get CWU and floor modes from BSB-LAN (primary source)
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
        # Use BSB-LAN detection (more accurate) with power-based fallback
        fake_heating = False
        if self._operating_mode == MODE_BROKEN_HEATER:
            if self._bsb_lan_data:
                fake_heating = self._detect_fake_heating_bsb()
            else:
                # Fallback to power-based detection
                fake_heating = self._detect_fake_heating(power, wh_state)

        # Update energy tracking
        self._update_energy_tracking()

        # Periodically save energy data (every 5 minutes)
        await self._maybe_save_energy_data()

        # Check for daily report
        await self._check_and_send_daily_report()

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
            "state_history": self._state_history[-20:],
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
                self._log_action("Manual override expired")

        # Handle fake heating even in manual CWU mode
        # (don't switch to floor, just restart CWU after wait period)
        if self._manual_override and self._current_state == STATE_HEATING_CWU:
            if fake_heating:
                self._change_state(STATE_FAKE_HEATING_DETECTED)
                self._fake_heating_detected_at = datetime.now()
                # Stop all heating
                await self._async_set_cwu_off()
                await self._async_set_floor_off()
                await self._async_send_notification(
                    "CWU Controller Alert (Manual Mode)",
                    f"Fake heating detected! Pump trying electric heater (broken). "
                    f"CWU temp: {cwu_temp}°C. Waiting {HP_RESTART_MIN_WAIT}+ min for HP ready..."
                )
                self._log_action(f"Manual mode: Fake heating detected - all OFF, waiting {HP_RESTART_MIN_WAIT}+ min")

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
                        self._log_action(f"Manual mode: Waiting for HP ready - {hp_reason}")
                    return data  # Keep waiting

                # HP ready - restart CWU
                await self._async_set_cwu_on()
                self._fake_heating_detected_at = None
                self._change_state(STATE_HEATING_CWU)
                self._cwu_heating_start = now  # Reset heating start for next detection
                self._last_mode_switch = now  # For anti-oscillation
                self._reset_max_temp_tracking()  # Reset max temp for new session
                self._log_action(f"Manual mode: HP ready - CWU restarted after {elapsed:.1f} min wait")

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
                self._log_action("BSB-LAN recovered - exiting safe mode")
                await self._async_send_notification(
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

        # Check if we need to enter safe mode due to BSB-LAN unavailability
        if not self._bsb_client.is_available:
            if self._bsb_lan_unavailable_since is None:
                self._bsb_lan_unavailable_since = datetime.now()
                _LOGGER.warning("BSB-LAN became unavailable - starting safe mode countdown")
            else:
                unavailable_minutes = (datetime.now() - self._bsb_lan_unavailable_since).total_seconds() / 60
                if unavailable_minutes >= BSB_LAN_UNAVAILABLE_TIMEOUT:
                    self._log_action(
                        f"BSB-LAN unavailable for {unavailable_minutes:.0f} minutes - entering safe mode"
                    )
                    await self._async_send_notification(
                        "CWU Controller - Safe Mode",
                        f"BSB-LAN has been unavailable for {unavailable_minutes:.0f} minutes.\n\n"
                        f"Entering safe mode - using cloud control as backup.\n"
                        f"CWU and floor heating will be turned on via cloud.\n"
                        f"Normal BSB-LAN control will resume when connection recovers."
                    )
                    await self._enter_safe_mode()
                    self._change_state(STATE_SAFE_MODE)
                    return
        else:
            # BSB-LAN is available, clear the unavailable timestamp
            if self._bsb_lan_unavailable_since is not None:
                self._log_action("BSB-LAN connection restored")
                self._bsb_lan_unavailable_since = None
                self._control_source = CONTROL_SOURCE_BSB_LAN

        # Route based on operating mode
        if self._operating_mode == MODE_WINTER:
            await self._run_winter_mode_logic(cwu_urgency, floor_urgency, cwu_temp, salon_temp)
            return
        elif self._operating_mode == MODE_SUMMER:
            # Summer mode not implemented yet
            self._log_action("Summer mode not implemented - using floor heating")
            if self._current_state != STATE_HEATING_FLOOR:
                await self._switch_to_floor()
                self._change_state(STATE_HEATING_FLOOR)
            return

        # Default: Broken heater mode (original logic)
        await self._run_broken_heater_mode_logic(
            cwu_urgency, floor_urgency, fake_heating, cwu_temp, salon_temp
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

        Criteria:
        1. Flow temp (8412) not rising significantly for 30 min
        2. Pump tried electric heater 2+ times (Charging electric)
        3. Remember this temp as max

        Returns True if max temp detected (should switch to floor).
        """
        if not self._bsb_lan_data:
            return False

        flow_temp = self._bsb_lan_data.get("flow_temp")
        dhw_status = self._bsb_lan_data.get("dhw_status", "")
        cwu_temp = self._bsb_lan_data.get("cwu_temp")

        # Count "Charging electric" occurrences
        if "electric" in dhw_status.lower():
            self._electric_fallback_count += 1
            _LOGGER.debug(f"Electric fallback count: {self._electric_fallback_count}")

        # Initialize flow temp tracking
        if self._flow_temp_at_max_check is None:
            self._flow_temp_at_max_check = flow_temp
            self._max_temp_at = datetime.now()
            return False

        if flow_temp is None or self._flow_temp_at_max_check is None:
            return False

        flow_rise = flow_temp - self._flow_temp_at_max_check
        elapsed = (datetime.now() - self._max_temp_at).total_seconds() / 60 if self._max_temp_at else 0

        if elapsed >= MAX_TEMP_DETECTION_WINDOW:
            # Check if flow stagnated AND electric fallback happened
            if flow_rise < MAX_TEMP_FLOW_STAGNATION and self._electric_fallback_count >= MAX_TEMP_ELECTRIC_FALLBACK_COUNT:
                # Max reached
                self._max_temp_achieved = cwu_temp
                self._log_action(
                    f"Max temp detected: {cwu_temp}°C (flow stagnant +{flow_rise:.1f}°C, electric x{self._electric_fallback_count})"
                )
                return True

            # Reset for next window
            self._flow_temp_at_max_check = flow_temp
            self._max_temp_at = datetime.now()
            self._electric_fallback_count = 0

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

        # No max recorded - use standard target (already BSB-adjusted)
        target = self._get_target_temp()
        return cwu_temp >= target - 3.0  # 3°C margin

    def _detect_rapid_drop(self) -> tuple[bool, float]:
        """Detect rapid CWU temperature drop (hot water usage / bath).

        Uses BSB 8830 (bottom of tank) for fast detection.

        Returns:
            Tuple of (drop_detected: bool, drop_amount: float)
        """
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

    # =========================================================================
    # BROKEN HEATER MODE - Main Logic (Refactored)
    # =========================================================================

    async def _run_broken_heater_mode_logic(
        self,
        cwu_urgency: int,
        floor_urgency: int,
        fake_heating: bool,
        cwu_temp: float | None,
        salon_temp: float | None,
    ) -> None:
        """Run control logic for broken heater mode (refactored).

        Strategy:
        - CWU priority almost all day (except 03:00-06:00)
        - Night window 03:00-06:00: floor if CWU is OK
        - Respect HP states (Compressor off time, Defrosting, Overrun)
        - Anti-oscillation via minimum hold times
        - Max temp detection - give pump a break when it can't heat more
        - Rapid CWU drop detection - interrupt floor for hot water emergency
        """
        now = datetime.now()
        current_hour = now.hour

        # =====================================================================
        # Phase 1: Handle fake heating detection (first detection)
        # =====================================================================
        if fake_heating and self._current_state in (STATE_HEATING_CWU, STATE_EMERGENCY_CWU):
            self._change_state(STATE_FAKE_HEATING_DETECTED)
            self._fake_heating_detected_at = now
            self._low_power_start = None  # Reset to prevent duplicate detection
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
        if self._current_state == STATE_FAKE_HEATING_DETECTED and self._fake_heating_detected_at:
            elapsed = (now - self._fake_heating_detected_at).total_seconds() / 60

            # Wait minimum time
            if elapsed < HP_RESTART_MIN_WAIT:
                return

            # Check HP status before restarting
            hp_ready, hp_reason = self._is_hp_ready_for_cwu()
            if not hp_ready:
                # Log only every 2 minutes to avoid spam
                if int(elapsed) % 2 == 0:
                    self._log_action(f"Fake heating recovery waiting: {hp_reason}")
                return

            # HP ready - restart CWU
            self._change_state(STATE_FAKE_HEATING_RESTARTING)
            self._log_action("HP ready - restarting CWU after fake heating")
            await self._async_set_floor_off()
            await self._async_set_cwu_on()
            self._low_power_start = None
            self._fake_heating_detected_at = None
            self._change_state(STATE_HEATING_CWU)
            self._cwu_heating_start = now
            self._last_mode_switch = now
            self._reset_max_temp_tracking()
            # Set session start temp
            cwu_start_temp = self._get_cwu_temperature()
            self._cwu_session_start_temp = cwu_start_temp if cwu_start_temp else self._last_known_cwu_temp
            self._log_action(f"CWU restarted after fake heating (temp: {self._cwu_session_start_temp}°C)")
            return

        # =====================================================================
        # Phase 3: Handle pause state (3h limit)
        # =====================================================================
        if self._current_state == STATE_PAUSE:
            if self._is_pause_complete():
                self._pause_start = None
                # Resume CWU heating - start new session
                await self._async_set_cwu_on()
                self._change_state(STATE_HEATING_CWU)
                self._cwu_heating_start = now
                self._last_mode_switch = now
                self._reset_max_temp_tracking()
                cwu_start_temp = self._get_cwu_temperature()
                if cwu_start_temp is None:
                    cwu_start_temp = self._last_known_cwu_temp
                self._cwu_session_start_temp = cwu_start_temp
                self._log_action(f"Pause complete, starting new CWU session (temp: {cwu_start_temp}°C)")
            return

        # =====================================================================
        # Phase 4: Check 3-hour CWU limit
        # =====================================================================
        if self._current_state == STATE_HEATING_CWU and self._should_restart_cwu_cycle():
            self._change_state(STATE_PAUSE)
            self._pause_start = now
            self._cwu_heating_start = None
            await self._async_set_cwu_off()
            await self._async_set_floor_off()
            self._log_action(f"CWU cycle limit reached, pausing for {CWU_PAUSE_TIME} minutes")
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
            can_switch, reason = self._can_switch_mode(STATE_HEATING_FLOOR, STATE_EMERGENCY_CWU)
            if can_switch:
                self._log_action(f"Rapid CWU drop {drop_amount:.1f}°C - emergency switch to CWU")
                await self._switch_to_cwu()
                self._change_state(STATE_EMERGENCY_CWU)
                self._cwu_heating_start = now
                self._last_mode_switch = now
                self._reset_max_temp_tracking()
                await self._async_send_notification(
                    "CWU Drop Detected",
                    f"Hot water usage detected ({drop_amount:.1f}°C drop in {CWU_RAPID_DROP_WINDOW}min). "
                    f"Starting emergency CWU heating."
                )
            else:
                self._log_action(f"Rapid drop detected but switch blocked: {reason}")
            return

        # =====================================================================
        # Phase 6: Max temp detection (pump can't heat more)
        # =====================================================================
        if self._current_state in (STATE_HEATING_CWU, STATE_EMERGENCY_CWU):
            if self._detect_max_temp_achieved():
                can_switch, reason = self._can_switch_mode(self._current_state, STATE_HEATING_FLOOR)
                if can_switch:
                    self._log_action(f"Max temp {self._max_temp_achieved}°C reached - switching to floor")
                    await self._switch_to_floor()
                    self._change_state(STATE_HEATING_FLOOR)
                    self._cwu_heating_start = None
                    self._last_mode_switch = now
                    await self._async_send_notification(
                        "CWU Max Temp Reached",
                        f"Pump reached maximum achievable temp: {self._max_temp_achieved}°C. "
                        f"Switching to floor heating."
                    )
                else:
                    self._log_action(f"Max temp reached but switch blocked: {reason}")
                return

        # =====================================================================
        # Phase 7: Night window 03:00-06:00 - floor if CWU OK
        # =====================================================================
        if BROKEN_HEATER_FLOOR_WINDOW_START <= current_hour < BROKEN_HEATER_FLOOR_WINDOW_END:
            if self._is_cwu_temp_acceptable(cwu_temp) and cwu_urgency < URGENCY_CRITICAL:
                if self._current_state != STATE_HEATING_FLOOR:
                    can_switch, reason = self._can_switch_mode(self._current_state, STATE_HEATING_FLOOR)
                    if can_switch:
                        self._log_action(f"Night window: CWU OK ({cwu_temp}°C), switching to floor")
                        await self._switch_to_floor()
                        self._change_state(STATE_HEATING_FLOOR)
                        self._cwu_heating_start = None
                        self._last_mode_switch = now
                    else:
                        _LOGGER.debug(f"Night window floor switch blocked: {reason}")
                return
            # CWU not acceptable in night window - continue to normal logic

        # =====================================================================
        # Phase 8: Emergency handling (critical urgencies)
        # =====================================================================
        if cwu_urgency == URGENCY_CRITICAL and floor_urgency != URGENCY_CRITICAL:
            if self._current_state != STATE_EMERGENCY_CWU:
                can_switch, reason = self._can_switch_mode(self._current_state, STATE_EMERGENCY_CWU)
                if can_switch:
                    await self._switch_to_cwu()
                    self._change_state(STATE_EMERGENCY_CWU)
                    self._cwu_heating_start = now
                    self._last_mode_switch = now
                    self._reset_max_temp_tracking()
                    await self._async_send_notification(
                        "CWU Emergency!",
                        f"CWU critically low: {cwu_temp}°C! Switching to emergency CWU heating."
                    )
                else:
                    self._log_action(f"CWU emergency delayed: {reason}")
            return

        if floor_urgency == URGENCY_CRITICAL and cwu_urgency != URGENCY_CRITICAL:
            if self._current_state != STATE_EMERGENCY_FLOOR:
                can_switch, reason = self._can_switch_mode(self._current_state, STATE_EMERGENCY_FLOOR)
                if can_switch:
                    await self._switch_to_floor()
                    self._change_state(STATE_EMERGENCY_FLOOR)
                    self._cwu_heating_start = None
                    self._last_mode_switch = now
                    await self._async_send_notification(
                        "Floor Emergency!",
                        f"Room too cold: Salon {salon_temp}°C! Switching to floor heating."
                    )
                else:
                    self._log_action(f"Floor emergency delayed: {reason}")
            return

        # Both critical - alternate every 45 minutes (longer than before)
        if cwu_urgency == URGENCY_CRITICAL and floor_urgency == URGENCY_CRITICAL:
            minutes_in_state = (now - self._last_state_change).total_seconds() / 60
            if minutes_in_state >= 45:
                if self._current_state in (STATE_HEATING_CWU, STATE_EMERGENCY_CWU):
                    await self._switch_to_floor()
                    self._change_state(STATE_EMERGENCY_FLOOR)
                    self._last_mode_switch = now
                else:
                    await self._switch_to_cwu()
                    self._change_state(STATE_EMERGENCY_CWU)
                    self._cwu_heating_start = now
                    self._last_mode_switch = now
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

            if cwu_temp is not None and cwu_temp < target - 3.0:
                should_resume = True
                resume_reason = f"temp {cwu_temp}°C < target-3 ({target - 3.0}°C)"
            elif cwu_urgency >= URGENCY_HIGH:
                should_resume = True
                resume_reason = f"urgency HIGH ({cwu_urgency})"
            elif not self._is_cwu_temp_acceptable(cwu_temp):
                should_resume = True
                resume_reason = f"temp {cwu_temp}°C not acceptable"

            if should_resume:
                can_switch, reason = self._can_switch_mode(STATE_HEATING_FLOOR, STATE_HEATING_CWU)
                if can_switch:
                    self._log_action(f"Resuming CWU: {resume_reason}")
                    await self._switch_to_cwu()
                    self._change_state(STATE_HEATING_CWU)
                    self._cwu_heating_start = now
                    self._last_mode_switch = now
                    self._reset_max_temp_tracking()
                    # Set session start temp
                    cwu_start_temp = self._get_cwu_temperature()
                    self._cwu_session_start_temp = cwu_start_temp if cwu_start_temp else self._last_known_cwu_temp
                else:
                    _LOGGER.debug(f"CWU resume blocked: {reason}")
            return

        # Currently heating CWU - check if should switch to floor
        if self._current_state in (STATE_HEATING_CWU, STATE_EMERGENCY_CWU):
            # Check if pump reports "Charged" (reached target)
            if self._is_pump_charged():
                # DHW Charged rest time - wait before switching to floor
                if self._dhw_charged_at is None:
                    self._dhw_charged_at = now
                    self._log_action(
                        "DHW Charged",
                        f"Pump reports charged at {cwu_temp:.1f}°C, waiting {DHW_CHARGED_REST_TIME}min"
                        if cwu_temp else f"Pump reports charged, waiting {DHW_CHARGED_REST_TIME}min"
                    )

                # Check if rest time elapsed
                elapsed = (now - self._dhw_charged_at).total_seconds() / 60
                if elapsed >= DHW_CHARGED_REST_TIME:
                    can_switch, reason = self._can_switch_mode(self._current_state, STATE_HEATING_FLOOR)
                    if can_switch:
                        await self._switch_to_floor()
                        self._change_state(STATE_HEATING_FLOOR)
                        self._cwu_heating_start = None
                        self._last_mode_switch = now
                        self._dhw_charged_at = None
                        self._log_action(
                            "Switch to floor",
                            f"DHW rest complete ({elapsed:.0f}min), CWU at {cwu_temp:.1f}°C"
                            if cwu_temp else f"DHW rest complete ({elapsed:.0f}min)"
                        )
                    else:
                        _LOGGER.debug(f"Floor switch after Charged blocked: {reason}")
            else:
                # Not charged anymore - reset
                self._dhw_charged_at = None
            return

        # Idle - start with CWU (priority)
        if self._current_state == STATE_IDLE:
            target = self._get_target_temp()
            cwu_start_temp = self._get_cwu_temperature()
            self._log_action(
                "CWU ON",
                f"CWU {cwu_start_temp:.1f}°C < target {target:.1f}°C" if cwu_start_temp else f"Starting CWU heating"
            )
            await self._switch_to_cwu()
            self._change_state(STATE_HEATING_CWU)
            self._cwu_heating_start = now
            self._last_mode_switch = now
            self._reset_max_temp_tracking()
            self._cwu_session_start_temp = cwu_start_temp if cwu_start_temp else self._last_known_cwu_temp

    async def _run_winter_mode_logic(
        self,
        cwu_urgency: int,
        floor_urgency: int,
        cwu_temp: float | None,
        salon_temp: float | None,
    ) -> None:
        """Run control logic for winter mode.

        Winter mode features:
        - Heat CWU during cheap tariff windows (03:00-06:00 and 13:00-15:00)
        - No 3-hour session limit (heat until target reached)
        - No fake heating detection (pump can use real heater)
        - Higher CWU target temperature (+5°C)
        - Only heat CWU outside windows if temperature drops significantly
        - When not heating water -> heat house
        """
        now = datetime.now()
        winter_target = self.get_winter_cwu_target()
        emergency_threshold = self.get_winter_cwu_emergency_threshold()
        is_heating_window = self.is_winter_cwu_heating_window()

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
            if self._check_winter_cwu_no_progress(cwu_temp):
                start_temp = self._cwu_session_start_temp
                elapsed_hours = (now - self._cwu_heating_start).total_seconds() / 3600 if self._cwu_heating_start else 0
                self._log_action(
                    f"Winter mode: No progress after {elapsed_hours:.1f}h "
                    f"(start: {start_temp}°C, current: {cwu_temp}°C). Resetting to floor."
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
                self._cwu_heating_start = None
                self._cwu_session_start_temp = None
                return

        # Handle CWU heating window (03:00-06:00 and 13:00-15:00)
        if is_heating_window:
            # During heating window: heat CWU if below target OR if temp unknown
            # When temp is unknown, enable both floor+CWU and let heat pump decide
            if cwu_temp is None:
                # Temperature unknown - enable both, let pump decide (safe default)
                if self._current_state != STATE_SAFE_MODE:
                    self._log_action(
                        "Winter mode: CWU temp UNKNOWN during heating window - enabling both (pump decides)"
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
                    self._cwu_heating_start = now
                    self._log_action(
                        f"Winter mode: Heating window started, CWU {cwu_temp}°C -> target {winter_target}°C"
                    )
                # Continue heating until target reached (no session limit in winter mode)
                return
            else:
                # Target reached during window - switch to floor
                if self._current_state == STATE_HEATING_CWU:
                    self._log_action(
                        f"Winter mode: CWU target reached ({cwu_temp}°C >= {winter_target}°C)"
                    )
                    await self._switch_to_floor()
                    self._change_state(STATE_HEATING_FLOOR)
                    self._cwu_heating_start = None
                return

        # Outside heating window: if temp unknown, enable both (pump decides)
        if cwu_temp is None:
            if self._current_state != STATE_SAFE_MODE:
                self._log_action(
                    "Winter mode: CWU temp UNKNOWN outside window - enabling both (pump decides)"
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
                self._cwu_heating_start = now
                await self._async_send_notification(
                    "CWU Emergency (Winter Mode)",
                    f"CWU dropped to {cwu_temp}°C (below {emergency_threshold}°C threshold). "
                    f"Starting emergency heating outside window."
                )
                self._log_action(
                    f"Winter mode: Emergency CWU heating ({cwu_temp}°C < {emergency_threshold}°C)"
                )
            # If already in emergency heating, continue until buffer temp reached
            return

        # Check if we should exit emergency CWU heating (temp risen above buffer)
        if self._current_state == STATE_EMERGENCY_CWU and cwu_temp is not None:
            buffer_temp = emergency_threshold + 3.0
            if cwu_temp >= buffer_temp:
                self._log_action(
                    f"Winter mode: Emergency CWU complete ({cwu_temp}°C >= {buffer_temp}°C)"
                )
                await self._switch_to_floor()
                self._change_state(STATE_HEATING_FLOOR)
                self._cwu_heating_start = None
                return

        # Currently heating CWU but outside window and above emergency threshold
        if self._current_state in (STATE_HEATING_CWU, STATE_EMERGENCY_CWU):
            # Check if we should continue (during heating window check above already handles this)
            if cwu_temp is not None and cwu_temp >= winter_target:
                self._log_action(
                    f"Winter mode: CWU at target ({cwu_temp}°C), switching to floor"
                )
                await self._switch_to_floor()
                self._change_state(STATE_HEATING_FLOOR)
                self._cwu_heating_start = None
                return

        # Default: heat floor (if not already heating something)
        if self._current_state not in (STATE_HEATING_FLOOR, STATE_HEATING_CWU, STATE_EMERGENCY_CWU, STATE_SAFE_MODE):
            self._log_action("Winter mode: Default to floor heating")
            await self._switch_to_floor()
            self._change_state(STATE_HEATING_FLOOR)

    async def _switch_to_cwu(self) -> None:
        """Switch to CWU heating mode with proper delays."""
        if self._transition_in_progress:
            self._log_action("Switch to CWU skipped - transition in progress")
            return

        self._transition_in_progress = True
        try:
            self._log_action("Switching to CWU heating...")

            # First turn off floor heating (BSB-LAN)
            await self._async_set_floor_off()
            self._log_action("Floor heating off, waiting 60s...")
            await asyncio.sleep(60)  # Wait 1 minute for pump to settle

            # Then enable CWU (BSB-LAN)
            await self._async_set_cwu_on()
        finally:
            self._transition_in_progress = False

        # Track session start - get current temp (BSB-LAN preferred)
        cwu_temp = self._get_cwu_temperature()
        if cwu_temp is None:
            cwu_temp = self._last_known_cwu_temp
        self._cwu_session_start_temp = cwu_temp

    async def _switch_to_floor(self) -> None:
        """Switch to floor heating mode with proper delays."""
        if self._transition_in_progress:
            self._log_action("Switch to floor skipped - transition in progress")
            return

        self._transition_in_progress = True
        try:
            self._log_action("Switching to floor heating...")

            # First turn off CWU (BSB-LAN)
            await self._async_set_cwu_off()
            self._log_action("CWU off, waiting 60s...")
            await asyncio.sleep(60)  # Wait 1 minute for pump to settle

            # Then enable floor heating (BSB-LAN)
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
            self._log_action("Enter safe mode skipped - transition in progress")
            return

        self._transition_in_progress = True
        try:
            self._control_source = CONTROL_SOURCE_HA_CLOUD
            self._log_action("Entering safe mode - BSB-LAN unavailable, using cloud fallback")

            # Turn on CWU via cloud (always send command)
            await self._async_safe_mode_cwu_on()
            self._log_action(f"Safe mode: CWU enabled, waiting {SAFE_MODE_DELAY}s before floor...")

            # Wait 2 minutes before enabling floor
            await asyncio.sleep(SAFE_MODE_DELAY)

            # Turn on floor via cloud (always send command)
            await self._async_safe_mode_floor_on()

            self._log_action("Safe mode active - heat pump in control via cloud")
        finally:
            self._transition_in_progress = False
