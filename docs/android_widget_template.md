# CWU Controller - Android Widget Templates

Template'y do użycia w Home Assistant Android Widget.

## Pliki z kodem widgetów

Każdy widget w osobnym pliku - łatwo skopiować:

| Plik | Opis |
|------|------|
| [widget_full.jinja2](widgets/widget_full.jinja2) | Pełny widget ze wszystkimi informacjami |
| [widget_medium.jinja2](widgets/widget_medium.jinja2) | Średni - status + BSB |
| [widget_compact.jinja2](widgets/widget_compact.jinja2) | Kompaktowy - 4 linijki |

---

## Podgląd widgetów

### Full (widget_full.jinja2)
```
🔥 Grzanie CWU
⏱️ Hold: 3min

🌡️ CWU: 48.2°C / 50°C
🌍 Zewn: 4.4°C

BSB Tryby:
🔵 CWU: ON (On)
🟢 Floor: ON (Automatic)

Pompa:
DHW: Charging
HP: Compressor 1 on
✅ HP Ready

Temp przepływu:
Flow: 24.3°C | Ret: 24.8°C
ΔT: -0.5°C (brak)

⚡ Moc: 83W
📊 Dziś: CWU 2.45kWh (1.77zł) | Floor 1.23kWh (0.89zł)

💰 Tania taryfa 💚

04:03:25
```

### Medium (widget_medium.jinja2)
```
CWU Controller

🔥 Grzanie CWU (3m)

🌡️ CWU: 48.2°C
⚡ 83W

📡 BSB:
CWU: 🟢 On | Floor: 🟢 Automatic
DHW: Charging
HP: Compressor 1 on
✅ Ready

04:03:25
```

### Compact (widget_compact.jinja2)
```
🔥CWU (3m)
🌡️ 48.2°C | 🌍 4.4°C
⚡ 83W | 💚Tania
04:03
```

---

## Encje używane w template'ach

| Encja | Opis |
|-------|------|
| `sensor.cwu_controller_state` | Stan kontrolera |
| `sensor.cwu_controller_bsb_cwu_temperature` | Temperatura CWU |
| `sensor.cwu_controller_bsb_outside_temperature` | Temperatura zewnętrzna |
| `sensor.cwu_controller_bsb_cwu_mode` | Tryb CWU (Off/On/Eco) |
| `sensor.cwu_controller_bsb_floor_mode` | Tryb podłogi |
| `sensor.cwu_controller_bsb_dhw_status` | Status DHW |
| `sensor.cwu_controller_bsb_heat_pump_status` | Status pompy |
| `sensor.cwu_controller_bsb_flow_temperature` | Temp zasilania |
| `sensor.cwu_controller_bsb_return_temperature` | Temp powrotu |
| `sensor.cwu_controller_bsb_delta_t` | Delta T |
| `sensor.cwu_controller_average_power` | Moc |
| `sensor.cwu_controller_cwu_energy_today` | Energia CWU dziś |
| `sensor.cwu_controller_floor_energy_today` | Energia podłogi dziś |
| `sensor.cwu_controller_tariff_rate` | Taryfa |

## Atrybuty state sensor

```yaml
hold_time_remaining: 0        # Minuty do przełączenia
hp_ready: true               # Czy pompa gotowa
hp_ready_reason: "OK"        # Powód blokady
```

---

## Jak użyć

1. Otwórz plik `.jinja2` na GitHub (Raw)
2. Skopiuj całą zawartość
3. W aplikacji HA Android dodaj widget "Template"
4. Wklej kod
5. Gotowe!
