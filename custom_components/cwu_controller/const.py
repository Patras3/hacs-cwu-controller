"""Constants for the CWU Controller integration."""
from typing import Final

DOMAIN: Final = "cwu_controller"
MANUFACTURER: Final = "CWU Controller"

# Operating modes
MODE_BROKEN_HEATER: Final = "broken_heater"
MODE_WINTER: Final = "winter"
MODE_SUMMER: Final = "summer"
MODE_HEAT_PUMP: Final = "heat_pump"

OPERATING_MODES: Final = [MODE_BROKEN_HEATER, MODE_WINTER, MODE_SUMMER, MODE_HEAT_PUMP]

# Configuration keys
CONF_OPERATING_MODE: Final = "operating_mode"
CONF_SALON_TEMP_SENSOR: Final = "salon_temp_sensor"
CONF_BEDROOM_TEMP_SENSOR: Final = "bedroom_temp_sensor"
CONF_KIDS_ROOM_TEMP_SENSOR: Final = "kids_room_temp_sensor"
CONF_POWER_SENSOR: Final = "power_sensor"
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
DEFAULT_CWU_TARGET_TEMP: Final = 55.0
DEFAULT_CWU_MIN_TEMP: Final = 40.0
DEFAULT_CWU_CRITICAL_TEMP: Final = 35.0
DEFAULT_SALON_TARGET_TEMP: Final = 22.0
DEFAULT_SALON_MIN_TEMP: Final = 21.0
DEFAULT_BEDROOM_MIN_TEMP: Final = 19.0

# CWU Hysteresis (pump won't heat if difference < this value)
CONF_CWU_HYSTERESIS: Final = "cwu_hysteresis"
DEFAULT_CWU_HYSTERESIS: Final = 5.0  # Heat pump typically needs 5°C difference to heat

# Power thresholds
POWER_IDLE_THRESHOLD: Final = 10  # Below this = pump waiting for broken heater
POWER_SPIKE_THRESHOLD: Final = 200  # Min power spike indicating real CWU heating
POWER_PUMP_RUNNING: Final = 80  # Pump running but not compressor
POWER_THERMODYNAMIC_MIN: Final = 300  # Thermodynamic heating active
POWER_THERMODYNAMIC_FULL: Final = 1000  # Full thermodynamic heating
POWER_ELECTRIC_HEATER_MIN: Final = 2500  # Electric heater should draw ~3.3kW, >2.5kW expected

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

# Heat Pump mode states (pump decides, we monitor)
STATE_PUMP_IDLE: Final = "pump_idle"  # Both enabled, pump not heating
STATE_PUMP_HEATING_CWU: Final = "pump_heating_cwu"  # Pump heating CWU thermodynamically
STATE_PUMP_HEATING_FLOOR: Final = "pump_heating_floor"  # Pump heating floor
STATE_PUMP_HEATING_CWU_ELECTRIC: Final = "pump_heating_cwu_electric"  # CWU via electric heater (3.3kW)

# Urgency levels
URGENCY_NONE: Final = 0
URGENCY_LOW: Final = 1
URGENCY_MEDIUM: Final = 2
URGENCY_HIGH: Final = 3
URGENCY_CRITICAL: Final = 4

# Safe mode - BSB-LAN unavailability (cloud used ONLY as last resort)
BSB_LAN_UNAVAILABLE_TIMEOUT: Final = 15  # minutes before entering safe mode
SAFE_MODE_WATER_HEATER: Final = "water_heater.pompa_ciepla_io_13873843_2"
SAFE_MODE_CLIMATE: Final = "climate.pompa_ciepla_dom"
SAFE_MODE_DELAY: Final = 120  # 2 minutes between CWU and floor commands

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
# Note: Winter mode now uses the same target temperature as other modes (no offset)
WINTER_CWU_NO_PROGRESS_TIMEOUT: Final = 180  # Minutes before checking for progress (3h)
WINTER_CWU_MIN_TEMP_INCREASE: Final = 1.0  # Minimum temp increase required in timeout period

# BSB-LAN Heat Pump Integration
CONF_BSB_LAN_HOST: Final = "bsb_lan_host"
DEFAULT_BSB_LAN_HOST: Final = "192.168.50.219"
BSB_LAN_READ_TIMEOUT: Final = 5  # seconds for reads
BSB_LAN_WRITE_TIMEOUT: Final = 10  # seconds for writes (allow more time)
BSB_LAN_FAILURES_THRESHOLD: Final = 3  # consecutive failures before marking unavailable
BSB_LAN_STATE_VERIFY_INTERVAL: Final = 5  # minutes - how often to verify pump state matches expected

# BSB-LAN Parameters for reading (includes 1610 for CWU target setpoint)
# Diagnostic parameters: 8749 (HC1 thermostat demand), 8820/8821 (pump/heater state),
# 8840-8843 (run hours and start counters for DHW pump and electric heater)
BSB_LAN_READ_PARAMS: Final = "700,710,1600,1610,8000,8003,8006,8412,8410,8830,8700,8749,8820,8821,8840,8841,8842,8843"

# BSB-LAN Control Parameters (write)
BSB_LAN_PARAM_CWU_MODE: Final = 1600  # 0=Off, 1=On, 2=Eco
BSB_LAN_PARAM_FLOOR_MODE: Final = 700  # 0=Protection, 1=Automatic, 2=Reduced, 3=Comfort

# BSB-LAN CWU Target Setpoint Parameters
BSB_LAN_PARAM_CWU_TARGET_NOMINAL: Final = 1610  # DHW nominal setpoint
BSB_LAN_PARAM_CWU_TARGET_REDUCED: Final = 1612  # DHW reduced setpoint
BSB_LAN_CWU_MAX_TEMP: Final = 55  # Maximum CWU temperature settable

# BSB-LAN Floor Comfort Setpoint Parameter
BSB_LAN_PARAM_FLOOR_COMFORT_SETPOINT: Final = 710  # Room temp comfort setpoint
BSB_FLOOR_BOOST_TEMP: Final = 28.0  # Temperature for floor boost (max)
BSB_FLOOR_MIN_TEMP: Final = 15.0  # Minimum floor temperature settable
BSB_FLOOR_MAX_TEMP: Final = 28.0  # Maximum floor temperature settable

# BSB-LAN CWU Modes (parameter 1600)
BSB_CWU_MODE_OFF: Final = 0
BSB_CWU_MODE_ON: Final = 1
BSB_CWU_MODE_ECO: Final = 2

# BSB-LAN Floor Modes (parameter 700)
BSB_FLOOR_MODE_PROTECTION: Final = 0
BSB_FLOOR_MODE_AUTOMATIC: Final = 1
BSB_FLOOR_MODE_REDUCED: Final = 2
BSB_FLOOR_MODE_COMFORT: Final = 3

# BSB-LAN DHW Status values (from 8003)
BSB_DHW_STATUS_OFF: Final = "Off"
BSB_DHW_STATUS_READY: Final = "Ready"
BSB_DHW_STATUS_CHARGING: Final = "Charging"
BSB_DHW_STATUS_CHARGING_ELECTRIC: Final = "Charging electric"  # Broken heater!

# BSB-LAN Compressor status indicators (from 8006)
BSB_HP_COMPRESSOR_ON: Final = "Compressor"  # substring match
BSB_HP_OFF_TIME_ACTIVE: Final = "off time"  # "Compressor off time min active" - mandatory rest period

# Control source tracking
CONTROL_SOURCE_BSB_LAN: Final = "bsb_lan"
CONTROL_SOURCE_HA_CLOUD: Final = "ha_cloud"

# BSB-LAN fake heating detection
BSB_FAKE_HEATING_DETECTION_TIME: Final = 10  # Minutes of "charging but no compressor" before detection

# =============================================================================
# BROKEN HEATER MODE - Refactored Constants
# =============================================================================

# Time-of-Day Floor Window (podłogówka tylko w tym oknie jeśli CWU OK)
BROKEN_HEATER_FLOOR_WINDOW_START: Final = 3   # 03:00
BROKEN_HEATER_FLOOR_WINDOW_END: Final = 6     # 06:00

# Anti-Oscillation: Minimum Hold Times (z HP status check)
MIN_CWU_HEATING_TIME: Final = 15    # 15 min min na CWU przed przełączeniem
MIN_FLOOR_HEATING_TIME: Final = 20  # 20 min min na floor przed przełączeniem

# Max Temp Detection (pompa nie daje rady więcej)
MAX_TEMP_DETECTION_WINDOW: Final = 30        # 30 min obserwacji flow temp
MAX_TEMP_FLOW_STAGNATION: Final = 2.0        # Flow temp nie rośnie o >2°C = stagnacja
MAX_TEMP_ELECTRIC_FALLBACK_COUNT: Final = 2  # 2x "Charging electric" = max osiągnięty
MAX_TEMP_ACCEPTABLE_DROP: Final = 5.0        # Spadek o 5°C od max = OK
MAX_TEMP_CRITICAL_THRESHOLD: Final = 38.0    # Poniżej 38°C spadek nieakceptowalny

# Anti-fighting constants (avoid fighting for last few degrees for hours)
MAX_TEMP_FIGHTING_WINDOW: Final = 60         # Rolling window: last 60 min
MAX_TEMP_FIGHTING_PROGRESS: Final = 2.0      # Less than 2°C rise in window = fighting
MAX_TEMP_FIGHTING_THRESHOLD: Final = 5.0     # Within 5°C of target = close enough, stop fighting
MAX_TEMP_FIGHTING_ELECTRIC_COUNT: Final = 4  # 4+ electric fallbacks in window = fighting
# Note: Each electric fallback cycle takes 5-15 min (fake heating detection + HP wait)
# So 4 events in 60 min = pump struggling for ~45+ min = clear sign of fighting

# Rapid Drop Detection (pobór CWU - kąpiel)
CWU_RAPID_DROP_THRESHOLD: Final = 5.0   # 5°C spadek = ktoś się kąpie
CWU_RAPID_DROP_WINDOW: Final = 15       # w ciągu 15 min

# HP Status Check before restart
HP_RESTART_MIN_WAIT: Final = 5  # 5 min min czekania po fake heating
HP_STATUS_DEFROSTING: Final = "Defrost"  # substring - HP rozmraża
HP_STATUS_OVERRUN: Final = "Overrun"     # substring - dobieg pompy

# DHW Status Check
DHW_STATUS_CHARGED: Final = "charged"  # substring - pompa osiągnęła cel (case insensitive)
DHW_CHARGED_REST_TIME: Final = 5  # minutes - rest time after pump reports charged before switching

# Manual Heat-to Feature
MANUAL_HEAT_TO_MIN_TEMP: Final = 36  # Minimum temperature for manual heat-to
MANUAL_HEAT_TO_MAX_TEMP: Final = 55  # Maximum temperature for manual heat-to

# Outside Temp Thresholds (info only, nie zmieniamy targetu)
OUTSIDE_TEMP_COLD: Final = 0      # < 0°C - pompa mniej wydajna
OUTSIDE_TEMP_VERY_COLD: Final = -5
OUTSIDE_TEMP_EXTREME: Final = -10
