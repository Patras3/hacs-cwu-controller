# Sterowanie CWU i Ogrzewaniem - Dokumentacja BSB-LAN

## Spis treści
1. [Włączanie/Wyłączanie](#włączaniewyłączanie)
2. [Odczyt statusów](#odczyt-statusów)
3. [ENUM-y stanów](#enumy-stanów)
4. [Setpointy i temperatury](#setpointy-i-temperatury)
5. [Czujniki temperatury](#czujniki-temperatury)
6. [Dane debugowe](#dane-debugowe)
7. [Optymalizacja requestów](#optymalizacja-requestów)

---

## Włączanie/Wyłączanie

### CWU (Ciepła Woda Użytkowa) - Parametr 1600

```bash
# Odczyt
curl "http://192.168.50.219/JQ=1600"

# Zapis
curl "http://192.168.50.219/S1600=1"   # Włącz
curl "http://192.168.50.219/S1600=0"   # Wyłącz
```

| Wartość | Opis | Kiedy używać |
|---------|------|--------------|
| `0` | **Off** | Całkowite wyłączenie grzania CWU |
| `1` | **On** | Normalna praca, grzanie do setpointu |
| `2` | **Eco** | Tryb oszczędny (reduced setpoint) |

### Ogrzewanie podłogowe / Obieg grzewczy 1 - Parametr 700

```bash
# Odczyt
curl "http://192.168.50.219/JQ=700"

# Zapis
curl "http://192.168.50.219/S700=1"   # Automatic
curl "http://192.168.50.219/S700=0"   # Protection (wyłączone)
```

| Wartość | Opis | Kiedy używać |
|---------|------|--------------|
| `0` | **Protection** | Tylko ochrona przed zamarzaniem (wyłączone) |
| `1` | **Automatic** | Automatyczny tryb (harmonogram) |
| `2` | **Reduced** | Obniżona temperatura |
| `3` | **Comfort** | Temperatura komfortowa |

---

## Odczyt statusów

### Jeden request - wszystkie kluczowe statusy

```bash
curl "http://192.168.50.219/JQ=700,1600,8000,8003,8006"
```

### Parametry statusowe

| Parametr | Nazwa | Co pokazuje |
|----------|-------|-------------|
| **700** | Operating mode (HC1) | Tryb pracy obiegu grzewczego |
| **1600** | Operating mode (DHW) | Tryb pracy CWU |
| **8000** | Status heating circuit 1 | Aktualny status obiegu grzewczego |
| **8003** | Status DHW | Aktualny status grzania CWU |
| **8006** | Status heat pump | Aktualny status pompy ciepła |

---

## ENUM-y stanów

### 8000 - Status heating circuit 1 (Obieg grzewczy)

| Wartość | Opis PL | Znaczenie |
|---------|---------|-----------|
| `---` | Nieaktywny | Obieg nie działa |
| `Room temperature limitation` | Ograniczenie temp. pokojowej | Osiągnięto temperaturę, grzanie wstrzymane |
| `Comfort` | Komfort | Grzanie do temperatury komfortowej |
| `Reduced` | Obniżony | Grzanie do temperatury obniżonej |
| `Protection` | Ochrona | Tylko ochrona przed zamarzaniem |
| `Frost protection for plant active` | Ochrona instalacji | Tryb ochrony przed zamarzaniem |
| `Summer` | Lato | Tryb letni, grzanie wyłączone |
| `Setback` | Obniżenie | Czasowe obniżenie temperatury |

### 8003 - Status DHW (CWU)

| Wartość | Opis PL | Co robi HP? | Uwagi |
|---------|---------|-------------|-------|
| `Off` | Wyłączone | ✗ NIE | CWU wyłączone przez użytkownika |
| `Ready` | Gotowe | ✗ NIE | CWU osiągnęło temperaturę docelową |
| `Charging, nominal setpoint` | Ładowanie, setpoint nominalny | ✓ TAK | HP grzeje CWU do pełnej temperatury |
| `Charging, reduced setpoint` | Ładowanie, setpoint obniżony | ✓ TAK | HP grzeje CWU do obniżonej temperatury |
| `Charging electric, nominal setpoint` | Ładowanie elektryczne | ⚠️ GRZAŁKA | System delegował grzanie do grzałki! |
| `Push` | Push | ✓ TAK | Szybkie dogrzewanie |
| `Legionella function` | Funkcja legionelli | ✓ TAK | Cotygodniowe przegrzanie (70°C) |

**WAŻNE:** Gdy widzisz `Charging electric` - system myśli że grzałka elektryczna grzeje!
Jeśli grzałka jest spalona, NIC nie grzeje mimo tego statusu.

### 8006 - Status heat pump (Pompa ciepła)

| Wartość | Opis PL | Sprężarka? | Pobór mocy |
|---------|---------|------------|------------|
| `---` | Nieaktywny | ✗ NIE | ~0W |
| `Compressor 1 on` | Sprężarka włączona | ✓ TAK | 500-1500W |
| `Frost protection for plant active` | Ochrona instalacji | ✗ NIE | 40-100W |
| `Defrost active` | Rozmrażanie | ⚠️ Odwrotnie | 100-200W |
| `Pump overrun` | Dobieg pompy | ✗ NIE | ~80W |
| `Blocked` | Zablokowana | ✗ NIE | ~0W |
| `Antilegionella` | Antylegionella | ✓ TAK | 1000-2000W |

---

## Setpointy i temperatury

### Temperatura CWU

| Parametr | Nazwa | Opis | R/W |
|----------|-------|------|-----|
| **1610** | DHW temperature nominal setpoint | Docelowa temp. CWU (tryb On) | R/W |
| **1612** | DHW temperature reduced setpoint | Obniżona temp. CWU (tryb Eco) | R/W |
| **5020** | DHW flow setpoint boost | Boost - dodatek do setpointu | R/W |
| **5024** | DHW switching differential | Histereza (różnica wł/wył) | R/W |
| **8411** | Setpoint heat pump | **Efektywny** cel HP (wyliczony) | R |
| **8830** | DHW temperature actual | Aktualna temp. CWU | R |

### Jak działa wyliczenie efektywnego setpointu?

```
Efektywny setpoint (8411) = Setpoint nominalny (1610) + Boost (5020)

Przykład:
  1610 = 50°C (setpoint nominalny)
  5020 = 5°C  (boost)
  8411 = 55°C (efektywny cel HP)
```

### Histereza (5024)

```
Histereza = 4°C oznacza:
  - Cel: 50°C
  - Start grzania: gdy CWU < 46°C (50 - 4)
  - Stop grzania: gdy CWU >= 50°C
```

### Odczyt wszystkich setpointów jednym requestem

```bash
curl "http://192.168.50.219/JQ=1610,1612,5020,5024,8411,8830"
```

Odpowiedź:
```json
{
  "1610": {"name": "DHW temperature nominal setpoint", "value": "50.0", "unit": "°C"},
  "1612": {"name": "DHW temperature reduced setpoint", "value": "35.0", "unit": "°C"},
  "5020": {"name": "DHW flow setpoint boost", "value": "5.0", "unit": "°C"},
  "5024": {"name": "DHW switching differential", "value": "4.0", "unit": "°C"},
  "8411": {"name": "Setpoint heat pump", "value": "55.0", "unit": "°C"},
  "8830": {"name": "DHW temperature actual value top (B3)", "value": "45.2", "unit": "°C"}
}
```

---

## Czujniki temperatury

### Temperatury obiegu

| Parametr | Nazwa | Opis |
|----------|-------|------|
| **8412** | Flow temp heat pump | Temperatura zasilania (wyjście z HP) |
| **8410** | Return temperature heat pump | Temperatura powrotu (wejście do HP) |
| **ΔT** | Delta T | `8412 - 8410` = transfer ciepła |

### Delta T - interpretacja

| ΔT | Znaczenie |
|----|-----------|
| **+3 do +5°C** | Normalne grzanie |
| **+0.5 do +2°C** | Słabe grzanie / niski przepływ |
| **~0°C** | Brak przepływu ciepła |
| **Ujemna** | Defrost lub błąd |

### Temperatura CWU

| Parametr | Nazwa | Opis |
|----------|-------|------|
| **8830** | DHW temperature actual value top (B3) | Temp. góra zbiornika |


### Temperatura zewnętrzna

| Parametr | Nazwa | Opis |
|----------|-------|------|
| **8700** | Outside temp | Temperatura na zewnątrz |

### Odczyt wszystkich temperatur jednym requestem

```bash
curl "http://192.168.50.219/JQ=8412,8410,8830,8700"
```

---

## Dane debugowe

### Statystyki sprężarki

| Parametr | Nazwa | Opis |
|----------|-------|------|
| **8450** | Hours run compressor 1 | Godziny pracy sprężarki |
| **8451** | Start counter compressor 1 | Licznik startów sprężarki |

```bash
curl "http://192.168.50.219/JQ=8450,8451"
```

Średni czas cyklu = `8450 * 60 / 8451` minut

### Historia błędów

| Parametr | Nazwa |
|----------|-------|
| **6700** | Error (aktualny błąd) |
| **6800** | Time stamp error history entry 1 |
| **6801** | Error code history entry 1 |

```bash
curl "http://192.168.50.219/JQ=6700,6800,6801,6802,6803"
```

### Parametr grzałki elektrycznej

| Parametr | Nazwa | Opis |
|----------|-------|------|
| **2884** | Release electric flow below outside temp | Próg temp. zewn. włączenia grzałki |

---

## Optymalizacja requestów

### Problem: Za dużo requestów do API

Chmura / integracja narzeka na zbyt częste odpytywanie BSB-LAN.

### Rozwiązanie: Jeden request zamiast wielu

**ŹLE - 5 osobnych requestów:**
```bash
curl "http://192.168.50.219/JQ=8003"
curl "http://192.168.50.219/JQ=8006"
curl "http://192.168.50.219/JQ=8412"
curl "http://192.168.50.219/JQ=8830"
curl "http://192.168.50.219/JQ=8700"
```

**DOBRZE - 1 request:**
```bash
curl "http://192.168.50.219/JQ=8003,8006,8412,8410,8830,8700"
```

### Gotowe zapytania dla integracji

#### Pełny status (wszystko co potrzebne)
```bash
curl "http://192.168.50.219/JQ=700,1600,8000,8003,8006,8412,8410,8830,8700,8411"
```

#### Tylko statusy (minimalne)
```bash
curl "http://192.168.50.219/JQ=8003,8006"
```

#### Tylko temperatury
```bash
curl "http://192.168.50.219/JQ=8412,8410,8830,8700"
```

#### Setpointy CWU
```bash
curl "http://192.168.50.219/JQ=1610,1612,5020,5024,8411"
```

---

## Przykład logiki sterowania w Python

```python
import requests

BSB_URL = "http://192.168.50.219"

def get_status():
    """Pobiera wszystkie statusy jednym requestem"""
    r = requests.get(f"{BSB_URL}/JQ=700,1600,8003,8006,8412,8410,8830,8700")
    data = r.json()

    flow = float(data['8412']['value'])
    ret = float(data['8410']['value'])

    return {
        'heating_mode': data['700']['desc'],        # Protection/Automatic/Reduced/Comfort
        'dhw_mode': data['1600']['desc'],           # Off/On/Eco
        'dhw_status': data['8003']['desc'],         # Charging/Ready/Off
        'hp_status': data['8006']['desc'],          # Compressor on/Frost protection
        'flow_temp': flow,
        'return_temp': ret,
        'delta_t': flow - ret,
        'cwu_temp': float(data['8830']['value']),
        'outside_temp': float(data['8700']['value']),
    }

def set_dhw(mode: int):
    """Ustawia tryb CWU: 0=Off, 1=On, 2=Eco"""
    requests.get(f"{BSB_URL}/S1600={mode}")

def set_heating(mode: int):
    """Ustawia tryb ogrzewania: 0=Protection, 1=Automatic, 2=Reduced, 3=Comfort"""
    requests.get(f"{BSB_URL}/S700={mode}")

def is_hp_actually_heating():
    """Sprawdza czy HP faktycznie grzeje (nie tylko status)"""
    status = get_status()

    # Sprawdź czy sprężarka działa
    if 'Compressor' not in status['hp_status']:
        return False

    # Sprawdź czy jest przepływ ciepła
    if status['delta_t'] < 1.0:
        return False

    return True

def is_safe_to_turn_off():
    """Czy można bezpiecznie wyłączyć grzanie?"""
    status = get_status()

    # NIE wyłączaj podczas frost protection
    if 'Frost protection' in status['hp_status']:
        return False

    # NIE wyłączaj gdy grzałka elektryczna działa
    if 'electric' in status['dhw_status'].lower():
        return False

    return True
```

---

## Podsumowanie - najważniejsze parametry

### Sterowanie (R/W)

| Parametr | Co robi | Wartości |
|----------|---------|----------|
| **700** | Włącz/wyłącz ogrzewanie | 0=Off, 1=Auto, 2=Reduced, 3=Comfort |
| **1600** | Włącz/wyłącz CWU | 0=Off, 1=On, 2=Eco |
| **1610** | Ustaw temperaturę CWU | np. 50.0 |

### Odczyt statusu (R)

| Parametr | Co pokazuje |
|----------|-------------|
| **8003** | Status CWU (Charging/Ready/Off) |
| **8006** | Status HP (Compressor on/Frost protection) |
| **8000** | Status obiegu grzewczego |

### Temperatury (R)

| Parametr | Co pokazuje |
|----------|-------------|
| **8412** | Flow temp (zasilanie) |
| **8410** | Return temp (powrót) |
| **8830** | Temp. CWU |
| **8700** | Temp. zewnętrzna |
| **8411** | Efektywny setpoint HP |
