"""Switch entities for CWU Controller."""
from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
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
    """Set up switch entities."""
    coordinator: CWUControllerCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = [
        CWUControllerEnabledSwitch(coordinator, entry),
    ]

    async_add_entities(entities)


class CWUControllerEnabledSwitch(CoordinatorEntity, SwitchEntity):
    """Switch to enable/disable the controller."""

    def __init__(
        self,
        coordinator: CWUControllerCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize switch."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_enabled"
        self._attr_name = "CWU Controller Enabled"
        self._attr_icon = "mdi:power"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": "CWU Controller",
            "manufacturer": MANUFACTURER,
            "model": "Smart Heat Pump Controller",
            "sw_version": "4.0.3",
        }

    @property
    def is_on(self) -> bool:
        """Return if controller is enabled."""
        return self.coordinator.is_enabled

    async def async_turn_on(self, **kwargs) -> None:
        """Enable the controller."""
        await self.coordinator.async_enable()
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        """Disable the controller."""
        await self.coordinator.async_disable()
        self.async_write_ha_state()
