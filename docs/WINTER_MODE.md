# Winter Mode - Szczegółowy opis działania

## Cel trybu Winter

Tryb Winter optymalizuje grzanie CWU (ciepłej wody użytkowej) pod kątem **taryfy G12w**, grzejąc wodę tylko w godzinach taniej energii. Dzięki temu maksymalizujesz oszczędności na rachunkach za prąd.

## Taryfa G12w - godziny taniej energii

| Okres | Godziny | Taryfa |
|-------|---------|--------|
| Noc | 00:00 - 06:00 | Tania (0.72 zł/kWh) |
| Rano | 06:00 - 13:00 | Droga (1.16 zł/kWh) |
| Popołudnie | 13:00 - 15:00 | Tania (0.72 zł/kWh) |
| Popołudnie/Wieczór | 15:00 - 22:00 | Droga (1.16 zł/kWh) |
| Noc | 22:00 - 24:00 | Tania (0.72 zł/kWh) |
| **Weekendy i święta** | Cały dzień | Tania (0.72 zł/kWh) |

## Okna grzewcze CWU w trybie Winter

Kontroler grzeje CWU **tylko** w tych oknach czasowych:

| Okno | Godziny | Opis |
|------|---------|------|
| Poranne | **03:00 - 06:00** | 3 godziny przed końcem taniej taryfy nocnej |
| Popołudniowe | **13:00 - 15:00** | Całe 2-godzinne okno taniej taryfy |
| Wieczorne | **22:00 - 24:00** | Po kąpieli dzieci, przed kąpielą dorosłych |

### Dlaczego 03:00-06:00, a nie 00:00-06:00?

Grzanie zaczyna się o 03:00, bo:
1. Woda nagrzana o północy wystygłaby do rana
2. 3 godziny wystarczą na pełne nagrzanie zbiornika
3. Woda jest najcieplejsza rano, gdy jest najbardziej potrzebna (prysznice)

### Dlaczego 22:00-24:00?

Okno wieczorne zostało dodane, bo:
1. Do 22:00 dzieci są już wykąpane - woda mogła się schłodzić
2. Dorośli kąpią się 2-4h później (około północy)
3. Taryfa jest tania od 22:00, więc dogrzanie nic nie kosztuje ekstra

## Temperatury w trybie Winter

Winter mode używa **tych samych ustawień temperatury** co pozostałe tryby:

| Parametr | Domyślna | Opis |
|----------|----------|------|
| **CWU Target** | 55°C | Docelowa temperatura (konfigurowalna) |
| **CWU Min** | 40°C | Poniżej tej temperatury grzanie włącza się ZAWSZE (emergency) |
| **Hysteresis** | 5°C | Grzanie zaczyna się gdy temp < target - hysteresis |

## Funkcje identyczne z trybem Broken Heater

Winter mode dzieli następujące funkcje z trybem Broken Heater:

- **Hysteresis** - zapobiega częstym przełączeniom (grzej gdy temp < target - 5°C)
- **Anti-oscillation** - minimalne czasy grzania (15 min CWU, 20 min podłoga)
- **DHW Charged handling** - 5 min przerwy po "naładowaniu" przed przełączeniem
- **Fake heating notification** - powiadomienie gdy grzałka może być zepsuta

## Scenariusze działania

### Scenariusz 1: Normalny dzień roboczy

```
Poniedziałek, workday sensor = ON, target = 55°C, hysteresis = 5°C

00:00-03:00  │ Floor - czekamy na okno grzewcze
             │ CWU: 52°C (powyżej progu 50°C = target-hysteresis)
             │
03:00        │ ✅ START okna grzewczego (poranne)
             │ CWU: 48°C < 50°C → Rozpoczynamy grzanie do 55°C
             │
05:30        │ CWU osiąga 55°C → przełącz na floor
             │
06:00        │ Koniec okna, koniec taniej taryfy
             │
06:00-13:00  │ Floor - droga taryfa
             │ CWU spada powoli: 55°C → 51°C
             │
13:00        │ ✅ START okna grzewczego (popołudniowe)
             │ CWU: 51°C > 50°C → NIE grzejemy (hysteresis)
             │
14:30        │ CWU: 49°C < 50°C → Dogrzewamy do 55°C
             │
15:00        │ Koniec okna, koniec taniej taryfy
             │
15:00-18:00  │ Floor - droga taryfa
             │
18:00-21:00  │ 🛁 Kąpiel dzieci
             │ CWU spada: 55°C → 46°C
             │
22:00        │ ✅ START okna grzewczego (wieczorne)
             │ CWU: 44°C < 50°C → Dogrzewamy do 55°C
             │
23:15        │ CWU osiąga 55°C → przełącz na floor
             │
24:00        │ 🛁 Kąpiel dorosłych (00:00-02:00)
             │ Woda ciepła i gotowa!
```

### Scenariusz 2: Weekend (lub święto)

```
Sobota, workday sensor = OFF → Cały dzień TANIA TARYFA

W weekend kontroler działa tak samo jak w dni robocze:
- Okna grzewcze: 03:00-06:00, 13:00-15:00, 22:00-24:00
- Ale CAŁA energia jest w taniej taryfie!

Różnica: jeśli CWU spadnie poniżej 40°C o 10:00,
grzanie włączy się i nadal będzie liczone jako tanie.
```

### Scenariusz 3: Awaryjne grzanie (poniżej 40°C)

```
Środa, godz. 18:00 - droga taryfa
CWU spadło do 38°C (poniżej progu 40°C = CWU Min)

18:00        │ ⚠️ EMERGENCY! CWU < 40°C
             │ Grzanie włącza się MIMO drogiej taryfy
             │ Stan: emergency_cwu
             │
18:45        │ CWU osiąga 43°C (min + 3°C buffer)
             │ → przełącz na floor
             │
             │ Pełne nagrzanie do 55°C nastąpi
             │ w następnym oknie (22:00 lub 03:00)
```

## Logika decyzyjna

```
┌─────────────────────────────────────────────────────────┐
│                    WINTER MODE                          │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  CWU < CWU_MIN (40°C) ?                                │
│      │                                                  │
│      ├── TAK → GRZEJ NATYCHMIAST (emergency)           │
│      │         (niezależnie od taryfy i okna)          │
│      │         do osiągnięcia min + 3°C                │
│      │                                                  │
│      └── NIE → Czy jest okno grzewcze?                 │
│                (03:00-06:00, 13:00-15:00, 22:00-24:00) │
│                    │                                    │
│                    ├── TAK → CWU < TARGET - HYSTERESIS?│
│                    │             │                      │
│                    │             ├── TAK → GRZEJ       │
│                    │             │   (do TARGET)       │
│                    │             └── NIE → FLOOR       │
│                    │                                    │
│                    └── NIE → FLOOR (czekaj na okno)    │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

## Porównanie kosztów: Winter vs Broken Heater mode

Załóżmy dzienne zużycie 5 kWh na CWU:

| Tryb | Rozkład zużycia | Koszt dzienny |
|------|-----------------|---------------|
| **Broken Heater** | 50% tania / 50% droga | 2.5×0.72 + 2.5×1.16 = **4.70 zł** |
| **Winter** | 90% tania / 10% droga (emergency) | 4.5×0.72 + 0.5×1.16 = **3.82 zł** |

**Oszczędność: ~0.88 zł dziennie = ~26 zł miesięcznie**

## Interakcja z ogrzewaniem podłogowym

W trybie Winter:
1. Priorytet ma CWU podczas okien grzewczych (jeśli temp < target - hysteresis)
2. Podłogówka działa gdy CWU jest nagrzane lub poza oknami
3. Awaryjne grzanie CWU (< 40°C) ma najwyższy priorytet
4. Anti-oscillation zapobiega częstym przełączeniom

## Monitorowanie grzałki

Winter mode zakłada, że grzałka elektryczna działa poprawnie. Jeśli wykryje próbę użycia grzałki bez jej działania (fake heating), wyśle powiadomienie:

> ⚠️ Heater Problem Detected!
> Pump is trying to use electric heater but it may not be working.
> Please check the heater!

Grzanie kontynuuje się normalnie - to tylko ostrzeżenie.

## Wymagania

- **Workday sensor**: Wymagany do wykrywania świąt (binary_sensor.workday_sensor)
- Bez workday sensor święta nie są rozpoznawane jako dni z tanią taryfą

## Konfiguracja

Wszystkie wartości można zmienić w UI (Ustawienia → Urządzenia → CWU Controller → Konfiguruj):

| Parametr | Domyślna | Zakres | Opis |
|----------|----------|--------|------|
| CWU Target Temp | 55°C | 40-55°C | Docelowa temperatura CWU |
| CWU Min Temp | 40°C | 35-45°C | Próg awaryjny (emergency) |
| CWU Hysteresis | 5°C | 2-10°C | Różnica przed rozpoczęciem grzania |
| Tariff Cheap Rate | 0.72 zł | 0.1-5.0 | Kalkulacja kosztów |
| Tariff Expensive Rate | 1.16 zł | 0.1-5.0 | Kalkulacja kosztów |
