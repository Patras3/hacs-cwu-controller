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
        # Summer mode sensors - always registered but only active in summer mode
        SummerPVEnergyTodaySensor(coordinator, entry),
        SummerTariffEnergyTodaySensor(coordinator, entry),
        SummerPVEfficiencySensor(coordinator, entry),
        SummerSavingsTodaySensor(coordinator, entry),
        SummerHeatingSourceSensor(coordinator, entry),
        SummerPVBalanceSensor(coordinator, entry),
        SummerCurrentSlotSensor(coordinator, entry),
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
            "sw_version": "3.0.2",
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
            # Summer mode specific
            "summer_cwu_target": data.get("summer_cwu_target"),
            "summer_night_target": data.get("summer_night_target"),
            "summer_current_slot": data.get("summer_current_slot"),
            "summer_heating_source": data.get("summer_heating_source"),
            "summer_excess_mode_active": data.get("summer_excess_mode_active"),
            "summer_decision_reason": data.get("summer_decision_reason"),
            "summer_pv_balance": data.get("summer_pv_balance"),
            "summer_pv_production": data.get("summer_pv_production"),
            "summer_grid_power": data.get("summer_grid_power"),
            "summer_cooldown_active": data.get("summer_cooldown_active"),
            "summer_min_heating_elapsed": data.get("summer_min_heating_elapsed"),
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
    """Sensor showing CWU target temperature from config."""

    def __init__(self, coordinator: CWUControllerCoordinator, entry: ConfigEntry) -> None:
        """Initialize sensor."""
        super().__init__(coordinator, entry, "cwu_target_temp", "CWU Target Temp")
        self._attr_device_class = SensorDeviceClass.TEMPERATURE
        self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        self._attr_icon = "mdi:thermometer-water"

    @property
    def native_value(self) -> float | None:
        """Return target temperature."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get("cwu_target_temp", 45.0)

    @property
    def extra_state_attributes(self) -> dict:
        """Return extra attributes."""
        if self.coordinator.data is None:
            return {}
        return {
            "cwu_min_temp": self.coordinator.data.get("cwu_min_temp"),
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


# =============================================================================
# Summer Mode Sensors
# =============================================================================


class SummerPVEnergyTodaySensor(CWUControllerBaseSensor):
    """Sensor showing PV energy used for CWU heating today (Summer mode)."""

    def __init__(self, coordinator: CWUControllerCoordinator, entry: ConfigEntry) -> None:
        """Initialize sensor."""
        super().__init__(coordinator, entry, "summer_pv_energy_today", "Summer PV Energy Today")
        self._attr_device_class = SensorDeviceClass.ENERGY
        self._attr_state_class = SensorStateClass.TOTAL
        self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
        self._attr_icon = "mdi:solar-power"
        self._attr_suggested_display_precision = 2

    @property
    def native_value(self) -> float | None:
        """Return PV energy used today in kWh."""
        if self.coordinator.data is None:
            return None
        summer_energy = self.coordinator.data.get("summer_energy_today")
        if summer_energy is None:
            return 0.0
        return round(summer_energy.get("total_pv", 0), 3)

    @property
    def extra_state_attributes(self) -> dict:
        """Return extra attributes."""
        if self.coordinator.data is None:
            return {}
        summer_energy = self.coordinator.data.get("summer_energy_today") or {}
        yesterday = self.coordinator.data.get("summer_energy_yesterday") or {}
        return {
            "last_reset": datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).isoformat(),
            "direct_pv_kwh": summer_energy.get("pv", 0),
            "excess_pv_kwh": summer_energy.get("pv_excess", 0),
            "yesterday_pv_kwh": yesterday.get("total_pv", 0),
            "note": "Energy used from PV for CWU heating (free!)",
        }


class SummerTariffEnergyTodaySensor(CWUControllerBaseSensor):
    """Sensor showing tariff energy used for CWU heating today (Summer mode)."""

    def __init__(self, coordinator: CWUControllerCoordinator, entry: ConfigEntry) -> None:
        """Initialize sensor."""
        super().__init__(coordinator, entry, "summer_tariff_energy_today", "Summer Tariff Energy Today")
        self._attr_device_class = SensorDeviceClass.ENERGY
        self._attr_state_class = SensorStateClass.TOTAL
        self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
        self._attr_icon = "mdi:transmission-tower"
        self._attr_suggested_display_precision = 2

    @property
    def native_value(self) -> float | None:
        """Return tariff energy used today in kWh."""
        if self.coordinator.data is None:
            return None
        summer_energy = self.coordinator.data.get("summer_energy_today")
        if summer_energy is None:
            return 0.0
        return round(summer_energy.get("total_tariff", 0), 3)

    @property
    def extra_state_attributes(self) -> dict:
        """Return extra attributes."""
        if self.coordinator.data is None:
            return {}
        summer_energy = self.coordinator.data.get("summer_energy_today") or {}
        yesterday = self.coordinator.data.get("summer_energy_yesterday") or {}
        return {
            "last_reset": datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).isoformat(),
            "cheap_tariff_kwh": summer_energy.get("tariff_cheap", 0),
            "expensive_tariff_kwh": summer_energy.get("tariff_expensive", 0),
            "yesterday_tariff_kwh": yesterday.get("total_tariff", 0),
            "note": "Energy used from grid for CWU heating (paid)",
        }


class SummerPVEfficiencySensor(CWUControllerBaseSensor):
    """Sensor showing percentage of energy from PV (Summer mode)."""

    def __init__(self, coordinator: CWUControllerCoordinator, entry: ConfigEntry) -> None:
        """Initialize sensor."""
        super().__init__(coordinator, entry, "summer_pv_efficiency", "Summer PV Efficiency")
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = "%"
        self._attr_icon = "mdi:solar-power-variant"
        self._attr_suggested_display_precision = 1

    @property
    def native_value(self) -> float | None:
        """Return PV efficiency percentage."""
        if self.coordinator.data is None:
            return None
        summer_energy = self.coordinator.data.get("summer_energy_today")
        if summer_energy is None:
            return 0.0
        return round(summer_energy.get("pv_efficiency", 0), 1)

    @property
    def extra_state_attributes(self) -> dict:
        """Return extra attributes."""
        if self.coordinator.data is None:
            return {}
        summer_energy = self.coordinator.data.get("summer_energy_today") or {}
        yesterday = self.coordinator.data.get("summer_energy_yesterday") or {}
        return {
            "total_energy_kwh": summer_energy.get("total", 0),
            "pv_energy_kwh": summer_energy.get("total_pv", 0),
            "tariff_energy_kwh": summer_energy.get("total_tariff", 0),
            "yesterday_efficiency": yesterday.get("pv_efficiency", 0),
            "note": "Percentage of CWU heating energy from PV (higher = better)",
        }


class SummerSavingsTodaySensor(CWUControllerBaseSensor):
    """Sensor showing estimated savings from PV usage (Summer mode)."""

    def __init__(self, coordinator: CWUControllerCoordinator, entry: ConfigEntry) -> None:
        """Initialize sensor."""
        super().__init__(coordinator, entry, "summer_savings_today", "Summer Savings Today")
        self._attr_device_class = SensorDeviceClass.MONETARY
        self._attr_state_class = SensorStateClass.TOTAL
        self._attr_native_unit_of_measurement = "PLN"
        self._attr_icon = "mdi:piggy-bank"
        self._attr_suggested_display_precision = 2

    @property
    def native_value(self) -> float | None:
        """Return estimated savings in PLN."""
        if self.coordinator.data is None:
            return None
        summer_energy = self.coordinator.data.get("summer_energy_today")
        if summer_energy is None:
            return 0.0
        return round(summer_energy.get("savings", 0), 2)

    @property
    def extra_state_attributes(self) -> dict:
        """Return extra attributes."""
        if self.coordinator.data is None:
            return {}
        summer_energy = self.coordinator.data.get("summer_energy_today") or {}
        yesterday = self.coordinator.data.get("summer_energy_yesterday") or {}
        return {
            "last_reset": datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).isoformat(),
            "actual_cost": summer_energy.get("actual_cost", 0),
            "yesterday_savings": yesterday.get("savings", 0),
            "note": "Savings compared to using expensive tariff for all heating",
        }


class SummerHeatingSourceSensor(CWUControllerBaseSensor):
    """Sensor showing current heating source (Summer mode)."""

    def __init__(self, coordinator: CWUControllerCoordinator, entry: ConfigEntry) -> None:
        """Initialize sensor."""
        super().__init__(coordinator, entry, "summer_heating_source", "Summer Heating Source")
        self._attr_icon = "mdi:information-outline"

    @property
    def native_value(self) -> str | None:
        """Return current heating source."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get("summer_heating_source", "none")

    @property
    def icon(self) -> str:
        """Return icon based on heating source."""
        source = self.native_value
        icons = {
            "none": "mdi:power-sleep",
            "pv": "mdi:solar-power",
            "pv_excess": "mdi:solar-power-variant",
            "tariff_cheap": "mdi:currency-usd",
            "tariff_expensive": "mdi:currency-usd-off",
            "emergency": "mdi:alert",
        }
        return icons.get(source, "mdi:information-outline")

    @property
    def extra_state_attributes(self) -> dict:
        """Return extra attributes."""
        if self.coordinator.data is None:
            return {}
        return {
            "current_slot": self.coordinator.data.get("summer_current_slot"),
            "excess_mode_active": self.coordinator.data.get("summer_excess_mode_active"),
            "decision_reason": self.coordinator.data.get("summer_decision_reason"),
            "cooldown_active": self.coordinator.data.get("summer_cooldown_active"),
            "min_heating_elapsed": self.coordinator.data.get("summer_min_heating_elapsed"),
        }


class SummerPVBalanceSensor(CWUControllerBaseSensor):
    """Sensor showing current hourly PV balance (Summer mode)."""

    def __init__(self, coordinator: CWUControllerCoordinator, entry: ConfigEntry) -> None:
        """Initialize sensor."""
        super().__init__(coordinator, entry, "summer_pv_balance", "Summer PV Balance")
        self._attr_device_class = SensorDeviceClass.ENERGY
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
        self._attr_icon = "mdi:scale-balance"
        self._attr_suggested_display_precision = 2

    @property
    def native_value(self) -> float | None:
        """Return current hourly PV balance in kWh."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get("summer_pv_balance")

    @property
    def extra_state_attributes(self) -> dict:
        """Return extra attributes."""
        if self.coordinator.data is None:
            return {}
        balance = self.coordinator.data.get("summer_pv_balance")
        return {
            "pv_production_w": self.coordinator.data.get("summer_pv_production"),
            "grid_power_w": self.coordinator.data.get("summer_grid_power"),
            "status": "exporting" if balance is not None and balance > 0 else "importing",
            "note": "Hourly balance - resets each hour",
        }


class SummerCurrentSlotSensor(CWUControllerBaseSensor):
    """Sensor showing current time slot (Summer mode)."""

    def __init__(self, coordinator: CWUControllerCoordinator, entry: ConfigEntry) -> None:
        """Initialize sensor."""
        super().__init__(coordinator, entry, "summer_current_slot", "Summer Current Slot")
        self._attr_icon = "mdi:clock-outline"

    @property
    def native_value(self) -> str | None:
        """Return current time slot."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get("summer_current_slot", "unknown")

    @property
    def icon(self) -> str:
        """Return icon based on slot."""
        slot = self.native_value
        icons = {
            "slot_pv": "mdi:weather-sunny",
            "slot_evening": "mdi:weather-sunset",
            "slot_night": "mdi:weather-night",
        }
        return icons.get(slot, "mdi:clock-outline")

    @property
    def extra_state_attributes(self) -> dict:
        """Return extra attributes."""
        if self.coordinator.data is None:
            return {}
        slot = self.native_value
        descriptions = {
            "slot_pv": "PV slot (08:00-18:00) - Prioritize solar energy",
            "slot_evening": "Evening slot (18:00-24:00) - Fallback to cheap tariff",
            "slot_night": "Night slot (00:00-08:00) - Only safety buffer heating",
        }
        return {
            "description": descriptions.get(slot, "Unknown slot"),
            "is_cheap_tariff": self.coordinator.data.get("is_cheap_tariff"),
        }
