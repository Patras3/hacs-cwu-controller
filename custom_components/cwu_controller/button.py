"""Button entities for CWU Controller - for testing actions."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
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
    """Set up button entities."""
    coordinator: CWUControllerCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = [
        TestCWUOnButton(coordinator, entry),
        TestCWUOffButton(coordinator, entry),
        TestFloorOnButton(coordinator, entry),
        TestFloorOffButton(coordinator, entry),
        ForceCWU3HButton(coordinator, entry),
        ForceCWU6HButton(coordinator, entry),
        ForceFloor3HButton(coordinator, entry),
        ForceFloor6HButton(coordinator, entry),
        ForceAutoButton(coordinator, entry),
        # Floor boost buttons (session and cancel only - use service for timed boost)
        FloorBoostSessionButton(coordinator, entry),
        FloorBoostCancelButton(coordinator, entry),
    ]

    async_add_entities(entities)


class CWUControllerBaseButton(CoordinatorEntity, ButtonEntity):
    """Base button for CWU Controller."""

    def __init__(
        self,
        coordinator: CWUControllerCoordinator,
        entry: ConfigEntry,
        button_type: str,
        name: str,
    ) -> None:
        """Initialize button."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_{button_type}"
        self._attr_name = f"CWU Controller {name}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": "CWU Controller",
            "manufacturer": MANUFACTURER,
            "model": "Smart Heat Pump Controller",
            "sw_version": "6.0.0",
        }


class TestCWUOnButton(CWUControllerBaseButton):
    """Button to test turning CWU on."""

    def __init__(self, coordinator: CWUControllerCoordinator, entry: ConfigEntry) -> None:
        """Initialize button."""
        super().__init__(coordinator, entry, "test_cwu_on", "Test CWU ON")
        self._attr_icon = "mdi:water-boiler"

    async def async_press(self) -> None:
        """Handle button press."""
        await self.coordinator.async_test_cwu_on()


class TestCWUOffButton(CWUControllerBaseButton):
    """Button to test turning CWU off."""

    def __init__(self, coordinator: CWUControllerCoordinator, entry: ConfigEntry) -> None:
        """Initialize button."""
        super().__init__(coordinator, entry, "test_cwu_off", "Test CWU OFF")
        self._attr_icon = "mdi:water-boiler-off"

    async def async_press(self) -> None:
        """Handle button press."""
        await self.coordinator.async_test_cwu_off()


class TestFloorOnButton(CWUControllerBaseButton):
    """Button to test turning floor heating on."""

    def __init__(self, coordinator: CWUControllerCoordinator, entry: ConfigEntry) -> None:
        """Initialize button."""
        super().__init__(coordinator, entry, "test_floor_on", "Test Floor ON")
        self._attr_icon = "mdi:heating-coil"

    async def async_press(self) -> None:
        """Handle button press."""
        await self.coordinator.async_test_floor_on()


class TestFloorOffButton(CWUControllerBaseButton):
    """Button to test turning floor heating off."""

    def __init__(self, coordinator: CWUControllerCoordinator, entry: ConfigEntry) -> None:
        """Initialize button."""
        super().__init__(coordinator, entry, "test_floor_off", "Test Floor OFF")
        self._attr_icon = "mdi:radiator-off"

    async def async_press(self) -> None:
        """Handle button press."""
        await self.coordinator.async_test_floor_off()


class ForceCWU3HButton(CWUControllerBaseButton):
    """Button to force CWU heating for 3 hours."""

    def __init__(self, coordinator: CWUControllerCoordinator, entry: ConfigEntry) -> None:
        """Initialize button."""
        super().__init__(coordinator, entry, "force_cwu_3h", "Force CWU 3h")
        self._attr_icon = "mdi:water-boiler-alert"

    async def async_press(self) -> None:
        """Handle button press - 3 hours = 180 minutes."""
        await self.coordinator.async_force_cwu(180)


class ForceCWU6HButton(CWUControllerBaseButton):
    """Button to force CWU heating for 6 hours (with automatic pause after 3h)."""

    def __init__(self, coordinator: CWUControllerCoordinator, entry: ConfigEntry) -> None:
        """Initialize button."""
        super().__init__(coordinator, entry, "force_cwu_6h", "Force CWU 6h")
        self._attr_icon = "mdi:water-boiler-alert"

    async def async_press(self) -> None:
        """Handle button press - 6 hours = 360 minutes with pause handling."""
        await self.coordinator.async_force_cwu(360)


class ForceFloor3HButton(CWUControllerBaseButton):
    """Button to force floor heating for 3 hours."""

    def __init__(self, coordinator: CWUControllerCoordinator, entry: ConfigEntry) -> None:
        """Initialize button."""
        super().__init__(coordinator, entry, "force_floor_3h", "Force Floor 3h")
        self._attr_icon = "mdi:home-thermometer"

    async def async_press(self) -> None:
        """Handle button press - 3 hours = 180 minutes."""
        await self.coordinator.async_force_floor(180)


class ForceFloor6HButton(CWUControllerBaseButton):
    """Button to force floor heating for 6 hours."""

    def __init__(self, coordinator: CWUControllerCoordinator, entry: ConfigEntry) -> None:
        """Initialize button."""
        super().__init__(coordinator, entry, "force_floor_6h", "Force Floor 6h")
        self._attr_icon = "mdi:home-thermometer"

    async def async_press(self) -> None:
        """Handle button press - 6 hours = 360 minutes."""
        await self.coordinator.async_force_floor(360)


class ForceAutoButton(CWUControllerBaseButton):
    """Button to cancel manual override and return to auto mode."""

    def __init__(self, coordinator: CWUControllerCoordinator, entry: ConfigEntry) -> None:
        """Initialize button."""
        super().__init__(coordinator, entry, "force_auto", "Force Auto")
        self._attr_icon = "mdi:autorenew"

    async def async_press(self) -> None:
        """Handle button press - cancel override and let controller decide."""
        await self.coordinator.async_force_auto()


class FloorBoostSessionButton(CWUControllerBaseButton):
    """Button to boost floor heating until session ends."""

    def __init__(self, coordinator: CWUControllerCoordinator, entry: ConfigEntry) -> None:
        """Initialize button."""
        super().__init__(coordinator, entry, "floor_boost_session", "Floor Boost Session")
        self._attr_icon = "mdi:radiator"

    async def async_press(self) -> None:
        """Handle button press - boost until floor heating session ends."""
        await self.coordinator.async_floor_boost_session()


class FloorBoostCancelButton(CWUControllerBaseButton):
    """Button to cancel floor boost and restore original settings."""

    def __init__(self, coordinator: CWUControllerCoordinator, entry: ConfigEntry) -> None:
        """Initialize button."""
        super().__init__(coordinator, entry, "floor_boost_cancel", "Floor Boost Cancel")
        self._attr_icon = "mdi:radiator-off"

    async def async_press(self) -> None:
        """Handle button press - cancel boost and restore settings."""
        await self.coordinator.async_floor_boost_cancel()
