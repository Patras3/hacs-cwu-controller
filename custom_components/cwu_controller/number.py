"""Number entities for CWU Controller - editable temperature thresholds."""
from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    MANUFACTURER,
    CONF_CWU_TARGET_TEMP,
    CONF_CWU_MIN_TEMP,
    CONF_CWU_CRITICAL_TEMP,
    CONF_CWU_HYSTERESIS,
    CONF_SALON_TARGET_TEMP,
    CONF_SALON_MIN_TEMP,
    CONF_BEDROOM_MIN_TEMP,
    DEFAULT_CWU_TARGET_TEMP,
    DEFAULT_CWU_MIN_TEMP,
    DEFAULT_CWU_CRITICAL_TEMP,
    DEFAULT_CWU_HYSTERESIS,
    DEFAULT_SALON_TARGET_TEMP,
    DEFAULT_SALON_MIN_TEMP,
    DEFAULT_BEDROOM_MIN_TEMP,
)
from .coordinator import CWUControllerCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up number entities."""
    coordinator: CWUControllerCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = [
        CWUTargetTempNumber(coordinator, entry),
        CWUMinTempNumber(coordinator, entry),
        CWUCriticalTempNumber(coordinator, entry),
        CWUHysteresisNumber(coordinator, entry),
        SalonTargetTempNumber(coordinator, entry),
        SalonMinTempNumber(coordinator, entry),
        BedroomMinTempNumber(coordinator, entry),
    ]

    async_add_entities(entities)


class CWUControllerNumberEntity(CoordinatorEntity, NumberEntity):
    """Base class for CWU Controller number entities."""

    _attr_mode = NumberMode.BOX
    _attr_native_step = 0.5

    def __init__(
        self,
        coordinator: CWUControllerCoordinator,
        entry: ConfigEntry,
        config_key: str,
        default_value: float,
        unique_id_suffix: str,
        name: str,
        icon: str,
        min_value: float,
        max_value: float,
    ) -> None:
        """Initialize number entity."""
        super().__init__(coordinator)
        self._config_key = config_key
        self._default_value = default_value
        self._attr_unique_id = f"{entry.entry_id}_{unique_id_suffix}"
        self._attr_name = name
        self._attr_icon = icon
        self._attr_native_min_value = min_value
        self._attr_native_max_value = max_value
        self._attr_native_unit_of_measurement = "°C"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": "CWU Controller",
            "manufacturer": MANUFACTURER,
            "model": "Smart Heat Pump Controller",
            "sw_version": "4.3.0",
        }

    @property
    def native_value(self) -> float:
        """Return current value."""
        return self.coordinator.get_config_value(self._config_key, self._default_value)

    async def async_set_native_value(self, value: float) -> None:
        """Set new value."""
        await self.coordinator.async_set_config_value(self._config_key, value)
        self.async_write_ha_state()


class CWUTargetTempNumber(CWUControllerNumberEntity):
    """CWU target temperature number entity."""

    def __init__(self, coordinator: CWUControllerCoordinator, entry: ConfigEntry) -> None:
        """Initialize CWU target temp number."""
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            config_key=CONF_CWU_TARGET_TEMP,
            default_value=DEFAULT_CWU_TARGET_TEMP,
            unique_id_suffix="cwu_target_temp",
            name="CWU Target Temperature",
            icon="mdi:thermometer-water",
            min_value=40.0,
            max_value=55.0,
        )


class CWUMinTempNumber(CWUControllerNumberEntity):
    """CWU minimum temperature number entity."""

    def __init__(self, coordinator: CWUControllerCoordinator, entry: ConfigEntry) -> None:
        """Initialize CWU min temp number."""
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            config_key=CONF_CWU_MIN_TEMP,
            default_value=DEFAULT_CWU_MIN_TEMP,
            unique_id_suffix="cwu_min_temp",
            name="CWU Minimum Temperature",
            icon="mdi:thermometer-low",
            min_value=35.0,
            max_value=50.0,
        )


class CWUCriticalTempNumber(CWUControllerNumberEntity):
    """CWU critical temperature number entity."""

    def __init__(self, coordinator: CWUControllerCoordinator, entry: ConfigEntry) -> None:
        """Initialize CWU critical temp number."""
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            config_key=CONF_CWU_CRITICAL_TEMP,
            default_value=DEFAULT_CWU_CRITICAL_TEMP,
            unique_id_suffix="cwu_critical_temp",
            name="CWU Critical Temperature",
            icon="mdi:thermometer-alert",
            min_value=30.0,
            max_value=40.0,
        )


class CWUHysteresisNumber(CWUControllerNumberEntity):
    """CWU hysteresis margin number entity.

    Controls how many degrees below target before resuming CWU heating.
    Heat pumps typically need 5°C difference to start heating.
    """

    def __init__(self, coordinator: CWUControllerCoordinator, entry: ConfigEntry) -> None:
        """Initialize CWU hysteresis number."""
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            config_key=CONF_CWU_HYSTERESIS,
            default_value=DEFAULT_CWU_HYSTERESIS,
            unique_id_suffix="cwu_hysteresis",
            name="CWU Hysteresis",
            icon="mdi:arrow-up-down",
            min_value=3.0,
            max_value=15.0,
        )


class SalonTargetTempNumber(CWUControllerNumberEntity):
    """Salon target temperature number entity."""

    def __init__(self, coordinator: CWUControllerCoordinator, entry: ConfigEntry) -> None:
        """Initialize salon target temp number."""
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            config_key=CONF_SALON_TARGET_TEMP,
            default_value=DEFAULT_SALON_TARGET_TEMP,
            unique_id_suffix="salon_target_temp",
            name="Living Room Target Temperature",
            icon="mdi:sofa",
            min_value=18.0,
            max_value=25.0,
        )


class SalonMinTempNumber(CWUControllerNumberEntity):
    """Salon minimum temperature number entity."""

    def __init__(self, coordinator: CWUControllerCoordinator, entry: ConfigEntry) -> None:
        """Initialize salon min temp number."""
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            config_key=CONF_SALON_MIN_TEMP,
            default_value=DEFAULT_SALON_MIN_TEMP,
            unique_id_suffix="salon_min_temp",
            name="Living Room Minimum Temperature",
            icon="mdi:sofa-outline",
            min_value=17.0,
            max_value=23.0,
        )


class BedroomMinTempNumber(CWUControllerNumberEntity):
    """Bedroom minimum temperature number entity."""

    def __init__(self, coordinator: CWUControllerCoordinator, entry: ConfigEntry) -> None:
        """Initialize bedroom min temp number."""
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            config_key=CONF_BEDROOM_MIN_TEMP,
            default_value=DEFAULT_BEDROOM_MIN_TEMP,
            unique_id_suffix="bedroom_min_temp",
            name="Bedroom Minimum Temperature",
            icon="mdi:bed",
            min_value=16.0,
            max_value=22.0,
        )
