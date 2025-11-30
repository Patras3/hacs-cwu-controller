"""CWU Controller integration for Home Assistant."""
from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components import frontend
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import CWUControllerCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.SWITCH, Platform.BINARY_SENSOR, Platform.BUTTON]

# Panel configuration
PANEL_URL_PATH = DOMAIN
PANEL_TITLE = "CWU Controller"
PANEL_ICON = "mdi:water-boiler"


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the CWU Controller component."""
    # Register static path for frontend files
    frontend_path = Path(__file__).parent / "frontend"

    await hass.http.async_register_static_paths([
        StaticPathConfig(
            url_path=f"/{DOMAIN}_panel",
            path=str(frontend_path),
            cache_headers=False
        )
    ])

    _LOGGER.info("CWU Controller frontend registered at /%s_panel", DOMAIN)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up CWU Controller from a config entry."""
    coordinator = CWUControllerCoordinator(hass, dict(entry.data))

    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    # Register services
    await _async_register_services(hass, coordinator)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register sidebar panel
    panel_url = f"/{DOMAIN}_panel/panel.html"

    frontend.async_register_built_in_panel(
        hass,
        component_name="iframe",
        sidebar_title=PANEL_TITLE,
        sidebar_icon=PANEL_ICON,
        frontend_url_path=PANEL_URL_PATH,
        config={"url": panel_url},
        require_admin=True,
    )

    _LOGGER.info("CWU Controller panel registered in sidebar")

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

        # Remove sidebar panel
        frontend.async_remove_panel(hass, PANEL_URL_PATH)
        _LOGGER.info("CWU Controller panel removed from sidebar")

    return unload_ok


async def _async_register_services(hass: HomeAssistant, coordinator: CWUControllerCoordinator) -> None:
    """Register services for CWU Controller."""

    async def handle_force_cwu(call):
        """Handle force CWU service."""
        duration = call.data.get("duration", 60)
        await coordinator.async_force_cwu(duration)

    async def handle_force_floor(call):
        """Handle force floor heating service."""
        duration = call.data.get("duration", 60)
        await coordinator.async_force_floor(duration)

    async def handle_enable(call):
        """Handle enable service."""
        await coordinator.async_enable()

    async def handle_disable(call):
        """Handle disable service."""
        await coordinator.async_disable()

    hass.services.async_register(DOMAIN, "force_cwu", handle_force_cwu)
    hass.services.async_register(DOMAIN, "force_floor", handle_force_floor)
    hass.services.async_register(DOMAIN, "enable", handle_enable)
    hass.services.async_register(DOMAIN, "disable", handle_disable)
