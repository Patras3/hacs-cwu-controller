"""Energy tracking for CWU Controller.

Tracks energy consumption split by:
- CWU vs Floor heating
- Cheap vs Expensive tariff

Uses delta calculation from energy meter for accuracy.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Callable

from homeassistant.helpers.storage import Store

from .const import (
    STATE_HEATING_CWU,
    STATE_HEATING_FLOOR,
    STATE_EMERGENCY_CWU,
    STATE_EMERGENCY_FLOOR,
    STATE_FAKE_HEATING_DETECTED,
    STATE_FAKE_HEATING_RESTARTING,
    STATE_SAFE_MODE,
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
    """Tracks energy consumption for CWU and floor heating."""

    def __init__(
        self,
        hass: HomeAssistant,
        get_meter_value: Callable[[], float | None],
        get_current_state: Callable[[], str],
        is_cheap_tariff: Callable[[], bool],
    ) -> None:
        """Initialize energy tracker.

        Args:
            hass: Home Assistant instance
            get_meter_value: Callback to get current energy meter reading (kWh)
            get_current_state: Callback to get current controller state
            is_cheap_tariff: Callback to check if current tariff is cheap
        """
        self._hass = hass
        self._get_meter_value = get_meter_value
        self._get_current_state = get_current_state
        self._is_cheap_tariff = is_cheap_tariff

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
        self._last_meter_state: str | None = None
        self._last_meter_tariff_cheap: bool | None = None
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

    def _is_heating_state(self, state: str | None) -> bool:
        """Check if given state is an active heating state."""
        if state is None:
            return False
        return state in (
            STATE_HEATING_CWU, STATE_EMERGENCY_CWU,
            STATE_FAKE_HEATING_DETECTED, STATE_FAKE_HEATING_RESTARTING,
            STATE_HEATING_FLOOR, STATE_EMERGENCY_FLOOR,
            STATE_SAFE_MODE,
        )

    def _is_cwu_state(self, state: str | None) -> bool:
        """Check if given state is a CWU heating state."""
        if state is None:
            return False
        return state in (
            STATE_HEATING_CWU, STATE_EMERGENCY_CWU,
            STATE_FAKE_HEATING_DETECTED, STATE_FAKE_HEATING_RESTARTING,
        )

    def _is_floor_state(self, state: str | None) -> bool:
        """Check if given state is a floor heating state."""
        if state is None:
            return False
        return state in (STATE_HEATING_FLOOR, STATE_EMERGENCY_FLOOR)

    def _attribute_energy(self, kwh: float, state: str, is_cheap: bool) -> None:
        """Attribute energy consumption to the appropriate counter."""
        if kwh <= 0:
            return

        if self._is_cwu_state(state):
            if is_cheap:
                self._cwu_cheap_today += kwh
            else:
                self._cwu_expensive_today += kwh
            _LOGGER.debug(
                "Attributed %.4f kWh to CWU (%s tariff)",
                kwh, "cheap" if is_cheap else "expensive"
            )
        elif self._is_floor_state(state):
            if is_cheap:
                self._floor_cheap_today += kwh
            else:
                self._floor_expensive_today += kwh
            _LOGGER.debug(
                "Attributed %.4f kWh to Floor (%s tariff)",
                kwh, "cheap" if is_cheap else "expensive"
            )
        elif state == STATE_SAFE_MODE:
            # Safe mode - split 50/50 between CWU and floor
            half_kwh = kwh / 2
            if is_cheap:
                self._cwu_cheap_today += half_kwh
                self._floor_cheap_today += half_kwh
            else:
                self._cwu_expensive_today += half_kwh
                self._floor_expensive_today += half_kwh
            _LOGGER.debug(
                "Attributed %.4f kWh to Safe Mode (50/50 split, %s tariff)",
                kwh, "cheap" if is_cheap else "expensive"
            )

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
        """Update energy consumption tracking using energy meter delta."""
        if not self._data_loaded:
            _LOGGER.debug("Energy tracking skipped - waiting for persisted data to load")
            return

        now = datetime.now()
        self._handle_day_rollover(now)

        # Get current readings
        current_meter = self._get_meter_value()
        if current_meter is None:
            _LOGGER.debug("Energy meter unavailable, skipping tracking")
            return

        is_cheap = self._is_cheap_tariff()
        current_state = self._get_current_state()

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

        # Calculate delta
        delta_kwh = current_meter - self._last_meter_reading

        # Sanity checks
        if delta_kwh < 0:
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
                "Unusually large energy delta: %.3f kWh in %.2f hours. Skipping.",
                delta_kwh, time_diff
            )
            self._last_meter_reading = current_meter
            self._last_meter_time = now
            self._last_meter_state = current_state
            self._last_meter_tariff_cheap = is_cheap
            return

        # Attribute energy
        if delta_kwh > 0:
            if self._is_heating_state(current_state):
                if current_state == self._last_meter_state:
                    self._attribute_energy(delta_kwh, current_state, is_cheap)
                elif self._last_meter_state is None:
                    self._attribute_energy(delta_kwh, current_state, is_cheap)
                else:
                    _LOGGER.debug(
                        "State changed (%s -> %s), attributing %.4f kWh to current state",
                        self._last_meter_state, current_state, delta_kwh
                    )
                    self._attribute_energy(delta_kwh, current_state, is_cheap)
            else:
                if self._is_heating_state(self._last_meter_state):
                    prev_cheap = self._last_meter_tariff_cheap if self._last_meter_tariff_cheap is not None else is_cheap
                    _LOGGER.debug(
                        "Heating stopped, attributing final %.4f kWh to %s",
                        delta_kwh, self._last_meter_state
                    )
                    self._attribute_energy(delta_kwh, self._last_meter_state, prev_cheap)
                else:
                    _LOGGER.debug("Idle energy delta: %.4f kWh (standby, not attributed)", delta_kwh)

        # Update tracking state
        self._last_meter_reading = current_meter
        self._last_meter_time = now
        self._last_meter_state = current_state
        self._last_meter_tariff_cheap = is_cheap

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
            self._last_meter_state = data.get("last_meter_state")
            self._last_meter_tariff_cheap = data.get("last_meter_tariff_cheap")
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
            "last_meter_state": self._last_meter_state,
            "last_meter_tariff_cheap": self._last_meter_tariff_cheap,
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
