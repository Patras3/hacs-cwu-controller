"""Pytest fixtures for CWU Controller tests."""
from __future__ import annotations

import sys
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
import pytest


# Create mock homeassistant module
class MockHomeAssistant:
    """Mock HomeAssistant module."""
    pass


# Create mock constants
class MockConst:
    STATE_UNAVAILABLE = "unavailable"
    STATE_UNKNOWN = "unknown"


class MockPlatform:
    SENSOR = "sensor"
    SWITCH = "switch"
    BINARY_SENSOR = "binary_sensor"
    BUTTON = "button"
    SELECT = "select"


class MockUnitOfTemperature:
    CELSIUS = "°C"


class MockUnitOfPower:
    WATT = "W"


class MockUnitOfTime:
    MINUTES = "min"


class MockUnitOfEnergy:
    KILO_WATT_HOUR = "kWh"


class MockSensorDeviceClass:
    TEMPERATURE = "temperature"
    POWER = "power"
    DURATION = "duration"
    ENERGY = "energy"
    MONETARY = "monetary"


class MockSensorStateClass:
    MEASUREMENT = "measurement"
    TOTAL = "total"


# Set up minimal mocks needed for imports
mock_ha_const = MagicMock()
mock_ha_const.STATE_UNAVAILABLE = "unavailable"
mock_ha_const.STATE_UNKNOWN = "unknown"
mock_ha_const.Platform = MockPlatform
mock_ha_const.UnitOfTemperature = MockUnitOfTemperature
mock_ha_const.UnitOfPower = MockUnitOfPower
mock_ha_const.UnitOfTime = MockUnitOfTime
mock_ha_const.UnitOfEnergy = MockUnitOfEnergy

mock_sensor = MagicMock()
mock_sensor.SensorEntity = type("SensorEntity", (), {})
mock_sensor.SensorDeviceClass = MockSensorDeviceClass
mock_sensor.SensorStateClass = MockSensorStateClass

mock_select = MagicMock()
mock_select.SelectEntity = type("SelectEntity", (), {})

mock_water_heater = MagicMock()
mock_water_heater.SERVICE_SET_OPERATION_MODE = "set_operation_mode"

mock_climate = MagicMock()
mock_climate.SERVICE_TURN_ON = "turn_on"
mock_climate.SERVICE_TURN_OFF = "turn_off"

# Create a real DataUpdateCoordinator base class
class MockDataUpdateCoordinator:
    """Mock DataUpdateCoordinator for testing."""
    def __init__(self, hass, logger, name, update_interval):
        self.hass = hass
        self.name = name
        self.update_interval = update_interval
        self.data = {}


mock_update_coordinator = MagicMock()
mock_update_coordinator.DataUpdateCoordinator = MockDataUpdateCoordinator
mock_update_coordinator.CoordinatorEntity = type("CoordinatorEntity", (), {"__init__": lambda self, coord: None})

# Create mock Store class for persistence
class MockStore:
    """Mock Store for testing persistence."""
    def __init__(self, hass, version, key):
        self.hass = hass
        self.version = version
        self.key = key
        self._data = None

    async def async_load(self):
        return self._data

    async def async_save(self, data):
        self._data = data


mock_storage = MagicMock()
mock_storage.Store = MockStore

# Set all mocks
sys.modules["homeassistant"] = MagicMock()
sys.modules["homeassistant.core"] = MagicMock()
sys.modules["homeassistant.config_entries"] = MagicMock()
sys.modules["homeassistant.const"] = mock_ha_const
sys.modules["homeassistant.const"].EVENT_HOMEASSISTANT_STOP = "homeassistant_stop"
sys.modules["homeassistant.helpers"] = MagicMock()
sys.modules["homeassistant.helpers.update_coordinator"] = mock_update_coordinator
sys.modules["homeassistant.helpers.entity_platform"] = MagicMock()
sys.modules["homeassistant.helpers.event"] = MagicMock()
sys.modules["homeassistant.helpers.storage"] = mock_storage
sys.modules["homeassistant.components"] = MagicMock()
sys.modules["homeassistant.components.frontend"] = MagicMock()
sys.modules["homeassistant.components.http"] = MagicMock()
sys.modules["homeassistant.components.sensor"] = mock_sensor
sys.modules["homeassistant.components.select"] = mock_select
sys.modules["homeassistant.components.water_heater"] = mock_water_heater
sys.modules["homeassistant.components.climate"] = mock_climate

# Now import the actual modules
from custom_components.cwu_controller.const import (
    CONF_OPERATING_MODE,
    MODE_BROKEN_HEATER,
    MODE_WINTER,
    DEFAULT_CWU_TARGET_TEMP,
    DEFAULT_CWU_MIN_TEMP,
    DEFAULT_CWU_CRITICAL_TEMP,
    DEFAULT_SALON_TARGET_TEMP,
    DEFAULT_SALON_MIN_TEMP,
    DEFAULT_BEDROOM_MIN_TEMP,
)


@pytest.fixture
def mock_hass():
    """Create a mock Home Assistant instance."""
    hass = MagicMock()
    hass.states = MagicMock()
    hass.services = MagicMock()
    hass.services.async_call = AsyncMock()
    hass.bus = MagicMock()
    hass.bus.async_listen_once = MagicMock(return_value=lambda: None)
    return hass


@pytest.fixture
def default_config():
    """Return default configuration for coordinator."""
    return {
        CONF_OPERATING_MODE: MODE_BROKEN_HEATER,
        "cwu_temp_sensor": "sensor.cwu_temp",
        "salon_temp_sensor": "sensor.salon_temp",
        "bedroom_temp_sensor": "sensor.bedroom_temp",
        "kids_room_temp_sensor": "sensor.kids_temp",
        "power_sensor": "sensor.power",
        "water_heater": "water_heater.cwu",
        "climate": "climate.floor",
        "notify_service": "notify.mobile",
        "cwu_target_temp": DEFAULT_CWU_TARGET_TEMP,
        "cwu_min_temp": DEFAULT_CWU_MIN_TEMP,
        "cwu_critical_temp": DEFAULT_CWU_CRITICAL_TEMP,
        "salon_target_temp": DEFAULT_SALON_TARGET_TEMP,
        "salon_min_temp": DEFAULT_SALON_MIN_TEMP,
        "bedroom_min_temp": DEFAULT_BEDROOM_MIN_TEMP,
    }


@pytest.fixture
def winter_config(default_config):
    """Return configuration with winter mode."""
    config = default_config.copy()
    config[CONF_OPERATING_MODE] = MODE_WINTER
    return config


@pytest.fixture
def mock_coordinator(mock_hass, default_config):
    """Create a mock coordinator for testing."""
    import logging
    from datetime import timedelta
    from custom_components.cwu_controller.coordinator import CWUControllerCoordinator

    # Create coordinator with mocked hass
    coordinator = CWUControllerCoordinator(mock_hass, default_config)

    return coordinator
