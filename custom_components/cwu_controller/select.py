"""Select entities for CWU Controller."""
from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    MODE_BROKEN_HEATER,
    MODE_WINTER,
    MODE_SUMMER,
)
from .coordinator import CWUControllerCoordinator


MODE_LABELS = {
    MODE_BROKEN_HEATER: "Broken Heater",
    MODE_WINTER: "Winter",
    MODE_SUMMER: "Summer",
}

MODE_OPTIONS = list(MODE_LABELS.keys())


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up CWU Controller select entities."""
    coordinator: CWUControllerCoordinator = hass.data[DOMAIN][entry.entry_id]

    async_add_entities([
        OperatingModeSelect(coordinator, entry),
    ])


class OperatingModeSelect(CoordinatorEntity, SelectEntity):
    """Select entity for operating mode."""

    def __init__(
        self,
        coordinator: CWUControllerCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the select entity."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_operating_mode"
        self._attr_name = "CWU Controller Operating Mode"
        self._attr_icon = "mdi:cog"
        self._attr_options = MODE_OPTIONS
        self._entry = entry

    @property
    def current_option(self) -> str | None:
        """Return the current selected option."""
        return self.coordinator.operating_mode

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        await self.coordinator.async_set_operating_mode(option)
        self.async_write_ha_state()
