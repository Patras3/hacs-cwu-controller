"""Config flow for CWU Controller integration."""
from __future__ import annotations

from typing import Any
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    DOMAIN,
    CONF_CWU_TEMP_SENSOR,
    CONF_SALON_TEMP_SENSOR,
    CONF_BEDROOM_TEMP_SENSOR,
    CONF_KIDS_ROOM_TEMP_SENSOR,
    CONF_POWER_SENSOR,
    CONF_WATER_HEATER,
    CONF_CLIMATE,
    CONF_NOTIFY_SERVICE,
    CONF_PUMP_INPUT_TEMP,
    CONF_PUMP_OUTPUT_TEMP,
    CONF_CWU_INPUT_TEMP,
    CONF_FLOOR_INPUT_TEMP,
    CONF_CWU_TARGET_TEMP,
    CONF_CWU_MIN_TEMP,
    CONF_CWU_CRITICAL_TEMP,
    CONF_SALON_TARGET_TEMP,
    CONF_SALON_MIN_TEMP,
    CONF_BEDROOM_MIN_TEMP,
    CONF_OPERATING_MODE,
    CONF_WORKDAY_SENSOR,
    CONF_TARIFF_EXPENSIVE_RATE,
    CONF_TARIFF_CHEAP_RATE,
    CONF_ENERGY_SENSOR,
    DEFAULT_CWU_TARGET_TEMP,
    DEFAULT_CWU_MIN_TEMP,
    DEFAULT_CWU_CRITICAL_TEMP,
    DEFAULT_SALON_TARGET_TEMP,
    DEFAULT_SALON_MIN_TEMP,
    DEFAULT_BEDROOM_MIN_TEMP,
    DEFAULT_ENERGY_SENSOR,
    TARIFF_EXPENSIVE_RATE,
    TARIFF_CHEAP_RATE,
    MODE_BROKEN_HEATER,
    MODE_WINTER,
    MODE_SUMMER,
    OPERATING_MODES,
)


class CWUControllerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for CWU Controller."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Handle the initial step - entity selection."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Validate that required entities exist
            for key in [CONF_CWU_TEMP_SENSOR, CONF_WATER_HEATER, CONF_CLIMATE]:
                if key in user_input:
                    state = self.hass.states.get(user_input[key])
                    if state is None:
                        errors[key] = "entity_not_found"

            if not errors:
                # Store entity config and move to thresholds
                self._entity_config = user_input
                return await self.async_step_thresholds()

        # Default entity IDs based on user's setup
        defaults = {
            CONF_CWU_TEMP_SENSOR: "sensor.temperatura_c_w_u",
            CONF_SALON_TEMP_SENSOR: "sensor.temperatura_govee_salon",
            CONF_BEDROOM_TEMP_SENSOR: "sensor.temperatura_govee_sypialnia",
            CONF_KIDS_ROOM_TEMP_SENSOR: "sensor.temperatura_govee_dzieciecy",
            CONF_POWER_SENSOR: "sensor.ogrzewanie_total_system_power",
            CONF_ENERGY_SENSOR: DEFAULT_ENERGY_SENSOR,
            CONF_WATER_HEATER: "water_heater.pompa_ciepla_io_13873843_2",
            CONF_CLIMATE: "climate.pompa_ciepla_dom",
            CONF_NOTIFY_SERVICE: "notify.mobile_app_patryk_s22_ultra",
            CONF_PUMP_INPUT_TEMP: "sensor.temperatura_wejscia_pompy_ciepla",
            CONF_PUMP_OUTPUT_TEMP: "sensor.temperatura_wyjscia_pompy_ciepla",
            CONF_CWU_INPUT_TEMP: "sensor.temperatura_wejscia_c_w_u",
            CONF_FLOOR_INPUT_TEMP: "sensor.temperatura_wejscia_ogrzewania_podlogowego",
            CONF_WORKDAY_SENSOR: "binary_sensor.workday_sensor",
        }

        data_schema = vol.Schema({
            vol.Required(CONF_CWU_TEMP_SENSOR, default=defaults[CONF_CWU_TEMP_SENSOR]): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor", device_class="temperature")
            ),
            vol.Required(CONF_SALON_TEMP_SENSOR, default=defaults[CONF_SALON_TEMP_SENSOR]): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor", device_class="temperature")
            ),
            vol.Optional(CONF_BEDROOM_TEMP_SENSOR, default=defaults[CONF_BEDROOM_TEMP_SENSOR]): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor", device_class="temperature")
            ),
            vol.Optional(CONF_KIDS_ROOM_TEMP_SENSOR, default=defaults[CONF_KIDS_ROOM_TEMP_SENSOR]): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor", device_class="temperature")
            ),
            vol.Required(CONF_POWER_SENSOR, default=defaults[CONF_POWER_SENSOR]): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor", device_class="power")
            ),
            vol.Optional(CONF_ENERGY_SENSOR, default=defaults[CONF_ENERGY_SENSOR]): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor", device_class="energy")
            ),
            vol.Required(CONF_WATER_HEATER, default=defaults[CONF_WATER_HEATER]): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="water_heater")
            ),
            vol.Required(CONF_CLIMATE, default=defaults[CONF_CLIMATE]): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="climate")
            ),
            vol.Required(CONF_WORKDAY_SENSOR, default=defaults[CONF_WORKDAY_SENSOR]): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="binary_sensor")
            ),
            vol.Optional(CONF_NOTIFY_SERVICE, default=defaults[CONF_NOTIFY_SERVICE]): selector.TextSelector(),
            vol.Optional(CONF_PUMP_INPUT_TEMP, default=defaults[CONF_PUMP_INPUT_TEMP]): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor", device_class="temperature")
            ),
            vol.Optional(CONF_PUMP_OUTPUT_TEMP, default=defaults[CONF_PUMP_OUTPUT_TEMP]): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor", device_class="temperature")
            ),
            vol.Optional(CONF_CWU_INPUT_TEMP, default=defaults[CONF_CWU_INPUT_TEMP]): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor", device_class="temperature")
            ),
            vol.Optional(CONF_FLOOR_INPUT_TEMP, default=defaults[CONF_FLOOR_INPUT_TEMP]): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor", device_class="temperature")
            ),
        })

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
            description_placeholders={
                "description": "Select the entities for CWU Controller"
            },
        )

    async def async_step_thresholds(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Handle threshold and tariff configuration."""
        if user_input is not None:
            # Combine entity config with thresholds
            full_config = {**self._entity_config, **user_input}

            return self.async_create_entry(
                title="CWU Controller",
                data=full_config,
            )

        mode_options = [
            selector.SelectOptionDict(value=MODE_BROKEN_HEATER, label="Broken Heater (Fake heating detection)"),
            selector.SelectOptionDict(value=MODE_WINTER, label="Winter (Tariff-optimized heating)"),
            selector.SelectOptionDict(value=MODE_SUMMER, label="Summer (Not implemented yet)"),
        ]

        data_schema = vol.Schema({
            vol.Required(CONF_OPERATING_MODE, default=MODE_BROKEN_HEATER): selector.SelectSelector(
                selector.SelectSelectorConfig(options=mode_options, mode=selector.SelectSelectorMode.DROPDOWN)
            ),
            # Temperature thresholds
            vol.Required(CONF_CWU_TARGET_TEMP, default=DEFAULT_CWU_TARGET_TEMP): selector.NumberSelector(
                selector.NumberSelectorConfig(min=40, max=55, step=0.5, unit_of_measurement="°C")
            ),
            vol.Required(CONF_CWU_MIN_TEMP, default=DEFAULT_CWU_MIN_TEMP): selector.NumberSelector(
                selector.NumberSelectorConfig(min=35, max=50, step=0.5, unit_of_measurement="°C")
            ),
            vol.Required(CONF_CWU_CRITICAL_TEMP, default=DEFAULT_CWU_CRITICAL_TEMP): selector.NumberSelector(
                selector.NumberSelectorConfig(min=30, max=40, step=0.5, unit_of_measurement="°C")
            ),
            vol.Required(CONF_SALON_TARGET_TEMP, default=DEFAULT_SALON_TARGET_TEMP): selector.NumberSelector(
                selector.NumberSelectorConfig(min=18, max=25, step=0.5, unit_of_measurement="°C")
            ),
            vol.Required(CONF_SALON_MIN_TEMP, default=DEFAULT_SALON_MIN_TEMP): selector.NumberSelector(
                selector.NumberSelectorConfig(min=17, max=23, step=0.5, unit_of_measurement="°C")
            ),
            vol.Required(CONF_BEDROOM_MIN_TEMP, default=DEFAULT_BEDROOM_MIN_TEMP): selector.NumberSelector(
                selector.NumberSelectorConfig(min=16, max=22, step=0.5, unit_of_measurement="°C")
            ),
            # Tariff rates (G12w)
            vol.Required(CONF_TARIFF_EXPENSIVE_RATE, default=TARIFF_EXPENSIVE_RATE): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0.1, max=5.0, step=0.01, unit_of_measurement="zł/kWh")
            ),
            vol.Required(CONF_TARIFF_CHEAP_RATE, default=TARIFF_CHEAP_RATE): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0.1, max=5.0, step=0.01, unit_of_measurement="zł/kWh")
            ),
        })

        return self.async_show_form(
            step_id="thresholds",
            data_schema=data_schema,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Get options flow."""
        return CWUControllerOptionsFlow(config_entry)


class CWUControllerOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Handle options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        data = self.config_entry.data

        mode_options = [
            selector.SelectOptionDict(value=MODE_BROKEN_HEATER, label="Broken Heater (Fake heating detection)"),
            selector.SelectOptionDict(value=MODE_WINTER, label="Winter (Tariff-optimized heating)"),
            selector.SelectOptionDict(value=MODE_SUMMER, label="Summer (Not implemented yet)"),
        ]

        data_schema = vol.Schema({
            vol.Required(CONF_OPERATING_MODE, default=data.get(CONF_OPERATING_MODE, MODE_BROKEN_HEATER)): selector.SelectSelector(
                selector.SelectSelectorConfig(options=mode_options, mode=selector.SelectSelectorMode.DROPDOWN)
            ),
            # Temperature thresholds
            vol.Required(CONF_CWU_TARGET_TEMP, default=data.get(CONF_CWU_TARGET_TEMP, DEFAULT_CWU_TARGET_TEMP)): selector.NumberSelector(
                selector.NumberSelectorConfig(min=40, max=55, step=0.5, unit_of_measurement="°C")
            ),
            vol.Required(CONF_CWU_MIN_TEMP, default=data.get(CONF_CWU_MIN_TEMP, DEFAULT_CWU_MIN_TEMP)): selector.NumberSelector(
                selector.NumberSelectorConfig(min=35, max=50, step=0.5, unit_of_measurement="°C")
            ),
            vol.Required(CONF_CWU_CRITICAL_TEMP, default=data.get(CONF_CWU_CRITICAL_TEMP, DEFAULT_CWU_CRITICAL_TEMP)): selector.NumberSelector(
                selector.NumberSelectorConfig(min=30, max=40, step=0.5, unit_of_measurement="°C")
            ),
            vol.Required(CONF_SALON_TARGET_TEMP, default=data.get(CONF_SALON_TARGET_TEMP, DEFAULT_SALON_TARGET_TEMP)): selector.NumberSelector(
                selector.NumberSelectorConfig(min=18, max=25, step=0.5, unit_of_measurement="°C")
            ),
            vol.Required(CONF_SALON_MIN_TEMP, default=data.get(CONF_SALON_MIN_TEMP, DEFAULT_SALON_MIN_TEMP)): selector.NumberSelector(
                selector.NumberSelectorConfig(min=17, max=23, step=0.5, unit_of_measurement="°C")
            ),
            vol.Required(CONF_BEDROOM_MIN_TEMP, default=data.get(CONF_BEDROOM_MIN_TEMP, DEFAULT_BEDROOM_MIN_TEMP)): selector.NumberSelector(
                selector.NumberSelectorConfig(min=16, max=22, step=0.5, unit_of_measurement="°C")
            ),
            # Tariff rates (G12w) - update when prices change
            vol.Required(CONF_TARIFF_EXPENSIVE_RATE, default=data.get(CONF_TARIFF_EXPENSIVE_RATE, TARIFF_EXPENSIVE_RATE)): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0.1, max=5.0, step=0.01, unit_of_measurement="zł/kWh")
            ),
            vol.Required(CONF_TARIFF_CHEAP_RATE, default=data.get(CONF_TARIFF_CHEAP_RATE, TARIFF_CHEAP_RATE)): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0.1, max=5.0, step=0.01, unit_of_measurement="zł/kWh")
            ),
        })

        return self.async_show_form(step_id="init", data_schema=data_schema)
