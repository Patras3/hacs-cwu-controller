"""Tests for CWU Controller sensor entities."""
from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch
import pytest

from custom_components.cwu_controller.const import (
    TARIFF_CHEAP_RATE,
    TARIFF_EXPENSIVE_RATE,
)


@pytest.fixture
def mock_entry():
    """Create a mock config entry."""
    entry = MagicMock()
    entry.entry_id = "test_entry_id"
    return entry


def make_sensor(sensor_class, coordinator, entry):
    """Create a sensor and properly initialize it with coordinator."""
    sensor = sensor_class(coordinator, entry)
    # The CoordinatorEntity base class normally sets this in __init__
    sensor.coordinator = coordinator
    return sensor


@pytest.fixture
def coordinator_with_data(mock_coordinator):
    """Create coordinator with mock data."""
    mock_coordinator.data = {
        "controller_state": "heating_cwu",
        "cwu_temp": 42.5,
        "salon_temp": 21.0,
        "bedroom_temp": 19.5,
        "kids_temp": 20.0,
        "power": 800.0,
        "avg_power": 750.0,
        "cwu_urgency": 2,
        "floor_urgency": 1,
        "enabled": True,
        "manual_override": False,
        "fake_heating": False,
        "cwu_heating_minutes": 45.5,
        "cwu_target_temp": 45.0,
        "cwu_min_temp": 40.0,
        "salon_target_temp": 22.0,
        "operating_mode": "broken_heater",
        "is_cheap_tariff": True,
        "current_tariff_rate": 0.72,
        "is_cwu_heating_window": False,
        "winter_cwu_target": None,
        "energy_today_cwu_kwh": 2.5,
        "energy_today_floor_kwh": 1.8,
        "energy_today_total_kwh": 4.3,
        "energy_yesterday_cwu_kwh": 3.0,
        "energy_yesterday_floor_kwh": 2.2,
        "energy_yesterday_total_kwh": 5.2,
        "cost_today_cwu_estimate": 2.35,
        "cost_today_floor_estimate": 1.69,
        "cost_today_estimate": 4.04,
        "cost_yesterday_cwu_estimate": 2.82,
        "cost_yesterday_floor_estimate": 2.07,
        "cost_yesterday_estimate": 4.89,
        # Daily counters and session data
        "electric_fallback_count_today": 3,
        "electric_fallback_count": 2,
        "bsb_lan_errors_today": 5,
        "bsb_lan_available": True,
        "session_energy_kwh": 1.25,
        "cwu_session_start_time": "2025-01-01T10:30:00",
        "cwu_session_start_temp": 38.5,
    }
    return mock_coordinator


class TestCWUEnergyTodaySensor:
    """Tests for CWU Energy Today sensor."""

    def test_sensor_value(self, coordinator_with_data, mock_entry):
        """Test sensor returns correct energy value."""
        from custom_components.cwu_controller.sensor import CWUEnergyTodaySensor

        sensor = make_sensor(CWUEnergyTodaySensor, coordinator_with_data, mock_entry)
        assert sensor.native_value == 2.5

    def test_sensor_attributes(self, coordinator_with_data, mock_entry):
        """Test sensor returns correct attributes."""
        from custom_components.cwu_controller.sensor import CWUEnergyTodaySensor

        sensor = make_sensor(CWUEnergyTodaySensor, coordinator_with_data, mock_entry)
        attrs = sensor.extra_state_attributes
        assert attrs["yesterday_kwh"] == 3.0
        assert "last_reset" in attrs

    def test_sensor_none_data(self, mock_coordinator, mock_entry):
        """Test sensor handles None data."""
        from custom_components.cwu_controller.sensor import CWUEnergyTodaySensor

        mock_coordinator.data = None
        sensor = make_sensor(CWUEnergyTodaySensor, mock_coordinator, mock_entry)
        assert sensor.native_value is None

    def test_sensor_unit(self, coordinator_with_data, mock_entry):
        """Test sensor has correct unit."""
        from custom_components.cwu_controller.sensor import CWUEnergyTodaySensor

        sensor = make_sensor(CWUEnergyTodaySensor, coordinator_with_data, mock_entry)
        assert sensor._attr_native_unit_of_measurement == "kWh"


class TestFloorEnergyTodaySensor:
    """Tests for Floor Energy Today sensor."""

    def test_sensor_value(self, coordinator_with_data, mock_entry):
        """Test sensor returns correct energy value."""
        from custom_components.cwu_controller.sensor import FloorEnergyTodaySensor

        sensor = make_sensor(FloorEnergyTodaySensor, coordinator_with_data, mock_entry)
        assert sensor.native_value == 1.8

    def test_sensor_attributes(self, coordinator_with_data, mock_entry):
        """Test sensor returns correct attributes."""
        from custom_components.cwu_controller.sensor import FloorEnergyTodaySensor

        sensor = make_sensor(FloorEnergyTodaySensor, coordinator_with_data, mock_entry)
        attrs = sensor.extra_state_attributes
        assert attrs["yesterday_kwh"] == 2.2


class TestTotalEnergyTodaySensor:
    """Tests for Total Energy Today sensor."""

    def test_sensor_value(self, coordinator_with_data, mock_entry):
        """Test sensor returns correct total energy value."""
        from custom_components.cwu_controller.sensor import TotalEnergyTodaySensor

        sensor = make_sensor(TotalEnergyTodaySensor, coordinator_with_data, mock_entry)
        assert sensor.native_value == 4.3

    def test_sensor_attributes(self, coordinator_with_data, mock_entry):
        """Test sensor returns correct breakdown in attributes."""
        from custom_components.cwu_controller.sensor import TotalEnergyTodaySensor

        sensor = make_sensor(TotalEnergyTodaySensor, coordinator_with_data, mock_entry)
        attrs = sensor.extra_state_attributes
        assert attrs["cwu_kwh"] == 2.5
        assert attrs["floor_kwh"] == 1.8
        assert attrs["yesterday_total_kwh"] == 5.2


class TestCWUEnergyCostTodaySensor:
    """Tests for CWU Energy Cost Today sensor."""

    def test_sensor_value(self, coordinator_with_data, mock_entry):
        """Test sensor returns correct cost value."""
        from custom_components.cwu_controller.sensor import CWUEnergyCostTodaySensor

        sensor = make_sensor(CWUEnergyCostTodaySensor, coordinator_with_data, mock_entry)
        assert sensor.native_value == 2.35

    def test_sensor_unit(self, coordinator_with_data, mock_entry):
        """Test sensor has PLN unit."""
        from custom_components.cwu_controller.sensor import CWUEnergyCostTodaySensor

        sensor = make_sensor(CWUEnergyCostTodaySensor, coordinator_with_data, mock_entry)
        assert sensor._attr_native_unit_of_measurement == "PLN"

    def test_sensor_attributes(self, coordinator_with_data, mock_entry):
        """Test sensor returns yesterday cost in attributes."""
        from custom_components.cwu_controller.sensor import CWUEnergyCostTodaySensor

        sensor = make_sensor(CWUEnergyCostTodaySensor, coordinator_with_data, mock_entry)
        attrs = sensor.extra_state_attributes
        assert attrs["yesterday_cost"] == 2.82
        assert "note" in attrs


class TestFloorEnergyCostTodaySensor:
    """Tests for Floor Energy Cost Today sensor."""

    def test_sensor_value(self, coordinator_with_data, mock_entry):
        """Test sensor returns correct cost value."""
        from custom_components.cwu_controller.sensor import FloorEnergyCostTodaySensor

        sensor = make_sensor(FloorEnergyCostTodaySensor, coordinator_with_data, mock_entry)
        assert sensor.native_value == 1.69

    def test_sensor_unit(self, coordinator_with_data, mock_entry):
        """Test sensor has PLN unit."""
        from custom_components.cwu_controller.sensor import FloorEnergyCostTodaySensor

        sensor = make_sensor(FloorEnergyCostTodaySensor, coordinator_with_data, mock_entry)
        assert sensor._attr_native_unit_of_measurement == "PLN"

    def test_sensor_attributes(self, coordinator_with_data, mock_entry):
        """Test sensor returns yesterday cost in attributes."""
        from custom_components.cwu_controller.sensor import FloorEnergyCostTodaySensor

        sensor = make_sensor(FloorEnergyCostTodaySensor, coordinator_with_data, mock_entry)
        attrs = sensor.extra_state_attributes
        assert attrs["yesterday_cost"] == 2.07


class TestCurrentTariffRateSensor:
    """Tests for Current Tariff Rate sensor."""

    def test_sensor_cheap_rate(self, coordinator_with_data, mock_entry):
        """Test sensor shows cheap rate."""
        from custom_components.cwu_controller.sensor import CurrentTariffRateSensor

        sensor = make_sensor(CurrentTariffRateSensor, coordinator_with_data, mock_entry)
        assert sensor.native_value == 0.72

    def test_sensor_expensive_rate(self, coordinator_with_data, mock_entry):
        """Test sensor shows expensive rate."""
        from custom_components.cwu_controller.sensor import CurrentTariffRateSensor

        coordinator_with_data.data["current_tariff_rate"] = TARIFF_EXPENSIVE_RATE
        coordinator_with_data.data["is_cheap_tariff"] = False

        sensor = make_sensor(CurrentTariffRateSensor, coordinator_with_data, mock_entry)
        assert sensor.native_value == TARIFF_EXPENSIVE_RATE

    def test_sensor_attributes_cheap(self, coordinator_with_data, mock_entry):
        """Test sensor attributes during cheap tariff."""
        from custom_components.cwu_controller.sensor import CurrentTariffRateSensor

        sensor = make_sensor(CurrentTariffRateSensor, coordinator_with_data, mock_entry)
        attrs = sensor.extra_state_attributes
        assert attrs["tariff_type"] == "cheap"
        assert attrs["is_cheap_tariff"] is True

    def test_sensor_attributes_expensive(self, coordinator_with_data, mock_entry):
        """Test sensor attributes during expensive tariff."""
        from custom_components.cwu_controller.sensor import CurrentTariffRateSensor

        coordinator_with_data.data["is_cheap_tariff"] = False
        sensor = make_sensor(CurrentTariffRateSensor, coordinator_with_data, mock_entry)
        attrs = sensor.extra_state_attributes
        assert attrs["tariff_type"] == "expensive"
        assert attrs["is_cheap_tariff"] is False


class TestCWUControllerStateSensor:
    """Tests for CWU Controller State sensor."""

    def test_sensor_state_value(self, coordinator_with_data, mock_entry):
        """Test sensor returns controller state."""
        from custom_components.cwu_controller.sensor import CWUControllerStateSensor

        sensor = make_sensor(CWUControllerStateSensor, coordinator_with_data, mock_entry)
        assert sensor.native_value == "heating_cwu"

    def test_sensor_attributes_complete(self, coordinator_with_data, mock_entry):
        """Test sensor returns complete attributes."""
        from custom_components.cwu_controller.sensor import CWUControllerStateSensor

        sensor = make_sensor(CWUControllerStateSensor, coordinator_with_data, mock_entry)
        attrs = sensor.extra_state_attributes

        assert attrs["cwu_temp"] == 42.5
        assert attrs["salon_temp"] == 21.0
        assert attrs["power"] == 800.0
        assert attrs["enabled"] is True
        assert attrs["manual_override"] is False
        assert attrs["operating_mode"] == "broken_heater"
        assert attrs["is_cheap_tariff"] is True


class TestCWUUrgencySensor:
    """Tests for CWU Urgency sensor."""

    def test_sensor_urgency_value(self, coordinator_with_data, mock_entry):
        """Test sensor returns urgency level."""
        from custom_components.cwu_controller.sensor import CWUUrgencySensor

        sensor = make_sensor(CWUUrgencySensor, coordinator_with_data, mock_entry)
        assert sensor.native_value == 2

    def test_sensor_urgency_name_attribute(self, coordinator_with_data, mock_entry):
        """Test sensor returns urgency level name."""
        from custom_components.cwu_controller.sensor import CWUUrgencySensor

        sensor = make_sensor(CWUUrgencySensor, coordinator_with_data, mock_entry)
        attrs = sensor.extra_state_attributes
        assert attrs["level_name"] == "Medium"


class TestFloorUrgencySensor:
    """Tests for Floor Urgency sensor."""

    def test_sensor_urgency_value(self, coordinator_with_data, mock_entry):
        """Test sensor returns urgency level."""
        from custom_components.cwu_controller.sensor import FloorUrgencySensor

        sensor = make_sensor(FloorUrgencySensor, coordinator_with_data, mock_entry)
        assert sensor.native_value == 1

    def test_sensor_urgency_name_attribute(self, coordinator_with_data, mock_entry):
        """Test sensor returns urgency level name."""
        from custom_components.cwu_controller.sensor import FloorUrgencySensor

        sensor = make_sensor(FloorUrgencySensor, coordinator_with_data, mock_entry)
        attrs = sensor.extra_state_attributes
        assert attrs["level_name"] == "Low"


class TestCWUHeatingTimeSensor:
    """Tests for CWU Heating Time sensor."""

    def test_sensor_time_value(self, coordinator_with_data, mock_entry):
        """Test sensor returns heating time."""
        from custom_components.cwu_controller.sensor import CWUHeatingTimeSensor

        sensor = make_sensor(CWUHeatingTimeSensor, coordinator_with_data, mock_entry)
        assert sensor.native_value == 45.5

    def test_sensor_remaining_time(self, coordinator_with_data, mock_entry):
        """Test sensor calculates remaining time."""
        from custom_components.cwu_controller.sensor import CWUHeatingTimeSensor

        sensor = make_sensor(CWUHeatingTimeSensor, coordinator_with_data, mock_entry)
        attrs = sensor.extra_state_attributes
        assert attrs["max_minutes"] == 170
        assert attrs["remaining_minutes"] == 124.5
        assert attrs["percentage"] == pytest.approx(26.76, rel=0.01)


class TestAveragePowerSensor:
    """Tests for Average Power sensor."""

    def test_sensor_power_value(self, coordinator_with_data, mock_entry):
        """Test sensor returns average power."""
        from custom_components.cwu_controller.sensor import AveragePowerSensor

        sensor = make_sensor(AveragePowerSensor, coordinator_with_data, mock_entry)
        assert sensor.native_value == 750.0

    def test_sensor_unit(self, coordinator_with_data, mock_entry):
        """Test sensor has Watt unit."""
        from custom_components.cwu_controller.sensor import AveragePowerSensor

        sensor = make_sensor(AveragePowerSensor, coordinator_with_data, mock_entry)
        assert sensor._attr_native_unit_of_measurement == "W"


class TestElectricFallbackCountTodaySensor:
    """Tests for Electric Fallback Count Today sensor."""

    def test_sensor_value(self, coordinator_with_data, mock_entry):
        """Test sensor returns correct electric fallback count."""
        from custom_components.cwu_controller.sensor import ElectricFallbackCountTodaySensor

        sensor = make_sensor(ElectricFallbackCountTodaySensor, coordinator_with_data, mock_entry)
        assert sensor.native_value == 3

    def test_sensor_zero_value(self, mock_coordinator, mock_entry):
        """Test sensor returns 0 when no fallback events."""
        from custom_components.cwu_controller.sensor import ElectricFallbackCountTodaySensor

        mock_coordinator.data = {"electric_fallback_count_today": 0}
        sensor = make_sensor(ElectricFallbackCountTodaySensor, mock_coordinator, mock_entry)
        assert sensor.native_value == 0

    def test_sensor_default_value(self, mock_coordinator, mock_entry):
        """Test sensor returns 0 when key is missing."""
        from custom_components.cwu_controller.sensor import ElectricFallbackCountTodaySensor

        mock_coordinator.data = {}
        sensor = make_sensor(ElectricFallbackCountTodaySensor, mock_coordinator, mock_entry)
        assert sensor.native_value == 0

    def test_sensor_attributes(self, coordinator_with_data, mock_entry):
        """Test sensor returns correct attributes."""
        from custom_components.cwu_controller.sensor import ElectricFallbackCountTodaySensor

        sensor = make_sensor(ElectricFallbackCountTodaySensor, coordinator_with_data, mock_entry)
        attrs = sensor.extra_state_attributes
        assert attrs["session_count"] == 2
        assert "last_reset" in attrs
        assert "note" in attrs

    def test_sensor_none_data(self, mock_coordinator, mock_entry):
        """Test sensor handles None data."""
        from custom_components.cwu_controller.sensor import ElectricFallbackCountTodaySensor

        mock_coordinator.data = None
        sensor = make_sensor(ElectricFallbackCountTodaySensor, mock_coordinator, mock_entry)
        assert sensor.native_value is None


class TestBsbLanErrorsTodaySensor:
    """Tests for BSB-LAN Errors Today sensor."""

    def test_sensor_value(self, coordinator_with_data, mock_entry):
        """Test sensor returns correct error count."""
        from custom_components.cwu_controller.sensor import BsbLanErrorsTodaySensor

        sensor = make_sensor(BsbLanErrorsTodaySensor, coordinator_with_data, mock_entry)
        assert sensor.native_value == 5

    def test_sensor_zero_value(self, mock_coordinator, mock_entry):
        """Test sensor returns 0 when no errors."""
        from custom_components.cwu_controller.sensor import BsbLanErrorsTodaySensor

        mock_coordinator.data = {"bsb_lan_errors_today": 0}
        sensor = make_sensor(BsbLanErrorsTodaySensor, mock_coordinator, mock_entry)
        assert sensor.native_value == 0

    def test_sensor_default_value(self, mock_coordinator, mock_entry):
        """Test sensor returns 0 when key is missing."""
        from custom_components.cwu_controller.sensor import BsbLanErrorsTodaySensor

        mock_coordinator.data = {}
        sensor = make_sensor(BsbLanErrorsTodaySensor, mock_coordinator, mock_entry)
        assert sensor.native_value == 0

    def test_sensor_attributes(self, coordinator_with_data, mock_entry):
        """Test sensor returns correct attributes."""
        from custom_components.cwu_controller.sensor import BsbLanErrorsTodaySensor

        sensor = make_sensor(BsbLanErrorsTodaySensor, coordinator_with_data, mock_entry)
        attrs = sensor.extra_state_attributes
        assert attrs["bsb_lan_available"] is True
        assert "last_reset" in attrs
        assert "note" in attrs

    def test_sensor_none_data(self, mock_coordinator, mock_entry):
        """Test sensor handles None data."""
        from custom_components.cwu_controller.sensor import BsbLanErrorsTodaySensor

        mock_coordinator.data = None
        sensor = make_sensor(BsbLanErrorsTodaySensor, mock_coordinator, mock_entry)
        assert sensor.native_value is None


class TestSessionEnergySensor:
    """Tests for CWU Session Energy sensor."""

    def test_sensor_value(self, coordinator_with_data, mock_entry):
        """Test sensor returns correct session energy."""
        from custom_components.cwu_controller.sensor import SessionEnergySensor

        sensor = make_sensor(SessionEnergySensor, coordinator_with_data, mock_entry)
        assert sensor.native_value == 1.25

    def test_sensor_none_value(self, mock_coordinator, mock_entry):
        """Test sensor returns None when no session active."""
        from custom_components.cwu_controller.sensor import SessionEnergySensor

        mock_coordinator.data = {"session_energy_kwh": None}
        sensor = make_sensor(SessionEnergySensor, mock_coordinator, mock_entry)
        assert sensor.native_value is None

    def test_sensor_missing_key(self, mock_coordinator, mock_entry):
        """Test sensor returns None when key is missing."""
        from custom_components.cwu_controller.sensor import SessionEnergySensor

        mock_coordinator.data = {}
        sensor = make_sensor(SessionEnergySensor, mock_coordinator, mock_entry)
        assert sensor.native_value is None

    def test_sensor_attributes(self, coordinator_with_data, mock_entry):
        """Test sensor returns correct attributes."""
        from custom_components.cwu_controller.sensor import SessionEnergySensor

        sensor = make_sensor(SessionEnergySensor, coordinator_with_data, mock_entry)
        attrs = sensor.extra_state_attributes
        assert attrs["session_start_time"] == "2025-01-01T10:30:00"
        assert attrs["session_start_temp"] == 38.5
        assert attrs["cwu_heating_minutes"] == 45.5
        assert "note" in attrs

    def test_sensor_unit(self, coordinator_with_data, mock_entry):
        """Test sensor has kWh unit."""
        from custom_components.cwu_controller.sensor import SessionEnergySensor

        sensor = make_sensor(SessionEnergySensor, coordinator_with_data, mock_entry)
        assert sensor._attr_native_unit_of_measurement == "kWh"

    def test_sensor_none_data(self, mock_coordinator, mock_entry):
        """Test sensor handles None data."""
        from custom_components.cwu_controller.sensor import SessionEnergySensor

        mock_coordinator.data = None
        sensor = make_sensor(SessionEnergySensor, mock_coordinator, mock_entry)
        assert sensor.native_value is None
