# CWU Controller - HACS Integration

Home Assistant integration for smart heat pump water heating management (CWU = Ciepła Woda Użytkowa / Domestic Hot Water).

## Project Structure

```
custom_components/cwu_controller/
├── coordinator.py    # Main control logic, state machine, mode routing
├── const.py          # All constants, thresholds, time windows
├── sensor.py         # HA sensor entities (state, urgency, energy, tariff)
├── select.py         # Operating mode selector entity
├── switch.py         # Enable/disable switch
├── button.py         # Force CWU/Floor/Auto buttons
├── binary_sensor.py  # Fake heating detection sensor
├── config_flow.py    # Integration setup wizard
└── frontend/         # Custom panel UI (panel.html, panel.js, styles.css)

tests/                # pytest test suite
docs/WINTER_MODE.md   # Winter mode documentation
```

## Operating Modes

1. **broken_heater** (default) - Original mode for broken immersion heater scenario
   - 3-hour CWU cycle limit with 10-min pause
   - Fake heating detection (power < 10W while heating)
   - Urgency-based switching between CWU and floor

2. **winter** - Scheduled CWU heating during cheap tariff windows
   - Windows: 03:00-06:00, 13:00-15:00, 22:00-24:00
   - Higher target temp (+5°C), max 55°C
   - Emergency heating if temp drops below threshold
   - 3h no-progress timeout protection

3. **summer** - Not implemented yet

## Key States

`idle`, `heating_cwu`, `heating_floor`, `pause`, `emergency_cwu`, `emergency_floor`, `fake_heating_detected`, `fake_heating_restarting`, `safe_mode`

## Safe Mode

Triggered when CWU sensor unavailable for 60 minutes. Turns on both floor and CWU, letting heat pump decide. Auto-recovers when sensors return.

## G12w Tariff (Poland/Energa)

- **Cheap**: 13:00-15:00, 22:00-06:00, weekends, holidays
- **Expensive**: All other times
- Uses `binary_sensor.workday_sensor` for holiday detection

## Commands

```bash
# Run tests
source .venv/bin/activate && python -m pytest tests/ -v

# Run specific test
python -m pytest tests/test_coordinator.py -k "test_name" -v
```

## Version Management

- Integration version: `manifest.json` → sync to all `sw_version` in entity files
- Frontend versions: `panel.html` has cache-busting query params (?v=X.X.X)
- JS/CSS have internal version comments

## Important Thresholds (const.py)

- `CWU_MAX_HEATING_TIME`: 170 min (before 3h limit)
- `CWU_PAUSE_TIME`: 10 min
- `CWU_SENSOR_UNAVAILABLE_TIMEOUT`: 60 min → safe mode
- `POWER_IDLE_THRESHOLD`: 10W (fake heating detection)
- `FAKE_HEATING_DETECTION_TIME`: 10 min
