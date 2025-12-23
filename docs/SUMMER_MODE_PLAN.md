# Summer Mode - Plan Implementacji

## Spis treści
1. [Cel trybu Summer](#cel-trybu-summer)
2. [Założenia i wymagania](#założenia-i-wymagania)
3. [Sensory i encje](#sensory-i-encje)
4. [Algorytm decyzyjny](#algorytm-decyzyjny)
5. [Szczegóły implementacji](#szczegóły-implementacji)
6. [Stany kontrolera](#stany-kontrolera)
7. [Scenariusze działania](#scenariusze-działania)
8. [Plan implementacji krok po kroku](#plan-implementacji-krok-po-kroku)
9. [Rozszerzenia opcjonalne](#rozszerzenia-opcjonalne)

---

## Cel trybu Summer

Tryb Summer optymalizuje grzanie CWU **pod kątem maksymalnego wykorzystania energii z fotowoltaiki** z fallbackiem na tanią taryfę G12w w przypadku niewystarczającej produkcji.

### Kluczowe różnice względem innych trybów

| Aspekt | Broken Heater | Winter | **Summer** |
|--------|--------------|--------|------------|
| Źródło ciepła | Pompa ciepła | Pompa ciepła | **Tylko grzałka** (tryb emergency) |
| Fake heating detection | ✅ Tak | ❌ Nie | ❌ Nie |
| Ogrzewanie podłogowe | ✅ Tak | ✅ Tak | **❌ Wyłączone** |
| Źródło energii | Sieć (taryfa) | Sieć (tania taryfa) | **PV → tania taryfa** |
| Bilansowanie | Nie | Nie | **Tak (godzinowe)** |

---

## Założenia i wymagania

### Założenia podstawowe

1. **Pompa ciepła w trybie emergency** - wyłączony kompresor, grzeje tylko grzałka elektryczna
2. **Grzałka działa poprawnie** - nie sprawdzamy fake heating
3. **Dom jest ciepły latem** - ogrzewanie podłogowe permanentnie wyłączone
4. **Rozliczenie za zbilansowane godziny** - liczy się saldo na koniec każdej godziny
5. **Grzałka CWU ~3.3 kW** - konfigurowalna wartość, domyślnie 3300W

### Wymagania sensorów

| Sensor | Rola | Wymagany? |
|--------|------|-----------|
| `sensor.energia_bilans_netto` | Zbilansowana energia aktualnej godziny | **Wymagany** |
| `sensor.inverter_moc_czynna` | Aktualna produkcja PV w W | Opcjonalny (pomocniczy) |
| `sensor.glowny_total_system_power` | Aktualne zużycie/eksport w W | Opcjonalny (pomocniczy) |
| Sensor temperatury CWU | Kontrola temperatury wody | **Wymagany** |
| Sensor deszczu/pogody | Prognoza warunków | Opcjonalny |

### Wymagania konfiguracyjne

| Parametr | Domyślna | Opis |
|----------|----------|------|
| `summer_heater_power` | 3300 W | Moc grzałki CWU |
| `summer_balance_threshold` | 50% mocy grzałki | Próg bilansu do włączenia (1.65 kWh dla 3.3kW) |
| `summer_pv_min_production` | 500 W | Minimalna produkcja PV do rozważenia grzania |
| `summer_cwu_target_temp` | 50°C | Docelowa temperatura CWU |
| `summer_cwu_min_temp` | 40°C | Minimalna akceptowalna temperatura |
| `summer_cwu_critical_temp` | 35°C | Temperatura krytyczna (emergency) |

---

## Sensory i encje

### Sensor: `sensor.energia_bilans_netto`

**Opis działania:**
- Pokazuje zbilansowaną energię w **aktualnej godzinie** (kWh)
- Resetuje się do 0 o każdej pełnej godzinie (XX:00)
- Wartość dodatnia = nadwyżka (energia wysłana do sieci)
- Wartość ujemna = pobór netto z sieci

**Przykład:**
```
Godzina 13:30, wartość = +2.0 kWh
→ W ciągu ostatnich 30 minut wyprodukowano 2 kWh więcej niż zużyto
→ Jeśli teraz włączymy grzałkę 3.3kW na 30 min i nie będzie produkcji,
   zużyjemy 1.65 kWh → saldo = +0.35 kWh (nadal na plus!)
```

### Sensor: `sensor.inverter_moc_czynna`

**Opis działania:**
- Aktualna chwilowa produkcja fotowoltaiki w W
- Maksymalnie ~6000W (zależnie od instalacji)
- 0W = noc/brak słońca

**Zastosowanie:**
- Pomocniczy do przewidywania czy produkcja się utrzyma
- Uśrednianie do oceny stabilności warunków

### Sensor: `sensor.glowny_total_system_power`

**Opis działania:**
- Chwilowy przepływ mocy przez licznik (W)
- Wartość dodatnia = pobór z sieci
- Wartość ujemna = eksport do sieci (nadwyżka)

**Zastosowanie:**
- Real-time monitoring podczas grzania
- Detekcja nagłego spadku produkcji PV

---

## Algorytm decyzyjny

### Filozofia: Sloty czasowe z priorytetami

**Problem z prostym podejściem "tania taryfa = grzej":**
W weekendy i święta cały dzień jest tania taryfa. Prosty algorytm zacząłby grzać o północy,
ale to nieoptymalne - lepiej poczekać na PV które da DARMOWĄ energię (a nie tylko tanią).

**Rozwiązanie: System slotów czasowych**

| Slot | Godziny | Priorytet | Opis |
|------|---------|-----------|------|
| **PV dzienny** | 08:00 - 18:00 | 🥇 Najwyższy | Czekamy na darmową energię z PV |
| **Taryfowy wieczorny** | 18:00 - 24:00 | 🥈 Średni | Fallback jeśli PV nie wystarczyło |
| **Taryfowy nocny** | 00:00 - 08:00 | 🥉 Niski | Tylko gdy woda zimna (< 40°C) |

### Główny algorytm z uwzględnieniem slotów

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    SUMMER MODE - ALGORYTM ZE SLOTAMI                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  1. EMERGENCY CHECK (zawsze pierwszy)                                        │
│     CWU < CRITICAL_TEMP (35°C)?                                             │
│     └── TAK → GRZEJ NATYCHMIAST (niezależnie od slotu)                      │
│                                                                              │
│  2. TARGET CHECK                                                             │
│     CWU >= TARGET_TEMP (50°C)?                                              │
│     └── TAK → IDLE (woda nagrzana, nic nie rób)                             │
│                                                                              │
│  3. OKREŚL AKTUALNY SLOT                                                     │
│     │                                                                        │
│     ├── 08:00 - 18:00 → SLOT_PV                                             │
│     │   └── Priorytet: PV > taryfa (ale taryfa jako backup)                 │
│     │                                                                        │
│     ├── 18:00 - 24:00 → SLOT_EVENING                                        │
│     │   └── PV (jeśli jeszcze jest) > taryfa                                │
│     │                                                                        │
│     └── 00:00 - 08:00 → SLOT_NIGHT                                          │
│         └── Tylko taryfa, ale ostrożnie (próg 40°C, nie target)             │
│                                                                              │
│  4. LOGIKA SLOT_PV (08:00 - 18:00)                                          │
│     │                                                                        │
│     │  Czy jest produkcja PV wystarczająca?                                 │
│     │  └── TAK → GRZEJ Z PV (algorytm bilansowania)                         │
│     │                                                                        │
│     │  Czy minął DEADLINE (16:00) i CWU < EVENING_THRESHOLD (42°C)?         │
│     │  └── TAK → GRZEJ Z TARYFY (PV nie dało rady, musimy przed wieczorem)  │
│     │                                                                        │
│     │  W pozostałych przypadkach:                                            │
│     │  └── IDLE (czekamy na lepsze warunki PV)                              │
│     │                                                                        │
│  5. LOGIKA SLOT_EVENING (18:00 - 24:00)                                     │
│     │                                                                        │
│     │  Czy jest produkcja PV wystarczająca?                                 │
│     │  └── TAK → GRZEJ Z PV (wykorzystaj resztkę)                           │
│     │                                                                        │
│     │  Czy jest tania taryfa (22:00-24:00 lub weekend)?                     │
│     │  └── TAK i CWU < target → GRZEJ Z TARYFY                              │
│     │                                                                        │
│     │  W pozostałych przypadkach:                                            │
│     │  └── IDLE (czekamy na 22:00 lub następny dzień)                       │
│     │                                                                        │
│  6. LOGIKA SLOT_NIGHT (00:00 - 08:00)                                       │
│     │                                                                        │
│     │  Czy CWU < NIGHT_THRESHOLD (40°C)?                                    │
│     │  └── TAK i tania taryfa → GRZEJ DO NIGHT_TARGET (42°C)                │
│     │      (nie do 50°C! tylko bufor żeby nie spaść do critical)            │
│     │                                                                        │
│     │  Czy CWU >= 40°C?                                                     │
│     │  └── TAK → IDLE (woda wystarczająco ciepła, czekaj na PV)             │
│     │                                                                        │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Parametry slotów (konfigurowalne)

| Parametr | Domyślna | Opis |
|----------|----------|------|
| `summer_pv_slot_start` | 08:00 | Początek slotu PV (kiedy foto może zacząć) |
| `summer_pv_slot_end` | 18:00 | Koniec slotu PV (zachód słońca latem) |
| `summer_pv_deadline` | 16:00 | Deadline - po tej godzinie fallback na taryfę jeśli potrzeba |
| `summer_evening_threshold` | 42°C | Poniżej tej temp włączamy fallback przed wieczorem |
| `summer_night_threshold` | 40°C | Poniżej tej temp grzejemy w nocy |
| `summer_night_target` | 42°C | Do jakiej temp grzać w nocy (tylko bufor) |

### Algorytm bilansowania godzinowego (dla slotu PV)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    ALGORYTM BILANSOWANIA (w slocie PV)                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Aktualna minuta >= 30?                                                     │
│  │                                                                           │
│  ├── TAK (XX:30-XX:59) → STRATEGIA "DRUGA POŁOWA"                           │
│  │   │                                                                       │
│  │   │  bilans_netto >= (moc_grzalki × 0.5h × próg)                         │
│  │   │  czyli >= 1.65 kWh dla grzałki 3.3kW i progu 50%                     │
│  │   │  │                                                                    │
│  │   │  ├── TAK → GRZEJ (mamy zapas na pozostałe ~30 min)                   │
│  │   │  │                                                                    │
│  │   │  └── NIE → Czy produkcja PV > moc grzałki?                           │
│  │   │            │                                                          │
│  │   │            ├── TAK → GRZEJ (produkcja pokrywa zużycie)               │
│  │   │            │                                                          │
│  │   │            └── NIE → IDLE (za mało, czekaj)                          │
│  │                                                                           │
│  └── NIE (XX:00-XX:29) → STRATEGIA "PIERWSZA POŁOWA"                        │
│      │                                                                       │
│      │  Czy produkcja PV > moc grzałki?                                     │
│      │  (inverter_moc_czynna > 3300W)                                       │
│      │  │                                                                    │
│      │  ├── TAK → GRZEJ (nadwyżka idzie na grzanie)                         │
│      │  │                                                                    │
│      │  └── NIE → Czy bilans >= 1.0 kWh?                                    │
│      │            │                                                          │
│      │            ├── TAK → GRZEJ (mamy zapas)                               │
│      │            │                                                          │
│      │            └── NIE → IDLE (budujemy bilans)                          │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Szczegółowy algorytm bilansowania

#### Pierwsza połowa godziny (XX:00-XX:29)

W pierwszej połowie godziny jesteśmy **ostrożni** - grzejemy tylko gdy mamy realną nadwyżkę:

```python
def should_heat_first_half():
    pv_production = sensor.inverter_moc_czynna  # W
    heater_power = config.summer_heater_power    # domyślnie 3300 W

    # Grzej tylko gdy produkcja PV pokrywa całą moc grzałki
    if pv_production >= heater_power:
        return True

    # Alternatywnie: mamy już solidny bilans dodatni
    # (np. wcześniej było więcej produkcji)
    if sensor.energia_bilans_netto >= 1.0:  # >= 1 kWh zapasu
        return True

    return False
```

**Uzasadnienie:** W pierwszej połowie nie wiemy jeszcze jak potoczy się godzina. Budujemy zapas.

#### Druga połowa godziny (XX:30-XX:59)

W drugiej połowie możemy być **bardziej agresywni** - wiemy ile mamy zapasu:

```python
def should_heat_second_half():
    bilans = sensor.energia_bilans_netto  # kWh
    heater_power = config.summer_heater_power  # W
    remaining_minutes = 60 - datetime.now().minute  # ~30 min

    # Ile energii zużyjemy w pozostałym czasie
    energy_needed = (heater_power / 1000) * (remaining_minutes / 60)  # kWh
    # Dla 3.3kW i 30 min: 3.3 * 0.5 = 1.65 kWh

    # Próg bezpieczeństwa (50% = jeśli mamy połowę, to ryzykujemy)
    threshold_ratio = config.summer_balance_threshold  # 0.5
    threshold = energy_needed * threshold_ratio  # 0.825 kWh

    # Czy mamy wystarczający zapas?
    if bilans >= threshold:
        return True

    # Produkcja pokrywa zużycie?
    if sensor.inverter_moc_czynna >= heater_power:
        return True

    return False
```

**Uzasadnienie:** Mając 1.65 kWh zapasu o 13:30, nawet jeśli chmury zakryją słońce, nadal zbilansujemy godzinę na plus lub blisko zera.

### Obsługa pochmurnych dni

Gdy produkcja PV jest niska/zerowa, fallback na **tanie taryfy**:

```python
def should_heat_fallback():
    # Brak produkcji PV (< 500W)
    if sensor.inverter_moc_czynna < 500:
        # Sprawdź tanie okna taryfowe
        if is_cheap_tariff():  # 13:00-15:00, 22:00-06:00, weekendy
            return True
    return False
```

---

## Szczegóły implementacji

### Nowe stałe w `const.py`

```python
# Summer mode specific settings
SUMMER_HEATER_POWER: Final = 3300  # W - domyślna moc grzałki CWU
SUMMER_BALANCE_THRESHOLD: Final = 0.5  # 50% - próg bilansu do włączenia
SUMMER_PV_MIN_PRODUCTION: Final = 500  # W - minimalna produkcja do uznania za "dzień słoneczny"
SUMMER_CWU_TARGET_TEMP: Final = 50.0  # °C - docelowa temperatura
SUMMER_CWU_NO_PROGRESS_TIMEOUT: Final = 60  # minut - timeout bez postępu (krótszy niż winter)
SUMMER_CWU_MIN_TEMP_INCREASE: Final = 2.0  # °C - oczekiwany wzrost temp

# Sloty czasowe (godziny)
SUMMER_PV_SLOT_START: Final = 8   # 08:00 - początek slotu PV
SUMMER_PV_SLOT_END: Final = 18    # 18:00 - koniec slotu PV
SUMMER_PV_DEADLINE: Final = 16    # 16:00 - po tej godzinie fallback na taryfę

# Progi temperaturowe dla slotów
SUMMER_EVENING_THRESHOLD: Final = 42.0  # °C - poniżej tej temp fallback po deadline
SUMMER_NIGHT_THRESHOLD: Final = 40.0    # °C - poniżej tej temp grzejemy w nocy
SUMMER_NIGHT_TARGET: Final = 42.0       # °C - do jakiej temp grzać w nocy (tylko bufor)

# Sensory PV (konfigurowalne)
CONF_PV_BALANCE_SENSOR: Final = "pv_balance_sensor"
CONF_PV_PRODUCTION_SENSOR: Final = "pv_production_sensor"
CONF_GRID_POWER_SENSOR: Final = "grid_power_sensor"
CONF_SUMMER_HEATER_POWER: Final = "summer_heater_power"
CONF_SUMMER_BALANCE_THRESHOLD: Final = "summer_balance_threshold"

# Sloty czasowe (konfigurowalne)
CONF_SUMMER_PV_SLOT_START: Final = "summer_pv_slot_start"
CONF_SUMMER_PV_SLOT_END: Final = "summer_pv_slot_end"
CONF_SUMMER_PV_DEADLINE: Final = "summer_pv_deadline"
CONF_SUMMER_NIGHT_THRESHOLD: Final = "summer_night_threshold"
CONF_SUMMER_NIGHT_TARGET: Final = "summer_night_target"

# Domyślne nazwy sensorów
DEFAULT_PV_BALANCE_SENSOR: Final = "sensor.energia_bilans_netto"
DEFAULT_PV_PRODUCTION_SENSOR: Final = "sensor.inverter_moc_czynna"
DEFAULT_GRID_POWER_SENSOR: Final = "sensor.glowny_total_system_power"
```

### Nowe konfiguracje w `config_flow.py`

Dodać do flow konfiguracyjnego:

```python
SUMMER_SCHEMA = vol.Schema({
    vol.Required(CONF_PV_BALANCE_SENSOR, default=DEFAULT_PV_BALANCE_SENSOR): selector.EntitySelector(
        selector.EntitySelectorConfig(domain="sensor")
    ),
    vol.Optional(CONF_PV_PRODUCTION_SENSOR, default=DEFAULT_PV_PRODUCTION_SENSOR): selector.EntitySelector(
        selector.EntitySelectorConfig(domain="sensor")
    ),
    vol.Optional(CONF_GRID_POWER_SENSOR, default=DEFAULT_GRID_POWER_SENSOR): selector.EntitySelector(
        selector.EntitySelectorConfig(domain="sensor")
    ),
    vol.Required(CONF_SUMMER_HEATER_POWER, default=SUMMER_HEATER_POWER): vol.All(
        vol.Coerce(int), vol.Range(min=1000, max=6000)
    ),
    vol.Required(CONF_SUMMER_BALANCE_THRESHOLD, default=0.5): vol.All(
        vol.Coerce(float), vol.Range(min=0.1, max=1.0)
    ),
    # Opcjonalne: sensor pogody/deszczu
    vol.Optional(CONF_WEATHER_SENSOR): selector.EntitySelector(
        selector.EntitySelectorConfig(domain=["weather", "sensor"])
    ),
})
```

### Nowe metody w `coordinator.py`

#### Pomocnicze metody odczytu sensorów PV

```python
def _get_pv_balance(self) -> float | None:
    """Get current hourly energy balance in kWh."""
    sensor = self.config.get(CONF_PV_BALANCE_SENSOR, DEFAULT_PV_BALANCE_SENSOR)
    return self._get_sensor_value(sensor)

def _get_pv_production(self) -> float | None:
    """Get current PV production in W."""
    sensor = self.config.get(CONF_PV_PRODUCTION_SENSOR, DEFAULT_PV_PRODUCTION_SENSOR)
    return self._get_sensor_value(sensor)

def _get_grid_power(self) -> float | None:
    """Get current grid power flow in W (positive = import, negative = export)."""
    sensor = self.config.get(CONF_GRID_POWER_SENSOR, DEFAULT_GRID_POWER_SENSOR)
    return self._get_sensor_value(sensor)

def _get_heater_power(self) -> int:
    """Get configured heater power in W."""
    return self.config.get(CONF_SUMMER_HEATER_POWER, SUMMER_HEATER_POWER)

def _get_balance_threshold(self) -> float:
    """Get balance threshold ratio (0.0-1.0)."""
    return self.config.get(CONF_SUMMER_BALANCE_THRESHOLD, SUMMER_BALANCE_THRESHOLD)
```

#### Metody decyzyjne dla Summer mode

```python
def _should_heat_from_pv(self, cwu_temp: float | None) -> tuple[bool, str]:
    """Determine if we should heat CWU from PV.

    Returns:
        (should_heat, reason) tuple
    """
    if cwu_temp is None:
        return False, "CWU temp unavailable"

    target = self.config.get("cwu_target_temp", SUMMER_CWU_TARGET_TEMP)
    if cwu_temp >= target:
        return False, f"CWU at target ({cwu_temp}°C >= {target}°C)"

    now = datetime.now()
    minute = now.minute

    pv_production = self._get_pv_production()
    pv_balance = self._get_pv_balance()
    heater_power = self._get_heater_power()
    threshold_ratio = self._get_balance_threshold()

    # Brak danych PV - nie możemy decydować
    if pv_balance is None:
        return False, "PV balance sensor unavailable"

    # Brak produkcji PV (< 500W) - nie grzejemy z PV
    if pv_production is None or pv_production < SUMMER_PV_MIN_PRODUCTION:
        return False, f"No PV production ({pv_production or 0}W < {SUMMER_PV_MIN_PRODUCTION}W)"

    # STRATEGIA: Pierwsza połowa godziny (XX:00 - XX:29)
    if minute < 30:
        # Grzej tylko gdy produkcja pokrywa całą moc grzałki
        if pv_production >= heater_power:
            return True, f"First half: PV covers heater ({pv_production}W >= {heater_power}W)"

        # Lub mamy solidny bilans (>=1 kWh zapasu)
        if pv_balance >= 1.0:
            return True, f"First half: Good balance ({pv_balance:.2f} kWh >= 1.0 kWh)"

        return False, f"First half: Building balance ({pv_balance:.2f} kWh, PV {pv_production}W)"

    # STRATEGIA: Druga połowa godziny (XX:30 - XX:59)
    else:
        remaining_minutes = 60 - minute
        energy_needed = (heater_power / 1000) * (remaining_minutes / 60)  # kWh
        threshold = energy_needed * threshold_ratio

        # Mamy wystarczający zapas?
        if pv_balance >= threshold:
            return True, f"Second half: Balance OK ({pv_balance:.2f} kWh >= {threshold:.2f} kWh threshold)"

        # Produkcja pokrywa zużycie?
        if pv_production >= heater_power:
            return True, f"Second half: PV covers heater ({pv_production}W >= {heater_power}W)"

        return False, f"Second half: Insufficient ({pv_balance:.2f} kWh < {threshold:.2f} kWh, PV {pv_production}W)"

def _get_summer_slot(self, hour: int) -> str:
    """Determine current time slot for summer mode."""
    pv_start = self.config.get(CONF_SUMMER_PV_SLOT_START, SUMMER_PV_SLOT_START)
    pv_end = self.config.get(CONF_SUMMER_PV_SLOT_END, SUMMER_PV_SLOT_END)

    if pv_start <= hour < pv_end:
        return "SLOT_PV"
    elif pv_end <= hour < 24:
        return "SLOT_EVENING"
    else:  # 0 <= hour < pv_start
        return "SLOT_NIGHT"

def _should_heat_from_tariff(self, cwu_temp: float | None) -> tuple[bool, str]:
    """Determine if we should heat CWU from cheap tariff (fallback).

    Implements slot-based logic:
    - SLOT_NIGHT (00:00-08:00): Only heat if CWU < night_threshold (40°C)
      Target is night_target (42°C), not full target - just safety buffer
    - SLOT_PV (08:00-18:00): Only heat after deadline (16:00) if CWU < evening_threshold
    - SLOT_EVENING (18:00-24:00): Heat if cheap tariff and CWU < target
    """
    if cwu_temp is None:
        return False, "CWU temp unavailable"

    now = datetime.now()
    hour = now.hour
    slot = self._get_summer_slot(hour)
    target = self.config.get("cwu_target_temp", SUMMER_CWU_TARGET_TEMP)

    # Already at target - no heating needed
    if cwu_temp >= target:
        return False, f"CWU at target ({cwu_temp}°C >= {target}°C)"

    # Get slot-specific thresholds
    night_threshold = self.config.get(CONF_SUMMER_NIGHT_THRESHOLD, SUMMER_NIGHT_THRESHOLD)
    night_target = self.config.get(CONF_SUMMER_NIGHT_TARGET, SUMMER_NIGHT_TARGET)
    evening_threshold = self.config.get("summer_evening_threshold", SUMMER_EVENING_THRESHOLD)
    deadline = self.config.get(CONF_SUMMER_PV_DEADLINE, SUMMER_PV_DEADLINE)

    # SLOT_NIGHT: Very conservative - only heat if really cold
    if slot == "SLOT_NIGHT":
        if cwu_temp < night_threshold:
            if self.is_cheap_tariff():
                # Return special target (night_target, not full target)
                return True, f"Night slot: CWU cold ({cwu_temp}°C < {night_threshold}°C), heating to {night_target}°C"
            return False, f"Night slot: CWU cold but expensive tariff"
        return False, f"Night slot: CWU OK ({cwu_temp}°C >= {night_threshold}°C), waiting for PV"

    # SLOT_PV: Only fallback after deadline
    if slot == "SLOT_PV":
        if hour >= deadline and cwu_temp < evening_threshold:
            if self.is_cheap_tariff():
                return True, f"PV slot deadline passed: CWU needs heating ({cwu_temp}°C < {evening_threshold}°C)"
            # Even in expensive tariff, if really needed
            if cwu_temp < night_threshold:
                return True, f"PV slot deadline: CWU too cold ({cwu_temp}°C), emergency tariff heating"
        return False, f"PV slot: Waiting for PV (hour {hour}, deadline {deadline})"

    # SLOT_EVENING: Standard fallback to cheap tariff
    if slot == "SLOT_EVENING":
        if self.is_cheap_tariff():
            return True, f"Evening slot: Cheap tariff, CWU needs heating ({cwu_temp}°C < {target}°C)"
        return False, f"Evening slot: Expensive tariff, waiting for 22:00"

    return False, f"Unknown slot: {slot}"

def _check_summer_cwu_no_progress(self, current_temp: float | None) -> bool:
    """Check if summer mode CWU heating has made no progress after timeout.

    Similar to winter mode but with shorter timeout (60 min vs 180 min)
    and higher expected increase (2°C vs 1°C) since heater should heat faster.
    """
    if self._cwu_heating_start is None:
        return False
    if self._cwu_session_start_temp is None:
        return False
    if current_temp is None:
        return False

    elapsed = (datetime.now() - self._cwu_heating_start).total_seconds() / 60
    if elapsed < SUMMER_CWU_NO_PROGRESS_TIMEOUT:
        return False

    # Check if temperature has increased sufficiently
    temp_increase = current_temp - self._cwu_session_start_temp
    return temp_increase < SUMMER_CWU_MIN_TEMP_INCREASE
```

#### Główna logika Summer mode

```python
async def _run_summer_mode_logic(
    self,
    cwu_urgency: int,
    cwu_temp: float | None,
) -> None:
    """Run control logic for summer mode.

    Summer mode features:
    - Heat pump in emergency mode (heater only, no compressor)
    - Floor heating permanently OFF
    - Heat CWU from PV surplus with hourly balancing
    - Fallback to cheap tariff when no PV
    - No fake heating detection (heater works)
    - Warning if no progress (similar to winter)
    """
    now = datetime.now()
    target = self.config.get("cwu_target_temp", SUMMER_CWU_TARGET_TEMP)
    critical = self.config.get("cwu_critical_temp", DEFAULT_CWU_CRITICAL_TEMP)

    # 1. EMERGENCY: Critical temperature - heat immediately
    if cwu_temp is not None and cwu_temp < critical:
        if self._current_state != STATE_EMERGENCY_CWU:
            await self._summer_start_heating()
            self._change_state(STATE_EMERGENCY_CWU)
            await self._async_send_notification(
                "CWU Emergency (Summer Mode)",
                f"CWU critically low: {cwu_temp}°C! Starting emergency heating."
            )
            self._log_action(f"Summer mode: Emergency CWU ({cwu_temp}°C < {critical}°C)")
        return

    # 2. Already heating - check progress and target
    if self._current_state in (STATE_HEATING_CWU, STATE_EMERGENCY_CWU):
        # Check for no-progress timeout (warning)
        if self._check_summer_cwu_no_progress(cwu_temp):
            start_temp = self._cwu_session_start_temp
            elapsed = (now - self._cwu_heating_start).total_seconds() / 60 if self._cwu_heating_start else 0

            self._log_action(
                f"Summer mode: No progress after {elapsed:.0f} min "
                f"(start: {start_temp}°C, current: {cwu_temp}°C)"
            )
            await self._async_send_notification(
                "CWU Heating Problem (Summer Mode)",
                f"CWU temperature hasn't increased after {elapsed:.0f} minutes.\n"
                f"Started at: {start_temp}°C\n"
                f"Current: {cwu_temp}°C\n"
                f"Expected increase: {SUMMER_CWU_MIN_TEMP_INCREASE}°C\n\n"
                f"Heater may have an issue. Stopping heating."
            )
            await self._summer_stop_heating()
            self._change_state(STATE_IDLE)
            self._cwu_heating_start = None
            self._cwu_session_start_temp = None
            return

        # Target reached - stop heating
        if cwu_temp is not None and cwu_temp >= target:
            self._log_action(f"Summer mode: CWU target reached ({cwu_temp}°C >= {target}°C)")
            await self._summer_stop_heating()
            self._change_state(STATE_IDLE)
            self._cwu_heating_start = None
            self._cwu_session_start_temp = None
            return

        # Still heating - check if conditions still allow it
        should_heat_pv, pv_reason = self._should_heat_from_pv(cwu_temp)
        should_heat_tariff, tariff_reason = self._should_heat_from_tariff(cwu_temp)

        if not should_heat_pv and not should_heat_tariff:
            # Conditions changed - stop heating
            self._log_action(f"Summer mode: Conditions changed, stopping. PV: {pv_reason}, Tariff: {tariff_reason}")
            await self._summer_stop_heating()
            self._change_state(STATE_IDLE)
            # Don't reset session - we might resume soon
        return

    # 3. Idle - check if we should start heating
    if cwu_temp is not None and cwu_temp >= target:
        # Already at target - nothing to do
        return

    # Try PV first
    should_heat_pv, pv_reason = self._should_heat_from_pv(cwu_temp)
    if should_heat_pv:
        self._log_action(f"Summer mode: Starting PV heating. {pv_reason}")
        await self._summer_start_heating()
        self._change_state(STATE_HEATING_CWU)
        return

    # Fallback to tariff
    should_heat_tariff, tariff_reason = self._should_heat_from_tariff(cwu_temp)
    if should_heat_tariff:
        self._log_action(f"Summer mode: Starting tariff heating. {tariff_reason}")
        await self._summer_start_heating()
        self._change_state(STATE_HEATING_CWU)
        return

    # No conditions met - stay idle
    # Log only occasionally to avoid spam
    if self._current_state != STATE_IDLE:
        self._log_action(f"Summer mode: Waiting. PV: {pv_reason}, Tariff: {tariff_reason}")
        self._change_state(STATE_IDLE)
```

#### Metody sterowania urządzeniami dla Summer mode

```python
async def _summer_start_heating(self) -> None:
    """Start CWU heating in summer mode.

    - Sets water heater to performance/emergency mode (heater only)
    - Ensures floor heating is OFF
    """
    if self._transition_in_progress:
        self._log_action("Summer start heating skipped - transition in progress")
        return

    self._transition_in_progress = True
    try:
        self._log_action("Summer mode: Starting CWU heating...")

        # Ensure floor is OFF (should already be, but safety)
        await self._async_set_climate(False)
        await asyncio.sleep(2)  # Short delay

        # Set water heater to performance mode (uses heater, not compressor)
        await self._async_set_water_heater_mode(WH_MODE_PERFORMANCE)
        self._log_action("Summer mode: CWU heater enabled (performance mode)")

        # Track session start
        cwu_temp = self._last_known_cwu_temp
        if cwu_temp is None:
            cwu_temp = self._get_sensor_value(self.config.get("cwu_temp_sensor"))
        self._cwu_session_start_temp = cwu_temp
        self._cwu_heating_start = datetime.now()

    finally:
        self._transition_in_progress = False

async def _summer_stop_heating(self) -> None:
    """Stop CWU heating in summer mode."""
    if self._transition_in_progress:
        self._log_action("Summer stop heating skipped - transition in progress")
        return

    self._transition_in_progress = True
    try:
        self._log_action("Summer mode: Stopping CWU heating...")
        await self._async_set_water_heater_mode(WH_MODE_OFF)
        # Floor stays OFF in summer mode
        self._log_action("Summer mode: CWU heater disabled")
    finally:
        self._transition_in_progress = False

async def _enter_summer_safe_mode(self) -> None:
    """Enter safe mode in summer - only CWU, no floor.

    Unlike winter safe mode, we only enable CWU heating.
    Floor heating stays OFF because house doesn't need it in summer.
    """
    if self._transition_in_progress:
        self._log_action("Summer safe mode skipped - transition in progress")
        return

    self._transition_in_progress = True
    try:
        self._log_action("Summer mode: Entering safe mode - enabling CWU only")

        # Ensure floor is OFF
        await self._async_set_climate(False)
        await asyncio.sleep(2)

        # Enable CWU with performance mode (heater)
        await self._async_set_water_heater_mode(WH_MODE_PERFORMANCE)
        self._log_action("Summer safe mode active - CWU heater in control")
    finally:
        self._transition_in_progress = False
```

---

## Stany kontrolera

### Stany używane w Summer mode

| Stan | Opis | Warunki wejścia |
|------|------|-----------------|
| `idle` | Oczekiwanie | CWU >= target LUB brak warunków do grzania |
| `heating_cwu` | Grzanie z PV/taryfy | Warunki PV/taryfy spełnione, CWU < target |
| `emergency_cwu` | Grzanie awaryjne | CWU < critical (35°C) |
| `safe_mode` | Tryb bezpieczny | Sensor CWU niedostępny > 60 min |

### Stany NIE używane w Summer mode

- `heating_floor` - podłogówka wyłączona
- `emergency_floor` - nie dotyczy
- `pause` - nie ma limitu 3h (grzałka nie ma tego ograniczenia)
- `fake_heating_detected/restarting` - nie sprawdzamy fake heating

---

## Scenariusze działania

### Scenariusz 1: Słoneczny dzień letni

```
Czwartek, Czerwiec, pogoda słoneczna

06:00   │ Wschód słońca
        │ PV zaczyna produkować: 0W → 500W → 1500W
        │ CWU: 42°C (użyta w nocy)
        │ Stan: idle (czekamy na więcej produkcji)
        │
08:30   │ PV: 4000W (> 3300W grzałki)
        │ Bilans od 08:00: +1.2 kWh
        │ CWU: 41°C
        │ → Warunek: "PV covers heater" spełniony
        │ → START grzania CWU
        │
09:00   │ Bilans 08:00-09:00: +0.5 kWh (ale mieliśmy +1.2 przed grzaniem!)
        │ Nowa godzina, bilans = 0
        │ PV: 4500W, grzałka ciągnie 3300W
        │ → Nadal grzejemy (produkcja > grzałka)
        │
09:30   │ Bilans od 09:00: +0.6 kWh (produkowaliśmy ~4.5kW, zużywaliśmy 3.3kW)
        │ CWU: 46°C
        │ → Nadal grzejemy
        │
10:00   │ CWU: 50°C (target osiągnięty!)
        │ → STOP grzania
        │ → Stan: idle
        │
10:00-20:00 │ CWU powoli stygnie: 50°C → 44°C
            │ Energia z PV idzie do sieci (bilans +)
            │
20:00   │ Zachód słońca, PV → 0W
        │ CWU: 44°C (> critical 35°C, < target 50°C)
        │ Taryfa: droga (do 22:00)
        │ → Stan: idle (czekamy na tanią taryfę)
        │
22:00   │ Tania taryfa
        │ CWU: 43°C < target 50°C
        │ → START grzania (fallback taryfowy)
        │
23:30   │ CWU: 50°C
        │ → STOP grzania
```

### Scenariusz 2: Pochmurny dzień z przebłyskami

```
Piątek, Lipiec, zmienne zachmurzenie

08:00   │ PV: 800W (chmury)
        │ CWU: 38°C (blisko critical!)
        │ → Produkcja < grzałka (800W < 3300W)
        │ → Stan: idle (ale blisko granicy!)
        │
09:00   │ PV: 200W (duża chmura)
        │ CWU: 37°C
        │ → Nadal idle (brak produkcji, droga taryfa)
        │
10:15   │ CWU: 35°C (CRITICAL!)
        │ → EMERGENCY! Grzej niezależnie od wszystkiego
        │ → Wysłana notyfikacja
        │
11:00   │ CWU: 40°C (powyżej critical)
        │ Ale taryfa droga i brak PV
        │ → STOP grzania (wyszliśmy z emergency)
        │ → Stan: idle
        │
13:00   │ TANIA TARYFA!
        │ CWU: 39°C < 50°C target
        │ → START grzania (fallback taryfowy)
        │
14:15   │ CWU: 48°C
        │ Słońce wyszło! PV: 5000W
        │ → Kontynuujemy grzanie (mamy i PV i tanią taryfę)
        │
14:45   │ CWU: 50°C
        │ → STOP grzania
        │ Pozostały czas (14:45-15:00) PV idzie do sieci
```

### Scenariusz 3: Weekend - NOWA LOGIKA (PV ma priorytet)

```
Sobota, Sierpień, słonecznie

SLOT_NIGHT (00:00 - 08:00) - tania taryfa, ale czekamy na PV
─────────────────────────────────────────────────────────────
00:00   │ Tania taryfa (weekend!)
        │ CWU: 44°C (> 40°C próg nocny)
        │ PV: 0W (noc)
        │ → CWU >= NIGHT_THRESHOLD (40°C)
        │ → IDLE ⏳ (NIE grzejemy! czekamy na darmowe PV)
        │
06:00   │ CWU: 42°C (powoli stygnie)
        │ → Nadal >= 40°C → IDLE

SLOT_PV (08:00 - 18:00) - priorytet fotowoltaiki
─────────────────────────────────────────────────────────────
08:00   │ SLOT_PV rozpoczęty!
        │ PV: 800W (jeszcze słabe)
        │ CWU: 41°C
        │ → Produkcja < grzałka → IDLE (budujemy bilans)
        │
09:30   │ PV: 4200W (słońce mocne!)
        │ Bilans od 09:00: +1.4 kWh
        │ CWU: 40°C
        │ → Produkcja > grzałka → START grzania z PV! 🌞
        │
11:00   │ CWU: 50°C
        │ → STOP (target osiągnięty)
        │ Reszta PV idzie do sieci (+bilans)

EFEKT: Woda nagrzana za DARMO z PV!
Gdyby stary algorytm: grzalibyśmy o 00:00 z taniej taryfy = płacimy 0.72 zł/kWh
Teraz: grzejemy o 09:30 z PV = płacimy 0 zł (a nawet zarabiamy na eksporcie!)

SLOT_EVENING (18:00 - 24:00) - woda jeszcze ciepła
─────────────────────────────────────────────────────────────
18:00   │ CWU: 47°C (użyte trochę)
        │ PV: 500W (słabe)
        │ → Produkcja < grzałka, ale CWU > target-5 → IDLE
        │
20:00   │ CWU: 45°C
        │ PV: 0W
        │ → Droga taryfa, czekamy na 22:00
        │
22:00   │ Tania taryfa
        │ CWU: 44°C < 50°C
        │ → START grzania z taryfy (fallback)
        │
23:15   │ CWU: 50°C
        │ → STOP
```

### Scenariusz 3b: Weekend - pochmurny dzień (PV zawodzi)

```
Niedziela, Wrzesień, całkowite zachmurzenie

SLOT_NIGHT (00:00 - 08:00)
─────────────────────────────────────────────────────────────
00:00   │ CWU: 43°C (> 40°C)
        │ → IDLE (czekamy na PV)
        │
07:00   │ CWU: 39°C (< 40°C próg nocny!)
        │ → START grzania z taryfy (bufor bezpieczeństwa)
        │ → Target: 42°C (nie 50°C - tylko bufor)
        │
07:45   │ CWU: 42°C
        │ → STOP (NIGHT_TARGET osiągnięty)

SLOT_PV (08:00 - 18:00)
─────────────────────────────────────────────────────────────
08:00   │ SLOT_PV rozpoczęty
        │ PV: 200W (chmury 😞)
        │ CWU: 42°C
        │ → Produkcja << grzałka → IDLE (czekamy na PV)
        │
12:00   │ PV: 400W (nadal chmury)
        │ CWU: 40°C
        │ → Nadal IDLE (produkcja za słaba)
        │
16:00   │ DEADLINE! ⏰
        │ PV: 300W (bez szans)
        │ CWU: 38°C < EVENING_THRESHOLD (42°C)
        │ → Fallback! START grzania z taryfy
        │ → Komunikat: "PV insufficient, using cheap tariff"
        │
17:30   │ CWU: 50°C
        │ → STOP

EFEKT: Poczekaliśmy do 16:00 na szansę dla PV.
Niestety pochmurno, więc fallback na tanią taryfę.
Bez deadline'u czekalibyśmy do wieczora i woda byłaby za zimna na kąpiel.
```

### Scenariusz 3c: Weekend - częściowe zachmurzenie

```
Sobota, Lipiec, zmienna pogoda

SLOT_NIGHT (00:00 - 08:00)
─────────────────────────────────────────────────────────────
06:00   │ CWU: 41°C (> 40°C) → IDLE

SLOT_PV (08:00 - 18:00)
─────────────────────────────────────────────────────────────
08:00   │ PV: 1000W (chmury)
        │ CWU: 40°C
        │ → IDLE
        │
10:00   │ PV: 3800W (słońce wyszło!)
        │ Bilans od 10:00: +0.5 kWh
        │ CWU: 39°C
        │ → START grzania z PV 🌤️
        │
10:30   │ PV: 1200W (chmura!)
        │ Bilans od 10:00: +0.8 kWh
        │ CWU: 42°C
        │ → Strategia "druga połowa": bilans 0.8 < 1.65 wymagane
        │ → Produkcja 1200W < 3300W
        │ → STOP (warunki się zmieniły)
        │
11:00   │ Nowa godzina, bilans = 0
        │ PV: 4500W (znowu słońce!)
        │ CWU: 42°C
        │ → START grzania z PV
        │
12:00   │ CWU: 47°C
        │ PV: 5000W (super!)
        │ → Kontynuujemy
        │
12:30   │ CWU: 50°C
        │ → STOP (target!)

EFEKT: Grzanie przerywane przez chmury, ale ostatecznie
udało się nagrzać z PV. Bilansowanie działa - nie płacimy
za prąd mimo zmiennych warunków.
```

### Scenariusz 4: Problem z grzałką (brak postępu)

```
Środa, sensor wykrywa problem

10:00   │ PV: 4500W
        │ CWU: 40°C
        │ → START grzania
        │ Session start temp: 40°C
        │
10:30   │ CWU: 40°C (brak wzrostu!)
        │ → Nadal grzejemy (timeout 60 min)
        │
11:00   │ CWU: 40.5°C (prawie brak wzrostu)
        │ Timeout 60 min osiągnięty!
        │ Wymagany wzrost: 2°C, rzeczywisty: 0.5°C
        │ → STOP grzania
        │ → Wysłana notyfikacja o problemie
        │ → Stan: idle
        │
        │ (Kontroler nie będzie próbował ponownie
        │  aż temperatura spadnie lub użytkownik sprawdzi)
```

---

## Plan implementacji krok po kroku

### Faza 1: Stałe i konfiguracja

**Pliki do modyfikacji:** `const.py`, `config_flow.py`, `strings.json`, `translations/`

1. Dodać stałe Summer mode do `const.py`:
   - `SUMMER_HEATER_POWER`
   - `SUMMER_BALANCE_THRESHOLD`
   - `SUMMER_PV_MIN_PRODUCTION`
   - `SUMMER_CWU_*` temperatury
   - `CONF_PV_*` klucze konfiguracji
   - `DEFAULT_PV_*` domyślne sensory

2. Rozszerzyć `config_flow.py`:
   - Dodać krok konfiguracji sensorów PV
   - Dodać walidację sensorów
   - Obsługa opcjonalnego sensora pogody

3. Dodać tłumaczenia:
   - `strings.json`
   - `translations/pl.json`
   - `translations/en.json`

### Faza 2: Logika koordynatora

**Pliki do modyfikacji:** `coordinator.py`

1. Dodać pomocnicze metody odczytu PV:
   - `_get_pv_balance()`
   - `_get_pv_production()`
   - `_get_grid_power()`
   - `_get_heater_power()`
   - `_get_balance_threshold()`

2. Dodać metody decyzyjne:
   - `_should_heat_from_pv()`
   - `_should_heat_from_tariff()`
   - `_check_summer_cwu_no_progress()`

3. Dodać metody sterowania:
   - `_summer_start_heating()`
   - `_summer_stop_heating()`
   - `_enter_summer_safe_mode()`

4. Zaimplementować główną logikę:
   - `_run_summer_mode_logic()`
   - Zaktualizować `_run_control_logic()` do routingu na summer

5. Zaktualizować `_async_update_data()`:
   - Dodać dane PV do zwracanego dict
   - Dodać metryki summer mode

### Faza 3: Sensory i UI

**Pliki do modyfikacji:** `sensor.py`, `frontend/panel.html`, `frontend/panel.js`

1. Dodać nowe atrybuty do sensora stanu:
   - `pv_balance`
   - `pv_production`
   - `grid_power`
   - `summer_heating_reason`

2. Zaktualizować panel UI:
   - Wyświetlanie danych PV gdy tryb summer
   - Wizualizacja bilansu godzinowego
   - Status "heating from PV" vs "heating from tariff"

### Faza 4: Testy

**Pliki do utworzenia/modyfikacji:** `tests/test_summer_mode.py`

1. Testy jednostkowe:
   - `test_should_heat_from_pv_first_half_*`
   - `test_should_heat_from_pv_second_half_*`
   - `test_should_heat_from_tariff_*`
   - `test_summer_no_progress_detection`
   - `test_summer_emergency_cwu`
   - `test_summer_safe_mode`

2. Testy integracyjne:
   - Pełny cykl słonecznego dnia
   - Fallback na taryfę
   - Przejścia między stanami

### Faza 5: Dokumentacja

**Pliki do utworzenia:** `docs/SUMMER_MODE.md`

1. Opis działania (podobny do WINTER_MODE.md)
2. Scenariusze użycia
3. FAQ / Troubleshooting

---

## Rozszerzenia opcjonalne

### 1. Sensor deszczu/pogody

Można dodać integrację z prognozą pogody do predykcji produkcji PV:

```python
CONF_WEATHER_SENSOR: Final = "weather_sensor"
CONF_RAIN_SENSOR: Final = "rain_sensor"

def _get_weather_forecast(self) -> str | None:
    """Get weather condition (sunny, cloudy, rainy, etc)."""
    sensor = self.config.get(CONF_WEATHER_SENSOR)
    if sensor:
        return self._get_entity_state(sensor)
    return None

def _is_rainy(self) -> bool:
    """Check if it's raining or heavy clouds expected."""
    rain = self._get_sensor_value(self.config.get(CONF_RAIN_SENSOR))
    if rain is not None and rain > 0:
        return True

    weather = self._get_weather_forecast()
    if weather in ("rainy", "pouring", "lightning", "lightning-rainy"):
        return True

    return False
```

Zastosowanie: Gdy deszcz → od razu fallback na taryfę, nie czekamy na PV.

### 2. Predykcja produkcji

Można analizować historię produkcji PV z poprzednich dni/godzin:

```python
def _predict_pv_production(self, hours_ahead: int = 1) -> float:
    """Predict PV production based on historical data and current trends."""
    # Analiza historii z statistics
    # Uwzględnienie godziny dnia i pory roku
    # Porównanie z aktualnymi warunkami
    pass
```

### 3. Dynamiczny próg bilansu

Zamiast stałego 50%, próg może się zmieniać w zależności od:
- Minuty w godzinie (im bliżej końca, tym większy wymagany zapas)
- Trendu produkcji (rośnie/spada)
- Historii pochmurności danego dnia

```python
def _calculate_dynamic_threshold(self, minute: int, pv_trend: float) -> float:
    """Calculate dynamic balance threshold based on time and conditions."""
    base_threshold = 0.5

    # Im bliżej końca godziny, tym większy wymagany zapas
    time_factor = 1.0 + (minute - 30) * 0.02  # +2% per minute after :30

    # Jeśli produkcja spada, wymagamy większego zapasu
    trend_factor = 1.0
    if pv_trend < 0:  # produkcja spada
        trend_factor = 1.2

    return min(base_threshold * time_factor * trend_factor, 1.0)
```

### 4. Inteligentne okno startowe

Zamiast sztywnego startu o XX:30, można dynamicznie wybierać moment startu:

```python
def _find_optimal_start_minute(self) -> int:
    """Find optimal minute to start heating in current hour."""
    pv_production = self._get_pv_production()
    heater_power = self._get_heater_power()

    if pv_production >= heater_power * 1.5:
        # Bardzo dobra produkcja - można zacząć wcześniej
        return 15
    elif pv_production >= heater_power:
        # Dobra produkcja - standardowy start
        return 30
    else:
        # Słaba produkcja - czekamy dłużej
        return 45
```

---

## Podsumowanie

Tryb Summer to zaawansowany algorytm optymalizujący wykorzystanie energii z fotowoltaiki do grzania CWU. Kluczowe cechy:

1. **System slotów czasowych** - PV ma priorytet, taryfa jest fallbackiem
   - SLOT_PV (08:00-18:00): Czekamy na darmową energię z PV
   - SLOT_EVENING (18:00-24:00): Fallback na tanią taryfę
   - SLOT_NIGHT (00:00-08:00): Tylko bufor bezpieczeństwa (grzanie do 42°C gdy <40°C)

2. **Bilansowanie godzinowe** - maksymalizuje oszczędności przy rozliczeniu za zbilansowane godziny
   - Pierwsza połowa: ostrożna strategia, budujemy bilans
   - Druga połowa: agresywna strategia, wykorzystujemy zgromadzony zapas

3. **Deadline dla PV (16:00)** - jeśli PV nie nagrzało wody do 16:00, fallback na taryfę
   - Zapobiega sytuacji gdy woda jest za zimna na wieczorną kąpiel

4. **Inteligentna obsługa weekendów** - NIE grzejemy o północy mimo taniej taryfy!
   - Czekamy na PV które da DARMOWĄ energię
   - Oszczędność: 0 zł vs 0.72 zł/kWh z taniej taryfy

5. **Brak grzania podłogowego** - uproszczona logika na lato

6. **Detekcja problemów** - ostrzeżenia gdy grzałka nie działa (brak wzrostu temp)

### Porównanie oszczędności

| Scenariusz | Stary algorytm | Nowy algorytm | Oszczędność |
|------------|----------------|---------------|-------------|
| Weekend słoneczny | Grzanie o 00:00 z taryfy 0.72 zł/kWh | Grzanie o 10:00 z PV 0 zł | **100%** |
| Dzień roboczy słoneczny | Grzanie o 22:00 z taryfy | Grzanie o 10:00 z PV | **100%** |
| Weekend pochmurny | Grzanie o 00:00 | Grzanie o 16:00 (deadline) | **0%** (ale ta sama cena) |
| Częściowe zachmurzenie | Mix taryfa + PV | Maksymalizacja PV | **~50%** |

Implementacja wymaga modyfikacji ~5 plików i dodania ~400-500 linii kodu. Testy powinny obejmować wszystkie scenariusze opisane w tym dokumencie.
