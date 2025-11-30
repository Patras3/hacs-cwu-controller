# CWU Controller - Tile Card Integration Guide

Dokumentacja dla integracji z kartami typu Tile/Tileboard poprzez WebSocket HA.

## Encje do wykorzystania

### Główne sensory

| Entity ID | Opis | Wartość | Atrybuty |
|-----------|------|---------|----------|
| `sensor.cwu_controller_state` | **Aktualny stan** | `idle`, `heating_cwu`, `heating_floor`, `pause`, `emergency_cwu`, `emergency_floor`, `fake_heating_detected`, `fake_heating_restarting` | Pełne dane (patrz niżej) |
| `sensor.cwu_controller_cwu_urgency` | Pilność grzania CWU | 0-4 | `level_name`, `cwu_temp` |
| `sensor.cwu_controller_floor_urgency` | Pilność grzania podłogi | 0-4 | `level_name`, `salon_temp`, `bedroom_temp` |
| `sensor.cwu_controller_cwu_heating_time` | Czas grzania w cyklu | 0-170 min | `max_minutes`, `remaining_minutes`, `percentage` |
| `sensor.cwu_controller_cwu_target_temp` | Temperatura docelowa CWU | °C | `cwu_min_temp`, `salon_target_temp` |
| `sensor.cwu_controller_average_power` | Średnia moc | W | - |

### Binary Sensors (on/off)

| Entity ID | Opis | Użycie |
|-----------|------|--------|
| `binary_sensor.cwu_controller_cwu_heating` | Czy grzeje CWU | Ikona aktywna gdy `on` |
| `binary_sensor.cwu_controller_floor_heating` | Czy grzeje podłogę | Ikona aktywna gdy `on` |
| `binary_sensor.cwu_controller_manual_override` | Tryb manualny | Pokazuje gdy wymuszone |
| `binary_sensor.cwu_controller_fake_heating_detected` | Problem z grzaniem | Alert gdy `on` |

### Przyciski (akcje)

| Entity ID | Opis | Serwis |
|-----------|------|--------|
| `button.cwu_controller_force_auto` | Powrót do AUTO | `button.press` |
| `button.cwu_controller_force_cwu_3h` | Wymuś CWU 3h | `button.press` |
| `button.cwu_controller_force_cwu_6h` | Wymuś CWU 6h | `button.press` |
| `button.cwu_controller_force_floor_3h` | Wymuś podłogę 3h | `button.press` |
| `button.cwu_controller_force_floor_6h` | Wymuś podłogę 6h | `button.press` |

### Switch

| Entity ID | Opis |
|-----------|------|
| `switch.cwu_controller_enabled` | Włącz/wyłącz kontroler |

---

## Atrybuty sensor.cwu_controller_state

Główny sensor zawiera wszystkie dane:

```yaml
# Temperatury
cwu_temp: 40.5              # Aktualna temp CWU
salon_temp: 22.0            # Salon
bedroom_temp: 19.4          # Sypialnia
kids_temp: 21.6             # Dziecięcy

# Moc
power: 82.98                # Aktualna moc [W]

# Stan urządzeń
water_heater_state: heat_pump   # off, heat_pump, performance
climate_state: off              # off, heat, auto
enabled: true                   # Kontroler włączony
manual_override: false          # Tryb manualny
fake_heating_detected: false    # Problem z grzaniem

# Sesja CWU (gdy grzeje)
cwu_session_start_time: "2025-11-30T21:58:36"  # ISO timestamp
cwu_session_start_temp: 41.75                   # Temp startowa
cwu_heating_minutes: 82.0                       # Czas grzania

# Historia (ostatnie 10)
state_history: [...]
action_history: [...]
```

---

## Sugestie dla Tile Card

### Mini karta (główna)

**Wyświetlaj:**
- Stan: `sensor.cwu_controller_state` → ikona zależna od stanu
- Czas pozostały: `sensor.cwu_controller_cwu_heating_time` → atrybut `remaining_minutes`
- Temperatura CWU: atrybut `cwu_temp` z state sensora

**Ikony stanów:**
| Stan | Ikona MDI | Kolor |
|------|-----------|-------|
| `idle` | `mdi:sleep` | szary |
| `heating_cwu` | `mdi:water-boiler` | cyan |
| `heating_floor` | `mdi:heating-coil` | pomarańcz |
| `pause` | `mdi:pause-circle` | szary |
| `emergency_*` | `mdi:alert` | czerwony |
| `fake_heating_*` | `mdi:alert-circle` | czerwony |

**Przykład logiki:**
```javascript
// Stan
const state = states['sensor.cwu_controller_state'].state;
const attrs = states['sensor.cwu_controller_state'].attributes;

// Czas pozostały (gdy grzeje CWU)
const heatingTime = states['sensor.cwu_controller_cwu_heating_time'];
const remaining = heatingTime.attributes.remaining_minutes;
const percentage = heatingTime.attributes.percentage;

// Temperatury
const cwuTemp = attrs.cwu_temp;
const sessionStart = attrs.cwu_session_start_temp;
const tempChange = cwuTemp - sessionStart;

// Tryb
const isManual = states['binary_sensor.cwu_controller_manual_override'].state === 'on';
const isCwuHeating = states['binary_sensor.cwu_controller_cwu_heating'].state === 'on';
```

### Popup / szczegóły

**Sekcja 1: Aktualny stan**
- Stan + czas trwania
- Temp CWU: `cwu_temp` → `target_temp` (45°C)
- Progress bar: `percentage` z heating_time

**Sekcja 2: Sesja (gdy grzeje CWU)**
- Start: `cwu_session_start_temp` °C
- Teraz: `cwu_temp` °C
- Zmiana: +X.X °C
- Czas: `cwu_heating_minutes` min
- Pozostało: `remaining_minutes` min

**Sekcja 3: Pilność**
- CWU: `sensor.cwu_controller_cwu_urgency` (0-4)
- Floor: `sensor.cwu_controller_floor_urgency` (0-4)

**Sekcja 4: Akcje**
- Przycisk AUTO → `button.cwu_controller_force_auto`
- Przycisk CWU → `button.cwu_controller_force_cwu_3h` lub `force_cwu_6h`
- Przycisk Floor → `button.cwu_controller_force_floor_3h` lub `force_floor_6h`

---

## Serwisy do wywołania

```yaml
# Wymuś CWU z dowolnym czasem (minuty)
service: cwu_controller.force_cwu
data:
  duration: 180  # 3 godziny

# Wymuś podłogę
service: cwu_controller.force_floor
data:
  duration: 360  # 6 godzin

# Powrót do AUTO
service: cwu_controller.force_auto

# Włącz/wyłącz kontroler
service: switch.turn_on / switch.turn_off
target:
  entity_id: switch.cwu_controller_enabled
```

---

## Przykład minimalnej karty

```
┌─────────────────────────┐
│ 🔥 Heating CWU    82min │  ← state + remaining
│ ████████░░░  48%        │  ← progress bar
│ 40.6°C → 45°C           │  ← cwu_temp → target
│ [AUTO] [CWU] [FLOOR]    │  ← przyciski akcji
└─────────────────────────┘
```

**Gdy idle:**
```
┌─────────────────────────┐
│ 😴 Idle                 │
│ CWU: 44.2°C  ✓          │
│ Floor: 22.0°C  ✓        │
│ [AUTO] [CWU] [FLOOR]    │
└─────────────────────────┘
```
