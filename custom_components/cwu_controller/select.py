"""Select entities for CWU Controller."""
from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    MODE_BROKEN_HEATER,
    MODE_WINTER,
    MODE_SUMMER,
    OPERATING_MODES,
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


class OperatingModeSelect(CoordinatorEntity, RestoreEntity, SelectEntity):
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

    async def async_added_to_hass(self) -> None:
        """Restore previous state when entity is added to Home Assistant."""
        await super().async_added_to_hass()

        # Try to restore previous operating mode
        if (last_state := await self.async_get_last_state()) is not None:
            if last_state.state in OPERATING_MODES:
                await self.coordinator.async_set_operating_mode(last_state.state)

    @property
    def current_option(self) -> str | None:
        """Return the current selected option."""
        return self.coordinator.operating_mode

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        await self.coordinator.async_set_operating_mode(option)
        self.async_write_ha_state()
