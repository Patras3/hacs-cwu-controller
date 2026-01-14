# CWU Controller - Card Integration Guide

Documentation for integrating external Home Assistant cards with CWU Controller entities.

## Quick Reference

**Main entity:** `sensor.cwu_controller_state`
**Entity prefix:** `sensor.cwu_controller_*`, `binary_sensor.cwu_controller_*`, etc.

---

## Operating Modes

Selected via `select.cwu_controller_operating_mode`

| Mode | Value | Description |
|------|-------|-------------|
| Broken Heater | `broken_heater` | Default mode. Pump has broken electric heater - controller manages CWU/floor switching |
| Winter | `winter` | Scheduled CWU heating during cheap tariff windows |
| Summer | `summer` | Placeholder (not implemented) |
| Heat Pump | `heat_pump` | Pump decides everything, controller only monitors |

---

## Controller States

Available in `sensor.cwu_controller_state` (state attribute)

### Standard Modes (broken_heater, winter, summer)

| State | Description |
|-------|-------------|
| `idle` | Nothing heating |
| `heating_cwu` | CWU (hot water) heating active |
| `heating_floor` | Floor heating active |
| `pause` | 10-min pause after 3h CWU cycle limit |
| `emergency_cwu` | Critical CWU temp, priority heating |
| `emergency_floor` | Critical room temp, priority floor heating |
| `fake_heating_detected` | Waiting for HP ready after fake heating detected |
| `fake_heating_restarting` | Restarting CWU after fake heating |
| `safe_mode` | BSB-LAN unavailable, both CWU and floor enabled (pump decides) |

### Heat Pump Mode States

| State | Description |
|-------|-------------|
| `pump_idle` | Both enabled, pump not heating anything |
| `pump_cwu` | CWU is being heated (compressor or electric or both) |
| `pump_floor` | Floor is being heated (compressor or electric or both) |
| `pump_both` | Both CWU and floor are being heated simultaneously |

---

## Compressor Target

**Sensor:** `sensor.cwu_controller_compressor_target`

Shows what the heat pump compressor is currently heating.

| Value | Description |
|-------|-------------|
| `idle` | Compressor not running |
| `cwu` | Compressor heating CWU (hot water) |
| `floor` | Compressor heating floor |
| `defrost` | Compressor in defrost mode |

**Extra attributes:**
- `dhw_status` - Raw DHW status from BSB-LAN
- `hp_status` - Raw heat pump status from BSB-LAN
- `hc1_status` - Raw HC1 (heating circuit) status from BSB-LAN

---

## Urgency Levels

Used in `sensor.cwu_controller_cwu_urgency` and `sensor.cwu_controller_floor_urgency`

| Level | Value | Meaning |
|-------|-------|---------|
| None | `0` | No heating needed |
| Low | `1` | Below target, can wait |
| Medium | `2` | Getting low, should heat soon |
| High | `3` | Low temperature, heat now |
| Critical | `4` | Emergency - immediate action required |

**Sensor attributes:**
- `level_name` - Human readable: "None", "Low", "Medium", "High", "Critical"
- `cwu_temp` / `salon_temp` / `bedroom_temp` - Current temperatures

---

## Main State Sensor Attributes

`sensor.cwu_controller_state` provides extensive data in `extra_state_attributes`:

### Temperatures
| Attribute | Type | Description |
|-----------|------|-------------|
| `cwu_temp` | float | Current CWU (hot water) temperature |
| `salon_temp` | float | Living room temperature |
| `bedroom_temp` | float | Bedroom temperature |
| `kids_temp` | float | Kids room temperature |

### Configuration
| Attribute | Type | Description |
|-----------|------|-------------|
| `cwu_target_temp` | float | Target CWU temperature |
| `cwu_min_temp` | float | Minimum CWU temperature |
| `cwu_critical_temp` | float | Critical CWU temperature |
| `salon_target_temp` | float | Target living room temperature |

### Status Flags
| Attribute | Type | Description |
|-----------|------|-------------|
| `enabled` | bool | Controller enabled |
| `manual_override` | bool | Manual override active |
| `manual_override_until` | datetime | When manual override expires |
| `fake_heating_detected` | bool | Fake heating currently detected |
| `operating_mode` | string | Current operating mode |

### CWU Session Tracking
| Attribute | Type | Description |
|-----------|------|-------------|
| `cwu_session_start_time` | datetime | When CWU heating session started |
| `cwu_session_start_temp` | float | CWU temp when session started |
| `cwu_heating_minutes` | int | Minutes of CWU heating in current cycle |

### Energy Tracking
| Attribute | Type | Description |
|-----------|------|-------------|
| `energy_today_cwu_kwh` | float | CWU energy today (kWh) |
| `energy_today_floor_kwh` | float | Floor energy today (kWh) |
| `energy_today_total_kwh` | float | Total energy today (kWh) |
| `energy_yesterday_cwu_kwh` | float | CWU energy yesterday |
| `energy_yesterday_floor_kwh` | float | Floor energy yesterday |
| `energy_yesterday_total_kwh` | float | Total energy yesterday |
| `energy_today_cwu_cheap_kwh` | float | CWU cheap tariff energy today |
| `energy_today_cwu_expensive_kwh` | float | CWU expensive tariff energy today |
| `energy_today_floor_cheap_kwh` | float | Floor cheap tariff energy today |
| `energy_today_floor_expensive_kwh` | float | Floor expensive tariff energy today |

### Cost Estimates
| Attribute | Type | Description |
|-----------|------|-------------|
| `cost_today_estimate` | float | Total cost estimate today (PLN) |
| `cost_today_cwu_estimate` | float | CWU cost estimate today |
| `cost_today_floor_estimate` | float | Floor cost estimate today |
| `cost_yesterday_estimate` | float | Total cost estimate yesterday |
| `tariff_cheap_rate` | float | Cheap tariff rate (PLN/kWh) |
| `tariff_expensive_rate` | float | Expensive tariff rate (PLN/kWh) |

### Tariff Info
| Attribute | Type | Description |
|-----------|------|-------------|
| `is_cheap_tariff` | bool | Currently in cheap tariff period |
| `current_tariff_rate` | float | Current tariff rate (PLN/kWh) |
| `is_cwu_heating_window` | bool | In winter mode CWU heating window |

### Anti-Oscillation (broken_heater mode)
| Attribute | Type | Description |
|-----------|------|-------------|
| `hold_time_remaining` | int | Minutes until can switch |
| `can_switch_to_cwu` | bool | Switching to CWU allowed |
| `can_switch_to_floor` | bool | Switching to floor allowed |
| `switch_blocked_reason` | string | Why switching is blocked |

### Heat Pump Status
| Attribute | Type | Description |
|-----------|------|-------------|
| `hp_ready` | bool | Heat pump ready to heat |
| `hp_ready_reason` | string | Why HP is/isn't ready |
| `compressor_target` | string | What compressor is heating (cwu/floor/idle/defrost) |

### Max Temp Detection (broken_heater mode)
| Attribute | Type | Description |
|-----------|------|-------------|
| `max_temp_achieved` | float | Maximum CWU temp achieved |
| `max_temp_detected` | bool | Max temp detection active |
| `electric_fallback_count` | int | Electric fallback events this session |

### Floor Boost Status
| Attribute | Type | Description |
|-----------|------|-------------|
| `floor_boost_active` | bool | Floor boost currently active |
| `floor_boost_session` | bool | Boost until session ends (vs timed) |
| `floor_boost_until` | datetime | When boost expires |
| `floor_boost_original_mode` | string | Mode before boost |
| `floor_boost_original_setpoint` | float | Temp setpoint before boost |

### BSB-LAN Data
| Attribute | Type | Description |
|-----------|------|-------------|
| `bsb_lan` | dict | Full BSB-LAN data object |
| `bsb_lan_data` | dict | Alias for compatibility |

### History
| Attribute | Type | Description |
|-----------|------|-------------|
| `state_history` | list | Recent state changes |
| `action_history` | list | Recent actions with reasoning |
| `last_reasoning` | string | Last action reasoning |

---

## BSB-LAN Data Object

Available in `bsb_lan` / `bsb_lan_data` attribute of state sensor:

| Key | Type | Description |
|-----|------|-------------|
| `dhw_status` | string | DHW status (Off/Ready/Charging/Charging electric) |
| `hp_status` | string | Heat pump status (includes "Compressor", "Defrost", etc.) |
| `hc1_status` | string | HC1 heating circuit status |
| `cwu_mode` | string | CWU mode (Off/On/Eco) |
| `floor_mode` | string | Floor mode (Protection/Automatic/Reduced/Comfort) |
| `cwu_temp` | float | CWU temperature from BSB-LAN |
| `flow_temp` | float | Flow temperature |
| `return_temp` | float | Return temperature |
| `delta_t` | float | Delta T (flow - return) |
| `outside_temp` | float | Outside temperature |
| `dhw_pump_state` | string | DHW pump state |
| `dhw_pump_hours` | float | DHW pump run hours |
| `dhw_pump_starts` | int | DHW pump start count |
| `electric_heater_cwu_state` | string | CWU electric heater state (On/Off) |
| `electric_heater_cwu_hours` | float | CWU heater run hours |
| `electric_heater_cwu_starts` | int | CWU heater start count |
| `electric_heater_floor_1_state` | string | Floor heater 1 state |
| `electric_heater_floor_2_state` | string | Floor heater 2 state |
| `electric_heater_floor_hours` | float | Floor heater run hours |
| `electric_heater_floor_starts` | int | Floor heater start count |
| `hc1_thermostat_demand` | string | Thermostat demand status |

---

## All Entities Reference

### Sensors

| Entity ID | Type | Description |
|-----------|------|-------------|
| `sensor.cwu_controller_state` | string | Main state + all attributes |
| `sensor.cwu_controller_cwu_urgency` | int (0-4) | CWU heating urgency |
| `sensor.cwu_controller_floor_urgency` | int (0-4) | Floor heating urgency |
| `sensor.cwu_controller_avg_power` | float (W) | Average power consumption |
| `sensor.cwu_controller_cwu_heating_time` | float (min) | CWU heating time in cycle |
| `sensor.cwu_controller_cwu_target_temp` | float (°C) | Effective CWU target |
| `sensor.cwu_controller_cwu_energy_today` | float (kWh) | CWU energy today |
| `sensor.cwu_controller_floor_energy_today` | float (kWh) | Floor energy today |
| `sensor.cwu_controller_total_energy_today` | float (kWh) | Total energy today |
| `sensor.cwu_controller_cwu_energy_cost_today` | float (PLN) | CWU cost today |
| `sensor.cwu_controller_floor_energy_cost_today` | float (PLN) | Floor cost today |
| `sensor.cwu_controller_tariff_rate` | float (PLN/kWh) | Current tariff rate |
| `sensor.cwu_controller_control_source` | string | bsb_lan or ha_cloud |
| `sensor.cwu_controller_electric_fallback_today` | int | Electric fallback count today |
| `sensor.cwu_controller_bsb_lan_errors_today` | int | BSB-LAN errors today |
| `sensor.cwu_controller_session_energy` | float (kWh) | Current CWU session energy |
| `sensor.cwu_controller_compressor_target` | string | What compressor heats |

### BSB-LAN Sensors

| Entity ID | Type | Description |
|-----------|------|-------------|
| `sensor.cwu_controller_bsb_dhw_status` | string | DHW status |
| `sensor.cwu_controller_bsb_hp_status` | string | Heat pump status |
| `sensor.cwu_controller_bsb_hc1_status` | string | HC1 circuit status |
| `sensor.cwu_controller_bsb_cwu_mode` | string | CWU mode (Off/On/Eco) |
| `sensor.cwu_controller_bsb_floor_mode` | string | Floor mode |
| `sensor.cwu_controller_bsb_cwu_temp` | float (°C) | CWU temp from BSB |
| `sensor.cwu_controller_bsb_flow_temp` | float (°C) | Flow temperature |
| `sensor.cwu_controller_bsb_return_temp` | float (°C) | Return temperature |
| `sensor.cwu_controller_bsb_delta_t` | float (°C) | Delta T |
| `sensor.cwu_controller_bsb_outside_temp` | float (°C) | Outside temperature |

### Binary Sensors

| Entity ID | Description |
|-----------|-------------|
| `binary_sensor.cwu_controller_cwu_heating` | CWU actively heating |
| `binary_sensor.cwu_controller_floor_heating` | Floor actively heating |
| `binary_sensor.cwu_controller_fake_heating` | Fake heating detected |
| `binary_sensor.cwu_controller_manual_override` | Manual override active |
| `binary_sensor.cwu_controller_bsb_lan_available` | BSB-LAN connectivity |
| `binary_sensor.cwu_controller_electric_heater_cwu` | CWU electric heater ON |
| `binary_sensor.cwu_controller_electric_heater_floor_1` | Floor heater 1 ON |
| `binary_sensor.cwu_controller_electric_heater_floor_2` | Floor heater 2 ON |

### Controls

| Entity ID | Type | Description |
|-----------|------|-------------|
| `switch.cwu_controller_enabled` | switch | Enable/disable controller |
| `select.cwu_controller_operating_mode` | select | Operating mode selector |

### Number Inputs (Editable)

| Entity ID | Range | Default | Description |
|-----------|-------|---------|-------------|
| `number.cwu_controller_cwu_target_temp` | 40-55°C | 55 | CWU target temperature |
| `number.cwu_controller_cwu_min_temp` | 35-50°C | 40 | CWU minimum temperature |
| `number.cwu_controller_cwu_critical_temp` | 30-40°C | 35 | CWU critical temperature |
| `number.cwu_controller_cwu_hysteresis` | 3-15°C | 5 | CWU hysteresis margin |
| `number.cwu_controller_salon_target_temp` | 18-25°C | 22 | Living room target |
| `number.cwu_controller_salon_min_temp` | 17-23°C | 21 | Living room minimum |
| `number.cwu_controller_bedroom_min_temp` | 16-22°C | 19 | Bedroom minimum |

### Buttons

| Entity ID | Description |
|-----------|-------------|
| `button.cwu_controller_force_cwu_3h` | Force CWU for 3 hours |
| `button.cwu_controller_force_cwu_6h` | Force CWU for 6 hours |
| `button.cwu_controller_force_floor_3h` | Force floor for 3 hours |
| `button.cwu_controller_force_floor_6h` | Force floor for 6 hours |
| `button.cwu_controller_force_auto` | Cancel override, return to auto |
| `button.cwu_controller_floor_boost_session` | Boost floor until session ends |
| `button.cwu_controller_floor_boost_cancel` | Cancel floor boost |

---

## Services

| Service | Parameters | Description |
|---------|------------|-------------|
| `cwu_controller.force_cwu` | `duration` (min, default 180) | Force CWU heating |
| `cwu_controller.force_floor` | `duration` (min, default 180) | Force floor heating |
| `cwu_controller.force_auto` | - | Cancel override |
| `cwu_controller.enable` | - | Enable controller |
| `cwu_controller.disable` | - | Disable controller |
| `cwu_controller.set_mode` | `mode` (string) | Set operating mode |
| `cwu_controller.heat_to_temp` | `target_temp` (36-55, default 50) | Heat CWU to specific temp |
| `cwu_controller.floor_boost` | `hours` (1-8, default 2) | Boost floor for hours |
| `cwu_controller.floor_boost_session` | - | Boost floor until session ends |
| `cwu_controller.floor_boost_cancel` | - | Cancel floor boost |
| `cwu_controller.floor_set_temperature` | `temperature` (15-28) | Set floor target temp |

---

## Heat Pump Mode Detection

In `heat_pump` mode, the controller monitors but doesn't control. Key attributes for cards:

```javascript
// Check what's being heated
const compressorTarget = stateObj.attributes.compressor_target;
// Values: "cwu", "floor", "idle", "defrost"

// Check controller state (for heat_pump mode)
const state = stateObj.state;
// Values: "pump_idle", "pump_cwu", "pump_floor", "pump_both"

// Check electric heaters (might be running while compressor does something else)
const cwuElectricOn = hass.states['binary_sensor.cwu_controller_electric_heater_cwu'].state === 'on';
const floor1ElectricOn = hass.states['binary_sensor.cwu_controller_electric_heater_floor_1'].state === 'on';
const floor2ElectricOn = hass.states['binary_sensor.cwu_controller_electric_heater_floor_2'].state === 'on';
```

### Understanding pump_both State

When `state === 'pump_both'`:
- Pump is heating both CWU and floor simultaneously
- Usually: compressor on floor + electric heater on CWU
- Check `compressor_target` to see where compressor is
- Check binary sensors to see which electric heaters are ON

---

## Example: Reading Data for Card

```javascript
// Get main state entity
const stateObj = hass.states['sensor.cwu_controller_state'];

// Basic info
const controllerState = stateObj.state;  // "heating_cwu", "pump_floor", etc.
const attrs = stateObj.attributes;

// Temperatures
const cwuTemp = attrs.cwu_temp;           // e.g., 42.5
const cwuTarget = attrs.cwu_target_temp;  // e.g., 55.0
const salonTemp = attrs.salon_temp;       // e.g., 21.3

// Status
const isEnabled = attrs.enabled;
const manualOverride = attrs.manual_override;
const overrideUntil = attrs.manual_override_until;
const operatingMode = attrs.operating_mode;  // "broken_heater", "heat_pump", etc.

// Urgency (0-4)
const cwuUrgency = hass.states['sensor.cwu_controller_cwu_urgency'].state;
const floorUrgency = hass.states['sensor.cwu_controller_floor_urgency'].state;

// Heat Pump mode specifics
const compressorTarget = attrs.compressor_target;  // "cwu", "floor", "idle", "defrost"

// Energy today
const cwuEnergyToday = attrs.energy_today_cwu_kwh;
const floorEnergyToday = attrs.energy_today_floor_kwh;
const costToday = attrs.cost_today_estimate;

// BSB-LAN raw data
const bsb = attrs.bsb_lan || {};
const dhwStatus = bsb.dhw_status;     // "Charging", "Ready", etc.
const hpStatus = bsb.hp_status;       // "Compressor running", etc.
const hc1Status = bsb.hc1_status;     // "Heating", etc.
```

---

## Temperature Display Tips

For displaying temperatures with 1 decimal only when needed:

```javascript
function formatTemp(temp) {
  if (temp === null || temp === undefined || isNaN(temp)) {
    return '---';
  }
  const num = Number(temp);
  // Show 1 decimal only if not .0
  return num % 1 === 0 ? num.toFixed(0) : num.toFixed(1);
}

// Usage
formatTemp(42.0)  // "42"
formatTemp(42.5)  // "42.5"
formatTemp(null)  // "---"
```

---

## Handling Force Mode Buttons

```javascript
// Force CWU with duration (via service)
hass.callService('cwu_controller', 'force_cwu', { duration: 180 });

// Force floor with duration
hass.callService('cwu_controller', 'force_floor', { duration: 180 });

// Return to auto
hass.callService('cwu_controller', 'force_auto', {});

// Or use button entities directly
hass.callService('button', 'press', { entity_id: 'button.cwu_controller_force_auto' });
```

---

## State Icon Mapping

Suggested icons for states:

```javascript
const STATE_ICONS = {
  // Standard states
  'idle': 'mdi:sleep',
  'heating_cwu': 'mdi:water-boiler',
  'heating_floor': 'mdi:heating-coil',
  'pause': 'mdi:pause-circle',
  'emergency_cwu': 'mdi:water-boiler-alert',
  'emergency_floor': 'mdi:home-alert',
  'fake_heating_detected': 'mdi:alert',
  'fake_heating_restarting': 'mdi:restart',
  'safe_mode': 'mdi:shield-alert',

  // Heat Pump mode states
  'pump_idle': 'mdi:heat-pump-outline',
  'pump_cwu': 'mdi:water-boiler',
  'pump_floor': 'mdi:heating-coil',
  'pump_both': 'mdi:heat-pump',
};
```

---

## Version History

- **v6.1.0** - Added Heat Pump mode, compressor_target sensor, pump_* states
- **v6.0.0** - BSB-LAN integration, floor boost, electric heater tracking
