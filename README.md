# CWU Controller for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![GitHub Release](https://img.shields.io/github/release/your-username/hacs-cwu-controller.svg)](https://github.com/your-username/hacs-cwu-controller/releases)

A smart Home Assistant integration that manages heat pump water heating (CWU) and floor heating when your CWU electric heater is broken. The controller ensures you always have hot water AND a warm house by intelligently switching between heating modes.

## Problem Solved

When your CWU electric heater breaks, the heat pump doesn't know it's broken - it thinks the heater is warming the water, but nothing happens. This integration:

- **Detects fake heating** - When power drops to <10W while water heater is "on", the pump is waiting for the broken heater
- **Forces thermodynamic heating** - Turns off floor heating so the heat pump actually heats water via thermodynamics
- **Manages 3-hour CWU limit** - Automatically restarts heating cycles to avoid the built-in 3-hour timeout
- **Prioritizes based on urgency** - Balances between hot water needs and keeping the house warm
- **Sends notifications** - Keeps you informed about state changes and emergencies

## Features

- Automatic switching between CWU and floor heating
- Broken heater detection (power <10W = fake heating)
- 3-hour heating cycle management with automatic restart
- Time-based urgency (prepares hot water before evening bath time)
- Emergency modes when temperatures are critical
- Beautiful Lovelace dashboard with charts and controls
- Test buttons to verify all actions work correctly
- Manual override for 1-hour forced heating
- Complete state and action history tracking

## Installation

### HACS (Recommended)

1. Open HACS in Home Assistant
2. Click on "Integrations"
3. Click the three dots in the top right corner
4. Select "Custom repositories"
5. Add the URL: `https://github.com/your-username/hacs-cwu-controller`
6. Select category: "Integration"
7. Click "Add"
8. Search for "CWU Controller" and install

### Manual Installation

1. Copy the `custom_components/cwu_controller` folder to your Home Assistant `custom_components` directory
2. Restart Home Assistant
3. Go to Settings > Devices & Services > Add Integration
4. Search for "CWU Controller"

## Configuration

The integration uses a config flow with two steps:

### Step 1: Entity Selection

| Entity | Description | Default |
|--------|-------------|---------|
| CWU Temperature | Water tank temperature sensor | `sensor.temperatura_c_w_u` |
| Salon Temperature | Main room temperature | `sensor.temperatura_govee_salon` |
| Bedroom Temperature | Bedroom sensor (optional) | `sensor.temperatura_govee_sypialnia` |
| Kids Room Temperature | Children's room (optional) | `sensor.temperatura_govee_dzieciecy` |
| Power Sensor | Heat pump power consumption | `sensor.ogrzewanie_total_system_power` |
| Water Heater | Water heater entity | `water_heater.pompa_ciepla_io_*` |
| Climate | Floor heating entity | `climate.pompa_ciepla_dom` |
| Notify Service | For notifications | `notify.mobile_app_*` |

### Step 2: Temperature Thresholds

| Setting | Description | Default |
|---------|-------------|---------|
| CWU Target | Desired water temperature | 45°C |
| CWU Minimum | Acceptable minimum | 40°C |
| CWU Critical | Emergency threshold | 35°C |
| Salon Target | Desired room temperature | 22°C |
| Salon Minimum | Acceptable minimum | 21°C |
| Bedroom Minimum | Bedroom threshold | 19°C |

## Entities Created

### Sensors
- **CWU Controller State** - Current controller state with history
- **CWU Urgency** - Water heating urgency level (0-4)
- **Floor Urgency** - Floor heating urgency level (0-4)
- **Average Power** - Average power consumption
- **CWU Heating Time** - Minutes in current heating cycle

### Binary Sensors
- **CWU Heating** - Is CWU being heated
- **Floor Heating** - Is floor heating active
- **Fake Heating Detected** - Broken heater situation detected
- **Manual Override** - Is manual override active

### Switch
- **Controller Enabled** - Enable/disable the controller

### Buttons (Test Actions)
- **Test CWU ON** - Test turning on water heating
- **Test CWU OFF** - Test turning off water heating
- **Test Floor ON** - Test turning on floor heating
- **Test Floor OFF** - Test turning off floor heating
- **Force CWU 1h** - Override: heat water for 1 hour
- **Force Floor 1h** - Override: heat floor for 1 hour

## Services

```yaml
# Force CWU heating for specified duration
service: cwu_controller.force_cwu
data:
  duration: 60  # minutes

# Force floor heating for specified duration
service: cwu_controller.force_floor
data:
  duration: 60  # minutes

# Enable controller
service: cwu_controller.enable

# Disable controller
service: cwu_controller.disable
```

## Algorithm

### Urgency Levels

| Level | CWU Conditions | Floor Conditions |
|-------|----------------|------------------|
| **0 - None** | ≥45°C | Salon ≥22°C |
| **1 - Low** | <45°C (morning) | Salon <22.5°C |
| **2 - Medium** | <40°C or <45°C after 3PM | Salon <22°C |
| **3 - High** | <38°C after 3PM | Salon <21°C |
| **4 - Critical** | <35°C after 6PM | Salon <19°C or bedroom <18°C |

### Decision Logic

1. **Emergency** - If any critical, handle immediately
2. **High CWU + Low Floor** - Heat CWU
3. **High Floor + Low CWU** - Heat Floor
4. **After 3PM** - Prepare for evening, prefer CWU
5. **Default** - Heat floor (keep house warm)

### Fake Heating Detection

The system detects when the pump thinks it's heating but actually isn't:
- Water heater mode is `heat_pump` or `performance`
- Power consumption is <10W for >5 minutes
- This triggers a mode restart cycle

### 3-Hour Cycle Management

Heat pumps typically have a 3-hour limit on CWU heating. The controller:
1. Tracks heating start time
2. After 2h50m, pauses everything for 10 minutes
3. Restarts the heating cycle
4. Sends a notification about the pause

## Lovelace Dashboard

A beautiful dashboard configuration is provided in `lovelace-dashboard.yaml`. Copy it to your Lovelace dashboard for:

- Status cards with current temperatures and states
- Timeline showing heating mode changes
- Charts for temperature and power history
- Test buttons for verifying actions
- Action history log

## Troubleshooting

### "Fake heating detected" keeps appearing

This usually means:
1. Your heater is indeed broken (expected)
2. The heat pump might need a restart
3. Check if `heat_pump` mode actually triggers thermodynamic heating

### Water never reaches target temperature

- Ensure floor heating is OFF when CWU is heating
- Check that the heat pump can reach 45°C thermodynamically
- Consider lowering target temperature temporarily

### Floor heating doesn't turn on

- Verify the climate entity is correct
- Check if climate supports `turn_on` service
- Try using the test buttons to debug

## Contributing

Contributions are welcome! Please open an issue or PR on GitHub.

## License

MIT License - see LICENSE file for details.
