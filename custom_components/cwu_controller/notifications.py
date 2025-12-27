"""Notification utilities for CWU Controller."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .coordinator import CWUControllerCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_send_notification(
    coordinator: CWUControllerCoordinator,
    title: str,
    message: str,
) -> None:
    """Send notification via configured service."""
    notify_service = coordinator.config.get("notify_service")
    if not notify_service:
        return

    try:
        service_domain, service_name = notify_service.split(".", 1)
        await coordinator.hass.services.async_call(
            service_domain,
            service_name,
            {"title": title, "message": message},
            blocking=False,
        )
    except Exception as e:
        _LOGGER.warning("Failed to send notification: %s", e)


async def async_check_and_send_daily_report(
    coordinator: CWUControllerCoordinator,
) -> None:
    """Check if it's time to send daily report and send it."""
    now = datetime.now()

    # Send report between 00:05 and 00:15
    if not (now.hour == 0 and 5 <= now.minute <= 15):
        return

    # Check if we already sent report today
    if coordinator._energy_tracker.last_daily_report_date is not None:
        if coordinator._energy_tracker.last_daily_report_date.date() == now.date():
            return

    # Get yesterday's energy data
    energy = coordinator.energy_yesterday
    cwu_kwh = energy["cwu"]
    floor_kwh = energy["floor"]
    total_kwh = energy["total"]

    if total_kwh < 0.1:
        coordinator._energy_tracker.last_daily_report_date = now
        return

    # Calculate costs
    cheap_rate = coordinator.get_tariff_cheap_rate()
    expensive_rate = coordinator.get_tariff_expensive_rate()

    cwu_cost = (energy["cwu_cheap"] * cheap_rate +
                energy["cwu_expensive"] * expensive_rate)
    floor_cost = (energy["floor_cheap"] * cheap_rate +
                  energy["floor_expensive"] * expensive_rate)
    total_cost = cwu_cost + floor_cost

    total_if_expensive = total_kwh * expensive_rate
    savings = total_if_expensive - total_cost

    message = (
        f"📊 Daily Energy Report (yesterday)\n\n"
        f"🚿 CWU: {cwu_kwh:.2f} kWh ({cwu_cost:.2f} zł)\n"
        f"   ├ Cheap: {energy['cwu_cheap']:.2f} kWh\n"
        f"   └ Expensive: {energy['cwu_expensive']:.2f} kWh\n\n"
        f"🏠 Floor: {floor_kwh:.2f} kWh ({floor_cost:.2f} zł)\n"
        f"   ├ Cheap: {energy['floor_cheap']:.2f} kWh\n"
        f"   └ Expensive: {energy['floor_expensive']:.2f} kWh\n\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📈 Total: {total_kwh:.2f} kWh ({total_cost:.2f} zł)\n"
        f"💰 Saved: {savings:.2f} zł vs expensive rate\n\n"
        f"💡 Mode: {coordinator._operating_mode.replace('_', ' ').title()}"
    )

    await async_send_notification(coordinator, "CWU Controller Daily Report", message)
    coordinator._energy_tracker.last_daily_report_date = now
    _LOGGER.info("Daily energy report sent: CWU %.2f kWh, Floor %.2f kWh, Cost %.2f zł",
                 cwu_kwh, floor_kwh, total_cost)
