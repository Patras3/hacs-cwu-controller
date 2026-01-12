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

from .const import (
    DOMAIN,
    MANUFACTURER,
    STATE_HEATING_CWU,
    STATE_HEATING_FLOOR,
    STATE_EMERGENCY_CWU,
    STATE_EMERGENCY_FLOOR,
    STATE_PUMP_CWU,
    STATE_PUMP_FLOOR,
    STATE_PUMP_BOTH,
)
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
        # Electric heater sensors (from BSB-LAN) - each has its own history
        ElectricHeaterCwuBinarySensor(coordinator, entry),
        ElectricHeaterFloor1BinarySensor(coordinator, entry),
        ElectricHeaterFloor2BinarySensor(coordinator, entry),
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
            "sw_version": "6.0.0",
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
        # Include Heat Pump mode states (pump_cwu, pump_both)
        return state in (STATE_HEATING_CWU, STATE_EMERGENCY_CWU, STATE_PUMP_CWU, STATE_PUMP_BOTH)


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
        # Include Heat Pump mode states (pump_floor, pump_both)
        return state in (STATE_HEATING_FLOOR, STATE_EMERGENCY_FLOOR, STATE_PUMP_FLOOR, STATE_PUMP_BOTH)


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


# =============================================================================
# Electric Heater Binary Sensors (from BSB-LAN with history)
# =============================================================================

class ElectricHeaterCwuBinarySensor(CWUControllerBaseBinarySensor):
    """Binary sensor showing if CWU electric heater is on (BSB-LAN param 8821)."""

    def __init__(self, coordinator: CWUControllerCoordinator, entry: ConfigEntry) -> None:
        """Initialize sensor."""
        super().__init__(coordinator, entry, "electric_heater_cwu", "Electric Heater CWU")
        self._attr_device_class = BinarySensorDeviceClass.HEAT
        self._attr_icon = "mdi:water-boiler-alert"

    @property
    def is_on(self) -> bool:
        """Return if CWU electric heater is on."""
        if self.coordinator.data is None:
            return False
        bsb = self.coordinator.data.get("bsb_lan", {})
        state = bsb.get("electric_heater_cwu_state", "Off")
        return state.lower() == "on"

    @property
    def extra_state_attributes(self) -> dict:
        """Return extra state attributes."""
        if self.coordinator.data is None:
            return {}
        bsb = self.coordinator.data.get("bsb_lan", {})
        return {
            "run_hours": bsb.get("electric_heater_cwu_hours"),
            "start_count": bsb.get("electric_heater_cwu_starts"),
            "bsb_param": 8821,
        }


class ElectricHeaterFloor1BinarySensor(CWUControllerBaseBinarySensor):
    """Binary sensor showing if floor electric heater 1 is on (BSB-LAN param 8402)."""

    def __init__(self, coordinator: CWUControllerCoordinator, entry: ConfigEntry) -> None:
        """Initialize sensor."""
        super().__init__(coordinator, entry, "electric_heater_floor_1", "Electric Heater Floor 1")
        self._attr_device_class = BinarySensorDeviceClass.HEAT
        self._attr_icon = "mdi:heating-coil"

    @property
    def is_on(self) -> bool:
        """Return if floor electric heater 1 is on."""
        if self.coordinator.data is None:
            return False
        bsb = self.coordinator.data.get("bsb_lan", {})
        state = bsb.get("electric_heater_floor_1_state", "Off")
        return state.lower() == "on"

    @property
    def extra_state_attributes(self) -> dict:
        """Return extra state attributes."""
        if self.coordinator.data is None:
            return {}
        bsb = self.coordinator.data.get("bsb_lan", {})
        return {
            "run_hours": bsb.get("electric_heater_floor_hours"),
            "start_count": bsb.get("electric_heater_floor_starts"),
            "bsb_param": 8402,
        }


class ElectricHeaterFloor2BinarySensor(CWUControllerBaseBinarySensor):
    """Binary sensor showing if floor electric heater 2 is on (BSB-LAN param 8403)."""

    def __init__(self, coordinator: CWUControllerCoordinator, entry: ConfigEntry) -> None:
        """Initialize sensor."""
        super().__init__(coordinator, entry, "electric_heater_floor_2", "Electric Heater Floor 2")
        self._attr_device_class = BinarySensorDeviceClass.HEAT
        self._attr_icon = "mdi:heating-coil"

    @property
    def is_on(self) -> bool:
        """Return if floor electric heater 2 is on."""
        if self.coordinator.data is None:
            return False
        bsb = self.coordinator.data.get("bsb_lan", {})
        state = bsb.get("electric_heater_floor_2_state", "Off")
        return state.lower() == "on"

    @property
    def extra_state_attributes(self) -> dict:
        """Return extra state attributes."""
        if self.coordinator.data is None:
            return {}
        bsb = self.coordinator.data.get("bsb_lan", {})
        return {
            "run_hours": bsb.get("electric_heater_floor_hours"),
            "start_count": bsb.get("electric_heater_floor_starts"),
            "bsb_param": 8403,
        }
