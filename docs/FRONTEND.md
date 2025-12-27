# CWU Controller - Frontend & Entity Documentation

Dokumentacja dla narzędzi generujących dashboardy/widgety Home Assistant.

---

## Część 1: CO POKAZUJE FRONTEND

### 1.1 Quick Stats (Widgety górne - mobile-first)

Trzy kompaktowe widgety widoczne na górze:

| Widget | Dane | Encja źródłowa |
|--------|------|----------------|
| **Power** | Aktualna moc w W | `sensor.ogrzewanie_total_system_power` (zewnętrzna) |
| **CWU Temp + State** | Temperatura CWU + aktualny stan kontrolera | `sensor.cwu_controller_bsb_cwu_temperature` + `sensor.cwu_controller_state` |
| **Mini Power Chart** | Wykres mocy z ostatniej godziny | Historia `sensor.ogrzewanie_total_system_power` |

### 1.2 BSB-LAN Heat Pump Card

Status pompy ciepła z BSB-LAN:

| Element | Opis | Encja |
|---------|------|-------|
| DHW Status | Status podgrzewania CWU (Charging/Charged/Off) | `sensor.cwu_controller_bsb_dhw_status` |
| HP Status | Status sprężarki (On/Off/Defrost) | `sensor.cwu_controller_bsb_heat_pump_status` |
| HC1 Status | Status obiegu grzewczego 1 | `sensor.cwu_controller_bsb_hc1_status` |
| CWU Mode | Tryb CWU w pompie (On/Off/Eco) | `sensor.cwu_controller_bsb_cwu_mode` |
| Floor Mode | Tryb podłogówki (Automatic/Protection) | `sensor.cwu_controller_bsb_floor_mode` |
| CWU Temp | Temperatura CWU z pompy | `sensor.cwu_controller_bsb_cwu_temperature` |
| Flow Temp | Temperatura zasilania | `sensor.cwu_controller_bsb_flow_temperature` |
| Return Temp | Temperatura powrotu | `sensor.cwu_controller_bsb_return_temperature` |
| Delta T | Różnica Flow-Return | `sensor.cwu_controller_bsb_delta_t` |
| Outside Temp | Temperatura zewnętrzna | `sensor.cwu_controller_bsb_outside_temperature` |
| Connection | Status połączenia BSB-LAN | `binary_sensor.cwu_controller_bsb_lan_available` |

### 1.3 Mode Control Bar

Pasek sterowania trybem:

| Element | Opis | Encja/Serwis |
|---------|------|--------------|
| Stan kontrolera | Ikona + nazwa stanu + czas trwania | `sensor.cwu_controller_state` |
| Przycisk AUTO | Powrót do automatyki | Serwis `cwu_controller.force_auto` |
| Przycisk CWU | Wymuszenie CWU na X godzin | Serwis `cwu_controller.force_cwu` |
| Przycisk FLOOR | Wymuszenie podłogówki na X godzin | Serwis `cwu_controller.force_floor` |
| Wskaźnik CWU | Świeci gdy CWU aktywne | `binary_sensor.cwu_controller_cwu_heating` |
| Wskaźnik Floor | Świeci gdy podłogówka aktywna | `binary_sensor.cwu_controller_floor_heating` |

### 1.4 Operating Mode & Tariff Card

| Element | Opis | Źródło danych |
|---------|------|---------------|
| Mode selector | Wybór trybu (broken_heater/winter/summer) | `select.cwu_controller_operating_mode` |
| Tariff status | Badge "Cheap/Expensive Tariff" | Atrybut `is_cheap_tariff` z state sensor |
| Current rate | Aktualna stawka PLN/kWh | Atrybut `current_tariff_rate` |
| Cheap rate | Stawka tania | Atrybut `tariff_cheap_rate` |
| Peak rate | Stawka droga | Atrybut `tariff_expensive_rate` |
| Heating window | Czy okno grzania CWU (winter mode) | Atrybut `is_cwu_heating_window` |
| Winter target | Cel temperatury winter mode | Atrybut `winter_cwu_target` |

### 1.5 Energy Consumption Card

Zużycie energii dziś/wczoraj:

| Metryka | Opis | Źródło (atrybuty state sensor) |
|---------|------|-------------------------------|
| CWU Today | Energia CWU dziś total | `energy_today_cwu_kwh` |
| CWU Today Cheap | Energia CWU tania taryfa | `energy_today_cwu_cheap_kwh` |
| CWU Today Peak | Energia CWU droga taryfa | `energy_today_cwu_expensive_kwh` |
| Floor Today | Energia podłogówki dziś | `energy_today_floor_kwh` |
| Floor Today Cheap | Podłogówka tania | `energy_today_floor_cheap_kwh` |
| Floor Today Peak | Podłogówka droga | `energy_today_floor_expensive_kwh` |
| Total Today | Suma dziś | `energy_today_total_kwh` |
| Cost Today | Szacowany koszt dziś | `cost_today_estimate` |
| Cost CWU | Koszt CWU | `cost_today_cwu_estimate` |
| Cost Floor | Koszt podłogówki | `cost_today_floor_estimate` |
| (analogicznie Yesterday) | | `energy_yesterday_*`, `cost_yesterday_*` |

### 1.6 CWU Session Tracking Card

Widoczna tylko podczas grzania CWU:

| Element | Opis | Źródło |
|---------|------|--------|
| Start Temp | Temperatura na początku sesji | `cwu_session_start_temp` |
| Current Temp | Aktualna temperatura | `sensor.cwu_controller_bsb_cwu_temperature` |
| Target Temp | Cel | Konfiguracja + atrybuty |
| Progress bar | Procent ukończenia | Obliczane |
| Duration | Czas trwania | `cwu_session_start_time` |
| Rate | Szybkość grzania °C/h | Obliczane |
| ETA | Szacowany czas do celu | Obliczane |
| Session Energy | Energia w sesji | Historia power |
| Cycle Timer | Licznik cyklu 170min | `cwu_heating_minutes` |
| Flow/Return/Delta | Temperatury pompy | BSB sensory |

### 1.7 Temperatures Card

| Temperatura | Ikona | Źródło |
|-------------|-------|--------|
| CWU Water | mdi:water-thermometer | `sensor.cwu_controller_bsb_cwu_temperature` |
| Living Room | mdi:sofa | `sensor.temperatura_govee_salon` (zewn.) |
| Bedroom | mdi:bed | `sensor.temperatura_govee_sypialnia` (zewn.) |
| Kids Room | mdi:teddy-bear | `sensor.temperatura_govee_dzieciecy` (zewn.) |

### 1.8 Urgency Gauges Card

Dwa wskaźniki pilności (0-4):

| Wskaźnik | Opis | Encja |
|----------|------|-------|
| CWU Urgency | Pilność grzania CWU | `sensor.cwu_controller_cwu_urgency` |
| Floor Urgency | Pilność grzania podłogi | `sensor.cwu_controller_floor_urgency` |

Poziomy: 0=None, 1=Low, 2=Medium, 3=High, 4=Critical

### 1.9 Power Consumption Card

| Element | Opis | Źródło |
|---------|------|--------|
| Current Power | Aktualna moc W | `sensor.ogrzewanie_total_system_power` |
| Power Bar | Wizualizacja 0-4500W | - |
| 10min Average | Średnia z 10 min | Historia power |
| Peak (10m) | Szczyt z 10 min | Historia power |
| Cycle Status | Status cyklu pompy | Obliczane |

### 1.10 Charts

| Wykres | Dane | Źródła |
|--------|------|--------|
| Temperature History | CWU, Salon, Sypialnia | BSB CWU + zewnętrzne sensory |
| Power History | Moc w czasie | `sensor.ogrzewanie_total_system_power` |
| Heat Pump Temps | CWU, Flow, Return, Delta | BSB sensory |
| Outside Temperature | Temp zewnętrzna | `sensor.cwu_controller_bsb_outside_temperature` |

### 1.11 System Status Card

| Element | Opis | Źródło |
|---------|------|--------|
| CWU Mode (BSB) | Tryb CWU w pompie | `sensor.cwu_controller_bsb_cwu_mode` |
| Floor Mode (BSB) | Tryb podłogówki w pompie | `sensor.cwu_controller_bsb_floor_mode` |
| Manual Override | Czy nadpisanie manualne | `binary_sensor.cwu_controller_manual_override` |
| Connection | Status połączenia | Wewnętrzny |

### 1.12 Test Actions Card

| Przycisk | Opis | Encja/Serwis |
|----------|------|--------------|
| CWU ON | Test włączenia CWU | `button.cwu_controller_test_cwu_on` |
| CWU OFF | Test wyłączenia CWU | `button.cwu_controller_test_cwu_off` |
| Floor ON | Test włączenia podłogi | `button.cwu_controller_test_floor_on` |
| Floor OFF | Test wyłączenia podłogi | `button.cwu_controller_test_floor_off` |

### 1.13 Action History Card

Lista ostatnich akcji z reasoning:
- Źródło: atrybut `action_history` z `sensor.cwu_controller_state`
- Format: `[timestamp, action, reasoning]`

### 1.14 State Timeline Card

Historia zmian stanów:
- Źródło: atrybut `state_history` z `sensor.cwu_controller_state`
- Format: `[timestamp, state, duration]`

### 1.15 Alerty

| Alert | Warunek | Encja |
|-------|---------|-------|
| Fake Heating Alert | Wykryto "fake heating" | `binary_sensor.cwu_controller_fake_heating_detected` |
| Manual Override Alert | Aktywne nadpisanie | `binary_sensor.cwu_controller_manual_override` + atrybut `manual_override_until` |

---

## Część 2: WSZYSTKIE DOSTĘPNE ENCJE

### 2.1 Sensory (sensor.*)

| Entity ID | Nazwa | Typ | Jednostka | Opis |
|-----------|-------|-----|-----------|------|
| `sensor.cwu_controller_state` | State | string | - | Główny stan kontrolera: idle, heating_cwu, heating_floor, pause, emergency_cwu, emergency_floor, fake_heating_detected, fake_heating_restarting, safe_mode |
| `sensor.cwu_controller_cwu_urgency` | CWU Urgency | int | 0-4 | Pilność grzania CWU |
| `sensor.cwu_controller_floor_urgency` | Floor Urgency | int | 0-4 | Pilność grzania podłogi |
| `sensor.cwu_controller_average_power` | Average Power | float | W | Średnia moc |
| `sensor.cwu_controller_cwu_heating_time` | CWU Heating Time | float | min | Czas grzania w cyklu (max 170 min) |
| `sensor.cwu_controller_cwu_target_temp` | CWU Target Temp | float | °C | Docelowa temperatura CWU |
| `sensor.cwu_controller_cwu_energy_today` | CWU Energy Today | float | kWh | Energia CWU dziś |
| `sensor.cwu_controller_floor_energy_today` | Floor Energy Today | float | kWh | Energia podłogówki dziś |
| `sensor.cwu_controller_total_energy_today` | Total Energy Today | float | kWh | Suma energii dziś |
| `sensor.cwu_controller_cwu_energy_cost_today` | CWU Energy Cost Today | float | PLN | Koszt CWU dziś |
| `sensor.cwu_controller_floor_energy_cost_today` | Floor Energy Cost Today | float | PLN | Koszt podłogówki dziś |
| `sensor.cwu_controller_tariff_rate` | Current Tariff Rate | float | PLN/kWh | Aktualna stawka |
| `sensor.cwu_controller_bsb_dhw_status` | BSB DHW Status | string | - | Status CWU z pompy (Charging/Charged/Off/Ready) |
| `sensor.cwu_controller_bsb_heat_pump_status` | BSB Heat Pump Status | string | - | Status sprężarki |
| `sensor.cwu_controller_bsb_hc1_status` | BSB HC1 Status | string | - | Status obiegu grzewczego 1 |
| `sensor.cwu_controller_bsb_cwu_mode` | BSB CWU Mode | string | - | Tryb CWU w pompie (On/Off/Eco) |
| `sensor.cwu_controller_bsb_floor_mode` | BSB Floor Mode | string | - | Tryb podłogówki (Automatic/Protection) |
| `sensor.cwu_controller_bsb_cwu_temperature` | BSB CWU Temperature | float | °C | Temperatura CWU z pompy |
| `sensor.cwu_controller_bsb_flow_temperature` | BSB Flow Temperature | float | °C | Temperatura zasilania |
| `sensor.cwu_controller_bsb_return_temperature` | BSB Return Temperature | float | °C | Temperatura powrotu |
| `sensor.cwu_controller_bsb_delta_t` | BSB Delta T | float | °C | Różnica flow-return |
| `sensor.cwu_controller_bsb_outside_temperature` | BSB Outside Temperature | float | °C | Temperatura zewnętrzna |
| `sensor.cwu_controller_control_source` | Control Source | string | - | Źródło sterowania (bsb_lan/ha_cloud) |

### 2.2 Binary Sensory (binary_sensor.*)

| Entity ID | Nazwa | Device Class | Opis |
|-----------|-------|--------------|------|
| `binary_sensor.cwu_controller_cwu_heating` | CWU Heating | heat | Czy aktywnie grzeje CWU |
| `binary_sensor.cwu_controller_floor_heating` | Floor Heating | heat | Czy aktywnie grzeje podłogę |
| `binary_sensor.cwu_controller_fake_heating_detected` | Fake Heating Detected | problem | Wykryto fake heating |
| `binary_sensor.cwu_controller_manual_override` | Manual Override | - | Aktywne ręczne nadpisanie |
| `binary_sensor.cwu_controller_bsb_lan_available` | BSB-LAN Available | connectivity | Czy BSB-LAN dostępny |

### 2.3 Przełączniki (switch.*)

| Entity ID | Nazwa | Opis |
|-----------|-------|------|
| `switch.cwu_controller_enabled` | CWU Controller Enabled | Główny włącznik kontrolera |

### 2.4 Wybory (select.*)

| Entity ID | Nazwa | Opcje | Opis |
|-----------|-------|-------|------|
| `select.cwu_controller_operating_mode` | Operating Mode | broken_heater, winter, summer | Tryb pracy |

### 2.5 Liczby (number.*)

| Entity ID | Nazwa | Zakres | Opis |
|-----------|-------|--------|------|
| `number.cwu_controller_cwu_target_temp` | CWU Target Temperature | 40-55°C | Docelowa temp CWU |
| `number.cwu_controller_cwu_min_temp` | CWU Minimum Temperature | 35-50°C | Minimalna temp CWU |
| `number.cwu_controller_cwu_critical_temp` | CWU Critical Temperature | 30-40°C | Krytyczna temp CWU |
| `number.cwu_controller_cwu_hysteresis` | CWU Hysteresis | 3-15°C | Histereza startu grzania |
| `number.cwu_controller_salon_target_temp` | Living Room Target | 18-25°C | Cel temp salonu |
| `number.cwu_controller_salon_min_temp` | Living Room Minimum | 17-23°C | Min temp salonu |
| `number.cwu_controller_bedroom_min_temp` | Bedroom Minimum | 16-22°C | Min temp sypialni |

### 2.6 Przyciski (button.*)

| Entity ID | Nazwa | Opis |
|-----------|-------|------|
| `button.cwu_controller_test_cwu_on` | Test CWU ON | Testowe włączenie CWU |
| `button.cwu_controller_test_cwu_off` | Test CWU OFF | Testowe wyłączenie CWU |
| `button.cwu_controller_test_floor_on` | Test Floor ON | Testowe włączenie podłogi |
| `button.cwu_controller_test_floor_off` | Test Floor OFF | Testowe wyłączenie podłogi |
| `button.cwu_controller_force_cwu_3h` | Force CWU 3h | Wymuś CWU na 3h |
| `button.cwu_controller_force_cwu_6h` | Force CWU 6h | Wymuś CWU na 6h |
| `button.cwu_controller_force_floor_3h` | Force Floor 3h | Wymuś podłogę na 3h |
| `button.cwu_controller_force_floor_6h` | Force Floor 6h | Wymuś podłogę na 6h |
| `button.cwu_controller_force_auto` | Force Auto | Anuluj override, wróć do auto |

---

## Część 3: ATRYBUTY GŁÓWNEGO SENSORA STATE

`sensor.cwu_controller_state` zawiera bogaty zestaw atrybutów:

### 3.1 Temperatury
```yaml
cwu_temp: 45.2          # °C - temperatura CWU
salon_temp: 21.5        # °C - temperatura salonu
bedroom_temp: 20.1      # °C - temperatura sypialni
kids_temp: 20.3         # °C - temperatura pokoju dzieci
```

### 3.2 Status systemu
```yaml
power: 1520             # W - aktualna moc
enabled: true           # czy kontroler włączony
manual_override: false  # czy ręczne nadpisanie
fake_heating_detected: false
operating_mode: "broken_heater"  # broken_heater/winter/summer
water_heater_state: "On"    # stan CWU w pompie
climate_state: "Automatic"  # stan podłogi w pompie
```

### 3.3 Sesja CWU
```yaml
cwu_session_start_time: "2024-01-15T10:30:00"
cwu_session_start_temp: 38.5
cwu_heating_minutes: 45  # minut w cyklu (max 170)
```

### 3.4 Taryfa G12w
```yaml
is_cheap_tariff: true
current_tariff_rate: 0.72
is_cwu_heating_window: false  # dla winter mode
tariff_cheap_rate: 0.72
tariff_expensive_rate: 1.16
```

### 3.5 Tryb winter
```yaml
winter_cwu_target: 50.0
winter_cwu_emergency_threshold: 35.0
```

### 3.6 Energia (kWh)
```yaml
# Dziś
energy_today_cwu_kwh: 2.45
energy_today_cwu_cheap_kwh: 1.80
energy_today_cwu_expensive_kwh: 0.65
energy_today_floor_kwh: 5.12
energy_today_floor_cheap_kwh: 4.20
energy_today_floor_expensive_kwh: 0.92
energy_today_total_kwh: 7.57

# Wczoraj (analogicznie)
energy_yesterday_cwu_kwh: 3.10
...
```

### 3.7 Koszty (PLN)
```yaml
cost_today_estimate: 6.45
cost_today_cwu_estimate: 2.10
cost_today_floor_estimate: 4.35
cost_yesterday_estimate: 7.20
...
```

### 3.8 Anti-oscillation (tryb broken_heater)
```yaml
hold_time_remaining: 8        # minuty do możliwości przełączenia
can_switch_to_cwu: true
can_switch_to_floor: false
switch_blocked_reason: "Floor min hold time"
hp_ready: true
hp_ready_reason: "OK"
max_temp_achieved: 48.5
max_temp_detected: false
electric_fallback_count: 1
is_night_floor_window: false  # okno 03:00-06:00
```

### 3.9 Manual Override
```yaml
manual_override_until: "2024-01-15T16:30:00"  # ISO timestamp
```

### 3.10 Historia
```yaml
state_history:
  - ["2024-01-15T10:30:00", "heating_cwu", "45 min"]
  - ["2024-01-15T09:45:00", "idle", "15 min"]

action_history:
  - ["2024-01-15T10:30:00", "CWU ON", "Idle → CWU, temp 38.5°C < target 45.0°C"]
  - ["2024-01-15T10:25:00", "Floor OFF", "Switching to CWU priority"]
```

### 3.11 Reasoning
```yaml
last_reasoning: "CWU 47.5°C (target 50.0°C, -2.5°C), progress +1.2°C/60min"
```

---

## Część 4: STANY KONTROLERA

| Stan | Opis | Ikona MDI |
|------|------|-----------|
| `idle` | Bezczynny, monitoruje | mdi:sleep |
| `heating_cwu` | Aktywne grzanie CWU | mdi:water-boiler |
| `heating_floor` | Aktywne grzanie podłogi | mdi:heating-coil |
| `pause` | Obowiązkowa pauza 10 min po 170 min | mdi:pause-circle |
| `emergency_cwu` | Krytycznie niska temp CWU | mdi:water-boiler-alert |
| `emergency_floor` | Krytycznie niska temp pokoju | mdi:home-alert |
| `fake_heating_detected` | Wykryto fake heating, czeka na HP | mdi:alert-circle |
| `fake_heating_restarting` | Restart CWU po fake heating | mdi:refresh-circle |
| `safe_mode` | BSB-LAN niedostępny | mdi:shield-check |

---

## Część 5: ZEWNĘTRZNE ENCJE (hardcoded)

Frontend używa tych zewnętrznych encji (nie z integracji):

| Entity ID | Opis | Użycie |
|-----------|------|--------|
| `sensor.ogrzewanie_total_system_power` | Moc całego systemu | Power widget, wykresy |
| `sensor.temperatura_govee_salon` | Temp salonu (Govee) | Temperatures card |
| `sensor.temperatura_govee_sypialnia` | Temp sypialni | Temperatures card |
| `sensor.temperatura_govee_dzieciecy` | Temp pokoju dzieci | Temperatures card |
| `sensor.temperatura_wejscia_pompy_ciepla` | Temp wejścia pompy | Tech chart |
| `sensor.temperatura_wyjscia_pompy_ciepla` | Temp wyjścia pompy | Tech chart |
| `sensor.temperatura_wejscia_c_w_u` | Temp wejścia CWU | Tech chart |
| `sensor.temperatura_wejscia_ogrzewania_podlogowego` | Temp wejścia podłogi | Tech chart |

---

## Część 6: SERWISY

Dostępne serwisy do wywoływania:

| Serwis | Parametry | Opis |
|--------|-----------|------|
| `cwu_controller.force_cwu` | `duration_minutes: int` | Wymuś CWU na X minut |
| `cwu_controller.force_floor` | `duration_minutes: int` | Wymuś podłogę na X minut |
| `cwu_controller.force_auto` | - | Anuluj override |
| `cwu_controller.heat_to_temp` | `target_temp: float` | Grzej CWU do temperatury |

---

## Część 7: PRZYKŁADY DASHBOARDÓW

### 7.1 Minimalny widget statusu

```yaml
type: entities
entities:
  - entity: sensor.cwu_controller_state
    name: Status
  - entity: sensor.cwu_controller_bsb_cwu_temperature
    name: Temperatura CWU
  - entity: sensor.cwu_controller_cwu_urgency
    name: Pilność CWU
  - entity: switch.cwu_controller_enabled
    name: Kontroler
```

### 7.2 Karty przycisków sterowania

```yaml
type: horizontal-stack
cards:
  - type: button
    entity: button.cwu_controller_force_cwu_3h
    name: CWU 3h
    icon: mdi:water-boiler
  - type: button
    entity: button.cwu_controller_force_floor_3h
    name: Floor 3h
    icon: mdi:heating-coil
  - type: button
    entity: button.cwu_controller_force_auto
    name: Auto
    icon: mdi:autorenew
```

### 7.3 Gauge temperatury

```yaml
type: gauge
entity: sensor.cwu_controller_bsb_cwu_temperature
name: CWU
min: 30
max: 55
severity:
  green: 45
  yellow: 38
  red: 35
```

### 7.4 Energy tracking

```yaml
type: entities
title: Energia
entities:
  - entity: sensor.cwu_controller_cwu_energy_today
    name: CWU dziś
  - entity: sensor.cwu_controller_floor_energy_today
    name: Podłoga dziś
  - entity: sensor.cwu_controller_total_energy_today
    name: Razem dziś
  - entity: sensor.cwu_controller_cwu_energy_cost_today
    name: Koszt CWU
  - entity: sensor.cwu_controller_floor_energy_cost_today
    name: Koszt podłogi
```

---

## Część 8: IKONY MDI

Używane ikony Material Design Icons:

| Ikona | Użycie |
|-------|--------|
| `mdi:water-boiler` | CWU |
| `mdi:heating-coil` | Podłogówka |
| `mdi:heat-pump` | Pompa ciepła |
| `mdi:thermometer` | Temperatura |
| `mdi:flash` / `mdi:lightning-bolt` | Moc/Energia |
| `mdi:gauge` | Pilność |
| `mdi:clock` / `mdi:timer` | Czas |
| `mdi:currency-usd` | Koszty |
| `mdi:leaf` | Tania taryfa |
| `mdi:fire` | Droga taryfa |
| `mdi:alert` | Alert |
| `mdi:autorenew` | Auto mode |
| `mdi:hand-back-right` | Manual override |
| `mdi:power` | Włącznik |
