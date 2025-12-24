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

# =============================================================================
# Summer Mode specific settings
# =============================================================================

# Summer mode time slots (hours)
SUMMER_PV_SLOT_START: Final = 8   # 08:00 - start of PV slot
SUMMER_PV_SLOT_END: Final = 18    # 18:00 - end of PV slot (sunset in summer)
SUMMER_PV_DEADLINE: Final = 16    # 16:00 - after this hour, fallback to tariff if needed

# Summer mode temperature thresholds
SUMMER_CWU_TARGET_TEMP: Final = 50.0  # °C - target temperature
SUMMER_EVENING_THRESHOLD: Final = 42.0  # °C - below this temp, enable fallback after deadline
SUMMER_NIGHT_THRESHOLD: Final = 40.0    # °C - below this temp, heat at night (safety buffer)
SUMMER_NIGHT_TARGET: Final = 42.0       # °C - target temp for night heating (just buffer)
SUMMER_CWU_MAX_TEMP: Final = 55.0       # °C - maximum safe temperature (emergency stop)

# Summer mode PV settings
SUMMER_HEATER_POWER: Final = 3300  # W - default heater power
SUMMER_BALANCE_THRESHOLD: Final = 0.5  # 50% - balance threshold ratio for heating decision
SUMMER_PV_MIN_PRODUCTION: Final = 500  # W - minimum PV production to consider "sunny day"

# Summer mode heater protection
SUMMER_MIN_HEATING_TIME: Final = 30  # min - minimum runtime after turning on (heater protection)
SUMMER_MIN_COOLDOWN: Final = 5  # min - minimum cooldown before turning on again
SUMMER_BALANCE_CHECK_INTERVAL: Final = 15  # min - how often to check balance during heating

# Summer mode no-progress detection
SUMMER_CWU_NO_PROGRESS_TIMEOUT: Final = 60  # min - timeout for no progress (shorter than winter)
SUMMER_CWU_MIN_TEMP_INCREASE: Final = 2.0  # °C - expected temp increase (higher than winter)

# Excess PV Mode - reheat water from surplus PV
SUMMER_EXCESS_EXPORT_THRESHOLD: Final = -3000  # W - export to grid required to activate
SUMMER_EXCESS_BALANCE_THRESHOLD: Final = 2.0  # kWh - minimum balance to activate
SUMMER_EXCESS_BALANCE_MIN: Final = 0.5  # kWh - balance below which we stop
SUMMER_EXCESS_GRID_WARNING: Final = 2000  # W - grid draw at which we warn
SUMMER_EXCESS_GRID_STOP: Final = 3000  # W - grid draw at which we stop
SUMMER_EXCESS_CWU_MIN_OFFSET: Final = 5.0  # °C - water must be above (target - this) to activate

# Summer mode PV sensor configuration keys
CONF_PV_BALANCE_SENSOR: Final = "pv_balance_sensor"
CONF_PV_PRODUCTION_SENSOR: Final = "pv_production_sensor"
CONF_GRID_POWER_SENSOR: Final = "grid_power_sensor"
CONF_SUMMER_HEATER_POWER: Final = "summer_heater_power"
CONF_SUMMER_BALANCE_THRESHOLD: Final = "summer_balance_threshold"

# Summer mode time slot configuration keys
CONF_SUMMER_PV_SLOT_START: Final = "summer_pv_slot_start"
CONF_SUMMER_PV_SLOT_END: Final = "summer_pv_slot_end"
CONF_SUMMER_PV_DEADLINE: Final = "summer_pv_deadline"
CONF_SUMMER_NIGHT_THRESHOLD: Final = "summer_night_threshold"
CONF_SUMMER_NIGHT_TARGET: Final = "summer_night_target"

# Default PV sensor names
DEFAULT_PV_BALANCE_SENSOR: Final = "sensor.energia_bilans_netto"
DEFAULT_PV_PRODUCTION_SENSOR: Final = "sensor.inverter_moc_czynna"
DEFAULT_GRID_POWER_SENSOR: Final = "sensor.glowny_total_system_power"

# Summer mode heating sources (for tracking and display)
HEATING_SOURCE_NONE: Final = "none"
HEATING_SOURCE_PV: Final = "pv"
HEATING_SOURCE_PV_EXCESS: Final = "pv_excess"
HEATING_SOURCE_TARIFF_CHEAP: Final = "tariff_cheap"
HEATING_SOURCE_TARIFF_EXPENSIVE: Final = "tariff_expensive"
HEATING_SOURCE_EMERGENCY: Final = "emergency"

# Summer mode time slots (for state tracking)
SLOT_PV: Final = "slot_pv"
SLOT_EVENING: Final = "slot_evening"
SLOT_NIGHT: Final = "slot_night"

# PV export rate (for savings calculation)
PV_EXPORT_RATE: Final = 0.30  # zł/kWh - typical rate for exported energy
