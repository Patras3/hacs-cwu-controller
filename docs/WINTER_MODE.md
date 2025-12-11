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

## Temperatury w trybie Winter (domyślne wartości)

| Parametr | Wartość | Opis |
|----------|---------|------|
| **Target zimowy** | **50°C** | Docelowa temperatura (45°C + 5°C offset) |
| **Próg awaryjny** | **40°C** | Poniżej tej temperatury grzanie włącza się ZAWSZE |
| **Maksimum** | **55°C** | Górny limit temperatury |

## Scenariusze działania

### Scenariusz 1: Normalny dzień roboczy

```
Poniedziałek, workday sensor = ON

00:00-03:00  │ Idle - czekamy na okno grzewcze
             │ CWU: 42°C (powyżej progu 40°C - OK)
             │
03:00        │ ✅ START okna grzewczego (poranne)
             │ CWU: 41°C → Rozpoczynamy grzanie do 50°C
             │
05:30        │ CWU osiąga 50°C → STOP grzania
             │
06:00        │ Koniec okna, koniec taniej taryfy
             │
06:00-13:00  │ Idle - droga taryfa
             │ CWU spada powoli: 50°C → 44°C
             │
13:00        │ ✅ START okna grzewczego (popołudniowe)
             │ CWU: 44°C → Dogrzewamy do 50°C
             │
14:15        │ CWU osiąga 50°C → STOP grzania
             │
15:00        │ Koniec okna, koniec taniej taryfy
             │
15:00-18:00  │ Idle - droga taryfa
             │
18:00-21:00  │ 🛁 Kąpiel dzieci
             │ CWU spada: 50°C → 43°C
             │
22:00        │ ✅ START okna grzewczego (wieczorne)
             │ CWU: 43°C → Dogrzewamy do 50°C
             │ (dzieci wykąpane, dorośli za 2-4h)
             │
23:15        │ CWU osiąga 50°C → STOP grzania
             │
24:00        │ Koniec okna wieczornego
             │ 🛁 Kąpiel dorosłych (00:00-02:00)
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
CWU spadło do 38°C (poniżej progu 40°C)

18:00        │ ⚠️ EMERGENCY! CWU < 40°C
             │ Grzanie włącza się MIMO drogiej taryfy
             │ Stan: emergency_cwu
             │
18:45        │ CWU osiąga 40°C → STOP grzania
             │ (grzejemy tylko do progu, nie do targetu)
             │ Powrót do Idle
             │
             │ Pełne nagrzanie do 50°C nastąpi
             │ w następnym oknie (03:00 lub 13:00)
```

## Logika decyzyjna

```
┌─────────────────────────────────────────────────────────┐
│                    WINTER MODE                          │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  CWU < 40°C ?                                          │
│      │                                                  │
│      ├── TAK → GRZEJ NATYCHMIAST (emergency)           │
│      │         (niezależnie od taryfy i okna)          │
│      │         do osiągnięcia 40°C                     │
│      │                                                  │
│      └── NIE → Czy jest okno grzewcze?                 │
│                (03:00-06:00, 13:00-15:00, 22:00-24:00) │
│                    │                                    │
│                    ├── TAK → CWU < 50°C ?              │
│                    │             │                      │
│                    │             ├── TAK → GRZEJ       │
│                    │             └── NIE → IDLE        │
│                    │                                    │
│                    └── NIE → IDLE (czekaj na okno)     │
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
1. Priorytet ma CWU podczas okien grzewczych
2. Podłogówka działa gdy CWU jest nagrzane lub poza oknami
3. Awaryjne grzanie CWU (< 40°C) ma najwyższy priorytet

## Wymagania

- **Workday sensor**: Wymagany do wykrywania świąt (binary_sensor.workday_sensor)
- Bez workday sensor święta nie są rozpoznawane jako dni z tanią taryfą

## Konfiguracja

Wszystkie wartości można zmienić w UI (Ustawienia → Urządzenia → CWU Controller → Konfiguruj):

| Parametr | Domyślna | Zakres | Wpływ na Winter mode |
|----------|----------|--------|---------------------|
| CWU Target Temp | 45°C | 40-55°C | Winter target = wartość + 5°C |
| Tariff Cheap Rate | 0.72 zł | 0.1-5.0 | Kalkulacja kosztów |
| Tariff Expensive Rate | 1.16 zł | 0.1-5.0 | Kalkulacja kosztów |
