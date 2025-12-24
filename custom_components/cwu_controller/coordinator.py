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
    POWER_THERMODYNAMIC_MIN,
    CWU_MAX_HEATING_TIME,
    CWU_PAUSE_TIME,
    FAKE_HEATING_DETECTION_TIME,
    FAKE_HEATING_RESTART_WAIT,
    SENSOR_UNAVAILABLE_GRACE,
    CWU_SENSOR_UNAVAILABLE_TIMEOUT,
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
    # Summer mode settings
    SUMMER_PV_SLOT_START,
    SUMMER_PV_SLOT_END,
    SUMMER_PV_DEADLINE,
    SUMMER_CWU_TARGET_TEMP,
    SUMMER_EVENING_THRESHOLD,
    SUMMER_NIGHT_THRESHOLD,
    SUMMER_NIGHT_TARGET,
    SUMMER_CWU_MAX_TEMP,
    SUMMER_HEATER_POWER,
    SUMMER_BALANCE_THRESHOLD,
    SUMMER_PV_MIN_PRODUCTION,
    SUMMER_MIN_HEATING_TIME,
    SUMMER_MIN_COOLDOWN,
    SUMMER_BALANCE_CHECK_INTERVAL,
    SUMMER_CWU_NO_PROGRESS_TIMEOUT,
    SUMMER_CWU_MIN_TEMP_INCREASE,
    SUMMER_EXCESS_EXPORT_THRESHOLD,
    SUMMER_EXCESS_BALANCE_THRESHOLD,
    SUMMER_EXCESS_BALANCE_MIN,
    SUMMER_EXCESS_GRID_WARNING,
    SUMMER_EXCESS_GRID_STOP,
    SUMMER_EXCESS_CWU_MIN_OFFSET,
    CONF_PV_BALANCE_SENSOR,
    CONF_PV_PRODUCTION_SENSOR,
    CONF_GRID_POWER_SENSOR,
    CONF_SUMMER_HEATER_POWER,
    CONF_SUMMER_BALANCE_THRESHOLD,
    CONF_SUMMER_PV_SLOT_START,
    CONF_SUMMER_PV_SLOT_END,
    CONF_SUMMER_PV_DEADLINE,
    CONF_SUMMER_NIGHT_THRESHOLD,
    CONF_SUMMER_NIGHT_TARGET,
    DEFAULT_PV_BALANCE_SENSOR,
    DEFAULT_PV_PRODUCTION_SENSOR,
    DEFAULT_GRID_POWER_SENSOR,
    HEATING_SOURCE_NONE,
    HEATING_SOURCE_PV,
    HEATING_SOURCE_PV_EXCESS,
    HEATING_SOURCE_TARIFF_CHEAP,
    HEATING_SOURCE_TARIFF_EXPENSIVE,
    HEATING_SOURCE_EMERGENCY,
    SLOT_PV,
    SLOT_EVENING,
    SLOT_NIGHT,
    PV_EXPORT_RATE,
)

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
        self._cwu_temp_unavailable_since: datetime | None = None
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

        # Summer mode state tracking
        self._summer_heating_source: str = HEATING_SOURCE_NONE
        self._summer_current_slot: str = SLOT_PV
        self._summer_heating_start: datetime | None = None
        self._summer_last_stop: datetime | None = None  # For cooldown tracking
        self._summer_excess_mode_active: bool = False
        self._summer_last_balance_check: datetime | None = None
        self._summer_decision_reason: str = ""

        # Summer mode PV statistics (for daily report)
        self._summer_energy_pv_today: float = 0.0  # kWh from PV
        self._summer_energy_pv_excess_today: float = 0.0  # kWh from excess PV mode
        self._summer_energy_tariff_cheap_today: float = 0.0  # kWh from cheap tariff
        self._summer_energy_tariff_expensive_today: float = 0.0  # kWh from expensive tariff
        self._summer_energy_pv_yesterday: float = 0.0
        self._summer_energy_pv_excess_yesterday: float = 0.0
        self._summer_energy_tariff_cheap_yesterday: float = 0.0
        self._summer_energy_tariff_expensive_yesterday: float = 0.0
        self._summer_energy_last_reset_date: datetime | None = None  # Track last reset date

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
        """Get CWU target temperature for winter mode (base + offset, max 55°C)."""
        base_target = self.config.get("cwu_target_temp", DEFAULT_CWU_TARGET_TEMP)
        return min(base_target + WINTER_CWU_TARGET_OFFSET, WINTER_CWU_MAX_TEMP)

    def get_winter_cwu_emergency_threshold(self) -> float:
        """Get temperature below which CWU heating is forced outside windows."""
        return self.get_winter_cwu_target() - WINTER_CWU_EMERGENCY_OFFSET

    # =========================================================================
    # Summer Mode Helper Methods
    # =========================================================================

    def _get_pv_balance(self) -> float | None:
        """Get current hourly energy balance in kWh.

        This sensor shows how much energy was exported/imported in the current hour.
        Positive = exported (surplus), Negative = imported (deficit).
        Resets to 0 at each full hour.
        """
        sensor = self.config.get(CONF_PV_BALANCE_SENSOR, DEFAULT_PV_BALANCE_SENSOR)
        return self._get_sensor_value(sensor)

    def _get_pv_production(self) -> float | None:
        """Get current PV production in W."""
        sensor = self.config.get(CONF_PV_PRODUCTION_SENSOR, DEFAULT_PV_PRODUCTION_SENSOR)
        return self._get_sensor_value(sensor)

    def _get_grid_power(self) -> float | None:
        """Get current grid power flow in W.

        Positive = importing from grid (consuming)
        Negative = exporting to grid (producing surplus)
        """
        sensor = self.config.get(CONF_GRID_POWER_SENSOR, DEFAULT_GRID_POWER_SENSOR)
        return self._get_sensor_value(sensor)

    def _get_summer_heater_power(self) -> int:
        """Get configured heater power in W."""
        return self.config.get(CONF_SUMMER_HEATER_POWER, SUMMER_HEATER_POWER)

    def _get_summer_balance_threshold(self) -> float:
        """Get balance threshold ratio (0.0-1.0)."""
        return self.config.get(CONF_SUMMER_BALANCE_THRESHOLD, SUMMER_BALANCE_THRESHOLD)

    def _get_summer_slot(self, hour: int | None = None) -> str:
        """Determine current time slot for summer mode.

        Returns:
            SLOT_PV: 08:00-18:00 - prioritize PV production
            SLOT_EVENING: 18:00-24:00 - fallback to cheap tariff
            SLOT_NIGHT: 00:00-08:00 - only safety buffer heating
        """
        if hour is None:
            hour = datetime.now().hour

        pv_start = self.config.get(CONF_SUMMER_PV_SLOT_START, SUMMER_PV_SLOT_START)
        pv_end = self.config.get(CONF_SUMMER_PV_SLOT_END, SUMMER_PV_SLOT_END)

        if pv_start <= hour < pv_end:
            return SLOT_PV
        elif pv_end <= hour < 24:
            return SLOT_EVENING
        else:  # 0 <= hour < pv_start
            return SLOT_NIGHT

    def get_summer_cwu_target(self) -> float:
        """Get CWU target temperature for summer mode."""
        return self.config.get("cwu_target_temp", SUMMER_CWU_TARGET_TEMP)

    def get_summer_night_threshold(self) -> float:
        """Get temperature threshold for night heating (safety buffer)."""
        return self.config.get(CONF_SUMMER_NIGHT_THRESHOLD, SUMMER_NIGHT_THRESHOLD)

    def get_summer_night_target(self) -> float:
        """Get target temperature for night heating (just safety buffer, not full target)."""
        return self.config.get(CONF_SUMMER_NIGHT_TARGET, SUMMER_NIGHT_TARGET)

    def _is_summer_cooldown_active(self) -> bool:
        """Check if cooldown period is active (min 5 min between heating cycles)."""
        if self._summer_last_stop is None:
            return False

        elapsed = (datetime.now() - self._summer_last_stop).total_seconds() / 60
        return elapsed < SUMMER_MIN_COOLDOWN

    def _is_summer_min_heating_time_elapsed(self) -> bool:
        """Check if minimum heating time has elapsed (heater protection)."""
        if self._summer_heating_start is None:
            return True

        elapsed = (datetime.now() - self._summer_heating_start).total_seconds() / 60
        return elapsed >= SUMMER_MIN_HEATING_TIME

    def _should_heat_from_pv(self, cwu_temp: float | None) -> tuple[bool, str]:
        """Determine if we should heat CWU from PV.

        Uses hourly balance-based decision making:
        - First half of hour (XX:00-XX:29): Conservative - only if PV > heater or balance >= 1kWh
        - Second half of hour (XX:30-XX:59): Aggressive - if balance covers remaining time

        Returns:
            (should_heat, reason) tuple
        """
        if cwu_temp is None:
            return False, "CWU temp unavailable"

        target = self.get_summer_cwu_target()
        if cwu_temp >= target:
            return False, f"CWU at target ({cwu_temp:.1f}°C >= {target:.1f}°C)"

        # Check cooldown
        if self._is_summer_cooldown_active():
            elapsed = (datetime.now() - self._summer_last_stop).total_seconds() / 60 if self._summer_last_stop else 0
            return False, f"Cooldown active ({elapsed:.1f}/{SUMMER_MIN_COOLDOWN} min)"

        now = datetime.now()
        minute = now.minute

        pv_production = self._get_pv_production()
        pv_balance = self._get_pv_balance()
        heater_power = self._get_summer_heater_power()
        threshold_ratio = self._get_summer_balance_threshold()

        # No PV data - can't make PV decision
        if pv_balance is None:
            return False, "PV balance sensor unavailable"

        # No/low production - not a PV opportunity
        if pv_production is None or pv_production < SUMMER_PV_MIN_PRODUCTION:
            return False, f"No PV production ({pv_production or 0:.0f}W < {SUMMER_PV_MIN_PRODUCTION}W)"

        # STRATEGY: First half of hour (XX:00-XX:29)
        if minute < 30:
            # Conservative - only heat if PV clearly exceeds heater power
            if pv_production >= heater_power:
                return True, f"First half: PV covers heater ({pv_production:.0f}W >= {heater_power}W)"

            # Or if we have a solid balance buffer (>= 1 kWh)
            if pv_balance >= 1.0:
                return True, f"First half: Good balance ({pv_balance:.2f} kWh >= 1.0 kWh)"

            return False, f"First half: Building balance ({pv_balance:.2f} kWh, PV {pv_production:.0f}W)"

        # STRATEGY: Second half of hour (XX:30-XX:59)
        else:
            remaining_minutes = 60 - minute
            energy_needed = (heater_power / 1000) * (remaining_minutes / 60)  # kWh
            threshold = energy_needed * threshold_ratio

            # Do we have enough balance to cover remaining time?
            if pv_balance >= threshold:
                return True, f"Second half: Balance OK ({pv_balance:.2f} kWh >= {threshold:.2f} kWh)"

            # Production covers consumption?
            if pv_production >= heater_power:
                return True, f"Second half: PV covers heater ({pv_production:.0f}W >= {heater_power}W)"

            return False, f"Second half: Insufficient ({pv_balance:.2f} kWh < {threshold:.2f} kWh, PV {pv_production:.0f}W)"

    def _should_heat_from_tariff_summer(self, cwu_temp: float | None) -> tuple[bool, str]:
        """Determine if we should heat CWU from cheap tariff (summer mode fallback).

        Implements slot-based logic:
        - SLOT_NIGHT: Only heat if CWU < night_threshold (40°C), target is night_target (42°C)
        - SLOT_PV: Use cheap window 13-15 if available, or deadline (16:00) fallback
        - SLOT_EVENING: Standard fallback to cheap tariff (22:00+)

        Returns:
            (should_heat, reason) tuple
        """
        if cwu_temp is None:
            return False, "CWU temp unavailable"

        now = datetime.now()
        hour = now.hour
        slot = self._get_summer_slot(hour)
        target = self.get_summer_cwu_target()

        # Already at target
        if cwu_temp >= target:
            return False, f"CWU at target ({cwu_temp:.1f}°C >= {target:.1f}°C)"

        # Check cooldown
        if self._is_summer_cooldown_active():
            elapsed = (datetime.now() - self._summer_last_stop).total_seconds() / 60 if self._summer_last_stop else 0
            return False, f"Cooldown active ({elapsed:.1f}/{SUMMER_MIN_COOLDOWN} min)"

        night_threshold = self.get_summer_night_threshold()
        night_target = self.get_summer_night_target()
        evening_threshold = self.config.get("summer_evening_threshold", SUMMER_EVENING_THRESHOLD)
        deadline = self.config.get(CONF_SUMMER_PV_DEADLINE, SUMMER_PV_DEADLINE)

        # SLOT_NIGHT (00:00-08:00): Very conservative - only safety buffer
        if slot == SLOT_NIGHT:
            if cwu_temp < night_threshold:
                if self.is_cheap_tariff():
                    return True, f"Night slot: CWU cold ({cwu_temp:.1f}°C < {night_threshold:.1f}°C), heating to {night_target:.1f}°C"
                return False, "Night slot: CWU cold but expensive tariff"
            return False, f"Night slot: CWU OK ({cwu_temp:.1f}°C >= {night_threshold:.1f}°C), waiting for PV"

        # SLOT_PV (08:00-18:00): Check cheap window (13-15) first, then deadline
        if slot == SLOT_PV:
            # Priority: Cheap tariff window (13:00-15:00)
            if self.is_cheap_tariff():
                return True, f"PV slot + cheap window (13-15): Heating at 0.72 zł/kWh ({cwu_temp:.1f}°C < {target:.1f}°C)"

            # Deadline fallback (after 16:00)
            if hour >= deadline and cwu_temp < evening_threshold:
                return True, f"PV slot deadline ({hour}:00 >= {deadline}:00): Emergency heating ({cwu_temp:.1f}°C < {evening_threshold:.1f}°C)"

            return False, f"PV slot: Waiting for PV or cheap window 13-15 (current hour: {hour})"

        # SLOT_EVENING (18:00-24:00): Standard fallback
        if slot == SLOT_EVENING:
            if self.is_cheap_tariff():
                return True, f"Evening slot + cheap tariff: Heating ({cwu_temp:.1f}°C < {target:.1f}°C)"
            return False, f"Evening slot: Expensive tariff, waiting for 22:00"

        return False, f"Unknown slot: {slot}"

    def _should_heat_excess_pv(self, cwu_temp: float | None) -> tuple[bool, str]:
        """Determine if we should activate Excess PV Mode (reheat from surplus).

        Excess PV Mode activates when:
        - Water is warm but below target (45°C < CWU < 50°C)
        - Large export to grid (> 3kW)
        - Good hourly balance (> 2 kWh)
        - In PV or Evening slot

        This uses surplus energy that would otherwise be exported for low prices.

        Returns:
            (should_heat, reason) tuple
        """
        if cwu_temp is None:
            return False, "CWU temp unavailable"

        target = self.get_summer_cwu_target()

        # Already at target
        if cwu_temp >= target:
            return False, f"CWU at target ({cwu_temp:.1f}°C >= {target:.1f}°C)"

        # Water must be warm (not cold) - we're optimizing, not emergency heating
        min_temp_for_excess = target - SUMMER_EXCESS_CWU_MIN_OFFSET
        if cwu_temp < min_temp_for_excess:
            return False, f"CWU too cold for excess mode ({cwu_temp:.1f}°C < {min_temp_for_excess:.1f}°C)"

        # Check cooldown
        if self._is_summer_cooldown_active():
            elapsed = (datetime.now() - self._summer_last_stop).total_seconds() / 60 if self._summer_last_stop else 0
            return False, f"Cooldown active ({elapsed:.1f}/{SUMMER_MIN_COOLDOWN} min)"

        # Must be in PV or Evening slot
        slot = self._get_summer_slot()
        if slot == SLOT_NIGHT:
            return False, "Night slot - no excess PV mode"

        grid_power = self._get_grid_power()
        pv_balance = self._get_pv_balance()

        if grid_power is None or pv_balance is None:
            return False, "Grid power or balance sensor unavailable"

        # Check for large export (negative grid power = export)
        if grid_power > SUMMER_EXCESS_EXPORT_THRESHOLD:
            return False, f"Not enough export ({grid_power:.0f}W > {SUMMER_EXCESS_EXPORT_THRESHOLD}W threshold)"

        # Check for good balance
        if pv_balance < SUMMER_EXCESS_BALANCE_THRESHOLD:
            return False, f"Balance too low ({pv_balance:.2f} kWh < {SUMMER_EXCESS_BALANCE_THRESHOLD:.1f} kWh)"

        export_kw = abs(grid_power) / 1000
        return True, f"Excess PV: Export {export_kw:.1f}kW, balance {pv_balance:.2f}kWh - better to heat than export"

    def _check_summer_excess_mode_conditions(self) -> tuple[bool, str]:
        """Check if Excess PV Mode should continue (called every 15 min during excess heating).

        Stops if:
        - CWU reached target
        - Balance dropped below minimum (0.5 kWh)
        - Grid draw exceeds stop threshold (3 kW)
        - Min heating time not elapsed (heater protection)

        Returns:
            (should_continue, reason) tuple
        """
        cwu_temp = self._get_sensor_value(self.config.get("cwu_temp_sensor"))
        target = self.get_summer_cwu_target()

        # Target reached - success!
        if cwu_temp is not None and cwu_temp >= target:
            return False, f"Excess mode: Target reached ({cwu_temp:.1f}°C >= {target:.1f}°C)"

        # Check min heating time (heater protection)
        if not self._is_summer_min_heating_time_elapsed():
            elapsed = (datetime.now() - self._summer_heating_start).total_seconds() / 60 if self._summer_heating_start else 0
            return True, f"Excess mode: Continuing (min heating time {elapsed:.0f}/{SUMMER_MIN_HEATING_TIME} min)"

        grid_power = self._get_grid_power()
        pv_balance = self._get_pv_balance()

        # Balance check
        if pv_balance is not None and pv_balance < SUMMER_EXCESS_BALANCE_MIN:
            return False, f"Excess mode: Balance exhausted ({pv_balance:.2f} kWh < {SUMMER_EXCESS_BALANCE_MIN:.1f} kWh)"

        # Grid draw check
        if grid_power is not None and grid_power > SUMMER_EXCESS_GRID_STOP:
            return False, f"Excess mode: Grid draw too high ({grid_power:.0f}W > {SUMMER_EXCESS_GRID_STOP}W)"

        # Warning for moderate grid draw
        if grid_power is not None and grid_power > SUMMER_EXCESS_GRID_WARNING:
            return True, f"Excess mode: WARNING - Grid draw {grid_power:.0f}W (watching)"

        return True, f"Excess mode: Conditions OK (balance {pv_balance:.2f} kWh, grid {grid_power:.0f}W)"

    def _check_summer_cwu_no_progress(self, current_temp: float | None) -> bool:
        """Check if summer mode CWU heating has made no progress after timeout.

        Similar to winter mode but with shorter timeout (60 min vs 180 min)
        and higher expected increase (2°C vs 1°C) since heater should heat faster.
        """
        if self._summer_heating_start is None:
            return False
        if self._cwu_session_start_temp is None:
            return False
        if current_temp is None:
            return False

        elapsed = (datetime.now() - self._summer_heating_start).total_seconds() / 60
        if elapsed < SUMMER_CWU_NO_PROGRESS_TIMEOUT:
            return False

        temp_increase = current_temp - self._cwu_session_start_temp
        return temp_increase < SUMMER_CWU_MIN_TEMP_INCREASE

    @property
    def summer_energy_today(self) -> dict[str, float]:
        """Return today's summer mode energy statistics."""
        total_pv = self._summer_energy_pv_today + self._summer_energy_pv_excess_today
        total_tariff = self._summer_energy_tariff_cheap_today + self._summer_energy_tariff_expensive_today
        total = total_pv + total_tariff

        # Calculate efficiency (% of energy from PV)
        pv_efficiency = (total_pv / total * 100) if total > 0 else 0.0

        # Calculate savings (vs all expensive tariff)
        expensive_rate = self.get_tariff_expensive_rate()
        cheap_rate = self.get_tariff_cheap_rate()
        export_rate = PV_EXPORT_RATE

        # What we would have paid with all expensive tariff
        cost_if_expensive = total * expensive_rate

        # What we actually saved:
        # - PV energy: free (plus we would have exported it for export_rate)
        # - PV excess: free (would have exported)
        # - Cheap tariff: paid cheap rate
        # - Expensive tariff: paid expensive rate
        actual_cost = (
            self._summer_energy_tariff_cheap_today * cheap_rate +
            self._summer_energy_tariff_expensive_today * expensive_rate
        )
        # Value of PV energy used (would have been exported)
        pv_value = total_pv * export_rate

        savings = cost_if_expensive - actual_cost + pv_value

        return {
            "pv": self._summer_energy_pv_today,
            "pv_excess": self._summer_energy_pv_excess_today,
            "tariff_cheap": self._summer_energy_tariff_cheap_today,
            "tariff_expensive": self._summer_energy_tariff_expensive_today,
            "total_pv": total_pv,
            "total_tariff": total_tariff,
            "total": total,
            "pv_efficiency": pv_efficiency,
            "savings": savings,
            "actual_cost": actual_cost,
        }

    @property
    def summer_energy_yesterday(self) -> dict[str, float]:
        """Return yesterday's summer mode energy statistics."""
        total_pv = self._summer_energy_pv_yesterday + self._summer_energy_pv_excess_yesterday
        total_tariff = self._summer_energy_tariff_cheap_yesterday + self._summer_energy_tariff_expensive_yesterday
        total = total_pv + total_tariff

        pv_efficiency = (total_pv / total * 100) if total > 0 else 0.0

        expensive_rate = self.get_tariff_expensive_rate()
        cheap_rate = self.get_tariff_cheap_rate()
        export_rate = PV_EXPORT_RATE

        cost_if_expensive = total * expensive_rate
        actual_cost = (
            self._summer_energy_tariff_cheap_yesterday * cheap_rate +
            self._summer_energy_tariff_expensive_yesterday * expensive_rate
        )
        pv_value = total_pv * export_rate
        savings = cost_if_expensive - actual_cost + pv_value

        return {
            "pv": self._summer_energy_pv_yesterday,
            "pv_excess": self._summer_energy_pv_excess_yesterday,
            "tariff_cheap": self._summer_energy_tariff_cheap_yesterday,
            "tariff_expensive": self._summer_energy_tariff_expensive_yesterday,
            "total_pv": total_pv,
            "total_tariff": total_tariff,
            "total": total,
            "pv_efficiency": pv_efficiency,
            "savings": savings,
            "actual_cost": actual_cost,
        }

    # =========================================================================
    # Summer Mode Control Methods
    # =========================================================================

    async def _summer_start_heating(self, source: str = HEATING_SOURCE_PV) -> None:
        """Start CWU heating in summer mode.

        Summer mode uses performance mode (heater only, no compressor).
        Floor heating is always OFF in summer.

        Args:
            source: The heating source (PV, tariff_cheap, tariff_expensive, emergency)
        """
        if self._transition_in_progress:
            self._log_action("Summer start heating skipped - transition in progress")
            return

        self._transition_in_progress = True
        try:
            self._log_action(f"Summer mode: Starting CWU heating from {source}...")

            # Ensure floor is OFF (safety - should already be off in summer)
            await self._async_set_climate(False)
            await asyncio.sleep(2)

            # Set water heater to performance mode (uses heater, not compressor)
            await self._async_set_water_heater_mode(WH_MODE_PERFORMANCE)
            self._log_action("Summer mode: CWU heater enabled (performance mode)")

            # Track session start
            cwu_temp = self._last_known_cwu_temp
            if cwu_temp is None:
                cwu_temp = self._get_sensor_value(self.config.get("cwu_temp_sensor"))
            self._cwu_session_start_temp = cwu_temp
            self._summer_heating_start = datetime.now()
            self._summer_heating_source = source
            self._cwu_heating_start = datetime.now()

        finally:
            self._transition_in_progress = False

    async def _summer_stop_heating(self) -> None:
        """Stop CWU heating in summer mode."""
        if self._transition_in_progress:
            self._log_action("Summer stop heating skipped - transition in progress")
            return

        self._transition_in_progress = True
        try:
            self._log_action("Summer mode: Stopping CWU heating...")

            # Track energy usage by source before stopping
            await self._track_summer_energy_usage()

            await self._async_set_water_heater_mode(WH_MODE_OFF)
            # Floor stays OFF in summer mode - no need to turn it on

            self._summer_last_stop = datetime.now()
            self._summer_heating_start = None  # Reset for next session
            self._summer_heating_source = HEATING_SOURCE_NONE
            self._summer_excess_mode_active = False
            self._log_action("Summer mode: CWU heater disabled")
        finally:
            self._transition_in_progress = False

    async def _track_summer_energy_usage(self) -> None:
        """Track energy usage by source when stopping heating.

        Called before stopping heater to accumulate energy stats.
        """
        if self._summer_heating_start is None:
            return

        # Calculate energy used in this session
        elapsed_hours = (datetime.now() - self._summer_heating_start).total_seconds() / 3600
        heater_power = self._get_summer_heater_power()
        energy_kwh = (heater_power / 1000) * elapsed_hours

        # Attribute to the correct source
        source = self._summer_heating_source
        if source == HEATING_SOURCE_PV:
            self._summer_energy_pv_today += energy_kwh
        elif source == HEATING_SOURCE_PV_EXCESS:
            self._summer_energy_pv_excess_today += energy_kwh
        elif source == HEATING_SOURCE_TARIFF_CHEAP:
            self._summer_energy_tariff_cheap_today += energy_kwh
        elif source in (HEATING_SOURCE_TARIFF_EXPENSIVE, HEATING_SOURCE_EMERGENCY):
            self._summer_energy_tariff_expensive_today += energy_kwh

        self._log_action(
            f"Summer energy tracked: {energy_kwh:.2f} kWh from {source} "
            f"({elapsed_hours:.2f}h at {heater_power}W)"
        )

    async def _enter_summer_safe_mode(self) -> None:
        """Enter safe mode in summer - only CWU, no floor.

        Unlike winter safe mode, we only enable CWU heating.
        Floor heating stays OFF because house doesn't need it in summer.
        """
        if self._transition_in_progress:
            self._log_action("Summer safe mode skipped - transition in progress")
            return

        self._transition_in_progress = True
        try:
            self._log_action("Summer mode: Entering safe mode - enabling CWU only")

            # Ensure floor is OFF
            await self._async_set_climate(False)
            await asyncio.sleep(2)

            # Enable CWU with performance mode (heater only)
            await self._async_set_water_heater_mode(WH_MODE_PERFORMANCE)
            self._log_action("Summer safe mode active - CWU heater in control")
        finally:
            self._transition_in_progress = False

    def _update_summer_slot(self) -> None:
        """Update current time slot and reset stats at midnight."""
        now = datetime.now()
        hour = now.hour
        today = now.date()

        # Update current slot
        self._summer_current_slot = self._get_summer_slot(hour)

        # Reset daily stats when date changes (handles restart scenarios too)
        if self._summer_energy_last_reset_date is None:
            # First run - just set the date
            self._summer_energy_last_reset_date = now
        elif self._summer_energy_last_reset_date.date() != today:
            # Date changed - check if any energy was tracked today
            total_today = (
                self._summer_energy_pv_today +
                self._summer_energy_pv_excess_today +
                self._summer_energy_tariff_cheap_today +
                self._summer_energy_tariff_expensive_today
            )

            if total_today > 0:
                # Move today's stats to yesterday
                self._summer_energy_pv_yesterday = self._summer_energy_pv_today
                self._summer_energy_pv_excess_yesterday = self._summer_energy_pv_excess_today
                self._summer_energy_tariff_cheap_yesterday = self._summer_energy_tariff_cheap_today
                self._summer_energy_tariff_expensive_yesterday = self._summer_energy_tariff_expensive_today

            # Reset today's stats
            self._summer_energy_pv_today = 0.0
            self._summer_energy_pv_excess_today = 0.0
            self._summer_energy_tariff_cheap_today = 0.0
            self._summer_energy_tariff_expensive_today = 0.0
            self._summer_energy_last_reset_date = now

    async def _run_summer_mode_logic(
        self,
        cwu_urgency: int,
        cwu_temp: float | None,
    ) -> None:
        """Run control logic for summer mode.

        Summer mode features:
        - Heat pump in emergency mode (heater only, no compressor)
        - Floor heating permanently OFF
        - Heat CWU from PV surplus with hourly balancing
        - Fallback to cheap tariff when no PV
        - Excess PV Mode for reheating from surplus
        - No fake heating detection (heater works properly)
        - Heater protection (min 30 min runtime, 5 min cooldown)
        - Warning if no progress (similar to winter mode)
        """
        now = datetime.now()
        target = self.get_summer_cwu_target()
        critical = self.config.get("cwu_critical_temp", DEFAULT_CWU_CRITICAL_TEMP)
        night_target = self.get_summer_night_target()
        slot = self._get_summer_slot()

        # Update slot tracking
        self._update_summer_slot()

        # =====================================================================
        # 1. EMERGENCY CHECK - Critical temperature takes immediate priority
        # =====================================================================
        if cwu_temp is not None and cwu_temp < critical:
            if self._current_state != STATE_EMERGENCY_CWU:
                await self._summer_start_heating(HEATING_SOURCE_EMERGENCY)
                self._change_state(STATE_EMERGENCY_CWU)
                await self._async_send_notification(
                    "CWU Emergency (Summer Mode)",
                    f"CWU critically low: {cwu_temp:.1f}°C (< {critical:.1f}°C)!\n"
                    f"Starting emergency heating immediately."
                )
                self._summer_decision_reason = f"Emergency: CWU {cwu_temp:.1f}°C < {critical:.1f}°C critical"
                self._log_action(f"Summer mode: {self._summer_decision_reason}")
            return

        # =====================================================================
        # 2. MAXIMUM TEMPERATURE CHECK - Emergency stop
        # =====================================================================
        if cwu_temp is not None and cwu_temp >= SUMMER_CWU_MAX_TEMP:
            if self._current_state in (STATE_HEATING_CWU, STATE_EMERGENCY_CWU):
                self._log_action(
                    f"Summer mode: MAX temperature reached ({cwu_temp:.1f}°C >= {SUMMER_CWU_MAX_TEMP:.1f}°C) - EMERGENCY STOP"
                )
                await self._summer_stop_heating()
                self._change_state(STATE_IDLE)
                self._summer_decision_reason = f"Emergency stop: {cwu_temp:.1f}°C >= max {SUMMER_CWU_MAX_TEMP:.1f}°C"
            return

        # =====================================================================
        # 3. CURRENTLY HEATING - Check if we should continue
        # =====================================================================
        if self._current_state in (STATE_HEATING_CWU, STATE_EMERGENCY_CWU):
            # Check for no-progress timeout
            if self._check_summer_cwu_no_progress(cwu_temp):
                start_temp = self._cwu_session_start_temp
                elapsed = (now - self._summer_heating_start).total_seconds() / 60 if self._summer_heating_start else 0

                self._summer_decision_reason = (
                    f"No progress after {elapsed:.0f} min "
                    f"(start: {start_temp:.1f}°C, current: {cwu_temp:.1f}°C)"
                )
                self._log_action(f"Summer mode: {self._summer_decision_reason}")
                await self._async_send_notification(
                    "CWU Heating Problem (Summer Mode)",
                    f"CWU temperature hasn't increased after {elapsed:.0f} minutes.\n"
                    f"Started at: {start_temp:.1f}°C\n"
                    f"Current: {cwu_temp:.1f}°C\n"
                    f"Expected increase: {SUMMER_CWU_MIN_TEMP_INCREASE:.1f}°C\n\n"
                    f"Heater may have an issue. Stopping heating."
                )
                await self._summer_stop_heating()
                self._change_state(STATE_IDLE)
                self._cwu_session_start_temp = None
                return

            # Determine effective target (night_target for night slot, full target otherwise)
            effective_target = night_target if slot == SLOT_NIGHT else target

            # Target reached - stop heating
            if cwu_temp is not None and cwu_temp >= effective_target:
                self._summer_decision_reason = f"Target reached: {cwu_temp:.1f}°C >= {effective_target:.1f}°C"
                self._log_action(f"Summer mode: {self._summer_decision_reason}")
                await self._summer_stop_heating()
                self._change_state(STATE_IDLE)
                self._cwu_session_start_temp = None
                return

            # Check if we're in Excess PV Mode - needs periodic condition check
            if self._summer_excess_mode_active:
                # Check if we should do a balance check (every 15 min)
                should_check = (
                    self._summer_last_balance_check is None or
                    (now - self._summer_last_balance_check).total_seconds() / 60 >= SUMMER_BALANCE_CHECK_INTERVAL
                )

                if should_check:
                    self._summer_last_balance_check = now
                    should_continue, reason = self._check_summer_excess_mode_conditions()

                    if not should_continue:
                        self._summer_decision_reason = reason
                        self._log_action(f"Summer mode: {reason}")
                        await self._summer_stop_heating()
                        self._change_state(STATE_IDLE)
                        return
                    else:
                        self._summer_decision_reason = reason
                        self._log_action(f"Summer mode: {reason}")

                # Continue excess mode heating
                return

            # Check heater protection - minimum heating time
            if not self._is_summer_min_heating_time_elapsed():
                elapsed = (now - self._summer_heating_start).total_seconds() / 60 if self._summer_heating_start else 0
                self._summer_decision_reason = (
                    f"Heater protection: continuing ({elapsed:.0f}/{SUMMER_MIN_HEATING_TIME} min elapsed)"
                )
                return

            # Re-evaluate heating conditions
            should_heat_pv, pv_reason = self._should_heat_from_pv(cwu_temp)
            should_heat_tariff, tariff_reason = self._should_heat_from_tariff_summer(cwu_temp)

            if should_heat_pv:
                # Still have PV conditions - continue
                self._summer_decision_reason = f"Continuing PV heating: {pv_reason}"
                return
            elif should_heat_tariff:
                # Switch to tariff if we were on PV
                if self._summer_heating_source == HEATING_SOURCE_PV:
                    # Track PV energy used so far
                    await self._track_summer_energy_usage()
                    # Reset timer for tariff energy tracking (not heater protection -
                    # that already passed since we're in the conditions re-evaluation block)
                    self._summer_heating_start = now
                    source = HEATING_SOURCE_TARIFF_CHEAP if self.is_cheap_tariff() else HEATING_SOURCE_TARIFF_EXPENSIVE
                    self._summer_heating_source = source
                    self._summer_decision_reason = f"Switched to tariff: {tariff_reason}"
                    self._log_action(f"Summer mode: {self._summer_decision_reason}")
                return
            else:
                # Conditions no longer met - stop
                self._summer_decision_reason = f"Conditions ended. PV: {pv_reason}, Tariff: {tariff_reason}"
                self._log_action(f"Summer mode: Stopping - {self._summer_decision_reason}")
                await self._summer_stop_heating()
                self._change_state(STATE_IDLE)
                return

        # =====================================================================
        # 4. IDLE - Determine if we should start heating
        # =====================================================================

        # Already at target
        if cwu_temp is not None and cwu_temp >= target:
            self._summer_decision_reason = f"At target: {cwu_temp:.1f}°C >= {target:.1f}°C"
            if self._current_state != STATE_IDLE:
                self._change_state(STATE_IDLE)
            return

        # Priority 1: Try PV heating
        should_heat_pv, pv_reason = self._should_heat_from_pv(cwu_temp)
        if should_heat_pv:
            self._summer_decision_reason = f"Starting PV heating: {pv_reason}"
            self._log_action(f"Summer mode: {self._summer_decision_reason}")
            await self._summer_start_heating(HEATING_SOURCE_PV)
            self._change_state(STATE_HEATING_CWU)
            return

        # Priority 2: Check Excess PV Mode (reheat from surplus)
        should_heat_excess, excess_reason = self._should_heat_excess_pv(cwu_temp)
        if should_heat_excess:
            self._summer_decision_reason = f"Starting Excess PV Mode: {excess_reason}"
            self._log_action(f"Summer mode: {self._summer_decision_reason}")
            self._summer_excess_mode_active = True
            self._summer_last_balance_check = now
            await self._summer_start_heating(HEATING_SOURCE_PV_EXCESS)
            self._change_state(STATE_HEATING_CWU)
            return

        # Priority 3: Tariff fallback
        should_heat_tariff, tariff_reason = self._should_heat_from_tariff_summer(cwu_temp)
        if should_heat_tariff:
            source = HEATING_SOURCE_TARIFF_CHEAP if self.is_cheap_tariff() else HEATING_SOURCE_TARIFF_EXPENSIVE
            self._summer_decision_reason = f"Starting tariff heating: {tariff_reason}"
            self._log_action(f"Summer mode: {self._summer_decision_reason}")
            await self._summer_start_heating(source)
            self._change_state(STATE_HEATING_CWU)
            return

        # No conditions met - stay idle
        self._summer_decision_reason = f"Waiting. PV: {pv_reason}"
        if self._current_state != STATE_IDLE:
            self._log_action(f"Summer mode: Idle - {self._summer_decision_reason}")
            self._change_state(STATE_IDLE)

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

        # Check if CWU heating is active (water heater in heat_pump mode with power)
        cwu_active = wh_state == WH_MODE_HEAT_PUMP and power is not None and power > POWER_IDLE_THRESHOLD

        # Check if floor heating is active
        floor_active = climate_state in (CLIMATE_HEAT, CLIMATE_AUTO)

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

    def _log_action(self, action: str) -> None:
        """Log an action to history (today + yesterday only)."""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "action": action,
            "state": self._current_state,
        }
        self._action_history.append(entry)
        self._cleanup_old_history()
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

        # Build message - different format for Summer mode
        if self._operating_mode == MODE_SUMMER:
            summer_energy = self.summer_energy_yesterday
            pv_total = summer_energy["total_pv"]
            tariff_total = summer_energy["total_tariff"]
            pv_efficiency = summer_energy["pv_efficiency"]
            summer_savings = summer_energy["savings"]

            message = (
                f"☀️ Daily Energy Report - Summer Mode (yesterday)\n\n"
                f"🌞 PV Energy: {pv_total:.2f} kWh (FREE)\n"
                f"   ├ Direct PV: {summer_energy['pv']:.2f} kWh\n"
                f"   └ Excess PV: {summer_energy['pv_excess']:.2f} kWh\n\n"
                f"⚡ Grid Energy: {tariff_total:.2f} kWh\n"
                f"   ├ Cheap tariff: {summer_energy['tariff_cheap']:.2f} kWh\n"
                f"   └ Expensive: {summer_energy['tariff_expensive']:.2f} kWh\n\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"📊 PV Efficiency: {pv_efficiency:.1f}%\n"
                f"💰 Saved: {summer_savings:.2f} zł\n"
                f"💵 Actual cost: {summer_energy['actual_cost']:.2f} zł\n\n"
                f"🚿 CWU Total: {cwu_kwh:.2f} kWh ({cwu_cost:.2f} zł)\n"
                f"💡 Mode: Summer"
            )
        else:
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
        # Add delay between commands to avoid cloud API issues
        await self._async_set_climate(True)
        self._log_action("Floor heating enabled, waiting 60s...")
        await asyncio.sleep(60)
        await self._async_set_water_heater_mode(WH_MODE_HEAT_PUMP)
        self._log_action("Safe mode active - heat pump in control")

    async def async_force_cwu(self, duration_minutes: int = 60) -> None:
        """Force CWU heating for specified duration."""
        self._manual_override = True
        self._manual_override_until = datetime.now() + timedelta(minutes=duration_minutes)

        await self._async_set_climate(False)
        await asyncio.sleep(1)
        await self._async_set_water_heater_mode(WH_MODE_HEAT_PUMP)

        self._change_state(STATE_HEATING_CWU)
        self._cwu_heating_start = datetime.now()
        # Set session start temp for UI tracking
        cwu_temp = self._get_sensor_value(self.config.get("cwu_temp_sensor"))
        self._cwu_session_start_temp = cwu_temp if cwu_temp is not None else self._last_known_cwu_temp
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

    async def async_force_auto(self) -> None:
        """Cancel manual override and let controller decide from scratch."""
        self._manual_override = False
        self._manual_override_until = None
        self._change_state(STATE_IDLE)
        self._cwu_heating_start = None
        self._cwu_session_start_temp = None
        self._log_action("Manual override cancelled - switching to auto mode")
        # Next coordinator update will run control logic and decide

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

        # First run - detect current state from actual device states
        if self._first_run:
            self._first_run = False
            self._detect_initial_state(wh_state, climate_state, power, cwu_temp)

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

        # Detect fake heating (only in broken_heater mode)
        fake_heating = False
        if self._operating_mode == MODE_BROKEN_HEATER:
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
            "cwu_heating_minutes": 0,
            "state_history": self._state_history[-20:],
            "action_history": self._action_history[-20:],
            "cwu_target_temp": self.config.get("cwu_target_temp", DEFAULT_CWU_TARGET_TEMP),
            "cwu_min_temp": self.config.get("cwu_min_temp", DEFAULT_CWU_MIN_TEMP),
            "salon_target_temp": self.config.get("salon_target_temp", DEFAULT_SALON_TARGET_TEMP),
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
            # Summer mode specific
            "summer_cwu_target": self.get_summer_cwu_target() if self._operating_mode == MODE_SUMMER else None,
            "summer_night_target": self.get_summer_night_target() if self._operating_mode == MODE_SUMMER else None,
            "summer_current_slot": self._summer_current_slot if self._operating_mode == MODE_SUMMER else None,
            "summer_heating_source": self._summer_heating_source if self._operating_mode == MODE_SUMMER else None,
            "summer_excess_mode_active": self._summer_excess_mode_active if self._operating_mode == MODE_SUMMER else False,
            "summer_decision_reason": self._summer_decision_reason if self._operating_mode == MODE_SUMMER else None,
            "summer_pv_balance": self._get_pv_balance() if self._operating_mode == MODE_SUMMER else None,
            "summer_pv_production": self._get_pv_production() if self._operating_mode == MODE_SUMMER else None,
            "summer_grid_power": self._get_grid_power() if self._operating_mode == MODE_SUMMER else None,
            "summer_cooldown_active": self._is_summer_cooldown_active() if self._operating_mode == MODE_SUMMER else False,
            "summer_min_heating_elapsed": self._is_summer_min_heating_time_elapsed() if self._operating_mode == MODE_SUMMER else True,
            # Summer mode energy stats (from property)
            "summer_energy_today": self.summer_energy_today if self._operating_mode == MODE_SUMMER else None,
            "summer_energy_yesterday": self.summer_energy_yesterday if self._operating_mode == MODE_SUMMER else None,
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
        """Run the main control logic - routes to mode-specific logic."""

        # Skip control logic if a transition is in progress
        if self._transition_in_progress:
            return

        # Handle safe mode - sensors unavailable
        if self._current_state == STATE_SAFE_MODE:
            # Check if sensors recovered - both CWU and at least one room temp needed
            if cwu_temp is not None and salon_temp is not None:
                self._log_action("Sensors recovered - exiting safe mode")
                await self._async_send_notification(
                    "CWU Controller Recovered",
                    f"Temperature sensors are back online.\n"
                    f"CWU: {cwu_temp}°C, Salon: {salon_temp}°C\n"
                    f"Resuming normal control."
                )
                self._cwu_temp_unavailable_since = None
                self._change_state(STATE_IDLE)
                # Continue to normal control logic below
            else:
                # Still in safe mode, nothing to do
                return

        # Check if we need to enter safe mode due to sensor unavailability
        if cwu_temp is None:
            if self._cwu_temp_unavailable_since is None:
                self._cwu_temp_unavailable_since = datetime.now()
            else:
                unavailable_minutes = (datetime.now() - self._cwu_temp_unavailable_since).total_seconds() / 60
                if unavailable_minutes >= CWU_SENSOR_UNAVAILABLE_TIMEOUT:
                    self._log_action(
                        f"CWU sensor unavailable for {unavailable_minutes:.0f} minutes - entering safe mode"
                    )
                    # Summer mode uses different safe mode (CWU only, no floor)
                    if self._operating_mode == MODE_SUMMER:
                        await self._async_send_notification(
                            "CWU Controller - Safe Mode (Summer)",
                            f"CWU temperature sensor has been unavailable for {unavailable_minutes:.0f} minutes.\n\n"
                            f"Entering safe mode - enabling CWU heater.\n"
                            f"Floor heating remains OFF (summer mode).\n"
                            f"Normal control will resume when sensors recover."
                        )
                        await self._enter_summer_safe_mode()
                    else:
                        await self._async_send_notification(
                            "CWU Controller - Safe Mode",
                            f"CWU temperature sensor has been unavailable for {unavailable_minutes:.0f} minutes.\n\n"
                            f"Entering safe mode - heat pump will control both floor and CWU.\n"
                            f"Normal control will resume when sensors recover."
                        )
                        await self._enter_safe_mode()
                    self._change_state(STATE_SAFE_MODE)
                    return
        else:
            # Sensor is available, clear the unavailable timestamp
            self._cwu_temp_unavailable_since = None

        # Route based on operating mode
        if self._operating_mode == MODE_WINTER:
            await self._run_winter_mode_logic(cwu_urgency, floor_urgency, cwu_temp, salon_temp)
            return
        elif self._operating_mode == MODE_SUMMER:
            await self._run_summer_mode_logic(cwu_urgency, cwu_temp)
            return

        # Default: Broken heater mode (original logic)
        await self._run_broken_heater_mode_logic(
            cwu_urgency, floor_urgency, fake_heating, cwu_temp, salon_temp
        )

    async def _run_broken_heater_mode_logic(
        self,
        cwu_urgency: int,
        floor_urgency: int,
        fake_heating: bool,
        cwu_temp: float | None,
        salon_temp: float | None,
    ) -> None:
        """Run control logic for broken heater mode (original behavior)."""

        # Handle fake heating detection - first detection
        if fake_heating and self._current_state in (STATE_HEATING_CWU, STATE_EMERGENCY_CWU):
            self._change_state(STATE_FAKE_HEATING_DETECTED)
            self._fake_heating_detected_at = datetime.now()
            self._low_power_start = None  # Reset to prevent duplicate detection
            await self._async_set_water_heater_mode(WH_MODE_OFF)
            await self._async_send_notification(
                "CWU Controller Alert",
                f"Fake heating detected! Power < 10W for {FAKE_HEATING_DETECTION_TIME}+ minutes. "
                f"CWU temp: {cwu_temp}°C. Waiting {FAKE_HEATING_RESTART_WAIT} min before restart..."
            )
            self._log_action(f"Fake heating detected - CWU OFF, waiting {FAKE_HEATING_RESTART_WAIT} min")
            return

        # Handle fake heating restart - wait period complete
        if self._current_state == STATE_FAKE_HEATING_DETECTED and self._fake_heating_detected_at:
            elapsed = (datetime.now() - self._fake_heating_detected_at).total_seconds() / 60
            if elapsed >= FAKE_HEATING_RESTART_WAIT:
                self._change_state(STATE_FAKE_HEATING_RESTARTING)
                self._log_action("Fake heating wait complete - restarting CWU...")
                await self._async_set_water_heater_mode(WH_MODE_HEAT_PUMP)
                self._low_power_start = None
                self._fake_heating_detected_at = None
                self._change_state(STATE_HEATING_CWU)
                self._log_action("CWU restarted after fake heating recovery")
            return

        # Handle pause state
        if self._current_state == STATE_PAUSE:
            if self._is_pause_complete():
                self._pause_start = None
                # Resume CWU heating - start new session
                await self._async_set_water_heater_mode(WH_MODE_HEAT_PUMP)
                self._change_state(STATE_HEATING_CWU)
                self._cwu_heating_start = datetime.now()
                # Get session start temp - from cache or fetch directly
                cwu_start_temp = self._last_known_cwu_temp
                if cwu_start_temp is None:
                    cwu_start_temp = self._get_sensor_value(self.config.get("cwu_temp_sensor"))
                self._cwu_session_start_temp = cwu_start_temp
                self._log_action(f"Pause complete, starting new CWU session (temp: {cwu_start_temp}°C)")
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
            # During heating window: heat CWU if below target
            if cwu_temp is not None and cwu_temp < winter_target:
                if self._current_state != STATE_HEATING_CWU:
                    await self._switch_to_cwu()
                    self._change_state(STATE_HEATING_CWU)
                    self._cwu_heating_start = now
                    self._log_action(
                        f"Winter mode: Heating window started, CWU {cwu_temp}°C -> target {winter_target}°C"
                    )
                # Continue heating until target reached (no session limit in winter mode)
                return
            elif cwu_temp is not None and cwu_temp >= winter_target:
                # Target reached during window - switch to floor
                if self._current_state == STATE_HEATING_CWU:
                    self._log_action(
                        f"Winter mode: CWU target reached ({cwu_temp}°C >= {winter_target}°C)"
                    )
                    await self._switch_to_floor()
                    self._change_state(STATE_HEATING_FLOOR)
                    self._cwu_heating_start = None
                return

        # Outside heating window: only heat CWU in emergency (below threshold)
        if cwu_temp is not None and cwu_temp < emergency_threshold:
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
        if self._current_state not in (STATE_HEATING_FLOOR, STATE_HEATING_CWU, STATE_EMERGENCY_CWU):
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

            # First turn off floor heating
            await self._async_set_climate(False)
            self._log_action("Floor heating off, waiting 60s...")
            await asyncio.sleep(60)  # Wait 1 minute for pump to settle

            # Then enable CWU
            await self._async_set_water_heater_mode(WH_MODE_HEAT_PUMP)
            self._log_action("CWU heating enabled")
        finally:
            self._transition_in_progress = False

        # Track session start - get current temp from sensor if not cached
        cwu_temp = self._last_known_cwu_temp
        if cwu_temp is None:
            cwu_temp = self._get_sensor_value(self.config.get("cwu_temp_sensor"))
        self._cwu_session_start_temp = cwu_temp

    async def _switch_to_floor(self) -> None:
        """Switch to floor heating mode with proper delays."""
        if self._transition_in_progress:
            self._log_action("Switch to floor skipped - transition in progress")
            return

        self._transition_in_progress = True
        try:
            self._log_action("Switching to floor heating...")

            # First turn off CWU
            await self._async_set_water_heater_mode(WH_MODE_OFF)
            self._log_action("CWU off, waiting 60s...")
            await asyncio.sleep(60)  # Wait 1 minute for pump to settle

            # Then enable floor heating
            await self._async_set_climate(True)
            self._log_action("Floor heating enabled")

            # Clear CWU session
            self._cwu_session_start_temp = None
        finally:
            self._transition_in_progress = False

    async def _enter_safe_mode(self) -> None:
        """Enter safe mode - hand control back to heat pump.

        Turns on both floor heating and CWU, letting the heat pump
        decide what to do. Used when sensors are unavailable.
        """
        if self._transition_in_progress:
            self._log_action("Enter safe mode skipped - transition in progress")
            return

        self._transition_in_progress = True
        try:
            self._log_action("Entering safe mode - enabling both floor and CWU")

            # Turn on both - let heat pump decide
            # Add delay between commands to avoid cloud API issues
            await self._async_set_climate(True)
            self._log_action("Floor heating enabled, waiting 60s...")
            await asyncio.sleep(60)
            await self._async_set_water_heater_mode(WH_MODE_HEAT_PUMP)

            self._log_action("Safe mode active - heat pump in control")
        finally:
            self._transition_in_progress = False
