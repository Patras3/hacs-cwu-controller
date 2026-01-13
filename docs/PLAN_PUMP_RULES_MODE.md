# Plan: Tryb "pump_rules" - pompa decyduje, my liczymy energię

## Cel
Dodać nowy tryb operacyjny `pump_rules` gdzie:
1. Włączone są **OBA** - CWU i podłogówka (pompa sama decyduje co grzać)
2. Controller **NIE** podejmuje decyzji o przełączaniu
3. Energię atrybuujemy na podstawie **statusów BSB-LAN** (nie stanu controllera)

## Strategia atrybuowania energii dla pump_rules

| dhw_status | hp_status | Atrybuuj do |
|------------|-----------|-------------|
| "Charging" | "Compressor" | **CWU** (pompa grzeje wodę) |
| "Charging electric" | * | **CWU** (grzałka elektryczna) |
| NOT "Charging" | "Compressor" | **Floor** (pompa grzeje dom) |
| * | "off time" / "Defrost" / "Overrun" | **Nic** (pompa nie grzeje) |
| * | "---" | **Nic** (standby) |

**Kluczowa logika:**
```python
dhw_charging = "charging" in dhw_status.lower()
compressor_on = "compressor" in hp_status.lower()
electric_heater = "electric" in dhw_status.lower()
hp_blocked = any(x in hp_status.lower() for x in ["off time", "defrost", "overrun"])

if hp_blocked:
    return None  # Nie atrybuujemy
elif electric_heater:
    return "CWU"  # Grzałka elektryczna = CWU
elif dhw_charging and compressor_on:
    return "CWU"  # Pompa grzeje wodę
elif compressor_on and not dhw_charging:
    return "Floor"  # Pompa grzeje dom
else:
    return None  # Standby
```

---

## Pliki do modyfikacji

### 1. `const.py` - dodanie stałych
```python
MODE_PUMP_RULES: Final = "pump_rules"
STATE_PUMP_RULES: Final = "pump_rules"
OPERATING_MODES: Final = [..., MODE_PUMP_RULES]
```

### 2. `modes/pump_rules.py` - nowy handler (NOWY PLIK)
- Klasa `PumpRulesMode(BaseModeHandler)`
- W `run_logic()`:
  - Przy pierwszym uruchomieniu: włącz CWU + Floor
  - Ustaw stan na `STATE_PUMP_RULES`
  - Nic więcej nie rób (pompa decyduje)

### 3. `modes/__init__.py` - export
```python
from .pump_rules import PumpRulesMode
__all__ = [..., "PumpRulesMode"]
```

### 4. `coordinator.py` - rejestracja handlera
- Import `MODE_PUMP_RULES` i `PumpRulesMode`
- Dodanie do `_mode_handlers` dict
- Aktualizacja walidacji w `async_set_operating_mode()`

### 5. `energy.py` - KLUCZOWA ZMIANA
- Dodać nowy callback: `get_bsb_lan_data: Callable[[], dict]`
- Dodać callback: `get_operating_mode: Callable[[], str]`
- W `_attribute_energy()`:
  - Jeśli tryb == `pump_rules` → użyj BSB-LAN logiki
  - W przeciwnym razie → użyj dotychczasowej logiki (controller state)

### 6. `select.py` - UI
- Dodać label: `MODE_PUMP_RULES: "Pump Rules"`

---

## Szczegółowa implementacja

### energy.py - modyfikacja konstruktora

```python
def __init__(
    self,
    hass: HomeAssistant,
    get_meter_value: Callable[[], float | None],
    get_current_state: Callable[[], str],
    is_cheap_tariff: Callable[[], bool],
    get_bsb_lan_data: Callable[[], dict] = lambda: {},  # NOWE
    get_operating_mode: Callable[[], str] = lambda: "",  # NOWE
) -> None:
```

### energy.py - nowa metoda atrybuowania

```python
def _determine_heating_target_from_bsb(self) -> str | None:
    """Determine what pump is heating based on BSB-LAN status.

    Returns: "cwu", "floor", or None (not heating)
    """
    bsb_data = self._get_bsb_lan_data()
    if not bsb_data:
        return None

    dhw_status = bsb_data.get("dhw_status", "").lower()
    hp_status = bsb_data.get("hp_status", "").lower()

    # HP blocked states - no heating
    if any(x in hp_status for x in ["off time", "defrost", "overrun"]):
        return None

    # Electric heater = CWU
    if "electric" in dhw_status:
        return "cwu"

    # Compressor + Charging = CWU
    if "charging" in dhw_status and "compressor" in hp_status:
        return "cwu"

    # Compressor running but not charging DHW = Floor
    if "compressor" in hp_status and "charging" not in dhw_status:
        return "floor"

    return None
```

### energy.py - modyfikacja update()

```python
def update(self) -> None:
    # ... existing delta calculation ...

    # Attribute based on mode
    operating_mode = self._get_operating_mode()

    if operating_mode == "pump_rules":
        # Use BSB-LAN status for attribution
        heating_target = self._determine_heating_target_from_bsb()
        if heating_target == "cwu":
            self._attribute_energy_to_cwu(delta_kwh, is_cheap)
        elif heating_target == "floor":
            self._attribute_energy_to_floor(delta_kwh, is_cheap)
        # else: not attributed (standby)
    else:
        # Existing logic - use controller state
        self._attribute_energy(delta_kwh, current_state, is_cheap)
```

### modes/pump_rules.py - pełna implementacja

```python
"""Pump Rules mode - let pump decide everything."""

from __future__ import annotations

import logging
from ..const import STATE_PUMP_RULES
from .base import BaseModeHandler

_LOGGER = logging.getLogger(__name__)


class PumpRulesMode(BaseModeHandler):
    """Mode where pump has full control.

    Both CWU and floor heating are enabled.
    Pump autonomously decides what to heat.
    Controller only observes and tracks energy.
    """

    async def run_logic(
        self,
        cwu_urgency: int,
        floor_urgency: int,
        cwu_temp: float | None,
        salon_temp: float | None,
    ) -> None:
        """Enable both heating modes and let pump decide."""

        # First run: enable both CWU and floor
        if self._current_state != STATE_PUMP_RULES:
            self._log_action(
                "Pump rules: Enabling both",
                f"CWU temp: {cwu_temp}°C, Room temp: {salon_temp}°C"
            )

            # Enable CWU (param 1600 = 1)
            await self._async_set_cwu_on()
            # Enable Floor (param 700 = 1)
            await self._async_set_floor_on()

            self._change_state(STATE_PUMP_RULES)
            return

        # Subsequent runs: just log status, don't interfere
        dhw_status = self._bsb_lan_data.get("dhw_status", "---")
        hp_status = self._bsb_lan_data.get("hp_status", "---")

        _LOGGER.debug(
            "Pump rules active: DHW=%s, HP=%s, CWU=%.1f°C, Room=%.1f°C",
            dhw_status, hp_status,
            cwu_temp or 0, salon_temp or 0
        )
```

---

## Weryfikacja

### Testy jednostkowe
1. Test że tryb pump_rules włącza oba (CWU + Floor)
2. Test że EnergyTracker używa BSB-LAN logiki w trybie pump_rules
3. Test atrybuowania: "Charging" + "Compressor" → CWU
4. Test atrybuowania: "Compressor" bez "Charging" → Floor
5. Test atrybuowania: "Charging electric" → CWU
6. Test że w innych trybach nadal działa stara logika

### Testy manualne
1. Przełącz na tryb "Pump Rules" w UI
2. Sprawdź że oba (CWU i Floor) są włączone w BSB-LAN
3. Obserwuj sensory energii - czy atrybuują prawidłowo
4. Sprawdź action_history - czy loguje status

### Komenda testowa
```bash
cd /home/patryk/ai/hacs-cwu-controller
source .venv/bin/activate
python -m pytest tests/ -v -k "pump_rules or energy"
```

---

## Kolejność implementacji

1. `const.py` - dodaj stałe
2. `modes/pump_rules.py` - stwórz handler
3. `modes/__init__.py` - dodaj export
4. `coordinator.py` - zarejestruj handler
5. `energy.py` - dodaj BSB-LAN atrybuowanie
6. `select.py` - dodaj label UI
7. Testy - napisz i uruchom
8. Manualna weryfikacja

---

## Pytania do wyjaśnienia

**Żadnych** - logika jest jasna:
- Tryb pump_rules = włącz oba, nie ingeruj
- Atrybuuj energię na podstawie tego co pompa faktycznie robi (BSB-LAN status)
