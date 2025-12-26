"""Binary sensor entities for CWU Controller."""
from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorDeviceClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER, STATE_HEATING_CWU, STATE_EMERGENCY_CWU
from .coordinator import CWUControllerCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up binary sensor entities."""
    coordinator: CWUControllerCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = [
        CWUHeatingBinarySensor(coordinator, entry),
        FloorHeatingBinarySensor(coordinator, entry),
        FakeHeatingBinarySensor(coordinator, entry),
        ManualOverrideBinarySensor(coordinator, entry),
        BsbLanAvailableBinarySensor(coordinator, entry),
    ]

    async_add_entities(entities)


class CWUControllerBaseBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Base binary sensor for CWU Controller."""

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
            "sw_version": "4.0.5",
        }


class CWUHeatingBinarySensor(CWUControllerBaseBinarySensor):
    """Binary sensor showing if CWU is being heated."""

    def __init__(self, coordinator: CWUControllerCoordinator, entry: ConfigEntry) -> None:
        """Initialize sensor."""
        super().__init__(coordinator, entry, "cwu_heating", "CWU Heating")
        self._attr_device_class = BinarySensorDeviceClass.HEAT
        self._attr_icon = "mdi:water-boiler"

    @property
    def is_on(self) -> bool:
        """Return if CWU is being heated."""
        if self.coordinator.data is None:
            return False
        state = self.coordinator.data.get("controller_state", "")
        return state in (STATE_HEATING_CWU, STATE_EMERGENCY_CWU)


class FloorHeatingBinarySensor(CWUControllerBaseBinarySensor):
    """Binary sensor showing if floor heating is active."""

    def __init__(self, coordinator: CWUControllerCoordinator, entry: ConfigEntry) -> None:
        """Initialize sensor."""
        super().__init__(coordinator, entry, "floor_heating", "Floor Heating")
        self._attr_device_class = BinarySensorDeviceClass.HEAT
        self._attr_icon = "mdi:heating-coil"

    @property
    def is_on(self) -> bool:
        """Return if floor heating is active."""
        if self.coordinator.data is None:
            return False
        state = self.coordinator.data.get("controller_state", "")
        return state in ("heating_floor", "emergency_floor")


class FakeHeatingBinarySensor(CWUControllerBaseBinarySensor):
    """Binary sensor showing if fake heating is detected."""

    def __init__(self, coordinator: CWUControllerCoordinator, entry: ConfigEntry) -> None:
        """Initialize sensor."""
        super().__init__(coordinator, entry, "fake_heating", "Fake Heating Detected")
        self._attr_device_class = BinarySensorDeviceClass.PROBLEM
        self._attr_icon = "mdi:alert"

    @property
    def is_on(self) -> bool:
        """Return if fake heating is detected."""
        if self.coordinator.data is None:
            return False
        return self.coordinator.data.get("fake_heating", False)


class ManualOverrideBinarySensor(CWUControllerBaseBinarySensor):
    """Binary sensor showing if manual override is active."""

    def __init__(self, coordinator: CWUControllerCoordinator, entry: ConfigEntry) -> None:
        """Initialize sensor."""
        super().__init__(coordinator, entry, "manual_override", "Manual Override")
        self._attr_icon = "mdi:hand-back-right"

    @property
    def is_on(self) -> bool:
        """Return if manual override is active."""
        if self.coordinator.data is None:
            return False
        return self.coordinator.data.get("manual_override", False)


class BsbLanAvailableBinarySensor(CWUControllerBaseBinarySensor):
    """Binary sensor showing if BSB-LAN is available."""

    def __init__(self, coordinator: CWUControllerCoordinator, entry: ConfigEntry) -> None:
        """Initialize sensor."""
        super().__init__(coordinator, entry, "bsb_lan_available", "BSB-LAN Available")
        self._attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
        self._attr_icon = "mdi:lan-connect"

    @property
    def is_on(self) -> bool:
        """Return if BSB-LAN is available."""
        if self.coordinator.data is None:
            return False
        return self.coordinator.data.get("bsb_lan_available", False)

    @property
    def extra_state_attributes(self) -> dict:
        """Return extra state attributes."""
        return {
            "control_source": self.coordinator.control_source,
        }
