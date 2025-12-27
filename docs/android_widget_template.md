# CWU Controller - Android Widget Template

Template do użycia w Home Assistant Android Widget (Markdown lub Text).

## Pełny Widget Template

```jinja2
{# --- CWU Controller Widget --- #}
{% set state = states('sensor.cwu_controller_state') %}
{% set state_attr = state_attr('sensor.cwu_controller_state', 'hold_time_remaining') | default(0) %}
{% set hp_ready = state_attr('sensor.cwu_controller_state', 'hp_ready') | default(true) %}
{% set hp_reason = state_attr('sensor.cwu_controller_state', 'hp_ready_reason') | default('OK') %}

{# --- Główny status --- #}
{% if state == 'heating_cwu' %}
🔥 <span style="color: #00BCD4; font-size: 24px;">Grzanie CWU</span>
{% elif state == 'heating_floor' %}
🏠 <span style="color: #4CAF50; font-size: 24px;">Podłogówka</span>
{% elif state == 'emergency_cwu' %}
🚨 <span style="color: #F44336; font-size: 24px;">Awaryjne CWU!</span>
{% elif state == 'emergency_floor' %}
🚨 <span style="color: #F44336; font-size: 24px;">Awaryjna Podłoga!</span>
{% elif state == 'pause' %}
⏸️ <span style="color: #FF9800; font-size: 24px;">Pauza</span>
{% elif state == 'fake_heating_detected' %}
⚠️ <span style="color: #FF5722; font-size: 24px;">Fake Heating!</span>
{% elif state == 'safe_mode' %}
🛡️ <span style="color: #9C27B0; font-size: 24px;">Safe Mode</span>
{% else %}
💤 <span style="color: #607D8B; font-size: 24px;">Idle</span>
{% endif %}

{# --- Hold timer --- #}
{% if state_attr > 0 %}
<br>⏱️ Hold: {{ state_attr }}min
{% endif %}

<br><br>
{# --- Temperatury --- #}
{% set cwu_temp = states('sensor.cwu_controller_bsb_cwu_temperature') | float(0) %}
{% set cwu_target = states('sensor.cwu_controller_cwu_target_temp') | float(45) %}
{% set outside = states('sensor.cwu_controller_bsb_outside_temperature') | float(0) %}

🌡️ <b>CWU:</b>
{% if cwu_temp < 38 %}
<span style="color: #F44336;">{{ cwu_temp | round(1) }}°C</span>
{% elif cwu_temp < 42 %}
<span style="color: #FF9800;">{{ cwu_temp | round(1) }}°C</span>
{% else %}
<span style="color: #4CAF50;">{{ cwu_temp | round(1) }}°C</span>
{% endif %}
 / {{ cwu_target | round(0) }}°C

<br>🌍 Zewn: {{ outside | round(1) }}°C

<br><br>
{# --- Tryby BSB --- #}
{% set cwu_mode = states('sensor.cwu_controller_bsb_cwu_mode') %}
{% set floor_mode = states('sensor.cwu_controller_bsb_floor_mode') %}

<b>BSB Tryby:</b><br>
{% if cwu_mode | lower in ['on', 'eco', '1'] %}
🔵 CWU: <span style="color: #4CAF50;">ON</span> ({{ cwu_mode }})
{% else %}
⚫ CWU: <span style="color: #9E9E9E;">OFF</span>
{% endif %}
<br>
{% if floor_mode | lower in ['automatic', 'comfort', '1'] %}
🟢 Floor: <span style="color: #4CAF50;">ON</span> ({{ floor_mode }})
{% else %}
⚫ Floor: <span style="color: #9E9E9E;">OFF</span>
{% endif %}

<br><br>
{# --- Statusy pompy --- #}
{% set dhw = states('sensor.cwu_controller_bsb_dhw_status') %}
{% set hp = states('sensor.cwu_controller_bsb_heat_pump_status') %}

<b>Pompa:</b><br>
DHW: {{ dhw }}<br>
HP: {% if 'compressor' in hp | lower %}
<span style="color: #4CAF50;">{{ hp }}</span>
{% elif 'off time' in hp | lower %}
<span style="color: #FF9800;">{{ hp }}</span>
{% else %}
{{ hp }}
{% endif %}

<br>
{% if hp_ready %}
✅ <span style="color: #4CAF50;">HP Ready</span>
{% else %}
⏳ <span style="color: #FF9800;">HP: {{ hp_reason }}</span>
{% endif %}

<br><br>
{# --- Przepływy --- #}
{% set flow = states('sensor.cwu_controller_bsb_flow_temperature') | float(0) %}
{% set ret = states('sensor.cwu_controller_bsb_return_temperature') | float(0) %}
{% set delta = states('sensor.cwu_controller_bsb_delta_t') | float(0) %}

<b>Temp przepływu:</b><br>
Flow: {{ flow | round(1) }}°C | Ret: {{ ret | round(1) }}°C<br>
ΔT: {% if delta >= 3 and delta <= 5 %}
<span style="color: #4CAF50;">{{ delta | round(1) }}°C</span> ✓
{% elif delta > 0.5 and delta < 3 %}
<span style="color: #FF9800;">{{ delta | round(1) }}°C</span> (słaby)
{% elif delta <= 0.5 %}
<span style="color: #F44336;">{{ delta | round(1) }}°C</span> (brak)
{% else %}
<span style="color: #2196F3;">{{ delta | round(1) }}°C</span> (wysoki)
{% endif %}

<br><br>
{# --- Moc --- #}
{% set power = states('sensor.cwu_controller_average_power') | float(0) %}

⚡ Moc: {% if power > 300 %}
<span style="color: #4CAF50;">{{ power | round(0) }}W</span>
{% elif power > 80 %}
<span style="color: #FF9800;">{{ power | round(0) }}W</span>
{% else %}
<span style="color: #9E9E9E;">{{ power | round(0) }}W</span>
{% endif %}

{# --- Energia dziś --- #}
{% set energy_cwu = states('sensor.cwu_controller_cwu_energy_today') | float(0) %}
{% set energy_floor = states('sensor.cwu_controller_floor_energy_today') | float(0) %}
{% set cost_cwu = states('sensor.cwu_controller_cwu_energy_cost_today') | float(0) %}
{% set cost_floor = states('sensor.cwu_controller_floor_energy_cost_today') | float(0) %}

<br>📊 Dziś: CWU {{ energy_cwu | round(2) }}kWh ({{ cost_cwu | round(2) }}zł) | Floor {{ energy_floor | round(2) }}kWh ({{ cost_floor | round(2) }}zł)

<br><br>
{# --- Taryfa --- #}
{% set is_cheap = state_attr('sensor.cwu_controller_tariff_rate', 'is_cheap_tariff') %}

💰 {% if is_cheap %}
<span style="color: #4CAF50;">Tania taryfa</span> 💚
{% else %}
<span style="color: #F44336;">Droga taryfa</span> ⛔
{% endif %}

<br><br>
<em style="color: #666;">{{ now().strftime('%H:%M:%S') }}</em>
```

---

## Kompaktowy Widget (mniejszy)

```jinja2
{% set state = states('sensor.cwu_controller_state') %}
{% set cwu_temp = states('sensor.cwu_controller_bsb_cwu_temperature') | float(0) %}
{% set outside = states('sensor.cwu_controller_bsb_outside_temperature') | float(0) %}
{% set power = states('sensor.cwu_controller_average_power') | float(0) %}
{% set is_cheap = state_attr('sensor.cwu_controller_tariff_rate', 'is_cheap_tariff') %}
{% set hold = state_attr('sensor.cwu_controller_state', 'hold_time_remaining') | default(0) %}

{# Status #}
{% if state == 'heating_cwu' %}🔥CWU{% elif state == 'heating_floor' %}🏠FLOOR{% elif 'emergency' in state %}🚨EMG{% elif state == 'pause' %}⏸️PAUZA{% elif state == 'fake_heating_detected' %}⚠️FAKE{% else %}💤IDLE{% endif %}
{% if hold > 0 %} ({{ hold }}m){% endif %}

<br>
🌡️ {{ cwu_temp | round(1) }}°C | 🌍 {{ outside | round(1) }}°C
<br>
⚡ {{ power | round(0) }}W | {% if is_cheap %}💚Tania{% else %}⛔Droga{% endif %}
<br>
<em>{{ now().strftime('%H:%M') }}</em>
```

---

## Widget ze statusem BSB (średni rozmiar)

```jinja2
{% set state = states('sensor.cwu_controller_state') %}
{% set cwu = states('sensor.cwu_controller_bsb_cwu_temperature') | float(0) %}
{% set cwu_mode = states('sensor.cwu_controller_bsb_cwu_mode') %}
{% set floor_mode = states('sensor.cwu_controller_bsb_floor_mode') %}
{% set dhw = states('sensor.cwu_controller_bsb_dhw_status') %}
{% set hp = states('sensor.cwu_controller_bsb_heat_pump_status') %}
{% set power = states('sensor.cwu_controller_average_power') | float(0) %}
{% set hold = state_attr('sensor.cwu_controller_state', 'hold_time_remaining') | default(0) %}
{% set hp_ready = state_attr('sensor.cwu_controller_state', 'hp_ready') | default(true) %}

{# Nagłówek #}
<b>CWU Controller</b>
<br><br>

{# Stan + Hold #}
{% if state == 'heating_cwu' %}
🔥 <span style="color:#00BCD4;font-size:20px;">Grzanie CWU</span>
{% elif state == 'heating_floor' %}
🏠 <span style="color:#4CAF50;font-size:20px;">Podłogówka</span>
{% elif state == 'emergency_cwu' or state == 'emergency_floor' %}
🚨 <span style="color:#F44336;font-size:20px;">EMERGENCY!</span>
{% elif state == 'pause' %}
⏸️ <span style="color:#FF9800;font-size:20px;">Pauza</span>
{% elif state == 'fake_heating_detected' %}
⚠️ <span style="color:#FF5722;font-size:20px;">Fake Heat</span>
{% else %}
💤 <span style="color:#607D8B;font-size:20px;">Idle</span>
{% endif %}
{% if hold > 0 %} <span style="color:#FF9800;">({{ hold }}m)</span>{% endif %}

<br><br>

{# Temperatury #}
🌡️ CWU: {% if cwu < 38 %}<span style="color:#F44336;">{% elif cwu < 42 %}<span style="color:#FF9800;">{% else %}<span style="color:#4CAF50;">{% endif %}<b>{{ cwu | round(1) }}°C</b></span>
<br>
⚡ {{ power | round(0) }}W

<br><br>

{# BSB Status #}
📡 <b>BSB:</b><br>
CWU: {% if cwu_mode | lower in ['on','eco','1'] %}🟢{% else %}⚫{% endif %} {{ cwu_mode }}
 | Floor: {% if floor_mode | lower in ['automatic','comfort','1'] %}🟢{% else %}⚫{% endif %} {{ floor_mode }}
<br>
DHW: {{ dhw }}<br>
HP: {{ hp }}
<br>
{% if hp_ready %}✅ Ready{% else %}⏳ Waiting{% endif %}

<br><br>
<em style="color:#888;">{{ now().strftime('%H:%M:%S') }}</em>
```

---

## Uwagi dotyczące Android Widgeta

1. **Nie wszystkie style HTML działają** - widget Androida ogranicza obsługę CSS
2. **Emoji są preferowane** do kolorowania (zawsze działają)
3. **Przetestuj na swoim telefonie** - różne wersje mają różną obsługę

### Encje używane w template:

| Encja | Opis |
|-------|------|
| `sensor.cwu_controller_state` | Stan kontrolera (idle, heating_cwu, heating_floor, etc.) |
| `sensor.cwu_controller_bsb_cwu_temperature` | Temperatura CWU z BSB-LAN |
| `sensor.cwu_controller_bsb_outside_temperature` | Temperatura zewnętrzna |
| `sensor.cwu_controller_bsb_cwu_mode` | Tryb CWU (Off/On/Eco) |
| `sensor.cwu_controller_bsb_floor_mode` | Tryb podłogi (Protection/Automatic) |
| `sensor.cwu_controller_bsb_dhw_status` | Status DHW (Charging, Charged, Ready) |
| `sensor.cwu_controller_bsb_heat_pump_status` | Status pompy ciepła |
| `sensor.cwu_controller_bsb_flow_temperature` | Temperatura zasilania |
| `sensor.cwu_controller_bsb_return_temperature` | Temperatura powrotu |
| `sensor.cwu_controller_bsb_delta_t` | Delta T (flow - return) |
| `sensor.cwu_controller_average_power` | Średnia moc |
| `sensor.cwu_controller_cwu_energy_today` | Energia CWU dziś |
| `sensor.cwu_controller_floor_energy_today` | Energia podłogi dziś |
| `sensor.cwu_controller_tariff_rate` | Aktualna taryfa |

### Atrybuty ze state sensor:

```yaml
hold_time_remaining: 0        # Minuty pozostałe do przełączenia
hp_ready: true               # Czy pompa gotowa
hp_ready_reason: "OK"        # Powód blokady pompy
is_night_floor_window: false # Czy okno nocne dla podłogi
```

---

## Przykładowa konfiguracja widgeta

W aplikacji Home Assistant Android:
1. Dodaj widget typu "Template"
2. Wklej jeden z powyższych template'ów
3. Ustaw interwał odświeżania (np. 60s)
4. Widget będzie automatycznie aktualizowany
