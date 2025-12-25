"""Constants for the CWU Controller integration."""
from typing import Final

DOMAIN: Final = "cwu_controller"
MANUFACTURER: Final = "CWU Controller"

# Operating modes
MODE_BROKEN_HEATER: Final = "broken_heater"
MODE_WINTER: Final = "winter"
MODE_SUMMER: Final = "summer"

OPERATING_MODES: Final = [MODE_BROKEN_HEATER, MODE_WINTER, MODE_SUMMER]

# Configuration keys
CONF_OPERATING_MODE: Final = "operating_mode"
CONF_CWU_TEMP_SENSOR: Final = "cwu_temp_sensor"
CONF_SALON_TEMP_SENSOR: Final = "salon_temp_sensor"
CONF_BEDROOM_TEMP_SENSOR: Final = "bedroom_temp_sensor"
CONF_KIDS_ROOM_TEMP_SENSOR: Final = "kids_room_temp_sensor"
CONF_POWER_SENSOR: Final = "power_sensor"
CONF_WATER_HEATER: Final = "water_heater"
CONF_CLIMATE: Final = "climate"
CONF_NOTIFY_SERVICE: Final = "notify_service"
CONF_PUMP_INPUT_TEMP: Final = "pump_input_temp"
CONF_PUMP_OUTPUT_TEMP: Final = "pump_output_temp"
CONF_CWU_INPUT_TEMP: Final = "cwu_input_temp"
CONF_FLOOR_INPUT_TEMP: Final = "floor_input_temp"
CONF_WORKDAY_SENSOR: Final = "workday_sensor"  # binary_sensor.workday_sensor

# Energy meter sensor for accurate energy tracking
CONF_ENERGY_SENSOR: Final = "energy_sensor"
DEFAULT_ENERGY_SENSOR: Final = "sensor.ogrzewanie_total_active_energy"

# Energy tracking intervals and thresholds
ENERGY_TRACKING_INTERVAL: Final = 60  # seconds - how often to check energy meter
ENERGY_DELTA_ANOMALY_THRESHOLD: Final = 10.0  # kWh - skip deltas larger than this (likely meter issue)

# Temperature thresholds
CONF_CWU_TARGET_TEMP: Final = "cwu_target_temp"
CONF_CWU_MIN_TEMP: Final = "cwu_min_temp"
CONF_CWU_CRITICAL_TEMP: Final = "cwu_critical_temp"
CONF_SALON_TARGET_TEMP: Final = "salon_target_temp"
CONF_SALON_MIN_TEMP: Final = "salon_min_temp"
CONF_BEDROOM_MIN_TEMP: Final = "bedroom_min_temp"

# Default values
DEFAULT_CWU_TARGET_TEMP: Final = 45.0
DEFAULT_CWU_MIN_TEMP: Final = 40.0
DEFAULT_CWU_CRITICAL_TEMP: Final = 35.0
DEFAULT_SALON_TARGET_TEMP: Final = 22.0
DEFAULT_SALON_MIN_TEMP: Final = 21.0
DEFAULT_BEDROOM_MIN_TEMP: Final = 19.0

# Power thresholds
POWER_IDLE_THRESHOLD: Final = 10  # Below this = pump waiting for broken heater
POWER_SPIKE_THRESHOLD: Final = 200  # Min power spike indicating real CWU heating
POWER_PUMP_RUNNING: Final = 80  # Pump running but not compressor
POWER_THERMODYNAMIC_MIN: Final = 300  # Thermodynamic heating active
POWER_THERMODYNAMIC_FULL: Final = 1000  # Full thermodynamic heating

# Time constants
CWU_MAX_HEATING_TIME: Final = 170  # 2h50m in minutes (before 3h limit)
CWU_PAUSE_TIME: Final = 10  # 10 minutes pause between cycles
FAKE_HEATING_DETECTION_TIME: Final = 10  # Minutes of low power before detection
FAKE_HEATING_RESTART_WAIT: Final = 2  # Minutes to wait before restarting after fake heating
SENSOR_UNAVAILABLE_GRACE: Final = 30  # Minutes before using fallback

# Evening bath time settings
EVENING_PREP_HOUR: Final = 15  # Start preparing CWU at 3 PM
BATH_TIME_HOUR: Final = 18  # Bath time starts at 6 PM

# States
STATE_IDLE: Final = "idle"
STATE_HEATING_CWU: Final = "heating_cwu"
STATE_HEATING_FLOOR: Final = "heating_floor"
STATE_PAUSE: Final = "pause"
STATE_EMERGENCY_CWU: Final = "emergency_cwu"
STATE_EMERGENCY_FLOOR: Final = "emergency_floor"
STATE_FAKE_HEATING_DETECTED: Final = "fake_heating_detected"
STATE_FAKE_HEATING_RESTARTING: Final = "fake_heating_restarting"
STATE_SAFE_MODE: Final = "safe_mode"  # Sensors unavailable - heat pump controls everything

# Urgency levels
URGENCY_NONE: Final = 0
URGENCY_LOW: Final = 1
URGENCY_MEDIUM: Final = 2
URGENCY_HIGH: Final = 3
URGENCY_CRITICAL: Final = 4

# Water heater modes
WH_MODE_OFF: Final = "off"
WH_MODE_HEAT_PUMP: Final = "heat_pump"
WH_MODE_PERFORMANCE: Final = "performance"

# Climate modes
CLIMATE_OFF: Final = "off"
CLIMATE_AUTO: Final = "auto"
CLIMATE_HEAT: Final = "heat"

# Safety: sensor unavailability timeout (minutes)
CWU_SENSOR_UNAVAILABLE_TIMEOUT: Final = 60  # Enter safe mode if CWU temp unavailable for this long

# Update interval
UPDATE_INTERVAL: Final = 60  # seconds

# G12w Tariff configuration (Energa 2025)
# Cheap hours: 13:00-15:00, 22:00-06:00, weekends, and public holidays
# Note: Rates can be updated via UI configuration
CONF_TARIFF_EXPENSIVE_RATE: Final = "tariff_expensive_rate"
CONF_TARIFF_CHEAP_RATE: Final = "tariff_cheap_rate"

# Default tariff rates (as of January 2025)
TARIFF_EXPENSIVE_RATE: Final = 1.16  # zł/kWh (0.62 energy + 0.54 distribution)
TARIFF_CHEAP_RATE: Final = 0.72  # zł/kWh (0.57 energy + 0.15 distribution)

# Cheap tariff time windows (weekdays only - weekends are always cheap)
TARIFF_CHEAP_WINDOWS: Final = [
    (13, 15),  # 13:00 - 15:00
    (22, 24),  # 22:00 - 24:00
    (0, 6),    # 00:00 - 06:00
]

# Holiday detection - use workday sensor (binary_sensor.workday_sensor from python-holidays)
# The workday sensor handles all Polish holidays dynamically including Easter-dependent ones

# Winter mode specific settings
WINTER_CWU_HEATING_WINDOWS: Final = [
    (3, 6),    # 03:00 - 06:00 (cheap tariff)
    (13, 15),  # 13:00 - 15:00 (cheap tariff)
    (22, 24),  # 22:00 - 24:00 (cheap tariff, after kids bath, before adults)
]
WINTER_CWU_TARGET_OFFSET: Final = 5.0  # Additional degrees above configured target
WINTER_CWU_EMERGENCY_OFFSET: Final = 10.0  # Heat outside windows if below target - this offset
WINTER_CWU_MAX_TEMP: Final = 55.0  # Maximum CWU temperature in winter mode
WINTER_CWU_NO_PROGRESS_TIMEOUT: Final = 180  # Minutes before checking for progress (3h)
WINTER_CWU_MIN_TEMP_INCREASE: Final = 1.0  # Minimum temp increase required in timeout period

# BSB-LAN Heat Pump Integration
BSB_LAN_HOST: Final = "192.168.50.219"
BSB_LAN_PARAMS: Final = "8003,8006,8412,8410,8830,8700"
BSB_LAN_TIMEOUT: Final = 5  # seconds
