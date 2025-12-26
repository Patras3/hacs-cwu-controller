"""Sensor entities for CWU Controller."""
from __future__ import annotations

from datetime import datetime

from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature, UnitOfPower, UnitOfTime, UnitOfEnergy
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
    """Set up sensor entities."""
    coordinator: CWUControllerCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = [
        CWUControllerStateSensor(coordinator, entry),
        CWUUrgencySensor(coordinator, entry),
        FloorUrgencySensor(coordinator, entry),
        AveragePowerSensor(coordinator, entry),
        CWUHeatingTimeSensor(coordinator, entry),
        CWUTargetTempSensor(coordinator, entry),
        # Energy tracking sensors
        CWUEnergyTodaySensor(coordinator, entry),
        FloorEnergyTodaySensor(coordinator, entry),
        TotalEnergyTodaySensor(coordinator, entry),
        # Cost sensors (separate for CWU and Floor)
        CWUEnergyCostTodaySensor(coordinator, entry),
        FloorEnergyCostTodaySensor(coordinator, entry),
        # Tariff sensor
        CurrentTariffRateSensor(coordinator, entry),
        # BSB-LAN sensors
        BsbDhwStatusSensor(coordinator, entry),
        BsbHpStatusSensor(coordinator, entry),
        BsbCwuTempSensor(coordinator, entry),
        BsbFlowTempSensor(coordinator, entry),
        BsbReturnTempSensor(coordinator, entry),
        BsbDeltaTSensor(coordinator, entry),
        BsbOutsideTempSensor(coordinator, entry),
        ControlSourceSensor(coordinator, entry),
    ]

    async_add_entities(entities)


class CWUControllerBaseSensor(CoordinatorEntity, SensorEntity):
    """Base sensor for CWU Controller."""

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


class CWUControllerStateSensor(CWUControllerBaseSensor):
    """Sensor showing current controller state."""

    def __init__(self, coordinator: CWUControllerCoordinator, entry: ConfigEntry) -> None:
        """Initialize sensor."""
        super().__init__(coordinator, entry, "state", "State")
        self._attr_icon = "mdi:state-machine"

    @property
    def native_value(self) -> str | None:
        """Return current state."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get("controller_state", "unknown")

    @property
    def extra_state_attributes(self) -> dict:
        """Return extra state attributes."""
        if self.coordinator.data is None:
            return {}

        data = self.coordinator.data
        return {
            "cwu_temp": data.get("cwu_temp"),
            "salon_temp": data.get("salon_temp"),
            "bedroom_temp": data.get("bedroom_temp"),
            "kids_temp": data.get("kids_temp"),
            "power": data.get("power"),
            "water_heater_state": data.get("wh_state"),
            "climate_state": data.get("climate_state"),
            "enabled": data.get("enabled"),
            "manual_override": data.get("manual_override"),
            "fake_heating_detected": data.get("fake_heating"),
            "state_history": data.get("state_history", []),
            "action_history": data.get("action_history", []),
            # CWU Session tracking
            "cwu_session_start_time": data.get("cwu_session_start_time"),
            "cwu_session_start_temp": data.get("cwu_session_start_temp"),
            "cwu_heating_minutes": data.get("cwu_heating_minutes", 0),
            # Operating mode
            "operating_mode": data.get("operating_mode"),
            # Tariff info
            "is_cheap_tariff": data.get("is_cheap_tariff"),
            "current_tariff_rate": data.get("current_tariff_rate"),
            "is_cwu_heating_window": data.get("is_cwu_heating_window"),
            # Winter mode specific
            "winter_cwu_target": data.get("winter_cwu_target"),
            "winter_cwu_emergency_threshold": data.get("winter_cwu_emergency_threshold"),
            # Energy tracking - totals
            "energy_today_cwu_kwh": data.get("energy_today_cwu_kwh"),
            "energy_today_floor_kwh": data.get("energy_today_floor_kwh"),
            "energy_today_total_kwh": data.get("energy_today_total_kwh"),
            "energy_yesterday_cwu_kwh": data.get("energy_yesterday_cwu_kwh"),
            "energy_yesterday_floor_kwh": data.get("energy_yesterday_floor_kwh"),
            "energy_yesterday_total_kwh": data.get("energy_yesterday_total_kwh"),
            # Energy tracking - tariff breakdown (cheap/expensive)
            "energy_today_cwu_cheap_kwh": data.get("energy_today_cwu_cheap_kwh"),
            "energy_today_cwu_expensive_kwh": data.get("energy_today_cwu_expensive_kwh"),
            "energy_today_floor_cheap_kwh": data.get("energy_today_floor_cheap_kwh"),
            "energy_today_floor_expensive_kwh": data.get("energy_today_floor_expensive_kwh"),
            "energy_yesterday_cwu_cheap_kwh": data.get("energy_yesterday_cwu_cheap_kwh"),
            "energy_yesterday_cwu_expensive_kwh": data.get("energy_yesterday_cwu_expensive_kwh"),
            "energy_yesterday_floor_cheap_kwh": data.get("energy_yesterday_floor_cheap_kwh"),
            "energy_yesterday_floor_expensive_kwh": data.get("energy_yesterday_floor_expensive_kwh"),
            # Cost estimates - total and breakdown
            "cost_today_estimate": data.get("cost_today_estimate"),
            "cost_today_cwu_estimate": data.get("cost_today_cwu_estimate"),
            "cost_today_floor_estimate": data.get("cost_today_floor_estimate"),
            "cost_yesterday_estimate": data.get("cost_yesterday_estimate"),
            "cost_yesterday_cwu_estimate": data.get("cost_yesterday_cwu_estimate"),
            "cost_yesterday_floor_estimate": data.get("cost_yesterday_floor_estimate"),
            # Tariff rates
            "tariff_cheap_rate": data.get("tariff_cheap_rate"),
            "tariff_expensive_rate": data.get("tariff_expensive_rate"),
            # Manual override
            "manual_override_until": data.get("manual_override_until"),
            # Anti-oscillation (broken_heater mode)
            "hold_time_remaining": data.get("hold_time_remaining", 0),
            "can_switch_to_cwu": data.get("can_switch_to_cwu", True),
            "can_switch_to_floor": data.get("can_switch_to_floor", True),
            "switch_blocked_reason": data.get("switch_blocked_reason", ""),
            # HP status (broken_heater mode)
            "hp_ready": data.get("hp_ready", True),
            "hp_ready_reason": data.get("hp_ready_reason", "OK"),
            # Max temp detection (broken_heater mode)
            "max_temp_achieved": data.get("max_temp_achieved"),
            "electric_fallback_count": data.get("electric_fallback_count", 0),
            "max_temp_detected": data.get("max_temp_detected", False),
            # Night floor window (broken_heater mode)
            "is_night_floor_window": data.get("is_night_floor_window", False),
        }


class CWUUrgencySensor(CWUControllerBaseSensor):
    """Sensor showing CWU heating urgency."""

    def __init__(self, coordinator: CWUControllerCoordinator, entry: ConfigEntry) -> None:
        """Initialize sensor."""
        super().__init__(coordinator, entry, "cwu_urgency", "CWU Urgency")
        self._attr_icon = "mdi:water-thermometer"

    @property
    def native_value(self) -> int | None:
        """Return urgency level."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get("cwu_urgency", 0)

    @property
    def extra_state_attributes(self) -> dict:
        """Return extra attributes."""
        urgency = self.native_value
        levels = {0: "None", 1: "Low", 2: "Medium", 3: "High", 4: "Critical"}
        return {
            "level_name": levels.get(urgency, "Unknown"),
            "cwu_temp": self.coordinator.data.get("cwu_temp") if self.coordinator.data else None,
        }


class FloorUrgencySensor(CWUControllerBaseSensor):
    """Sensor showing floor heating urgency."""

    def __init__(self, coordinator: CWUControllerCoordinator, entry: ConfigEntry) -> None:
        """Initialize sensor."""
        super().__init__(coordinator, entry, "floor_urgency", "Floor Urgency")
        self._attr_icon = "mdi:home-thermometer"

    @property
    def native_value(self) -> int | None:
        """Return urgency level."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get("floor_urgency", 0)

    @property
    def extra_state_attributes(self) -> dict:
        """Return extra attributes."""
        urgency = self.native_value
        levels = {0: "None", 1: "Low", 2: "Medium", 3: "High", 4: "Critical"}
        return {
            "level_name": levels.get(urgency, "Unknown"),
            "salon_temp": self.coordinator.data.get("salon_temp") if self.coordinator.data else None,
            "bedroom_temp": self.coordinator.data.get("bedroom_temp") if self.coordinator.data else None,
        }


class AveragePowerSensor(CWUControllerBaseSensor):
    """Sensor showing average power consumption."""

    def __init__(self, coordinator: CWUControllerCoordinator, entry: ConfigEntry) -> None:
        """Initialize sensor."""
        super().__init__(coordinator, entry, "avg_power", "Average Power")
        self._attr_device_class = SensorDeviceClass.POWER
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = UnitOfPower.WATT
        self._attr_icon = "mdi:flash"

    @property
    def native_value(self) -> float | None:
        """Return average power."""
        if self.coordinator.data is None:
            return None
        return round(self.coordinator.data.get("avg_power", 0), 1)


class CWUHeatingTimeSensor(CWUControllerBaseSensor):
    """Sensor showing CWU heating time in current cycle."""

    def __init__(self, coordinator: CWUControllerCoordinator, entry: ConfigEntry) -> None:
        """Initialize sensor."""
        super().__init__(coordinator, entry, "cwu_heating_time", "CWU Heating Time")
        self._attr_device_class = SensorDeviceClass.DURATION
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = UnitOfTime.MINUTES
        self._attr_icon = "mdi:timer"

    @property
    def native_value(self) -> float | None:
        """Return heating time in minutes."""
        if self.coordinator.data is None:
            return None
        return round(self.coordinator.data.get("cwu_heating_minutes", 0), 1)

    @property
    def extra_state_attributes(self) -> dict:
        """Return extra attributes."""
        minutes = self.native_value or 0
        max_minutes = 170  # 2h50m
        return {
            "max_minutes": max_minutes,
            "remaining_minutes": max(0, max_minutes - minutes),
            "percentage": min(100, (minutes / max_minutes) * 100) if max_minutes > 0 else 0,
        }


class CWUTargetTempSensor(CWUControllerBaseSensor):
    """Sensor showing CWU target temperature."""

    def __init__(self, coordinator: CWUControllerCoordinator, entry: ConfigEntry) -> None:
        """Initialize sensor."""
        super().__init__(coordinator, entry, "cwu_target_temp", "CWU Target Temp")
        self._attr_device_class = SensorDeviceClass.TEMPERATURE
        self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        self._attr_icon = "mdi:thermometer-water"

    @property
    def native_value(self) -> float | None:
        """Return target temperature from config."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get("cwu_target_temp", 45.0)

    @property
    def extra_state_attributes(self) -> dict:
        """Return extra attributes."""
        if self.coordinator.data is None:
            return {}
        return {
            "cwu_target_temp": self.coordinator.data.get("cwu_target_temp"),
            "cwu_min_temp": self.coordinator.data.get("cwu_min_temp"),
            "cwu_critical_temp": self.coordinator.data.get("cwu_critical_temp"),
            "salon_target_temp": self.coordinator.data.get("salon_target_temp"),
        }


class CWUEnergyTodaySensor(CWUControllerBaseSensor):
    """Sensor showing CWU energy consumption today."""

    def __init__(self, coordinator: CWUControllerCoordinator, entry: ConfigEntry) -> None:
        """Initialize sensor."""
        super().__init__(coordinator, entry, "cwu_energy_today", "CWU Energy Today")
        self._attr_device_class = SensorDeviceClass.ENERGY
        self._attr_state_class = SensorStateClass.TOTAL
        self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
        self._attr_icon = "mdi:water-boiler"
        self._attr_suggested_display_precision = 2

    @property
    def native_value(self) -> float | None:
        """Return CWU energy today in kWh."""
        if self.coordinator.data is None:
            return None
        return round(self.coordinator.data.get("energy_today_cwu_kwh", 0), 3)

    @property
    def extra_state_attributes(self) -> dict:
        """Return extra attributes."""
        if self.coordinator.data is None:
            return {}
        return {
            "last_reset": datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).isoformat(),
            "yesterday_kwh": self.coordinator.data.get("energy_yesterday_cwu_kwh", 0),
        }


class FloorEnergyTodaySensor(CWUControllerBaseSensor):
    """Sensor showing floor heating energy consumption today."""

    def __init__(self, coordinator: CWUControllerCoordinator, entry: ConfigEntry) -> None:
        """Initialize sensor."""
        super().__init__(coordinator, entry, "floor_energy_today", "Floor Energy Today")
        self._attr_device_class = SensorDeviceClass.ENERGY
        self._attr_state_class = SensorStateClass.TOTAL
        self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
        self._attr_icon = "mdi:heating-coil"
        self._attr_suggested_display_precision = 2

    @property
    def native_value(self) -> float | None:
        """Return floor energy today in kWh."""
        if self.coordinator.data is None:
            return None
        return round(self.coordinator.data.get("energy_today_floor_kwh", 0), 3)

    @property
    def extra_state_attributes(self) -> dict:
        """Return extra attributes."""
        if self.coordinator.data is None:
            return {}
        return {
            "last_reset": datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).isoformat(),
            "yesterday_kwh": self.coordinator.data.get("energy_yesterday_floor_kwh", 0),
        }


class TotalEnergyTodaySensor(CWUControllerBaseSensor):
    """Sensor showing total energy consumption today."""

    def __init__(self, coordinator: CWUControllerCoordinator, entry: ConfigEntry) -> None:
        """Initialize sensor."""
        super().__init__(coordinator, entry, "total_energy_today", "Total Energy Today")
        self._attr_device_class = SensorDeviceClass.ENERGY
        self._attr_state_class = SensorStateClass.TOTAL
        self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
        self._attr_icon = "mdi:lightning-bolt"
        self._attr_suggested_display_precision = 2

    @property
    def native_value(self) -> float | None:
        """Return total energy today in kWh."""
        if self.coordinator.data is None:
            return None
        return round(self.coordinator.data.get("energy_today_total_kwh", 0), 3)

    @property
    def extra_state_attributes(self) -> dict:
        """Return extra attributes."""
        if self.coordinator.data is None:
            return {}
        return {
            "last_reset": datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).isoformat(),
            "cwu_kwh": self.coordinator.data.get("energy_today_cwu_kwh", 0),
            "floor_kwh": self.coordinator.data.get("energy_today_floor_kwh", 0),
            "yesterday_total_kwh": self.coordinator.data.get("energy_yesterday_total_kwh", 0),
        }


class CWUEnergyCostTodaySensor(CWUControllerBaseSensor):
    """Sensor showing estimated CWU energy cost today."""

    def __init__(self, coordinator: CWUControllerCoordinator, entry: ConfigEntry) -> None:
        """Initialize sensor."""
        super().__init__(coordinator, entry, "cwu_energy_cost_today", "CWU Energy Cost Today")
        self._attr_device_class = SensorDeviceClass.MONETARY
        self._attr_state_class = SensorStateClass.TOTAL
        self._attr_native_unit_of_measurement = "PLN"
        self._attr_icon = "mdi:water-boiler"
        self._attr_suggested_display_precision = 2

    @property
    def native_value(self) -> float | None:
        """Return estimated CWU cost today in PLN."""
        if self.coordinator.data is None:
            return None
        return round(self.coordinator.data.get("cost_today_cwu_estimate", 0), 2)

    @property
    def extra_state_attributes(self) -> dict:
        """Return extra attributes."""
        if self.coordinator.data is None:
            return {}
        return {
            "last_reset": datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).isoformat(),
            "yesterday_cost": self.coordinator.data.get("cost_yesterday_cwu_estimate", 0),
            "note": "Estimated based on average tariff rate",
        }


class FloorEnergyCostTodaySensor(CWUControllerBaseSensor):
    """Sensor showing estimated floor heating energy cost today."""

    def __init__(self, coordinator: CWUControllerCoordinator, entry: ConfigEntry) -> None:
        """Initialize sensor."""
        super().__init__(coordinator, entry, "floor_energy_cost_today", "Floor Energy Cost Today")
        self._attr_device_class = SensorDeviceClass.MONETARY
        self._attr_state_class = SensorStateClass.TOTAL
        self._attr_native_unit_of_measurement = "PLN"
        self._attr_icon = "mdi:heating-coil"
        self._attr_suggested_display_precision = 2

    @property
    def native_value(self) -> float | None:
        """Return estimated floor heating cost today in PLN."""
        if self.coordinator.data is None:
            return None
        return round(self.coordinator.data.get("cost_today_floor_estimate", 0), 2)

    @property
    def extra_state_attributes(self) -> dict:
        """Return extra attributes."""
        if self.coordinator.data is None:
            return {}
        return {
            "last_reset": datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).isoformat(),
            "yesterday_cost": self.coordinator.data.get("cost_yesterday_floor_estimate", 0),
            "note": "Estimated based on average tariff rate",
        }


class CurrentTariffRateSensor(CWUControllerBaseSensor):
    """Sensor showing current electricity tariff rate."""

    def __init__(self, coordinator: CWUControllerCoordinator, entry: ConfigEntry) -> None:
        """Initialize sensor."""
        super().__init__(coordinator, entry, "tariff_rate", "Current Tariff Rate")
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = "PLN/kWh"
        self._attr_icon = "mdi:currency-usd"
        self._attr_suggested_display_precision = 2

    @property
    def native_value(self) -> float | None:
        """Return current tariff rate."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get("current_tariff_rate", 0)

    @property
    def extra_state_attributes(self) -> dict:
        """Return extra attributes."""
        if self.coordinator.data is None:
            return {}
        is_cheap = self.coordinator.data.get("is_cheap_tariff", False)
        return {
            "tariff_type": "cheap" if is_cheap else "expensive",
            "is_cheap_tariff": is_cheap,
            "is_cwu_heating_window": self.coordinator.data.get("is_cwu_heating_window", False),
        }


# -----------------------------------------------------------------------------
# BSB-LAN Sensors
# -----------------------------------------------------------------------------

class BsbDhwStatusSensor(CWUControllerBaseSensor):
    """Sensor showing DHW (CWU) status from BSB-LAN."""

    def __init__(self, coordinator: CWUControllerCoordinator, entry: ConfigEntry) -> None:
        """Initialize sensor."""
        super().__init__(coordinator, entry, "bsb_dhw_status", "BSB DHW Status")
        self._attr_icon = "mdi:water-boiler"

    @property
    def native_value(self) -> str | None:
        """Return DHW status."""
        if self.coordinator.data is None:
            return None
        bsb = self.coordinator.data.get("bsb_lan", {})
        return bsb.get("dhw_status", "---")


class BsbHpStatusSensor(CWUControllerBaseSensor):
    """Sensor showing heat pump status from BSB-LAN."""

    def __init__(self, coordinator: CWUControllerCoordinator, entry: ConfigEntry) -> None:
        """Initialize sensor."""
        super().__init__(coordinator, entry, "bsb_hp_status", "BSB Heat Pump Status")
        self._attr_icon = "mdi:heat-pump"

    @property
    def native_value(self) -> str | None:
        """Return HP status."""
        if self.coordinator.data is None:
            return None
        bsb = self.coordinator.data.get("bsb_lan", {})
        return bsb.get("hp_status", "---")


class BsbCwuTempSensor(CWUControllerBaseSensor):
    """Sensor showing CWU temperature from BSB-LAN (param 8830)."""

    def __init__(self, coordinator: CWUControllerCoordinator, entry: ConfigEntry) -> None:
        """Initialize sensor."""
        super().__init__(coordinator, entry, "bsb_cwu_temp", "BSB CWU Temperature")
        self._attr_device_class = SensorDeviceClass.TEMPERATURE
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        self._attr_icon = "mdi:water-thermometer"
        self._attr_suggested_display_precision = 1

    @property
    def native_value(self) -> float | None:
        """Return CWU temperature."""
        if self.coordinator.data is None:
            return None
        bsb = self.coordinator.data.get("bsb_lan", {})
        return bsb.get("cwu_temp")


class BsbFlowTempSensor(CWUControllerBaseSensor):
    """Sensor showing flow temperature from BSB-LAN (param 8412)."""

    def __init__(self, coordinator: CWUControllerCoordinator, entry: ConfigEntry) -> None:
        """Initialize sensor."""
        super().__init__(coordinator, entry, "bsb_flow_temp", "BSB Flow Temperature")
        self._attr_device_class = SensorDeviceClass.TEMPERATURE
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        self._attr_icon = "mdi:thermometer-chevron-up"
        self._attr_suggested_display_precision = 1

    @property
    def native_value(self) -> float | None:
        """Return flow temperature."""
        if self.coordinator.data is None:
            return None
        bsb = self.coordinator.data.get("bsb_lan", {})
        return bsb.get("flow_temp")


class BsbReturnTempSensor(CWUControllerBaseSensor):
    """Sensor showing return temperature from BSB-LAN (param 8410)."""

    def __init__(self, coordinator: CWUControllerCoordinator, entry: ConfigEntry) -> None:
        """Initialize sensor."""
        super().__init__(coordinator, entry, "bsb_return_temp", "BSB Return Temperature")
        self._attr_device_class = SensorDeviceClass.TEMPERATURE
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        self._attr_icon = "mdi:thermometer-chevron-down"
        self._attr_suggested_display_precision = 1

    @property
    def native_value(self) -> float | None:
        """Return return temperature."""
        if self.coordinator.data is None:
            return None
        bsb = self.coordinator.data.get("bsb_lan", {})
        return bsb.get("return_temp")


class BsbDeltaTSensor(CWUControllerBaseSensor):
    """Sensor showing delta T (flow - return) from BSB-LAN."""

    def __init__(self, coordinator: CWUControllerCoordinator, entry: ConfigEntry) -> None:
        """Initialize sensor."""
        super().__init__(coordinator, entry, "bsb_delta_t", "BSB Delta T")
        self._attr_device_class = SensorDeviceClass.TEMPERATURE
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        self._attr_icon = "mdi:thermometer-lines"
        self._attr_suggested_display_precision = 1

    @property
    def native_value(self) -> float | None:
        """Return delta T."""
        if self.coordinator.data is None:
            return None
        bsb = self.coordinator.data.get("bsb_lan", {})
        return bsb.get("delta_t")

    @property
    def extra_state_attributes(self) -> dict:
        """Return extra attributes with interpretation."""
        if self.coordinator.data is None:
            return {}
        bsb = self.coordinator.data.get("bsb_lan", {})
        delta = bsb.get("delta_t")
        if delta is None:
            return {"interpretation": "unknown"}

        if delta >= 3.0 and delta <= 5.0:
            interpretation = "good"
        elif delta > 0.5 and delta < 3.0:
            interpretation = "weak"
        elif delta <= 0.5:
            interpretation = "bad"
        else:
            interpretation = "high"

        return {
            "interpretation": interpretation,
            "flow_temp": bsb.get("flow_temp"),
            "return_temp": bsb.get("return_temp"),
        }


class BsbOutsideTempSensor(CWUControllerBaseSensor):
    """Sensor showing outside temperature from BSB-LAN (param 8700)."""

    def __init__(self, coordinator: CWUControllerCoordinator, entry: ConfigEntry) -> None:
        """Initialize sensor."""
        super().__init__(coordinator, entry, "bsb_outside_temp", "BSB Outside Temperature")
        self._attr_device_class = SensorDeviceClass.TEMPERATURE
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        self._attr_icon = "mdi:home-thermometer-outline"
        self._attr_suggested_display_precision = 1

    @property
    def native_value(self) -> float | None:
        """Return outside temperature."""
        if self.coordinator.data is None:
            return None
        bsb = self.coordinator.data.get("bsb_lan", {})
        return bsb.get("outside_temp")


class ControlSourceSensor(CWUControllerBaseSensor):
    """Sensor showing current control source (BSB-LAN or HA Cloud)."""

    def __init__(self, coordinator: CWUControllerCoordinator, entry: ConfigEntry) -> None:
        """Initialize sensor."""
        super().__init__(coordinator, entry, "control_source", "Control Source")
        self._attr_icon = "mdi:remote"

    @property
    def native_value(self) -> str | None:
        """Return control source."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get("control_source", "unknown")

    @property
    def extra_state_attributes(self) -> dict:
        """Return extra attributes."""
        if self.coordinator.data is None:
            return {}
        return {
            "bsb_lan_available": self.coordinator.data.get("bsb_lan_available", False),
        }
