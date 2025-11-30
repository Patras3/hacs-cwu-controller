"""Sensor entities for CWU Controller."""
from __future__ import annotations

from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature, UnitOfPower, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import CWUControllerCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensor entities."""
    coordinator: CWUControllerCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = [
        CWUControllerStateSensor(coordinator, entry),
        CWUUrgencySensor(coordinator, entry),
        FloorUrgencySensor(coordinator, entry),
        AveragePowerSensor(coordinator, entry),
        CWUHeatingTimeSensor(coordinator, entry),
        CWUTargetTempSensor(coordinator, entry),
    ]

    async_add_entities(entities)


class CWUControllerBaseSensor(CoordinatorEntity, SensorEntity):
    """Base sensor for CWU Controller."""

    def __init__(
        self,
        coordinator: CWUControllerCoordinator,
        entry: ConfigEntry,
        sensor_type: str,
        name: str,
    ) -> None:
        """Initialize sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_{sensor_type}"
        self._attr_name = f"CWU Controller {name}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": "CWU Controller",
            "manufacturer": MANUFACTURER,
            "model": "Smart Heat Pump Controller",
            "sw_version": "1.0.0",
        }


class CWUControllerStateSensor(CWUControllerBaseSensor):
    """Sensor showing current controller state."""

    def __init__(self, coordinator: CWUControllerCoordinator, entry: ConfigEntry) -> None:
        """Initialize sensor."""
        super().__init__(coordinator, entry, "state", "State")
        self._attr_icon = "mdi:state-machine"

    @property
    def native_value(self) -> str | None:
        """Return current state."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get("controller_state", "unknown")

    @property
    def extra_state_attributes(self) -> dict:
        """Return extra state attributes."""
        if self.coordinator.data is None:
            return {}

        data = self.coordinator.data
        return {
            "cwu_temp": data.get("cwu_temp"),
            "salon_temp": data.get("salon_temp"),
            "bedroom_temp": data.get("bedroom_temp"),
            "kids_temp": data.get("kids_temp"),
            "power": data.get("power"),
            "water_heater_state": data.get("wh_state"),
            "climate_state": data.get("climate_state"),
            "enabled": data.get("enabled"),
            "manual_override": data.get("manual_override"),
            "fake_heating_detected": data.get("fake_heating"),
            "state_history": data.get("state_history", []),
            "action_history": data.get("action_history", []),
            # CWU Session tracking
            "cwu_session_start_time": data.get("cwu_session_start_time"),
            "cwu_session_start_temp": data.get("cwu_session_start_temp"),
            "cwu_heating_minutes": data.get("cwu_heating_minutes", 0),
        }


class CWUUrgencySensor(CWUControllerBaseSensor):
    """Sensor showing CWU heating urgency."""

    def __init__(self, coordinator: CWUControllerCoordinator, entry: ConfigEntry) -> None:
        """Initialize sensor."""
        super().__init__(coordinator, entry, "cwu_urgency", "CWU Urgency")
        self._attr_icon = "mdi:water-thermometer"

    @property
    def native_value(self) -> int | None:
        """Return urgency level."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get("cwu_urgency", 0)

    @property
    def extra_state_attributes(self) -> dict:
        """Return extra attributes."""
        urgency = self.native_value
        levels = {0: "None", 1: "Low", 2: "Medium", 3: "High", 4: "Critical"}
        return {
            "level_name": levels.get(urgency, "Unknown"),
            "cwu_temp": self.coordinator.data.get("cwu_temp") if self.coordinator.data else None,
        }


class FloorUrgencySensor(CWUControllerBaseSensor):
    """Sensor showing floor heating urgency."""

    def __init__(self, coordinator: CWUControllerCoordinator, entry: ConfigEntry) -> None:
        """Initialize sensor."""
        super().__init__(coordinator, entry, "floor_urgency", "Floor Urgency")
        self._attr_icon = "mdi:home-thermometer"

    @property
    def native_value(self) -> int | None:
        """Return urgency level."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get("floor_urgency", 0)

    @property
    def extra_state_attributes(self) -> dict:
        """Return extra attributes."""
        urgency = self.native_value
        levels = {0: "None", 1: "Low", 2: "Medium", 3: "High", 4: "Critical"}
        return {
            "level_name": levels.get(urgency, "Unknown"),
            "salon_temp": self.coordinator.data.get("salon_temp") if self.coordinator.data else None,
            "bedroom_temp": self.coordinator.data.get("bedroom_temp") if self.coordinator.data else None,
        }


class AveragePowerSensor(CWUControllerBaseSensor):
    """Sensor showing average power consumption."""

    def __init__(self, coordinator: CWUControllerCoordinator, entry: ConfigEntry) -> None:
        """Initialize sensor."""
        super().__init__(coordinator, entry, "avg_power", "Average Power")
        self._attr_device_class = SensorDeviceClass.POWER
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = UnitOfPower.WATT
        self._attr_icon = "mdi:flash"

    @property
    def native_value(self) -> float | None:
        """Return average power."""
        if self.coordinator.data is None:
            return None
        return round(self.coordinator.data.get("avg_power", 0), 1)


class CWUHeatingTimeSensor(CWUControllerBaseSensor):
    """Sensor showing CWU heating time in current cycle."""

    def __init__(self, coordinator: CWUControllerCoordinator, entry: ConfigEntry) -> None:
        """Initialize sensor."""
        super().__init__(coordinator, entry, "cwu_heating_time", "CWU Heating Time")
        self._attr_device_class = SensorDeviceClass.DURATION
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = UnitOfTime.MINUTES
        self._attr_icon = "mdi:timer"

    @property
    def native_value(self) -> float | None:
        """Return heating time in minutes."""
        if self.coordinator.data is None:
            return None
        return round(self.coordinator.data.get("cwu_heating_minutes", 0), 1)

    @property
    def extra_state_attributes(self) -> dict:
        """Return extra attributes."""
        minutes = self.native_value or 0
        max_minutes = 170  # 2h50m
        return {
            "max_minutes": max_minutes,
            "remaining_minutes": max(0, max_minutes - minutes),
            "percentage": min(100, (minutes / max_minutes) * 100) if max_minutes > 0 else 0,
        }


class CWUTargetTempSensor(CWUControllerBaseSensor):
    """Sensor showing CWU target temperature from config."""

    def __init__(self, coordinator: CWUControllerCoordinator, entry: ConfigEntry) -> None:
        """Initialize sensor."""
        super().__init__(coordinator, entry, "cwu_target_temp", "CWU Target Temp")
        self._attr_device_class = SensorDeviceClass.TEMPERATURE
        self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        self._attr_icon = "mdi:thermometer-water"

    @property
    def native_value(self) -> float | None:
        """Return target temperature."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get("cwu_target_temp", 45.0)

    @property
    def extra_state_attributes(self) -> dict:
        """Return extra attributes."""
        if self.coordinator.data is None:
            return {}
        return {
            "cwu_min_temp": self.coordinator.data.get("cwu_min_temp"),
            "salon_target_temp": self.coordinator.data.get("salon_target_temp"),
        }
