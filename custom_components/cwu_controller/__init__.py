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

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.SWITCH, Platform.BINARY_SENSOR, Platform.BUTTON, Platform.SELECT, Platform.NUMBER]

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

    # Load persisted energy data before first refresh
    await coordinator.async_load_energy_data()

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
    # Save energy data before unloading
    coordinator: CWUControllerCoordinator = hass.data[DOMAIN].get(entry.entry_id)
    if coordinator:
        _LOGGER.info("Saving energy data before unloading CWU Controller...")
        await coordinator.async_save_energy_data()

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

    async def handle_force_auto(call):
        """Handle force auto service - cancel override."""
        await coordinator.async_force_auto()

    async def handle_set_mode(call):
        """Handle set operating mode service."""
        mode = call.data.get("mode")
        if mode:
            await coordinator.async_set_operating_mode(mode)

    async def handle_heat_to_temp(call):
        """Handle heat-to-temp service - heat CWU to specific temp then return to AUTO."""
        target_temp = call.data.get("target_temp", 50)
        await coordinator.async_heat_to_temp(target_temp)

    async def handle_floor_boost(call):
        """Handle floor boost service - raise floor temp to 28°C for X hours."""
        hours = call.data.get("hours", 2)
        await coordinator.async_floor_boost_timed(hours)

    async def handle_floor_boost_session(call):
        """Handle floor boost session - raise temp until floor heating session ends."""
        await coordinator.async_floor_boost_session()

    async def handle_floor_boost_cancel(call):
        """Handle floor boost cancel - restore original settings."""
        await coordinator.async_floor_boost_cancel()

    async def handle_floor_set_temperature(call):
        """Handle floor set temperature - set floor temp directly via BSB-LAN."""
        temp = call.data.get("temperature", 21)
        await coordinator.async_set_floor_temperature(temp)

    hass.services.async_register(DOMAIN, "force_cwu", handle_force_cwu)
    hass.services.async_register(DOMAIN, "force_floor", handle_force_floor)
    hass.services.async_register(DOMAIN, "force_auto", handle_force_auto)
    hass.services.async_register(DOMAIN, "enable", handle_enable)
    hass.services.async_register(DOMAIN, "disable", handle_disable)
    hass.services.async_register(DOMAIN, "set_mode", handle_set_mode)
    hass.services.async_register(DOMAIN, "heat_to_temp", handle_heat_to_temp)
    hass.services.async_register(DOMAIN, "floor_boost", handle_floor_boost)
    hass.services.async_register(DOMAIN, "floor_boost_session", handle_floor_boost_session)
    hass.services.async_register(DOMAIN, "floor_boost_cancel", handle_floor_boost_cancel)
    hass.services.async_register(DOMAIN, "floor_set_temperature", handle_floor_set_temperature)
