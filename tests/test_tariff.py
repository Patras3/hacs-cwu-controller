"""Tests for G12w tariff calculations."""
from __future__ import annotations

from datetime import datetime
from unittest.mock import patch
import pytest

from custom_components.cwu_controller.const import (
    TARIFF_CHEAP_RATE,
    TARIFF_EXPENSIVE_RATE,
)


class TestIsCheapTariff:
    """Tests for is_cheap_tariff method."""

    def test_weekday_cheap_window_morning(self, mock_coordinator):
        """Test cheap tariff during 00:00-06:00 window on weekday."""
        # Monday 03:00 (Jan 13, 2025 is a regular Monday)
        dt = datetime(2025, 1, 13, 3, 0)
        assert mock_coordinator.is_cheap_tariff(dt) is True

    def test_weekday_cheap_window_afternoon(self, mock_coordinator):
        """Test cheap tariff during 13:00-15:00 window on weekday."""
        # Monday 14:00
        dt = datetime(2025, 1, 13, 14, 0)
        assert mock_coordinator.is_cheap_tariff(dt) is True

    def test_weekday_cheap_window_night(self, mock_coordinator):
        """Test cheap tariff during 22:00-24:00 window on weekday."""
        # Monday 23:00
        dt = datetime(2025, 1, 13, 23, 0)
        assert mock_coordinator.is_cheap_tariff(dt) is True

    def test_weekday_expensive_morning(self, mock_coordinator):
        """Test expensive tariff during morning on weekday."""
        # Monday 08:00
        dt = datetime(2025, 1, 13, 8, 0)
        assert mock_coordinator.is_cheap_tariff(dt) is False

    def test_weekday_expensive_afternoon(self, mock_coordinator):
        """Test expensive tariff during afternoon on weekday."""
        # Monday 16:00
        dt = datetime(2025, 1, 13, 16, 0)
        assert mock_coordinator.is_cheap_tariff(dt) is False

    def test_weekend_saturday_always_cheap(self, mock_coordinator):
        """Test that Saturday is always cheap tariff."""
        # Saturday 10:00 (normally expensive on weekday)
        dt = datetime(2025, 1, 4, 10, 0)  # Saturday
        assert mock_coordinator.is_cheap_tariff(dt) is True

    def test_weekend_sunday_always_cheap(self, mock_coordinator):
        """Test that Sunday is always cheap tariff."""
        # Sunday 18:00 (normally expensive on weekday)
        dt = datetime(2025, 1, 5, 18, 0)  # Sunday
        assert mock_coordinator.is_cheap_tariff(dt) is True

    def test_weekday_without_workday_sensor_not_holiday(self, mock_coordinator):
        """Test that without workday sensor, weekday at expensive time is expensive."""
        # Without workday sensor configured, holidays are not detected
        # New Year's Day at 10:00 (Wednesday - no workday sensor = expensive)
        dt = datetime(2025, 1, 1, 10, 0)
        # Without workday sensor, only weekends and time windows are checked
        assert mock_coordinator.is_cheap_tariff(dt) is False

    def test_weekday_cheap_window_regardless_of_date(self, mock_coordinator):
        """Test that cheap time window works regardless of specific date."""
        # Christmas Day at 14:00 (cheap window 13-15)
        dt = datetime(2025, 12, 25, 14, 0)
        assert mock_coordinator.is_cheap_tariff(dt) is True

    def test_boundary_start_of_cheap_window(self, mock_coordinator):
        """Test boundary at start of cheap window."""
        # Monday 13:00 exactly (Jan 13, 2025)
        dt = datetime(2025, 1, 13, 13, 0)
        assert mock_coordinator.is_cheap_tariff(dt) is True

    def test_boundary_end_of_cheap_window(self, mock_coordinator):
        """Test boundary at end of cheap window."""
        # Monday 15:00 exactly (end of 13-15 window)
        dt = datetime(2025, 1, 13, 15, 0)
        assert mock_coordinator.is_cheap_tariff(dt) is False

    def test_boundary_start_of_night_window(self, mock_coordinator):
        """Test boundary at start of night window."""
        # Monday 22:00 exactly
        dt = datetime(2025, 1, 13, 22, 0)
        assert mock_coordinator.is_cheap_tariff(dt) is True

    def test_boundary_end_of_morning_window(self, mock_coordinator):
        """Test boundary at end of morning window."""
        # Monday 06:00 exactly (end of 00-06 window)
        dt = datetime(2025, 1, 13, 6, 0)
        assert mock_coordinator.is_cheap_tariff(dt) is False


class TestGetCurrentTariffRate:
    """Tests for get_current_tariff_rate method."""

    def test_cheap_rate_during_cheap_window(self, mock_coordinator):
        """Test that cheap rate is returned during cheap tariff window."""
        dt = datetime(2025, 1, 13, 3, 0)  # Monday 03:00
        rate = mock_coordinator.get_current_tariff_rate(dt)
        assert rate == TARIFF_CHEAP_RATE
        assert rate == 0.72

    def test_expensive_rate_during_expensive_window(self, mock_coordinator):
        """Test that expensive rate is returned during expensive tariff window."""
        dt = datetime(2025, 1, 13, 10, 0)  # Monday 10:00
        rate = mock_coordinator.get_current_tariff_rate(dt)
        assert rate == TARIFF_EXPENSIVE_RATE
        assert rate == 1.16

    def test_cheap_rate_on_weekend(self, mock_coordinator):
        """Test that cheap rate is returned on weekend."""
        dt = datetime(2025, 1, 4, 10, 0)  # Saturday 10:00
        rate = mock_coordinator.get_current_tariff_rate(dt)
        assert rate == TARIFF_CHEAP_RATE

    def test_expensive_rate_on_holiday_without_sensor(self, mock_coordinator):
        """Test that without workday sensor, weekday holidays are expensive (outside time windows)."""
        # Without workday sensor, holidays are not detected
        dt = datetime(2025, 5, 1, 12, 0)  # Labour Day 12:00 (not in cheap window)
        rate = mock_coordinator.get_current_tariff_rate(dt)
        assert rate == TARIFF_EXPENSIVE_RATE


class TestWinterCWUHeatingWindow:
    """Tests for winter mode CWU heating window."""

    def test_morning_window_active(self, mock_coordinator):
        """Test that morning window (03:00-06:00) is detected."""
        dt = datetime(2025, 1, 13, 4, 0)
        assert mock_coordinator.is_winter_cwu_heating_window(dt) is True

    def test_afternoon_window_active(self, mock_coordinator):
        """Test that afternoon window (13:00-15:00) is detected."""
        dt = datetime(2025, 1, 13, 14, 0)
        assert mock_coordinator.is_winter_cwu_heating_window(dt) is True

    def test_outside_window_morning(self, mock_coordinator):
        """Test that time before morning window is outside."""
        dt = datetime(2025, 1, 13, 2, 0)
        assert mock_coordinator.is_winter_cwu_heating_window(dt) is False

    def test_outside_window_after_morning(self, mock_coordinator):
        """Test that time after morning window is outside."""
        dt = datetime(2025, 1, 13, 7, 0)
        assert mock_coordinator.is_winter_cwu_heating_window(dt) is False

    def test_outside_window_between(self, mock_coordinator):
        """Test that time between windows is outside."""
        dt = datetime(2025, 1, 13, 10, 0)
        assert mock_coordinator.is_winter_cwu_heating_window(dt) is False

    def test_boundary_start_morning(self, mock_coordinator):
        """Test boundary at start of morning window."""
        dt = datetime(2025, 1, 13, 3, 0)
        assert mock_coordinator.is_winter_cwu_heating_window(dt) is True

    def test_boundary_end_morning(self, mock_coordinator):
        """Test boundary at end of morning window."""
        dt = datetime(2025, 1, 13, 6, 0)
        assert mock_coordinator.is_winter_cwu_heating_window(dt) is False

    def test_evening_window_active(self, mock_coordinator):
        """Test that evening window (22:00-24:00) is detected."""
        dt = datetime(2025, 1, 13, 23, 0)
        assert mock_coordinator.is_winter_cwu_heating_window(dt) is True

    def test_boundary_start_evening(self, mock_coordinator):
        """Test boundary at start of evening window."""
        dt = datetime(2025, 1, 13, 22, 0)
        assert mock_coordinator.is_winter_cwu_heating_window(dt) is True

    def test_outside_window_before_evening(self, mock_coordinator):
        """Test that time before evening window is outside."""
        dt = datetime(2025, 1, 13, 21, 0)
        assert mock_coordinator.is_winter_cwu_heating_window(dt) is False

    def test_outside_window_after_afternoon_before_evening(self, mock_coordinator):
        """Test that time between afternoon and evening windows is outside."""
        dt = datetime(2025, 1, 13, 18, 0)
        assert mock_coordinator.is_winter_cwu_heating_window(dt) is False


class TestWinterCWUTargets:
    """Tests for winter mode CWU temperature targets."""

    def test_winter_cwu_target_default(self, mock_coordinator):
        """Test winter CWU target with default config."""
        # Default target is 45, winter adds 5, max 55
        target = mock_coordinator.get_winter_cwu_target()
        assert target == 50.0

    def test_winter_cwu_target_capped_at_max(self, mock_coordinator):
        """Test winter CWU target is capped at 55C."""
        mock_coordinator.config["cwu_target_temp"] = 52.0
        target = mock_coordinator.get_winter_cwu_target()
        assert target == 55.0  # Capped at max

    def test_winter_cwu_emergency_threshold(self, mock_coordinator):
        """Test winter CWU emergency threshold calculation."""
        # Target 50, emergency offset 10, so threshold = 40
        threshold = mock_coordinator.get_winter_cwu_emergency_threshold()
        assert threshold == 40.0

    def test_winter_cwu_emergency_with_high_target(self, mock_coordinator):
        """Test winter CWU emergency threshold with high target."""
        mock_coordinator.config["cwu_target_temp"] = 52.0
        # Target capped at 55, threshold = 55 - 10 = 45
        threshold = mock_coordinator.get_winter_cwu_emergency_threshold()
        assert threshold == 45.0


class TestWorkdaySensorIntegration:
    """Tests for workday sensor integration for holiday detection."""

    def test_workday_sensor_off_means_cheap_tariff(self, mock_coordinator, mock_hass):
        """Test that workday sensor 'off' (holiday/weekend) returns cheap tariff."""
        from unittest.mock import MagicMock
        from custom_components.cwu_controller.const import CONF_WORKDAY_SENSOR

        # Configure workday sensor
        mock_coordinator.config[CONF_WORKDAY_SENSOR] = "binary_sensor.workday_sensor"

        # Mock the sensor state as "off" (holiday/weekend)
        mock_state = MagicMock()
        mock_state.state = "off"
        mock_hass.states.get.return_value = mock_state

        # Weekday during expensive time should still be cheap because workday=off
        dt = datetime(2025, 1, 13, 10, 0)  # Monday 10:00 (normally expensive)
        result = mock_coordinator.is_cheap_tariff(dt)
        assert result is True

    def test_workday_sensor_on_checks_time_windows(self, mock_coordinator, mock_hass):
        """Test that workday sensor 'on' (workday) checks time windows."""
        from unittest.mock import MagicMock
        from custom_components.cwu_controller.const import CONF_WORKDAY_SENSOR

        # Configure workday sensor
        mock_coordinator.config[CONF_WORKDAY_SENSOR] = "binary_sensor.workday_sensor"

        # Mock the sensor state as "on" (workday)
        mock_state = MagicMock()
        mock_state.state = "on"
        mock_hass.states.get.return_value = mock_state

        # Weekday during expensive time with workday=on should be expensive
        dt = datetime(2025, 1, 13, 10, 0)  # Monday 10:00
        result = mock_coordinator.is_cheap_tariff(dt)
        assert result is False

        # But cheap window should still be cheap
        dt_cheap = datetime(2025, 1, 13, 14, 0)  # Monday 14:00 (cheap window)
        result_cheap = mock_coordinator.is_cheap_tariff(dt_cheap)
        assert result_cheap is True

    def test_workday_sensor_unavailable_fallback(self, mock_coordinator, mock_hass):
        """Test fallback to static logic when workday sensor unavailable."""
        from unittest.mock import MagicMock
        from custom_components.cwu_controller.const import CONF_WORKDAY_SENSOR

        # Configure workday sensor
        mock_coordinator.config[CONF_WORKDAY_SENSOR] = "binary_sensor.workday_sensor"

        # Mock the sensor state as unavailable
        mock_state = MagicMock()
        mock_state.state = "unavailable"
        mock_hass.states.get.return_value = mock_state

        # Should fallback to weekend check
        dt_weekend = datetime(2025, 1, 4, 10, 0)  # Saturday
        assert mock_coordinator.is_cheap_tariff(dt_weekend) is True

        # Weekday without time window should be expensive
        dt_weekday = datetime(2025, 1, 13, 10, 0)  # Monday 10:00
        assert mock_coordinator.is_cheap_tariff(dt_weekday) is False

    def test_no_workday_sensor_no_holiday_detection(self, mock_coordinator):
        """Test that without workday sensor, holidays are NOT detected (only weekends)."""
        # Ensure no workday sensor configured
        if "workday_sensor" in mock_coordinator.config:
            del mock_coordinator.config["workday_sensor"]

        # Jan 1 (New Year) at 10:00 - without workday sensor, this is expensive
        # because holidays require workday sensor for detection
        dt = datetime(2025, 1, 1, 10, 0)  # Wednesday 10:00
        assert mock_coordinator.is_cheap_tariff(dt) is False

        # But weekends still work
        dt_weekend = datetime(2025, 1, 4, 10, 0)  # Saturday
        assert mock_coordinator.is_cheap_tariff(dt_weekend) is True

    def test_workday_sensor_workday_uses_time_windows(self, mock_coordinator, mock_hass):
        """Test that with workday sensor returning 'on', time windows are used."""
        from unittest.mock import MagicMock
        from custom_components.cwu_controller.const import CONF_WORKDAY_SENSOR

        # Configure workday sensor
        mock_coordinator.config[CONF_WORKDAY_SENSOR] = "binary_sensor.workday_sensor"

        # Mock the sensor state as "on" (workday)
        mock_state = MagicMock()
        mock_state.state = "on"
        mock_hass.states.get.return_value = mock_state

        # On a workday at 10:00 (not a cheap window), should be expensive
        dt = datetime(2025, 1, 1, 10, 0)  # New Year at 10:00
        # Since sensor says workday=on, and 10:00 is not a cheap window, should be expensive
        result = mock_coordinator.is_cheap_tariff(dt)
        assert result is False
