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
POWER_PUMP_RUNNING: Final = 80  # Pump running but not compressor
POWER_THERMODYNAMIC_MIN: Final = 300  # Thermodynamic heating active
POWER_THERMODYNAMIC_FULL: Final = 1000  # Full thermodynamic heating

# Time constants
CWU_MAX_HEATING_TIME: Final = 170  # 2h50m in minutes (before 3h limit)
CWU_PAUSE_TIME: Final = 10  # 10 minutes pause between cycles
FAKE_HEATING_DETECTION_TIME: Final = 5  # Minutes of low power before detection
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

# Update interval
UPDATE_INTERVAL: Final = 60  # seconds

# G12w Tariff configuration (Energa 2025)
# Cheap hours: 13:00-15:00, 22:00-06:00, weekends, and public holidays
TARIFF_EXPENSIVE_RATE: Final = 1.16  # zł/kWh (0.62 energy + 0.54 distribution)
TARIFF_CHEAP_RATE: Final = 0.72  # zł/kWh (0.57 energy + 0.15 distribution)

# Cheap tariff time windows (weekdays only - weekends are always cheap)
TARIFF_CHEAP_WINDOWS: Final = [
    (13, 15),  # 13:00 - 15:00
    (22, 24),  # 22:00 - 24:00
    (0, 6),    # 00:00 - 06:00
]

# Polish public holidays 2025
# Note: Easter-dependent holidays (Easter, Pentecost, Corpus Christi) change yearly
# Update these dates annually or implement dynamic Easter calculation
# Fixed holidays: Jan 1, Jan 6, May 1, May 3, Aug 15, Nov 1, Nov 11, Dec 25-26
# Easter 2025: April 20 -> Pentecost: June 8, Corpus Christi: June 19
PUBLIC_HOLIDAYS_2025: Final = [
    (1, 1),    # New Year
    (1, 6),    # Epiphany
    (4, 20),   # Easter Sunday (2025)
    (4, 21),   # Easter Monday (2025)
    (5, 1),    # Labour Day
    (5, 3),    # Constitution Day
    (6, 8),    # Pentecost (2025, Easter + 49 days)
    (6, 19),   # Corpus Christi (2025, Easter + 60 days)
    (8, 15),   # Assumption
    (11, 1),   # All Saints
    (11, 11),  # Independence Day
    (12, 25),  # Christmas Day
    (12, 26),  # Second Day of Christmas
]

# Winter mode specific settings
WINTER_CWU_HEATING_WINDOWS: Final = [
    (3, 6),    # 03:00 - 06:00 (cheap tariff)
    (13, 15),  # 13:00 - 15:00 (cheap tariff)
]
WINTER_CWU_TARGET_OFFSET: Final = 5.0  # Additional degrees above configured target
WINTER_CWU_EMERGENCY_OFFSET: Final = 10.0  # Heat outside windows if below target - this offset
WINTER_CWU_MAX_TEMP: Final = 55.0  # Maximum CWU temperature in winter mode
