"""Tests for CWU Controller coordinator."""
from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from custom_components.cwu_controller.const import (
    MODE_BROKEN_HEATER,
    MODE_WINTER,
    MODE_SUMMER,
    STATE_IDLE,
    STATE_HEATING_CWU,
    STATE_HEATING_FLOOR,
    STATE_PAUSE,
    STATE_EMERGENCY_CWU,
    STATE_EMERGENCY_FLOOR,
    URGENCY_NONE,
    URGENCY_LOW,
    URGENCY_MEDIUM,
    URGENCY_HIGH,
    URGENCY_CRITICAL,
    DEFAULT_CWU_TARGET_TEMP,
    DEFAULT_CWU_MIN_TEMP,
    DEFAULT_CWU_CRITICAL_TEMP,
    DEFAULT_SALON_TARGET_TEMP,
    DEFAULT_SALON_MIN_TEMP,
    DEFAULT_BEDROOM_MIN_TEMP,
)


class TestOperatingModes:
    """Tests for operating mode management."""

    @pytest.mark.asyncio
    async def test_set_operating_mode_winter(self, mock_coordinator):
        """Test setting operating mode to winter."""
        mock_coordinator._log_action = MagicMock()
        mock_coordinator._change_state = MagicMock()

        await mock_coordinator.async_set_operating_mode(MODE_WINTER)

        assert mock_coordinator._operating_mode == MODE_WINTER
        mock_coordinator._log_action.assert_called()
        mock_coordinator._change_state.assert_called_with(STATE_IDLE)

    @pytest.mark.asyncio
    async def test_set_operating_mode_broken_heater(self, mock_coordinator):
        """Test setting operating mode to broken heater."""
        mock_coordinator._log_action = MagicMock()
        mock_coordinator._change_state = MagicMock()
        mock_coordinator._operating_mode = MODE_WINTER

        await mock_coordinator.async_set_operating_mode(MODE_BROKEN_HEATER)

        assert mock_coordinator._operating_mode == MODE_BROKEN_HEATER

    @pytest.mark.asyncio
    async def test_set_invalid_mode_ignored(self, mock_coordinator):
        """Test that invalid mode is ignored."""
        mock_coordinator._log_action = MagicMock()
        mock_coordinator._operating_mode = MODE_BROKEN_HEATER

        await mock_coordinator.async_set_operating_mode("invalid_mode")

        assert mock_coordinator._operating_mode == MODE_BROKEN_HEATER
        mock_coordinator._log_action.assert_not_called()

    def test_operating_mode_property(self, mock_coordinator):
        """Test operating_mode property returns current mode."""
        mock_coordinator._operating_mode = MODE_WINTER
        assert mock_coordinator.operating_mode == MODE_WINTER


class TestCWUUrgencyCalculation:
    """Tests for CWU urgency calculation."""

    def test_urgency_none_above_target(self, mock_coordinator):
        """Test urgency none when above target temperature."""
        # Target is 45, temp is 50
        urgency = mock_coordinator._calculate_cwu_urgency(50.0, 10)
        assert urgency == URGENCY_NONE

    def test_urgency_critical_below_critical_evening(self, mock_coordinator):
        """Test critical urgency when below critical temp in evening."""
        # Critical is 35, temp is 30, hour is 20 (bath time)
        urgency = mock_coordinator._calculate_cwu_urgency(30.0, 20)
        assert urgency == URGENCY_CRITICAL

    def test_urgency_high_below_min_evening(self, mock_coordinator):
        """Test high urgency when below min temp in evening."""
        # Min is 40, temp is 38, hour is 20
        urgency = mock_coordinator._calculate_cwu_urgency(38.0, 20)
        assert urgency == URGENCY_HIGH

    def test_urgency_medium_below_target_evening(self, mock_coordinator):
        """Test medium urgency when below target in evening."""
        # Target is 45, temp is 42, hour is 20
        urgency = mock_coordinator._calculate_cwu_urgency(42.0, 20)
        assert urgency == URGENCY_MEDIUM

    def test_urgency_low_afternoon_prep(self, mock_coordinator):
        """Test low urgency during afternoon preparation."""
        # Hour 16 (after EVENING_PREP_HOUR=15), temp is 42
        urgency = mock_coordinator._calculate_cwu_urgency(42.0, 16)
        assert urgency == URGENCY_LOW

    def test_urgency_medium_morning_critical(self, mock_coordinator):
        """Test medium urgency in morning when below critical."""
        # Morning (hour 8), below critical 35
        urgency = mock_coordinator._calculate_cwu_urgency(32.0, 8)
        assert urgency == URGENCY_MEDIUM

    def test_urgency_with_none_temp(self, mock_coordinator):
        """Test urgency calculation with None temperature."""
        # Should return medium urgency when sensor unavailable
        urgency = mock_coordinator._calculate_cwu_urgency(None, 12)
        assert urgency == URGENCY_MEDIUM


class TestFloorUrgencyCalculation:
    """Tests for floor heating urgency calculation."""

    def test_urgency_none_above_target(self, mock_coordinator):
        """Test urgency none when salon above target."""
        # Target is 22, temp is 23
        urgency = mock_coordinator._calculate_floor_urgency(23.0, 20.0, 20.0)
        assert urgency == URGENCY_NONE

    def test_urgency_critical_bedroom_cold(self, mock_coordinator):
        """Test critical urgency when bedroom too cold."""
        # Bedroom min is 19, temp is 17
        urgency = mock_coordinator._calculate_floor_urgency(22.0, 17.0, 20.0)
        assert urgency == URGENCY_CRITICAL

    def test_urgency_critical_kids_room_cold(self, mock_coordinator):
        """Test critical urgency when kids room too cold."""
        # Kids room temp is 17
        urgency = mock_coordinator._calculate_floor_urgency(22.0, 20.0, 17.0)
        assert urgency == URGENCY_CRITICAL

    def test_urgency_critical_salon_very_cold(self, mock_coordinator):
        """Test critical urgency when salon very cold."""
        # Salon min is 21, temp is 18 (below 19)
        urgency = mock_coordinator._calculate_floor_urgency(18.0, 20.0, 20.0)
        assert urgency == URGENCY_CRITICAL

    def test_urgency_high_salon_cold(self, mock_coordinator):
        """Test high urgency when salon below min."""
        # Salon min is 21, temp is 20
        urgency = mock_coordinator._calculate_floor_urgency(20.0, 20.0, 20.0)
        assert urgency == URGENCY_HIGH

    def test_urgency_medium_below_target(self, mock_coordinator):
        """Test medium urgency when salon below target."""
        # Salon target is 22, temp is 21.5
        urgency = mock_coordinator._calculate_floor_urgency(21.5, 20.0, 20.0)
        assert urgency == URGENCY_MEDIUM

    def test_urgency_low_near_target(self, mock_coordinator):
        """Test low urgency when salon near target."""
        # Salon target is 22, temp is 22.3
        urgency = mock_coordinator._calculate_floor_urgency(22.3, 20.0, 20.0)
        assert urgency == URGENCY_LOW

    def test_urgency_with_none_salon(self, mock_coordinator):
        """Test urgency calculation with None salon temperature."""
        urgency = mock_coordinator._calculate_floor_urgency(None, 20.0, 20.0)
        assert urgency == URGENCY_MEDIUM


class TestEnergyTracking:
    """Tests for energy consumption tracking with tariff separation."""

    def test_energy_today_property(self, mock_coordinator):
        """Test energy_today property returns correct values with tariff split."""
        mock_coordinator._energy_cwu_cheap_today = 1000.0  # Wh
        mock_coordinator._energy_cwu_expensive_today = 500.0  # Wh
        mock_coordinator._energy_floor_cheap_today = 2000.0  # Wh
        mock_coordinator._energy_floor_expensive_today = 500.0  # Wh

        energy = mock_coordinator.energy_today
        assert energy["cwu"] == 1.5  # kWh (1000 + 500 Wh)
        assert energy["cwu_cheap"] == 1.0  # kWh
        assert energy["cwu_expensive"] == 0.5  # kWh
        assert energy["floor"] == 2.5  # kWh (2000 + 500 Wh)
        assert energy["floor_cheap"] == 2.0  # kWh
        assert energy["floor_expensive"] == 0.5  # kWh
        assert energy["total"] == 4.0  # kWh
        assert energy["total_cheap"] == 3.0  # kWh
        assert energy["total_expensive"] == 1.0  # kWh

    def test_energy_yesterday_property(self, mock_coordinator):
        """Test energy_yesterday property returns correct values with tariff split."""
        mock_coordinator._energy_cwu_cheap_yesterday = 2000.0  # Wh
        mock_coordinator._energy_cwu_expensive_yesterday = 1000.0  # Wh
        mock_coordinator._energy_floor_cheap_yesterday = 4000.0  # Wh
        mock_coordinator._energy_floor_expensive_yesterday = 1000.0  # Wh

        energy = mock_coordinator.energy_yesterday
        assert energy["cwu"] == 3.0  # kWh
        assert energy["cwu_cheap"] == 2.0  # kWh
        assert energy["cwu_expensive"] == 1.0  # kWh
        assert energy["floor"] == 5.0  # kWh
        assert energy["floor_cheap"] == 4.0  # kWh
        assert energy["floor_expensive"] == 1.0  # kWh
        assert energy["total"] == 8.0  # kWh

    def test_energy_tracking_cwu_state(self, mock_coordinator):
        """Test energy tracking attributes to CWU during CWU heating."""
        mock_coordinator._current_state = STATE_HEATING_CWU
        mock_coordinator._last_energy_update = datetime.now() - timedelta(minutes=10)
        mock_coordinator._last_power_for_energy = 1000.0

        mock_coordinator._update_energy_tracking(1000.0)

        # 1000W for ~10 minutes = ~166 Wh
        cwu_total = mock_coordinator._energy_cwu_cheap_today + mock_coordinator._energy_cwu_expensive_today
        floor_total = mock_coordinator._energy_floor_cheap_today + mock_coordinator._energy_floor_expensive_today
        assert cwu_total > 0
        assert floor_total == 0

    def test_energy_tracking_floor_state(self, mock_coordinator):
        """Test energy tracking attributes to floor during floor heating."""
        mock_coordinator._current_state = STATE_HEATING_FLOOR
        mock_coordinator._last_energy_update = datetime.now() - timedelta(minutes=10)
        mock_coordinator._last_power_for_energy = 1000.0

        mock_coordinator._update_energy_tracking(1000.0)

        # Energy should go to floor
        cwu_total = mock_coordinator._energy_cwu_cheap_today + mock_coordinator._energy_cwu_expensive_today
        floor_total = mock_coordinator._energy_floor_cheap_today + mock_coordinator._energy_floor_expensive_today
        assert cwu_total == 0
        assert floor_total > 0

    def test_energy_tracking_day_rollover(self, mock_coordinator):
        """Test energy tracking day rollover moves data to yesterday."""
        mock_coordinator._energy_cwu_cheap_today = 3000.0
        mock_coordinator._energy_cwu_expensive_today = 2000.0
        mock_coordinator._energy_floor_cheap_today = 2000.0
        mock_coordinator._energy_floor_expensive_today = 1000.0
        mock_coordinator._last_energy_update = datetime.now() - timedelta(days=1)
        mock_coordinator._current_state = STATE_IDLE

        mock_coordinator._update_energy_tracking(100.0)

        # Yesterday should have previous today's values
        assert mock_coordinator._energy_cwu_cheap_yesterday == 3000.0
        assert mock_coordinator._energy_cwu_expensive_yesterday == 2000.0
        assert mock_coordinator._energy_floor_cheap_yesterday == 2000.0
        assert mock_coordinator._energy_floor_expensive_yesterday == 1000.0
        # Today should be reset
        assert mock_coordinator._energy_cwu_cheap_today == 0.0
        assert mock_coordinator._energy_cwu_expensive_today == 0.0
        assert mock_coordinator._energy_floor_cheap_today == 0.0
        assert mock_coordinator._energy_floor_expensive_today == 0.0

    def test_energy_tracking_cheap_tariff(self, mock_coordinator):
        """Test energy goes to cheap bucket during cheap tariff."""
        from unittest.mock import patch

        mock_coordinator._current_state = STATE_HEATING_CWU
        mock_coordinator._last_energy_update = datetime.now() - timedelta(minutes=10)
        mock_coordinator._last_power_for_energy = 1000.0

        with patch.object(mock_coordinator, 'is_cheap_tariff', return_value=True):
            mock_coordinator._update_energy_tracking(1000.0)

        assert mock_coordinator._energy_cwu_cheap_today > 0
        assert mock_coordinator._energy_cwu_expensive_today == 0

    def test_energy_tracking_expensive_tariff(self, mock_coordinator):
        """Test energy goes to expensive bucket during expensive tariff."""
        from unittest.mock import patch

        mock_coordinator._current_state = STATE_HEATING_CWU
        mock_coordinator._last_energy_update = datetime.now() - timedelta(minutes=10)
        mock_coordinator._last_power_for_energy = 1000.0

        with patch.object(mock_coordinator, 'is_cheap_tariff', return_value=False):
            mock_coordinator._update_energy_tracking(1000.0)

        assert mock_coordinator._energy_cwu_cheap_today == 0
        assert mock_coordinator._energy_cwu_expensive_today > 0


class TestStateManagement:
    """Tests for controller state management."""

    def test_current_state_property(self, mock_coordinator):
        """Test current_state property returns state."""
        mock_coordinator._current_state = STATE_HEATING_CWU
        assert mock_coordinator.current_state == STATE_HEATING_CWU

    def test_is_enabled_property(self, mock_coordinator):
        """Test is_enabled property returns enabled state."""
        mock_coordinator._enabled = True
        assert mock_coordinator.is_enabled is True

        mock_coordinator._enabled = False
        assert mock_coordinator.is_enabled is False

    def test_change_state(self, mock_coordinator):
        """Test _change_state updates state and history."""
        mock_coordinator._current_state = STATE_IDLE
        mock_coordinator._change_state(STATE_HEATING_CWU)

        assert mock_coordinator._current_state == STATE_HEATING_CWU
        assert mock_coordinator._previous_state == STATE_IDLE
        assert len(mock_coordinator._state_history) == 1
        assert mock_coordinator._state_history[0]["from_state"] == STATE_IDLE
        assert mock_coordinator._state_history[0]["to_state"] == STATE_HEATING_CWU

    def test_change_state_same_state_no_op(self, mock_coordinator):
        """Test _change_state does nothing when state unchanged."""
        mock_coordinator._current_state = STATE_IDLE
        mock_coordinator._state_history = []

        mock_coordinator._change_state(STATE_IDLE)

        assert len(mock_coordinator._state_history) == 0


class TestFakeHeatingDetection:
    """Tests for fake heating detection (broken heater mode)."""

    def test_no_fake_heating_high_power(self, mock_coordinator):
        """Test no fake heating detected when power is high."""
        result = mock_coordinator._detect_fake_heating(500.0, "heat_pump")
        assert result is False

    def test_no_fake_heating_wrong_mode(self, mock_coordinator):
        """Test no fake heating detected when water heater is off."""
        mock_coordinator._low_power_start = datetime.now() - timedelta(minutes=10)
        result = mock_coordinator._detect_fake_heating(5.0, "off")
        assert result is False

    def test_fake_heating_detected_after_timeout(self, mock_coordinator):
        """Test fake heating detected after timeout with low power."""
        mock_coordinator._low_power_start = datetime.now() - timedelta(minutes=10)
        result = mock_coordinator._detect_fake_heating(5.0, "heat_pump")
        assert result is True

    def test_fake_heating_not_detected_short_duration(self, mock_coordinator):
        """Test fake heating not detected before timeout."""
        mock_coordinator._low_power_start = datetime.now() - timedelta(minutes=2)
        result = mock_coordinator._detect_fake_heating(5.0, "heat_pump")
        assert result is False


class TestCWUCycleManagement:
    """Tests for CWU heating cycle management."""

    def test_should_restart_no_start_time(self, mock_coordinator):
        """Test no restart needed when no heating started."""
        mock_coordinator._cwu_heating_start = None
        assert mock_coordinator._should_restart_cwu_cycle() is False

    def test_should_restart_after_limit(self, mock_coordinator):
        """Test restart needed after time limit."""
        # CWU_MAX_HEATING_TIME is 170 minutes
        mock_coordinator._cwu_heating_start = datetime.now() - timedelta(minutes=180)
        assert mock_coordinator._should_restart_cwu_cycle() is True

    def test_should_not_restart_within_limit(self, mock_coordinator):
        """Test no restart needed within time limit."""
        mock_coordinator._cwu_heating_start = datetime.now() - timedelta(minutes=60)
        assert mock_coordinator._should_restart_cwu_cycle() is False

    def test_pause_not_complete(self, mock_coordinator):
        """Test pause is not complete during pause period."""
        mock_coordinator._pause_start = datetime.now() - timedelta(minutes=5)
        assert mock_coordinator._is_pause_complete() is False

    def test_pause_complete_after_time(self, mock_coordinator):
        """Test pause is complete after pause time."""
        # CWU_PAUSE_TIME is 10 minutes
        mock_coordinator._pause_start = datetime.now() - timedelta(minutes=15)
        assert mock_coordinator._is_pause_complete() is True

    def test_pause_complete_no_start(self, mock_coordinator):
        """Test pause is complete when no pause started."""
        mock_coordinator._pause_start = None
        assert mock_coordinator._is_pause_complete() is True


class TestWinterModeNoProgress:
    """Tests for winter mode CWU no-progress safety check."""

    def test_no_progress_check_no_heating_start(self, mock_coordinator):
        """Test no progress check returns False when no heating started."""
        mock_coordinator._cwu_heating_start = None
        assert mock_coordinator._check_winter_cwu_no_progress(40.0) is False

    def test_no_progress_check_no_session_start_temp(self, mock_coordinator):
        """Test no progress check returns False when no session start temp."""
        mock_coordinator._cwu_heating_start = datetime.now() - timedelta(hours=4)
        mock_coordinator._cwu_session_start_temp = None
        assert mock_coordinator._check_winter_cwu_no_progress(40.0) is False

    def test_no_progress_check_none_current_temp(self, mock_coordinator):
        """Test no progress check returns False when current temp is None."""
        mock_coordinator._cwu_heating_start = datetime.now() - timedelta(hours=4)
        mock_coordinator._cwu_session_start_temp = 38.0
        assert mock_coordinator._check_winter_cwu_no_progress(None) is False

    def test_no_progress_check_within_timeout(self, mock_coordinator):
        """Test no progress check returns False within timeout period."""
        mock_coordinator._cwu_heating_start = datetime.now() - timedelta(hours=2)
        mock_coordinator._cwu_session_start_temp = 38.0
        # Even with no temp increase, should return False (not enough time)
        assert mock_coordinator._check_winter_cwu_no_progress(38.0) is False

    def test_no_progress_detected_temp_decreased(self, mock_coordinator):
        """Test no progress detected when temp decreased after timeout."""
        mock_coordinator._cwu_heating_start = datetime.now() - timedelta(hours=4)
        mock_coordinator._cwu_session_start_temp = 40.0
        # Temp went down
        assert mock_coordinator._check_winter_cwu_no_progress(38.0) is True

    def test_no_progress_detected_temp_same(self, mock_coordinator):
        """Test no progress detected when temp unchanged after timeout."""
        mock_coordinator._cwu_heating_start = datetime.now() - timedelta(hours=4)
        mock_coordinator._cwu_session_start_temp = 40.0
        # Temp same
        assert mock_coordinator._check_winter_cwu_no_progress(40.0) is True

    def test_no_progress_detected_minimal_increase(self, mock_coordinator):
        """Test no progress detected when temp increase is below threshold."""
        mock_coordinator._cwu_heating_start = datetime.now() - timedelta(hours=4)
        mock_coordinator._cwu_session_start_temp = 40.0
        # Temp increased by 0.5, but threshold is 1.0
        assert mock_coordinator._check_winter_cwu_no_progress(40.5) is True

    def test_progress_ok_above_threshold(self, mock_coordinator):
        """Test progress OK when temp increased above threshold."""
        mock_coordinator._cwu_heating_start = datetime.now() - timedelta(hours=4)
        mock_coordinator._cwu_session_start_temp = 40.0
        # Temp increased by 2.0, threshold is 1.0
        assert mock_coordinator._check_winter_cwu_no_progress(42.0) is False

    def test_progress_ok_exactly_threshold(self, mock_coordinator):
        """Test progress OK when temp increased exactly at threshold."""
        mock_coordinator._cwu_heating_start = datetime.now() - timedelta(hours=4)
        mock_coordinator._cwu_session_start_temp = 40.0
        # Temp increased by exactly 1.0
        assert mock_coordinator._check_winter_cwu_no_progress(41.0) is False
