# CWU Controller - HACS Integration

Home Assistant integration for smart heat pump water heating management (CWU = Ciepła Woda Użytkowa / Domestic Hot Water).

## Project Structure

```
custom_components/cwu_controller/
├── __init__.py       # Integration setup, service registration
├── coordinator.py    # Main control logic (~2900 lines) - NEEDS REFACTORING
├── const.py          # All constants, thresholds, time windows
├── bsb_lan.py        # BSB-LAN client for heat pump communication
├── sensor.py         # HA sensor entities (state, urgency, energy, tariff)
├── number.py         # Editable threshold entities (cwu_target, cwu_min, etc.)
├── select.py         # Operating mode selector entity
├── switch.py         # Enable/disable switch
├── button.py         # Force CWU/Floor/Auto buttons
├── binary_sensor.py  # Fake heating, manual override sensors
├── config_flow.py    # Integration setup wizard
├── services.yaml     # Service definitions
├── translations/     # UI translations (en.json)
└── frontend/         # Custom panel UI
    ├── panel.html
    ├── panel.js
    └── styles.css

tests/                # pytest test suite
docs/WINTER_MODE.md   # Winter mode documentation
```

## Commands

```bash
# Run tests
source .venv/bin/activate && python -m pytest tests/ -v

# Run specific test
python -m pytest tests/test_coordinator.py -k "test_name" -v
```

---

## BSB-LAN Integration

Primary control via BSB-LAN (direct heat pump communication):

### Parameters Read (every update cycle):
| Param | Name | Usage |
|-------|------|-------|
| 700 | Floor mode | Protection/Automatic |
| 1600 | CWU mode | Off/On/Eco |
| 1610 | CWU target setpoint | Actual pump target temp |
| 8000 | HC1 status | Floor heating circuit status |
| 8003 | DHW status | Charging/Charged/Off/Ready |
| 8006 | HP status | Compressor on/off/defrost |
| 8410 | Return temp | For delta-T calculation |
| 8412 | Flow temp | For max temp detection |
| 8830 | CWU temp | Primary temp source |
| 8700 | Outside temp | Diagnostics |

### Write Operations:
- `1600` - Set CWU mode (0=Off, 1=On)
- `700` - Set floor mode (0=Protection, 1=Automatic)
- `1610` - Set CWU target temperature

### Write Verification:
All writes use `async_write_and_verify()` - writes value, waits 1s, reads back to confirm. Sends notification on failure.

---

## Operating Modes

### 1. broken_heater (default)
For broken immersion heater scenario - pump tries electric heater but it doesn't work.

**Key features:**
- 3-hour CWU cycle limit with 10-min pause
- Fake heating detection via BSB-LAN (DHW status "Charging electric")
- Anti-oscillation: min 15min CWU, 20min floor before switching
- Night floor window: 03:00-06:00 (floor heating if CWU OK)
- Max temp detection (pump can't heat more)
- Anti-fighting (avoid fighting for last few degrees)
- Rapid drop detection (hot water usage during floor heating)
- DHW Charged handling (5min rest before switching to floor)

**Fake heating flow:**
1. Detect "Charging electric" in DHW status
2. Turn OFF both CWU and floor
3. Wait `HP_RESTART_MIN_WAIT` (5 min)
4. Check HP ready (not defrosting, not in mandatory off time)
5. Restart CWU heating

### 2. winter
Scheduled CWU heating during cheap tariff windows.

**Heating windows:** 03:00-06:00, 13:00-15:00, 22:00-24:00

**Features:**
- Higher target temp (+5°C from config), max 55°C
- No 3h limit (heat until target reached)
- No fake heating detection (real heater works)
- Emergency heating outside windows if temp drops critically
- 3h no-progress timeout protection

### 3. summer
Not implemented yet (placeholder).

---

## Anti-Fighting Detection

Prevents pump from fighting for hours to reach last few degrees.

**Rolling 60-minute window** tracking:
- CWU temperature history
- Electric fallback event timestamps

**Triggers (when within 5°C of target):**
- `slow_progress`: <2°C rise in last 60 min
- `electric_fighting`: 4+ electric fallback events in last 60 min

**Constants:**
```python
MAX_TEMP_FIGHTING_WINDOW = 60         # Rolling window minutes
MAX_TEMP_FIGHTING_PROGRESS = 2.0      # Min progress in window
MAX_TEMP_FIGHTING_THRESHOLD = 5.0     # Distance to target
MAX_TEMP_FIGHTING_ELECTRIC_COUNT = 4  # Electric events threshold
```

**Reasoning format:**
```
Action: "Anti-fighting: stop"
Reasoning: "CWU 47.5°C (target 50.0°C, -2.5°C), progress +1.2°C/60min"
```

---

## Key States

| State | Description |
|-------|-------------|
| `idle` | Nothing heating |
| `heating_cwu` | CWU heating active |
| `heating_floor` | Floor heating active |
| `pause` | 10min pause after 3h CWU limit |
| `emergency_cwu` | Critical CWU temp, priority heating |
| `emergency_floor` | Critical room temp, priority floor |
| `fake_heating_detected` | Waiting for HP ready after fake heating |
| `fake_heating_restarting` | Restarting CWU after fake heating |
| `safe_mode` | BSB-LAN unavailable, both on (pump decides) |

---

## Important Constants (const.py)

### Timing
- `CWU_MAX_HEATING_TIME`: 170 min (before 3h limit triggers)
- `CWU_PAUSE_TIME`: 10 min
- `BSB_FAKE_HEATING_DETECTION_TIME`: 10 min
- `HP_RESTART_MIN_WAIT`: 5 min (after fake heating)
- `DHW_CHARGED_REST_TIME`: 5 min (before switching to floor)

### Anti-oscillation
- `MIN_CWU_HEATING_TIME`: 15 min
- `MIN_FLOOR_HEATING_TIME`: 20 min

### Max Temp Detection
- `MAX_TEMP_DETECTION_WINDOW`: 30 min
- `MAX_TEMP_FLOW_STAGNATION`: 2.0°C
- `MAX_TEMP_ELECTRIC_FALLBACK_COUNT`: 2

### Rapid Drop Detection
- `CWU_RAPID_DROP_THRESHOLD`: 5.0°C
- `CWU_RAPID_DROP_WINDOW`: 15 min

---

## Action History with Reasoning

Every control decision logged with reasoning:

```python
self._log_action(
    "Action name",           # Short action (displayed in history)
    "Detailed reasoning"     # Why this decision was made
)
```

**Examples:**
- `("CWU ON", "Idle → CWU, temp 42.1°C < target 45.0°C")`
- `("Fake heating", "CWU+Floor OFF, waiting 5+ min")`
- `("Anti-fighting: stop", "CWU 47.5°C (target 50.0°C, -2.5°C), progress +1.2°C/60min")`
- `("DHW Charged", "Pump reports charged at 48.2°C, waiting 5min")`

---

## Planned Refactoring: Mode Separation

Coordinator.py (~2900 lines) should be split:

```
custom_components/cwu_controller/
├── coordinator.py          # Core: state, BSB-LAN, energy, routing
├── modes/
│   ├── __init__.py
│   ├── base.py             # BaseModeHandler class
│   ├── broken_heater.py    # BrokenHeaterMode (~350 lines)
│   ├── winter.py           # WinterMode (~200 lines)
│   └── summer.py           # SummerMode (placeholder)
```

**Structure:**
```python
# modes/base.py
class BaseModeHandler:
    def __init__(self, coordinator: "CWUControllerCoordinator"):
        self.coord = coordinator

    async def run_logic(self, cwu_urgency, floor_urgency, ...) -> None:
        raise NotImplementedError

# modes/broken_heater.py
class BrokenHeaterMode(BaseModeHandler):
    """Broken heater mode - fake heating detection, anti-fighting, etc."""

    async def run_logic(self, cwu_urgency, floor_urgency, fake_heating,
                        cwu_temp, salon_temp) -> None:
        # All _run_broken_heater_mode_logic code here
        # Access coordinator via self.coord._current_state, etc.

# coordinator.py
class CWUControllerCoordinator:
    def __init__(self, ...):
        self._modes = {
            MODE_BROKEN_HEATER: BrokenHeaterMode(self),
            MODE_WINTER: WinterMode(self),
            MODE_SUMMER: SummerMode(self),
        }

    async def _run_control_logic(self, ...):
        handler = self._modes[self._operating_mode]
        await handler.run_logic(...)
```

**What stays in coordinator.py:**
- State variables (`_current_state`, `_enabled`, etc.)
- BSB-LAN client and control methods
- Energy tracking
- Tariff logic
- Shared helpers (`_switch_to_cwu`, `_switch_to_floor`, etc.)
- `_log_action`, `_change_state`, `_async_send_notification`

**What moves to mode handlers:**
- `_run_broken_heater_mode_logic()` → `BrokenHeaterMode.run_logic()`
- `_run_winter_mode_logic()` → `WinterMode.run_logic()`
- Mode-specific helpers (if only used by that mode)

---

## G12w Tariff (Poland/Energa)

- **Cheap**: 13:00-15:00, 22:00-06:00, weekends, holidays
- **Expensive**: All other times
- Uses `binary_sensor.workday_sensor` for holiday detection

---

## Version Management

- Integration version: `manifest.json` → sync to all `sw_version` in entity files
- Frontend versions: `panel.html` has cache-busting query params (?v=X.X.X)
- JS/CSS have internal version comments
