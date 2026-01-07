"""Tariff and time window utilities for CWU Controller.

G12w tariff (Poland/Energa):
- Cheap: 13:00-15:00, 22:00-06:00, weekends, holidays
- Expensive: All other times

Winter mode CWU heating windows:
- 03:00-06:00, 13:00-15:00, 22:00-24:00
"""

from __future__ import annotations

from datetime import datetime

from .const import (
    TARIFF_CHEAP_WINDOWS,
    TARIFF_CHEAP_RATE,
    TARIFF_EXPENSIVE_RATE,
    WINTER_CWU_HEATING_WINDOWS,
)


def is_cheap_tariff(
    dt: datetime | None = None,
    workday_state: str | None = None,
) -> bool:
    """Check if given time is in cheap tariff window (G12w).

    Args:
        dt: Datetime to check (default: now)
        workday_state: State of workday sensor ("on"=workday, "off"=weekend/holiday)

    Returns:
        True if cheap tariff applies
    """
    if dt is None:
        dt = datetime.now()

    # If workday sensor says "off" -> weekend/holiday -> cheap all day
    if workday_state == "off":
        return True

    # Weekends are always cheap (fallback if workday sensor unavailable)
    if dt.weekday() >= 5:  # Saturday = 5, Sunday = 6
        return True

    # Check time windows (applies to workdays)
    current_hour = dt.hour
    for start_hour, end_hour in TARIFF_CHEAP_WINDOWS:
        if start_hour <= current_hour < end_hour:
            return True

    return False


def get_current_tariff_rate(
    cheap_rate: float = TARIFF_CHEAP_RATE,
    expensive_rate: float = TARIFF_EXPENSIVE_RATE,
    dt: datetime | None = None,
    workday_state: str | None = None,
) -> float:
    """Get current electricity rate in zł/kWh.

    Args:
        cheap_rate: Cheap tariff rate
        expensive_rate: Expensive tariff rate
        dt: Datetime to check (default: now)
        workday_state: State of workday sensor

    Returns:
        Current rate in zł/kWh
    """
    if is_cheap_tariff(dt, workday_state):
        return cheap_rate
    return expensive_rate


def is_winter_cwu_heating_window(dt: datetime | None = None) -> bool:
    """Check if current time is in winter mode CWU heating window.

    Windows: 03:00-06:00, 13:00-15:00, 22:00-24:00

    Args:
        dt: Datetime to check (default: now)

    Returns:
        True if in heating window
    """
    if dt is None:
        dt = datetime.now()

    current_hour = dt.hour
    for start_hour, end_hour in WINTER_CWU_HEATING_WINDOWS:
        if start_hour <= current_hour < end_hour:
            return True
    return False


