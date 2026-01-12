"""Energy tracking for CWU Controller.

Tracks energy consumption split by:
- CWU vs Floor heating
- Cheap vs Expensive tariff

Uses energy meter delta combined with BSB-LAN heater state detection.
Electric heaters have known constant power, so we can calculate their
exact consumption. Remaining energy is attributed based on compressor target.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Callable

from homeassistant.helpers.storage import Store

from .const import (
    UPDATE_INTERVAL,
    HEATER_POWER_CWU,
    HEATER_POWER_FLOOR_1,
    HEATER_POWER_FLOOR_2,
    COMPRESSOR_TARGET_CWU,
    COMPRESSOR_TARGET_FLOOR,
    COMPRESSOR_TARGET_IDLE,
    ENERGY_DELTA_ANOMALY_THRESHOLD,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

# Storage configuration
STORAGE_VERSION = 1
STORAGE_KEY = "cwu_controller_energy_data"
ENERGY_SAVE_INTERVAL = 300  # Save every 5 minutes


class EnergyTracker:
    """Tracks energy consumption for CWU and floor heating.

    Attribution logic:
    1. Read delta from energy meter (kWh consumed since last check)
    2. Calculate heater consumption using known power constants:
       - CWU heater: 3.3 kW when ON
       - Floor heater 1: 3.0 kW when ON
       - Floor heater 2: 3.0 kW when ON
    3. Attribute heater energy to respective category
    4. Remaining energy (compressor + pumps) attributed by compressor target:
       - If compressor targeting CWU → CWU
       - If compressor targeting floor or idle → Floor
    """

    def __init__(
        self,
        hass: HomeAssistant,
        get_meter_value: Callable[[], float | None],
        get_current_state: Callable[[], str],
        is_cheap_tariff: Callable[[], bool],
        get_heater_states: Callable[[], tuple[bool, bool, bool]],
        get_compressor_target: Callable[[], str],
    ) -> None:
        """Initialize energy tracker.

        Args:
            hass: Home Assistant instance
            get_meter_value: Callback to get current energy meter reading (kWh)
            get_current_state: Callback to get current controller state
            is_cheap_tariff: Callback to check if current tariff is cheap
            get_heater_states: Callback to get (cwu_on, floor1_on, floor2_on) tuple
            get_compressor_target: Callback to get compressor target (cwu/floor/idle)
        """
        self._hass = hass
        self._get_meter_value = get_meter_value
        self._get_current_state = get_current_state
        self._is_cheap_tariff = is_cheap_tariff
        self._get_heater_states = get_heater_states
        self._get_compressor_target = get_compressor_target

        # Energy counters - today
        self._cwu_cheap_today: float = 0.0
        self._cwu_expensive_today: float = 0.0
        self._floor_cheap_today: float = 0.0
        self._floor_expensive_today: float = 0.0

        # Energy counters - yesterday
        self._cwu_cheap_yesterday: float = 0.0
        self._cwu_expensive_yesterday: float = 0.0
        self._floor_cheap_yesterday: float = 0.0
        self._floor_expensive_yesterday: float = 0.0

        # Meter tracking state
        self._last_meter_reading: float | None = None
        self._last_meter_time: datetime | None = None
        self._meter_tracking_date: datetime | None = None

        # Daily report tracking
        self._last_daily_report_date: datetime | None = None

        # Persistence
        self._store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._last_save: datetime | None = None
        self._data_loaded: bool = False

    @property
    def energy_today(self) -> dict[str, float]:
        """Return today's energy consumption in kWh."""
        cwu_total = self._cwu_cheap_today + self._cwu_expensive_today
        floor_total = self._floor_cheap_today + self._floor_expensive_today
        return {
            "cwu": cwu_total,
            "cwu_cheap": self._cwu_cheap_today,
            "cwu_expensive": self._cwu_expensive_today,
            "floor": floor_total,
            "floor_cheap": self._floor_cheap_today,
            "floor_expensive": self._floor_expensive_today,
            "total": cwu_total + floor_total,
        }

    @property
    def energy_yesterday(self) -> dict[str, float]:
        """Return yesterday's energy consumption in kWh."""
        cwu_total = self._cwu_cheap_yesterday + self._cwu_expensive_yesterday
        floor_total = self._floor_cheap_yesterday + self._floor_expensive_yesterday
        return {
            "cwu": cwu_total,
            "cwu_cheap": self._cwu_cheap_yesterday,
            "cwu_expensive": self._cwu_expensive_yesterday,
            "floor": floor_total,
            "floor_cheap": self._floor_cheap_yesterday,
            "floor_expensive": self._floor_expensive_yesterday,
            "total": cwu_total + floor_total,
        }

    @property
    def data_loaded(self) -> bool:
        """Return whether persisted data has been loaded."""
        return self._data_loaded

    @property
    def last_daily_report_date(self) -> datetime | None:
        """Return last daily report date."""
        return self._last_daily_report_date

    @last_daily_report_date.setter
    def last_daily_report_date(self, value: datetime | None) -> None:
        """Set last daily report date."""
        self._last_daily_report_date = value

    def _add_cwu_energy(self, kwh: float, is_cheap: bool) -> None:
        """Add energy to CWU counter."""
        if kwh <= 0:
            return
        if is_cheap:
            self._cwu_cheap_today += kwh
        else:
            self._cwu_expensive_today += kwh

    def _add_floor_energy(self, kwh: float, is_cheap: bool) -> None:
        """Add energy to floor counter."""
        if kwh <= 0:
            return
        if is_cheap:
            self._floor_cheap_today += kwh
        else:
            self._floor_expensive_today += kwh

    def _handle_day_rollover(self, now: datetime) -> bool:
        """Handle day rollover for energy tracking. Returns True if rollover occurred."""
        if self._meter_tracking_date is None:
            self._meter_tracking_date = now
            return False

        if now.date() != self._meter_tracking_date.date():
            # New day - move today's stats to yesterday and reset
            self._cwu_cheap_yesterday = self._cwu_cheap_today
            self._cwu_expensive_yesterday = self._cwu_expensive_today
            self._floor_cheap_yesterday = self._floor_cheap_today
            self._floor_expensive_yesterday = self._floor_expensive_today
            self._cwu_cheap_today = 0.0
            self._cwu_expensive_today = 0.0
            self._floor_cheap_today = 0.0
            self._floor_expensive_today = 0.0

            _LOGGER.info(
                "Energy tracking day rollover - Yesterday CWU: %.2f kWh, Floor: %.2f kWh",
                self.energy_yesterday["cwu"],
                self.energy_yesterday["floor"]
            )
            self._last_save = None  # Force immediate save
            self._meter_tracking_date = now
            return True

        return False

    def update(self) -> None:
        """Update energy consumption tracking using energy meter delta.

        Attribution logic:
        1. Get delta from energy meter
        2. Calculate heater energy (heaters have known constant power)
        3. Subtract heater energy from delta
        4. Attribute remaining to compressor target
        """
        if not self._data_loaded:
            _LOGGER.debug("Energy tracking skipped - waiting for persisted data to load")
            return

        now = datetime.now()
        self._handle_day_rollover(now)

        # Get current meter reading
        current_meter = self._get_meter_value()
        if current_meter is None:
            _LOGGER.debug("Energy meter unavailable, skipping tracking")
            return

        # First reading ever - just store and return
        if self._last_meter_reading is None:
            self._last_meter_reading = current_meter
            self._last_meter_time = now
            _LOGGER.info("Energy meter tracking initialized: %.3f kWh", current_meter)
            return

        # Calculate delta and elapsed time
        delta_kwh = current_meter - self._last_meter_reading
        elapsed_seconds = (now - self._last_meter_time).total_seconds() if self._last_meter_time else UPDATE_INTERVAL

        # Sanity checks
        if delta_kwh < 0:
            _LOGGER.warning(
                "Energy meter went backwards (%.3f -> %.3f), resetting tracking",
                self._last_meter_reading, current_meter
            )
            self._last_meter_reading = current_meter
            self._last_meter_time = now
            return

        # Skip if too little time passed (avoid division issues)
        if elapsed_seconds < 10:
            _LOGGER.debug("Skipping energy update - only %.1fs elapsed", elapsed_seconds)
            return

        if delta_kwh > ENERGY_DELTA_ANOMALY_THRESHOLD:
            time_diff = elapsed_seconds / 3600
            _LOGGER.warning(
                "Unusually large energy delta: %.3f kWh in %.2f hours. Skipping.",
                delta_kwh, time_diff
            )
            self._last_meter_reading = current_meter
            self._last_meter_time = now
            return

        # Get current state info
        is_cheap = self._is_cheap_tariff()
        cwu_heater_on, floor1_on, floor2_on = self._get_heater_states()
        compressor_target = self._get_compressor_target()

        # Calculate heater energy consumption (heaters have constant power when ON)
        # Use actual elapsed time for accurate calculation
        interval_hours = elapsed_seconds / 3600  # Convert seconds to hours

        cwu_heater_kwh = HEATER_POWER_CWU * interval_hours if cwu_heater_on else 0.0
        floor1_kwh = HEATER_POWER_FLOOR_1 * interval_hours if floor1_on else 0.0
        floor2_kwh = HEATER_POWER_FLOOR_2 * interval_hours if floor2_on else 0.0

        total_heater_kwh = cwu_heater_kwh + floor1_kwh + floor2_kwh

        # Cap heater energy to meter delta (heaters can't consume more than meter shows)
        # This handles timing mismatch when heater turns on mid-interval
        if total_heater_kwh > delta_kwh and total_heater_kwh > 0:
            scale_factor = delta_kwh / total_heater_kwh
            cwu_heater_kwh *= scale_factor
            floor1_kwh *= scale_factor
            floor2_kwh *= scale_factor
            _LOGGER.debug(
                "Heater energy (%.4f kWh) exceeds meter delta (%.4f kWh). "
                "Scaling down by factor %.2f (heater likely turned on mid-interval).",
                total_heater_kwh, delta_kwh, scale_factor
            )
            total_heater_kwh = delta_kwh

        # Remaining energy is compressor + circulation pumps
        remaining_kwh = delta_kwh - total_heater_kwh

        # Log if there's significant energy to attribute
        if delta_kwh > 0.001:
            _LOGGER.debug(
                "Energy delta: %.4f kWh | Heaters: CWU=%.4f Floor=%.4f | "
                "Remaining: %.4f | Compressor target: %s | Tariff: %s",
                delta_kwh, cwu_heater_kwh, floor1_kwh + floor2_kwh,
                remaining_kwh, compressor_target, "cheap" if is_cheap else "expensive"
            )

        # Attribute heater energy
        if cwu_heater_kwh > 0:
            self._add_cwu_energy(cwu_heater_kwh, is_cheap)

        floor_heater_kwh = floor1_kwh + floor2_kwh
        if floor_heater_kwh > 0:
            self._add_floor_energy(floor_heater_kwh, is_cheap)

        # Attribute remaining energy (compressor + pumps) based on compressor target
        if remaining_kwh > 0:
            if compressor_target == COMPRESSOR_TARGET_CWU:
                self._add_cwu_energy(remaining_kwh, is_cheap)
            elif compressor_target == COMPRESSOR_TARGET_FLOOR:
                self._add_floor_energy(remaining_kwh, is_cheap)
            else:
                # COMPRESSOR_TARGET_IDLE - system standby/overhead
                # Split 50/50 between CWU and floor (fair attribution)
                self._add_cwu_energy(remaining_kwh / 2, is_cheap)
                self._add_floor_energy(remaining_kwh / 2, is_cheap)

        # Update tracking state
        self._last_meter_reading = current_meter
        self._last_meter_time = now

    async def async_load(self) -> None:
        """Load persisted energy data from storage."""
        try:
            data = await self._store.async_load()
            if data is None:
                _LOGGER.info("No stored energy data found, starting fresh")
                self._data_loaded = True
                return

            stored_date_str = data.get("date")
            today = datetime.now().date()

            if stored_date_str:
                stored_date = datetime.fromisoformat(stored_date_str).date()

                if stored_date == today:
                    # Same day - restore today's values
                    self._cwu_cheap_today = data.get("cwu_cheap_today", 0.0)
                    self._cwu_expensive_today = data.get("cwu_expensive_today", 0.0)
                    self._floor_cheap_today = data.get("floor_cheap_today", 0.0)
                    self._floor_expensive_today = data.get("floor_expensive_today", 0.0)
                    self._cwu_cheap_yesterday = data.get("cwu_cheap_yesterday", 0.0)
                    self._cwu_expensive_yesterday = data.get("cwu_expensive_yesterday", 0.0)
                    self._floor_cheap_yesterday = data.get("floor_cheap_yesterday", 0.0)
                    self._floor_expensive_yesterday = data.get("floor_expensive_yesterday", 0.0)
                    _LOGGER.info(
                        "Loaded energy data for today: CWU %.2f kWh, Floor %.2f kWh",
                        self.energy_today["cwu"], self.energy_today["floor"]
                    )
                elif stored_date == today - timedelta(days=1):
                    # Data from yesterday
                    self._cwu_cheap_yesterday = data.get("cwu_cheap_today", 0.0)
                    self._cwu_expensive_yesterday = data.get("cwu_expensive_today", 0.0)
                    self._floor_cheap_yesterday = data.get("floor_cheap_today", 0.0)
                    self._floor_expensive_yesterday = data.get("floor_expensive_today", 0.0)
                    _LOGGER.info(
                        "Day changed. Yesterday: CWU %.2f kWh, Floor %.2f kWh",
                        self.energy_yesterday["cwu"], self.energy_yesterday["floor"]
                    )
                else:
                    _LOGGER.info("Stored energy data is too old (%s), starting fresh", stored_date)

            # Restore meter tracking state
            last_meter = data.get("last_meter_reading")
            if last_meter is not None:
                self._last_meter_reading = last_meter
            last_meter_time_str = data.get("last_meter_time")
            if last_meter_time_str:
                self._last_meter_time = datetime.fromisoformat(last_meter_time_str)
            meter_date_str = data.get("meter_tracking_date")
            if meter_date_str:
                self._meter_tracking_date = datetime.fromisoformat(meter_date_str)

            report_date_str = data.get("last_daily_report_date")
            if report_date_str:
                self._last_daily_report_date = datetime.fromisoformat(report_date_str)

            self._data_loaded = True

        except Exception as e:
            _LOGGER.error("Failed to load energy data: %s", e)
            self._data_loaded = True

    async def async_save(self) -> None:
        """Save energy data to persistent storage."""
        now = datetime.now()
        data = {
            "date": now.isoformat(),
            "cwu_cheap_today": self._cwu_cheap_today,
            "cwu_expensive_today": self._cwu_expensive_today,
            "floor_cheap_today": self._floor_cheap_today,
            "floor_expensive_today": self._floor_expensive_today,
            "cwu_cheap_yesterday": self._cwu_cheap_yesterday,
            "cwu_expensive_yesterday": self._cwu_expensive_yesterday,
            "floor_cheap_yesterday": self._floor_cheap_yesterday,
            "floor_expensive_yesterday": self._floor_expensive_yesterday,
            "last_meter_reading": self._last_meter_reading,
            "last_meter_time": self._last_meter_time.isoformat() if self._last_meter_time else None,
            "meter_tracking_date": self._meter_tracking_date.isoformat() if self._meter_tracking_date else None,
            "last_daily_report_date": self._last_daily_report_date.isoformat() if self._last_daily_report_date else None,
        }

        try:
            await self._store.async_save(data)
            self._last_save = now
            _LOGGER.debug("Energy data saved: CWU %.2f kWh, Floor %.2f kWh",
                         self.energy_today["cwu"], self.energy_today["floor"])
        except Exception as e:
            _LOGGER.error("Failed to save energy data: %s", e)

    async def async_maybe_save(self) -> None:
        """Save energy data if enough time has passed since last save."""
        now = datetime.now()
        if self._last_save is None:
            await self.async_save()
            return

        if (now - self._last_save).total_seconds() >= ENERGY_SAVE_INTERVAL:
            await self.async_save()
