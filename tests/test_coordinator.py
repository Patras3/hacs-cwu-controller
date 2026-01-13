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
    STATE_FAKE_HEATING_DETECTED,
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
    MIN_CWU_HEATING_TIME,
    MIN_FLOOR_HEATING_TIME,
    CWU_RAPID_DROP_THRESHOLD,
    CWU_RAPID_DROP_WINDOW,
    MAX_TEMP_ACCEPTABLE_DROP,
    MAX_TEMP_CRITICAL_THRESHOLD,
    HP_STATUS_DEFROSTING,
    HP_STATUS_OVERRUN,
    BSB_HP_OFF_TIME_ACTIVE,
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
    """Tests for energy consumption tracking with meter delta and tariff separation."""

    def test_energy_today_property(self, mock_coordinator):
        """Test energy_today property returns correct values in kWh."""
        mock_coordinator._energy_tracker._cwu_cheap_today = 1.0  # kWh
        mock_coordinator._energy_tracker._cwu_expensive_today = 0.5  # kWh
        mock_coordinator._energy_tracker._floor_cheap_today = 2.0  # kWh
        mock_coordinator._energy_tracker._floor_expensive_today = 0.5  # kWh

        energy = mock_coordinator.energy_today
        assert energy["cwu"] == 1.5  # kWh
        assert energy["cwu_cheap"] == 1.0  # kWh
        assert energy["cwu_expensive"] == 0.5  # kWh
        assert energy["floor"] == 2.5  # kWh
        assert energy["floor_cheap"] == 2.0  # kWh
        assert energy["floor_expensive"] == 0.5  # kWh
        assert energy["total"] == 4.0  # kWh
        assert energy["total_cheap"] == 3.0  # kWh
        assert energy["total_expensive"] == 1.0  # kWh

    def test_energy_yesterday_property(self, mock_coordinator):
        """Test energy_yesterday property returns correct values in kWh."""
        mock_coordinator._energy_tracker._cwu_cheap_yesterday = 2.0  # kWh
        mock_coordinator._energy_tracker._cwu_expensive_yesterday = 1.0  # kWh
        mock_coordinator._energy_tracker._floor_cheap_yesterday = 4.0  # kWh
        mock_coordinator._energy_tracker._floor_expensive_yesterday = 1.0  # kWh

        energy = mock_coordinator.energy_yesterday
        assert energy["cwu"] == 3.0  # kWh
        assert energy["cwu_cheap"] == 2.0  # kWh
        assert energy["cwu_expensive"] == 1.0  # kWh
        assert energy["floor"] == 5.0  # kWh
        assert energy["floor_cheap"] == 4.0  # kWh
        assert energy["floor_expensive"] == 1.0  # kWh
        assert energy["total"] == 8.0  # kWh

    def test_energy_tracking_initialization(self, mock_coordinator):
        """Test first energy meter reading initializes tracking."""
        mock_coordinator._energy_tracker._data_loaded = True  # Enable energy tracking
        mock_coordinator._energy_tracker._last_meter_reading = None
        mock_coordinator._energy_tracker._meter_tracking_date = datetime.now()

        with patch.object(mock_coordinator, '_get_energy_meter_value', return_value=100.0):
            with patch.object(mock_coordinator, 'is_cheap_tariff', return_value=True):
                with patch.object(mock_coordinator, '_get_heater_states', return_value=(False, False, False)):
                    with patch.object(mock_coordinator, '_get_compressor_target', return_value='idle'):
                        mock_coordinator._energy_tracker.update()

        # First reading should just initialize
        assert mock_coordinator._energy_tracker._last_meter_reading == 100.0
        # No energy should be attributed on first reading
        assert mock_coordinator._energy_tracker._cwu_cheap_today == 0.0

    def test_energy_tracking_cwu_state(self, mock_coordinator):
        """Test energy tracking attributes to CWU when compressor targets CWU."""
        mock_coordinator._energy_tracker._data_loaded = True  # Enable energy tracking
        mock_coordinator._energy_tracker._last_meter_reading = 100.0
        mock_coordinator._energy_tracker._last_meter_time = datetime.now() - timedelta(minutes=10)
        mock_coordinator._energy_tracker._meter_tracking_date = datetime.now()

        # Meter increased by 0.5 kWh, compressor targeting CWU, no heaters
        with patch.object(mock_coordinator, '_get_energy_meter_value', return_value=100.5):
            with patch.object(mock_coordinator, 'is_cheap_tariff', return_value=True):
                with patch.object(mock_coordinator, '_get_heater_states', return_value=(False, False, False)):
                    with patch.object(mock_coordinator, '_get_compressor_target', return_value='cwu'):
                        mock_coordinator._energy_tracker.update()

        # 0.5 kWh should go to CWU (compressor target)
        assert mock_coordinator._energy_tracker._cwu_cheap_today == pytest.approx(0.5)
        assert mock_coordinator._energy_tracker._cwu_expensive_today == 0.0
        assert mock_coordinator._energy_tracker._floor_cheap_today == 0.0
        assert mock_coordinator._energy_tracker._floor_expensive_today == 0.0

    def test_energy_tracking_floor_state(self, mock_coordinator):
        """Test energy tracking attributes to floor when compressor targets floor."""
        mock_coordinator._energy_tracker._data_loaded = True  # Enable energy tracking
        mock_coordinator._energy_tracker._last_meter_reading = 100.0
        mock_coordinator._energy_tracker._last_meter_time = datetime.now() - timedelta(minutes=10)
        mock_coordinator._energy_tracker._meter_tracking_date = datetime.now()

        # Meter increased by 0.3 kWh, compressor targeting floor, no heaters
        with patch.object(mock_coordinator, '_get_energy_meter_value', return_value=100.3):
            with patch.object(mock_coordinator, 'is_cheap_tariff', return_value=True):
                with patch.object(mock_coordinator, '_get_heater_states', return_value=(False, False, False)):
                    with patch.object(mock_coordinator, '_get_compressor_target', return_value='floor'):
                        mock_coordinator._energy_tracker.update()

        # 0.3 kWh should go to Floor (compressor target)
        assert mock_coordinator._energy_tracker._cwu_cheap_today == 0.0
        assert mock_coordinator._energy_tracker._floor_cheap_today == pytest.approx(0.3)

    def test_energy_tracking_day_rollover(self, mock_coordinator):
        """Test energy tracking day rollover moves data to yesterday."""
        mock_coordinator._energy_tracker._data_loaded = True  # Enable energy tracking
        mock_coordinator._energy_tracker._cwu_cheap_today = 3.0  # kWh
        mock_coordinator._energy_tracker._cwu_expensive_today = 2.0
        mock_coordinator._energy_tracker._floor_cheap_today = 2.0
        mock_coordinator._energy_tracker._floor_expensive_today = 1.0
        mock_coordinator._energy_tracker._meter_tracking_date = datetime.now() - timedelta(days=1)
        mock_coordinator._energy_tracker._last_meter_reading = 100.0

        with patch.object(mock_coordinator, '_get_energy_meter_value', return_value=100.0):
            with patch.object(mock_coordinator, 'is_cheap_tariff', return_value=True):
                with patch.object(mock_coordinator, '_get_heater_states', return_value=(False, False, False)):
                    with patch.object(mock_coordinator, '_get_compressor_target', return_value='idle'):
                        mock_coordinator._energy_tracker.update()

        # Yesterday should have previous today's values
        assert mock_coordinator._energy_tracker._cwu_cheap_yesterday == 3.0
        assert mock_coordinator._energy_tracker._cwu_expensive_yesterday == 2.0
        assert mock_coordinator._energy_tracker._floor_cheap_yesterday == 2.0
        assert mock_coordinator._energy_tracker._floor_expensive_yesterday == 1.0
        # Today should be reset
        assert mock_coordinator._energy_tracker._cwu_cheap_today == 0.0
        assert mock_coordinator._energy_tracker._cwu_expensive_today == 0.0
        assert mock_coordinator._energy_tracker._floor_cheap_today == 0.0
        assert mock_coordinator._energy_tracker._floor_expensive_today == 0.0

    def test_energy_tracking_cheap_tariff(self, mock_coordinator):
        """Test energy goes to cheap bucket during cheap tariff."""
        mock_coordinator._energy_tracker._data_loaded = True  # Enable energy tracking
        mock_coordinator._energy_tracker._last_meter_reading = 100.0
        mock_coordinator._energy_tracker._last_meter_time = datetime.now() - timedelta(minutes=10)
        mock_coordinator._energy_tracker._meter_tracking_date = datetime.now()

        with patch.object(mock_coordinator, '_get_energy_meter_value', return_value=100.5):
            with patch.object(mock_coordinator, 'is_cheap_tariff', return_value=True):
                with patch.object(mock_coordinator, '_get_heater_states', return_value=(False, False, False)):
                    with patch.object(mock_coordinator, '_get_compressor_target', return_value='cwu'):
                        mock_coordinator._energy_tracker.update()

        assert mock_coordinator._energy_tracker._cwu_cheap_today == pytest.approx(0.5)
        assert mock_coordinator._energy_tracker._cwu_expensive_today == 0.0

    def test_energy_tracking_expensive_tariff(self, mock_coordinator):
        """Test energy goes to expensive bucket during expensive tariff."""
        mock_coordinator._energy_tracker._data_loaded = True  # Enable energy tracking
        mock_coordinator._energy_tracker._last_meter_reading = 100.0
        mock_coordinator._energy_tracker._last_meter_time = datetime.now() - timedelta(minutes=10)
        mock_coordinator._energy_tracker._meter_tracking_date = datetime.now()

        with patch.object(mock_coordinator, '_get_energy_meter_value', return_value=100.5):
            with patch.object(mock_coordinator, 'is_cheap_tariff', return_value=False):
                with patch.object(mock_coordinator, '_get_heater_states', return_value=(False, False, False)):
                    with patch.object(mock_coordinator, '_get_compressor_target', return_value='cwu'):
                        mock_coordinator._energy_tracker.update()

        assert mock_coordinator._energy_tracker._cwu_cheap_today == 0.0
        assert mock_coordinator._energy_tracker._cwu_expensive_today == pytest.approx(0.5)

    def test_energy_tracking_cwu_heater(self, mock_coordinator):
        """Test CWU heater energy is attributed to CWU (known power: 3.3kW)."""
        mock_coordinator._energy_tracker._data_loaded = True  # Enable energy tracking
        mock_coordinator._energy_tracker._last_meter_reading = 100.0
        mock_coordinator._energy_tracker._last_meter_time = datetime.now() - timedelta(seconds=60)
        mock_coordinator._energy_tracker._meter_tracking_date = datetime.now()

        # CWU heater ON, compressor idle, meter shows some consumption
        # 0.1 kWh in 60 seconds = 6kW average power
        with patch.object(mock_coordinator, '_get_energy_meter_value', return_value=100.1):
            with patch.object(mock_coordinator, 'is_cheap_tariff', return_value=True):
                with patch.object(mock_coordinator, '_get_heater_states', return_value=(True, False, False)):
                    with patch.object(mock_coordinator, '_get_compressor_target', return_value='idle'):
                        mock_coordinator._energy_tracker.update()

        # CWU heater should add 3.3kW * (60s/3600s) = 0.055 kWh to CWU
        # Remaining: 0.1 - 0.055 = 0.045 kWh → split 50/50 (idle)
        # CWU total: 0.055 + 0.0225 = 0.0775 kWh
        assert mock_coordinator._energy_tracker._cwu_cheap_today == pytest.approx(0.0775, abs=0.001)
        # Floor: 0.0225 kWh (idle half)
        assert mock_coordinator._energy_tracker._floor_cheap_today == pytest.approx(0.0225, abs=0.001)

    def test_energy_tracking_floor_heaters(self, mock_coordinator):
        """Test floor heaters energy is attributed to floor (known power: 3.0kW each)."""
        mock_coordinator._energy_tracker._data_loaded = True  # Enable energy tracking
        mock_coordinator._energy_tracker._last_meter_reading = 100.0
        mock_coordinator._energy_tracker._last_meter_time = datetime.now() - timedelta(seconds=60)
        mock_coordinator._energy_tracker._meter_tracking_date = datetime.now()

        # Both floor heaters ON, compressor idle
        # 0.2 kWh in 60 seconds = 12kW average power
        with patch.object(mock_coordinator, '_get_energy_meter_value', return_value=100.2):
            with patch.object(mock_coordinator, 'is_cheap_tariff', return_value=True):
                with patch.object(mock_coordinator, '_get_heater_states', return_value=(False, True, True)):
                    with patch.object(mock_coordinator, '_get_compressor_target', return_value='idle'):
                        mock_coordinator._energy_tracker.update()

        # Floor heaters: (3.0 + 3.0) * (60/3600) = 0.1 kWh
        # Remaining 0.1 kWh → 50/50 split (idle)
        # CWU: 0.05 kWh, Floor: 0.1 + 0.05 = 0.15 kWh
        assert mock_coordinator._energy_tracker._cwu_cheap_today == pytest.approx(0.05, abs=0.001)
        assert mock_coordinator._energy_tracker._floor_cheap_today == pytest.approx(0.15, abs=0.001)

    def test_energy_tracking_idle_splits_50_50(self, mock_coordinator):
        """Test idle/standby energy is split 50/50 between CWU and floor."""
        mock_coordinator._energy_tracker._data_loaded = True  # Enable energy tracking
        mock_coordinator._energy_tracker._last_meter_reading = 100.0
        mock_coordinator._energy_tracker._last_meter_time = datetime.now() - timedelta(minutes=10)
        mock_coordinator._energy_tracker._meter_tracking_date = datetime.now()

        # No heaters, compressor idle, small power consumption
        with patch.object(mock_coordinator, '_get_energy_meter_value', return_value=100.1):
            with patch.object(mock_coordinator, 'is_cheap_tariff', return_value=True):
                with patch.object(mock_coordinator, '_get_heater_states', return_value=(False, False, False)):
                    with patch.object(mock_coordinator, '_get_compressor_target', return_value='idle'):
                        mock_coordinator._energy_tracker.update()

        # Idle energy split 50/50 (0.1 kWh / 2 = 0.05 kWh each)
        assert mock_coordinator._energy_tracker._cwu_cheap_today == pytest.approx(0.05)
        assert mock_coordinator._energy_tracker._floor_cheap_today == pytest.approx(0.05)

    def test_energy_tracking_meter_backwards(self, mock_coordinator):
        """Test handling of meter going backwards (reset/error)."""
        mock_coordinator._energy_tracker._data_loaded = True  # Enable energy tracking
        mock_coordinator._energy_tracker._last_meter_reading = 100.0
        mock_coordinator._energy_tracker._last_meter_time = datetime.now() - timedelta(minutes=10)
        mock_coordinator._energy_tracker._meter_tracking_date = datetime.now()

        # Meter went backwards
        with patch.object(mock_coordinator, '_get_energy_meter_value', return_value=50.0):
            with patch.object(mock_coordinator, 'is_cheap_tariff', return_value=True):
                mock_coordinator._energy_tracker.update()

        # No energy attributed, tracking reset
        assert mock_coordinator._energy_tracker._cwu_cheap_today == 0.0
        assert mock_coordinator._energy_tracker._last_meter_reading == 50.0

    def test_energy_tracking_large_delta_skipped(self, mock_coordinator):
        """Test unusually large delta is skipped (anomaly detection)."""
        mock_coordinator._energy_tracker._data_loaded = True  # Enable energy tracking
        mock_coordinator._energy_tracker._last_meter_reading = 100.0
        mock_coordinator._energy_tracker._last_meter_time = datetime.now() - timedelta(minutes=10)
        mock_coordinator._energy_tracker._meter_tracking_date = datetime.now()

        # 15 kWh in one interval is suspicious
        with patch.object(mock_coordinator, '_get_energy_meter_value', return_value=115.0):
            with patch.object(mock_coordinator, 'is_cheap_tariff', return_value=True):
                with patch.object(mock_coordinator, '_get_heater_states', return_value=(False, False, False)):
                    with patch.object(mock_coordinator, '_get_compressor_target', return_value='cwu'):
                        mock_coordinator._energy_tracker.update()

        # Large delta should be skipped
        assert mock_coordinator._energy_tracker._cwu_cheap_today == 0.0
        assert mock_coordinator._energy_tracker._last_meter_reading == 115.0

    def test_energy_tracking_meter_unavailable(self, mock_coordinator):
        """Test handling of unavailable meter sensor."""
        mock_coordinator._energy_tracker._data_loaded = True  # Enable energy tracking
        mock_coordinator._energy_tracker._last_meter_reading = 100.0
        mock_coordinator._energy_tracker._meter_tracking_date = datetime.now()

        with patch.object(mock_coordinator, '_get_energy_meter_value', return_value=None):
            mock_coordinator._energy_tracker.update()

        # Nothing should change
        assert mock_coordinator._energy_tracker._last_meter_reading == 100.0
        assert mock_coordinator._energy_tracker._cwu_cheap_today == 0.0

    def test_energy_tracking_skipped_before_data_loaded(self, mock_coordinator):
        """Test energy tracking is skipped until persisted data is loaded."""
        mock_coordinator._energy_tracker._data_loaded = False
        mock_coordinator._energy_tracker._last_meter_reading = 100.0
        mock_coordinator._energy_tracker._meter_tracking_date = datetime.now()

        # Even with valid meter reading, tracking should be skipped
        with patch.object(mock_coordinator, '_get_energy_meter_value', return_value=100.5):
            with patch.object(mock_coordinator, 'is_cheap_tariff', return_value=True):
                mock_coordinator._energy_tracker.update()

        # Nothing should change - tracking was skipped
        assert mock_coordinator._energy_tracker._last_meter_reading == 100.0
        assert mock_coordinator._energy_tracker._cwu_cheap_today == 0.0

    def test_energy_tracking_short_interval_skipped(self, mock_coordinator):
        """Test energy tracking skips if too little time passed (< 10 seconds)."""
        mock_coordinator._energy_tracker._data_loaded = True
        mock_coordinator._energy_tracker._last_meter_reading = 100.0
        mock_coordinator._energy_tracker._last_meter_time = datetime.now() - timedelta(seconds=5)
        mock_coordinator._energy_tracker._meter_tracking_date = datetime.now()

        with patch.object(mock_coordinator, '_get_energy_meter_value', return_value=100.1):
            with patch.object(mock_coordinator, 'is_cheap_tariff', return_value=True):
                with patch.object(mock_coordinator, '_get_heater_states', return_value=(False, False, False)):
                    with patch.object(mock_coordinator, '_get_compressor_target', return_value='cwu'):
                        mock_coordinator._energy_tracker.update()

        # Too little time - tracking skipped
        assert mock_coordinator._energy_tracker._cwu_cheap_today == 0.0
        assert mock_coordinator._energy_tracker._last_meter_reading == 100.0  # Not updated

    def test_energy_tracking_mixed_cwu_heater_and_floor_compressor(self, mock_coordinator):
        """Test CWU heater ON + compressor heating floor = split attribution."""
        mock_coordinator._energy_tracker._data_loaded = True
        mock_coordinator._energy_tracker._last_meter_reading = 100.0
        mock_coordinator._energy_tracker._last_meter_time = datetime.now() - timedelta(seconds=60)
        mock_coordinator._energy_tracker._meter_tracking_date = datetime.now()

        # Total: 0.2 kWh, CWU heater (3.3kW) ON, compressor targeting floor
        # CWU heater: 3.3kW * (60/3600) = 0.055 kWh to CWU
        # Remaining: 0.2 - 0.055 = 0.145 kWh to floor (compressor target)
        with patch.object(mock_coordinator, '_get_energy_meter_value', return_value=100.2):
            with patch.object(mock_coordinator, 'is_cheap_tariff', return_value=True):
                with patch.object(mock_coordinator, '_get_heater_states', return_value=(True, False, False)):
                    with patch.object(mock_coordinator, '_get_compressor_target', return_value='floor'):
                        mock_coordinator._energy_tracker.update()

        assert mock_coordinator._energy_tracker._cwu_cheap_today == pytest.approx(0.055, abs=0.001)
        assert mock_coordinator._energy_tracker._floor_cheap_today == pytest.approx(0.145, abs=0.001)

    def test_energy_tracking_floor_heater_and_cwu_compressor(self, mock_coordinator):
        """Test floor heater ON + compressor heating CWU = split attribution."""
        mock_coordinator._energy_tracker._data_loaded = True
        mock_coordinator._energy_tracker._last_meter_reading = 100.0
        mock_coordinator._energy_tracker._last_meter_time = datetime.now() - timedelta(seconds=60)
        mock_coordinator._energy_tracker._meter_tracking_date = datetime.now()

        # Total: 0.2 kWh, floor heater 1 (3.0kW) ON, compressor targeting CWU
        # Floor heater: 3.0kW * (60/3600) = 0.05 kWh to floor
        # Remaining: 0.2 - 0.05 = 0.15 kWh to CWU (compressor target)
        with patch.object(mock_coordinator, '_get_energy_meter_value', return_value=100.2):
            with patch.object(mock_coordinator, 'is_cheap_tariff', return_value=True):
                with patch.object(mock_coordinator, '_get_heater_states', return_value=(False, True, False)):
                    with patch.object(mock_coordinator, '_get_compressor_target', return_value='cwu'):
                        mock_coordinator._energy_tracker.update()

        assert mock_coordinator._energy_tracker._cwu_cheap_today == pytest.approx(0.15, abs=0.001)
        assert mock_coordinator._energy_tracker._floor_cheap_today == pytest.approx(0.05, abs=0.001)

    def test_energy_tracking_all_heaters_on(self, mock_coordinator):
        """Test all 3 heaters ON simultaneously (max load scenario)."""
        mock_coordinator._energy_tracker._data_loaded = True
        mock_coordinator._energy_tracker._last_meter_reading = 100.0
        mock_coordinator._energy_tracker._last_meter_time = datetime.now() - timedelta(seconds=60)
        mock_coordinator._energy_tracker._meter_tracking_date = datetime.now()

        # Total: 0.3 kWh in 60s (18kW average)
        # CWU heater: 3.3kW * (60/3600) = 0.055 kWh to CWU
        # Floor heaters: (3.0 + 3.0) * (60/3600) = 0.1 kWh to floor
        # Remaining: 0.3 - 0.055 - 0.1 = 0.145 kWh to compressor target (cwu)
        with patch.object(mock_coordinator, '_get_energy_meter_value', return_value=100.3):
            with patch.object(mock_coordinator, 'is_cheap_tariff', return_value=True):
                with patch.object(mock_coordinator, '_get_heater_states', return_value=(True, True, True)):
                    with patch.object(mock_coordinator, '_get_compressor_target', return_value='cwu'):
                        mock_coordinator._energy_tracker.update()

        # CWU: 0.055 (heater) + 0.145 (compressor) = 0.2
        assert mock_coordinator._energy_tracker._cwu_cheap_today == pytest.approx(0.2, abs=0.001)
        # Floor: 0.1 (heaters)
        assert mock_coordinator._energy_tracker._floor_cheap_today == pytest.approx(0.1, abs=0.001)

    def test_energy_tracking_heater_capped_to_delta(self, mock_coordinator):
        """Test heater energy is capped to meter delta (heater turned on mid-interval)."""
        mock_coordinator._energy_tracker._data_loaded = True
        mock_coordinator._energy_tracker._last_meter_reading = 100.0
        mock_coordinator._energy_tracker._last_meter_time = datetime.now() - timedelta(seconds=60)
        mock_coordinator._energy_tracker._meter_tracking_date = datetime.now()

        # Meter delta: 0.03 kWh (heater was ON for ~33s, not full 60s)
        # Calculated heater: 3.3kW * 60s = 0.055 kWh
        # Heater energy should be CAPPED to delta: 0.03 kWh
        with patch.object(mock_coordinator, '_get_energy_meter_value', return_value=100.03):
            with patch.object(mock_coordinator, 'is_cheap_tariff', return_value=True):
                with patch.object(mock_coordinator, '_get_heater_states', return_value=(True, False, False)):
                    with patch.object(mock_coordinator, '_get_compressor_target', return_value='cwu'):
                        mock_coordinator._energy_tracker.update()

        # CWU heater capped to meter delta (0.03 kWh, not 0.055)
        # Remaining is 0 (all energy attributed to heater)
        assert mock_coordinator._energy_tracker._cwu_cheap_today == pytest.approx(0.03, abs=0.001)
        assert mock_coordinator._energy_tracker._floor_cheap_today == 0.0

    def test_energy_tracking_multiple_heaters_scaled_proportionally(self, mock_coordinator):
        """Test multiple heaters are scaled proportionally when exceeding delta."""
        mock_coordinator._energy_tracker._data_loaded = True
        mock_coordinator._energy_tracker._last_meter_reading = 100.0
        mock_coordinator._energy_tracker._last_meter_time = datetime.now() - timedelta(seconds=60)
        mock_coordinator._energy_tracker._meter_tracking_date = datetime.now()

        # Meter delta: 0.08 kWh
        # Calculated: CWU 0.055 + Floor1 0.05 + Floor2 0.05 = 0.155 kWh
        # Scale factor: 0.08 / 0.155 = 0.516
        # Scaled: CWU 0.0284, Floor1 0.0258, Floor2 0.0258
        with patch.object(mock_coordinator, '_get_energy_meter_value', return_value=100.08):
            with patch.object(mock_coordinator, 'is_cheap_tariff', return_value=True):
                with patch.object(mock_coordinator, '_get_heater_states', return_value=(True, True, True)):
                    with patch.object(mock_coordinator, '_get_compressor_target', return_value='idle'):
                        mock_coordinator._energy_tracker.update()

        # All heaters scaled proportionally to fit meter delta
        # CWU: 0.055 * (0.08/0.155) = 0.0284
        # Floor: (0.05 + 0.05) * (0.08/0.155) = 0.0516
        # Total: 0.08 (matches meter delta)
        scale = 0.08 / 0.155
        expected_cwu = 0.055 * scale
        expected_floor = 0.1 * scale
        assert mock_coordinator._energy_tracker._cwu_cheap_today == pytest.approx(expected_cwu, abs=0.001)
        assert mock_coordinator._energy_tracker._floor_cheap_today == pytest.approx(expected_floor, abs=0.001)
        # Total should equal meter delta
        total = mock_coordinator._energy_tracker._cwu_cheap_today + mock_coordinator._energy_tracker._floor_cheap_today
        assert total == pytest.approx(0.08, abs=0.001)

    def test_energy_tracking_actual_elapsed_time(self, mock_coordinator):
        """Test energy calculation uses actual elapsed time, not fixed interval."""
        mock_coordinator._energy_tracker._data_loaded = True
        mock_coordinator._energy_tracker._last_meter_reading = 100.0
        # 2 minutes elapsed instead of 1 minute
        mock_coordinator._energy_tracker._last_meter_time = datetime.now() - timedelta(seconds=120)
        mock_coordinator._energy_tracker._meter_tracking_date = datetime.now()

        # CWU heater ON for 2 minutes = 3.3kW * (120/3600) = 0.11 kWh
        # Total delta: 0.15 kWh, remaining = 0.04 kWh to compressor target
        with patch.object(mock_coordinator, '_get_energy_meter_value', return_value=100.15):
            with patch.object(mock_coordinator, 'is_cheap_tariff', return_value=True):
                with patch.object(mock_coordinator, '_get_heater_states', return_value=(True, False, False)):
                    with patch.object(mock_coordinator, '_get_compressor_target', return_value='floor'):
                        mock_coordinator._energy_tracker.update()

        # CWU: 0.11 kWh (heater for 2 min)
        assert mock_coordinator._energy_tracker._cwu_cheap_today == pytest.approx(0.11, abs=0.001)
        # Floor: 0.04 kWh (remaining to compressor target)
        assert mock_coordinator._energy_tracker._floor_cheap_today == pytest.approx(0.04, abs=0.001)

    def test_energy_tracking_zero_delta(self, mock_coordinator):
        """Test handling of zero energy delta (pump idle, no consumption)."""
        mock_coordinator._energy_tracker._data_loaded = True
        mock_coordinator._energy_tracker._last_meter_reading = 100.0
        mock_coordinator._energy_tracker._last_meter_time = datetime.now() - timedelta(seconds=60)
        mock_coordinator._energy_tracker._meter_tracking_date = datetime.now()

        # Zero delta - nothing consumed
        with patch.object(mock_coordinator, '_get_energy_meter_value', return_value=100.0):
            with patch.object(mock_coordinator, 'is_cheap_tariff', return_value=True):
                with patch.object(mock_coordinator, '_get_heater_states', return_value=(False, False, False)):
                    with patch.object(mock_coordinator, '_get_compressor_target', return_value='idle'):
                        mock_coordinator._energy_tracker.update()

        assert mock_coordinator._energy_tracker._cwu_cheap_today == 0.0
        assert mock_coordinator._energy_tracker._floor_cheap_today == 0.0

    def test_energy_tracking_tariff_changes_during_interval(self, mock_coordinator):
        """Test tariff is captured at update time (not retroactively changed)."""
        mock_coordinator._energy_tracker._data_loaded = True
        mock_coordinator._energy_tracker._last_meter_reading = 100.0
        mock_coordinator._energy_tracker._last_meter_time = datetime.now() - timedelta(seconds=60)
        mock_coordinator._energy_tracker._meter_tracking_date = datetime.now()

        # First update - cheap tariff
        with patch.object(mock_coordinator, '_get_energy_meter_value', return_value=100.1):
            with patch.object(mock_coordinator, 'is_cheap_tariff', return_value=True):
                with patch.object(mock_coordinator, '_get_heater_states', return_value=(False, False, False)):
                    with patch.object(mock_coordinator, '_get_compressor_target', return_value='cwu'):
                        mock_coordinator._energy_tracker.update()

        assert mock_coordinator._energy_tracker._cwu_cheap_today == pytest.approx(0.1)
        assert mock_coordinator._energy_tracker._cwu_expensive_today == 0.0

        # Second update - expensive tariff (tariff changed)
        mock_coordinator._energy_tracker._last_meter_time = datetime.now() - timedelta(seconds=60)
        with patch.object(mock_coordinator, '_get_energy_meter_value', return_value=100.2):
            with patch.object(mock_coordinator, 'is_cheap_tariff', return_value=False):
                with patch.object(mock_coordinator, '_get_heater_states', return_value=(False, False, False)):
                    with patch.object(mock_coordinator, '_get_compressor_target', return_value='cwu'):
                        mock_coordinator._energy_tracker.update()

        assert mock_coordinator._energy_tracker._cwu_cheap_today == pytest.approx(0.1)
        assert mock_coordinator._energy_tracker._cwu_expensive_today == pytest.approx(0.1)

    def test_energy_tracking_cumulative_over_multiple_updates(self, mock_coordinator):
        """Test energy accumulates correctly over multiple update cycles."""
        mock_coordinator._energy_tracker._data_loaded = True
        mock_coordinator._energy_tracker._last_meter_reading = 100.0
        mock_coordinator._energy_tracker._last_meter_time = datetime.now() - timedelta(seconds=60)
        mock_coordinator._energy_tracker._meter_tracking_date = datetime.now()

        # Simulate 5 update cycles, each with 0.05 kWh consumption
        for i in range(5):
            with patch.object(mock_coordinator, '_get_energy_meter_value', return_value=100.0 + (i + 1) * 0.05):
                with patch.object(mock_coordinator, 'is_cheap_tariff', return_value=True):
                    with patch.object(mock_coordinator, '_get_heater_states', return_value=(False, False, False)):
                        with patch.object(mock_coordinator, '_get_compressor_target', return_value='cwu'):
                            mock_coordinator._energy_tracker.update()
            mock_coordinator._energy_tracker._last_meter_time = datetime.now() - timedelta(seconds=60)

        # Total: 5 * 0.05 = 0.25 kWh
        assert mock_coordinator._energy_tracker._cwu_cheap_today == pytest.approx(0.25)

    def test_energy_tracking_one_floor_heater_only(self, mock_coordinator):
        """Test with only one floor heater ON (K25 or K26 individually)."""
        mock_coordinator._energy_tracker._data_loaded = True
        mock_coordinator._energy_tracker._last_meter_reading = 100.0
        mock_coordinator._energy_tracker._last_meter_time = datetime.now() - timedelta(seconds=60)
        mock_coordinator._energy_tracker._meter_tracking_date = datetime.now()

        # Only floor heater 2 (K26) ON: 3.0kW * (60/3600) = 0.05 kWh
        with patch.object(mock_coordinator, '_get_energy_meter_value', return_value=100.1):
            with patch.object(mock_coordinator, 'is_cheap_tariff', return_value=True):
                with patch.object(mock_coordinator, '_get_heater_states', return_value=(False, False, True)):
                    with patch.object(mock_coordinator, '_get_compressor_target', return_value='idle'):
                        mock_coordinator._energy_tracker.update()

        # Floor heater: 0.05 kWh
        # Remaining: 0.05 kWh → 50/50 split
        # CWU: 0.025, Floor: 0.05 + 0.025 = 0.075
        assert mock_coordinator._energy_tracker._floor_cheap_today == pytest.approx(0.075, abs=0.001)
        assert mock_coordinator._energy_tracker._cwu_cheap_today == pytest.approx(0.025, abs=0.001)

    def test_energy_tracking_fake_heating_ignores_heater(self, mock_coordinator):
        """Test that during fake heating states, heater is not counted (broken heater mode).

        In fake_heating_detected/fake_heating_restarting states, BSB-LAN reports heater ON
        but it's not actually consuming power. Energy tracking should ignore the heater.
        """
        mock_coordinator._energy_tracker._data_loaded = True
        mock_coordinator._energy_tracker._last_meter_reading = 100.0
        mock_coordinator._energy_tracker._last_meter_time = datetime.now() - timedelta(seconds=60)
        mock_coordinator._energy_tracker._meter_tracking_date = datetime.now()

        # Set state to fake_heating_detected
        mock_coordinator._current_state = STATE_FAKE_HEATING_DETECTED

        # BSB-LAN reports CWU heater ON, but due to fake heating state, _get_heater_states returns False
        mock_coordinator._bsb_lan_data = {"electric_heater_cwu_state": "On"}

        with patch.object(mock_coordinator, '_get_energy_meter_value', return_value=100.05):
            with patch.object(mock_coordinator, 'is_cheap_tariff', return_value=True):
                with patch.object(mock_coordinator, '_get_compressor_target', return_value='idle'):
                    mock_coordinator._energy_tracker.update()

        # No heater energy should be attributed (heater is broken)
        # All goes to idle (50/50 split): 0.025 each
        assert mock_coordinator._energy_tracker._cwu_cheap_today == pytest.approx(0.025)
        assert mock_coordinator._energy_tracker._floor_cheap_today == pytest.approx(0.025)

    def test_energy_tracking_bsb_lan_unavailable(self, mock_coordinator):
        """Test energy tracking when BSB-LAN is unavailable (no heater states).

        When BSB-LAN data is unavailable, heater states default to (False, False, False)
        and compressor target defaults to 'idle'. Energy is split 50/50.
        """
        mock_coordinator._energy_tracker._data_loaded = True
        mock_coordinator._energy_tracker._last_meter_reading = 100.0
        mock_coordinator._energy_tracker._last_meter_time = datetime.now() - timedelta(seconds=60)
        mock_coordinator._energy_tracker._meter_tracking_date = datetime.now()

        # Simulate BSB-LAN unavailable - returns defaults
        with patch.object(mock_coordinator, '_get_energy_meter_value', return_value=100.1):
            with patch.object(mock_coordinator, 'is_cheap_tariff', return_value=True):
                # Simulate BSB-LAN unavailable - heater states all False, compressor idle
                with patch.object(mock_coordinator, '_get_heater_states', return_value=(False, False, False)):
                    with patch.object(mock_coordinator, '_get_compressor_target', return_value='idle'):
                        mock_coordinator._energy_tracker.update()

        # All energy split 50/50 (compressor idle)
        assert mock_coordinator._energy_tracker._cwu_cheap_today == pytest.approx(0.05)
        assert mock_coordinator._energy_tracker._floor_cheap_today == pytest.approx(0.05)

    def test_energy_tracking_realistic_scenario_cwu_heating(self, mock_coordinator):
        """Test realistic CWU heating scenario: compressor + pumps, no electric heaters.

        Heat pump heating CWU thermodynamically uses ~2kW compressor.
        In 60 seconds: 2kW * (60/3600) = 0.033 kWh
        """
        mock_coordinator._energy_tracker._data_loaded = True
        mock_coordinator._energy_tracker._last_meter_reading = 100.0
        mock_coordinator._energy_tracker._last_meter_time = datetime.now() - timedelta(seconds=60)
        mock_coordinator._energy_tracker._meter_tracking_date = datetime.now()

        # Compressor drawing ~2kW for CWU heating
        with patch.object(mock_coordinator, '_get_energy_meter_value', return_value=100.033):
            with patch.object(mock_coordinator, 'is_cheap_tariff', return_value=True):
                with patch.object(mock_coordinator, '_get_heater_states', return_value=(False, False, False)):
                    with patch.object(mock_coordinator, '_get_compressor_target', return_value='cwu'):
                        mock_coordinator._energy_tracker.update()

        # All goes to CWU
        assert mock_coordinator._energy_tracker._cwu_cheap_today == pytest.approx(0.033)
        assert mock_coordinator._energy_tracker._floor_cheap_today == 0.0

    def test_energy_tracking_realistic_scenario_floor_with_electric(self, mock_coordinator):
        """Test realistic floor heating with electric heater backup.

        Compressor targeting floor + 1 electric floor heater (3kW) active.
        """
        mock_coordinator._energy_tracker._data_loaded = True
        mock_coordinator._energy_tracker._last_meter_reading = 100.0
        mock_coordinator._energy_tracker._last_meter_time = datetime.now() - timedelta(seconds=60)
        mock_coordinator._energy_tracker._meter_tracking_date = datetime.now()

        # Compressor (2kW) + floor heater 1 (3kW) = 5kW
        # In 60 seconds: 5kW * (60/3600) = 0.083 kWh
        with patch.object(mock_coordinator, '_get_energy_meter_value', return_value=100.083):
            with patch.object(mock_coordinator, 'is_cheap_tariff', return_value=True):
                with patch.object(mock_coordinator, '_get_heater_states', return_value=(False, True, False)):
                    with patch.object(mock_coordinator, '_get_compressor_target', return_value='floor'):
                        mock_coordinator._energy_tracker.update()

        # Floor heater: 3kW * (60/3600) = 0.05 kWh
        # Compressor remainder: 0.083 - 0.05 = 0.033 kWh
        # All goes to floor
        assert mock_coordinator._energy_tracker._cwu_cheap_today == 0.0
        assert mock_coordinator._energy_tracker._floor_cheap_today == pytest.approx(0.083, abs=0.001)

    def test_energy_tracking_realistic_broken_heater_mode(self, mock_coordinator):
        """Test broken heater mode: CWU heater ON but power low - capped to meter delta.

        Broken heater scenario: pump reports CWU heater on, but actual power is much lower
        because the heater is broken. Energy is capped to meter delta (actual consumption).
        """
        mock_coordinator._energy_tracker._data_loaded = True
        mock_coordinator._energy_tracker._last_meter_reading = 100.0
        mock_coordinator._energy_tracker._last_meter_time = datetime.now() - timedelta(seconds=60)
        mock_coordinator._energy_tracker._meter_tracking_date = datetime.now()

        # Pump reports CWU heater ON but actual consumption is only 0.01 kWh (broken heater)
        # Calculated: 3.3kW * (60/3600) = 0.055 kWh
        # CAPPED to meter delta: 0.01 kWh
        with patch.object(mock_coordinator, '_get_energy_meter_value', return_value=100.01):
            with patch.object(mock_coordinator, 'is_cheap_tariff', return_value=True):
                with patch.object(mock_coordinator, '_get_heater_states', return_value=(True, False, False)):
                    with patch.object(mock_coordinator, '_get_compressor_target', return_value='cwu'):
                        mock_coordinator._energy_tracker.update()

        # Heater energy capped to meter delta (0.01 kWh, not 0.055)
        # This is correct - we can't attribute more than meter actually shows
        assert mock_coordinator._energy_tracker._cwu_cheap_today == pytest.approx(0.01, abs=0.001)
        # No remaining energy
        assert mock_coordinator._energy_tracker._floor_cheap_today == 0.0

    def test_energy_tracking_very_long_interval(self, mock_coordinator):
        """Test energy tracking handles long intervals correctly (e.g., after HA restart)."""
        mock_coordinator._energy_tracker._data_loaded = True
        mock_coordinator._energy_tracker._last_meter_reading = 100.0
        # 30 minutes elapsed (1800 seconds)
        mock_coordinator._energy_tracker._last_meter_time = datetime.now() - timedelta(minutes=30)
        mock_coordinator._energy_tracker._meter_tracking_date = datetime.now()

        # Compressor heating CWU for 30 minutes at ~2kW = 2kW * 0.5h = 1 kWh
        with patch.object(mock_coordinator, '_get_energy_meter_value', return_value=101.0):
            with patch.object(mock_coordinator, 'is_cheap_tariff', return_value=True):
                with patch.object(mock_coordinator, '_get_heater_states', return_value=(False, False, False)):
                    with patch.object(mock_coordinator, '_get_compressor_target', return_value='cwu'):
                        mock_coordinator._energy_tracker.update()

        assert mock_coordinator._energy_tracker._cwu_cheap_today == pytest.approx(1.0)

    def test_energy_tracking_multiple_heaters_during_peak_demand(self, mock_coordinator):
        """Test simultaneous operation: CWU heater + both floor heaters + compressor.

        Worst case scenario: all electric heaters on during high demand.
        CWU heater (3.3kW) + Floor 1 (3kW) + Floor 2 (3kW) + Compressor (~2kW) = ~11kW
        """
        mock_coordinator._energy_tracker._data_loaded = True
        mock_coordinator._energy_tracker._last_meter_reading = 100.0
        mock_coordinator._energy_tracker._last_meter_time = datetime.now() - timedelta(seconds=60)
        mock_coordinator._energy_tracker._meter_tracking_date = datetime.now()

        # Total: 11kW * (60/3600) = 0.183 kWh
        with patch.object(mock_coordinator, '_get_energy_meter_value', return_value=100.183):
            with patch.object(mock_coordinator, 'is_cheap_tariff', return_value=False):
                with patch.object(mock_coordinator, '_get_heater_states', return_value=(True, True, True)):
                    # Compressor targeting CWU while electric heaters supplement
                    with patch.object(mock_coordinator, '_get_compressor_target', return_value='cwu'):
                        mock_coordinator._energy_tracker.update()

        # CWU: 3.3kW * (60/3600) = 0.055 kWh (CWU heater)
        # Floor: 6kW * (60/3600) = 0.1 kWh (both floor heaters)
        # Remaining: 0.183 - 0.055 - 0.1 = 0.028 kWh → CWU (compressor target)
        # Total CWU: 0.055 + 0.028 = 0.083 kWh
        assert mock_coordinator._energy_tracker._cwu_expensive_today == pytest.approx(0.083, abs=0.001)
        assert mock_coordinator._energy_tracker._floor_expensive_today == pytest.approx(0.1, abs=0.001)


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
        """Test _change_state updates state correctly."""
        mock_coordinator._current_state = STATE_IDLE
        mock_coordinator._change_state(STATE_HEATING_CWU)

        assert mock_coordinator._current_state == STATE_HEATING_CWU
        assert mock_coordinator._previous_state == STATE_IDLE

    def test_change_state_same_state_no_op(self, mock_coordinator):
        """Test _change_state does nothing when state unchanged."""
        mock_coordinator._current_state = STATE_IDLE
        mock_coordinator._previous_state = None

        mock_coordinator._change_state(STATE_IDLE)

        # State should remain unchanged
        assert mock_coordinator._current_state == STATE_IDLE
        assert mock_coordinator._previous_state is None


class TestFakeHeatingDetection:
    """Tests for fake heating detection (broken heater mode).

    Fake heating is detected when:
    - Water heater is in active mode (On/performance)
    - CWU heating has been active for 10+ minutes
    - No power spike >= 200W (POWER_SPIKE_THRESHOLD) in the last 10 minutes
    """

    def test_no_fake_heating_high_power(self, mock_coordinator):
        """Test no fake heating detected when power spike exists."""
        now = datetime.now()
        mock_coordinator._cwu_heating_start = now - timedelta(minutes=15)
        # Power readings with a spike above 200W (POWER_SPIKE_THRESHOLD)
        mock_coordinator._recent_power_readings = [
            (now - timedelta(minutes=9), 50.0),
            (now - timedelta(minutes=7), 250.0),  # Spike above 200W threshold
            (now - timedelta(minutes=5), 50.0),
            (now - timedelta(minutes=3), 45.0),
            (now - timedelta(minutes=1), 40.0),
        ]
        result = mock_coordinator._detect_fake_heating(40.0, "On")  # BSB mode
        assert result is False

    def test_no_fake_heating_wrong_mode(self, mock_coordinator):
        """Test no fake heating detected when water heater is off."""
        now = datetime.now()
        mock_coordinator._cwu_heating_start = now - timedelta(minutes=15)
        mock_coordinator._recent_power_readings = [
            (now - timedelta(minutes=5), 5.0),
            (now - timedelta(minutes=3), 5.0),
            (now - timedelta(minutes=1), 5.0),
        ]
        result = mock_coordinator._detect_fake_heating(5.0, "Off")  # BSB mode
        assert result is False

    def test_fake_heating_detected_low_power(self, mock_coordinator):
        """Test fake heating detected when power stays below threshold (< 10W)."""
        now = datetime.now()
        mock_coordinator._cwu_heating_start = now - timedelta(minutes=15)
        # All readings below 100W (pump waiting for broken heater)
        mock_coordinator._recent_power_readings = [
            (now - timedelta(minutes=9), 5.0),
            (now - timedelta(minutes=7), 5.0),
            (now - timedelta(minutes=5), 5.0),
            (now - timedelta(minutes=3), 5.0),
            (now - timedelta(minutes=1), 5.0),
        ]
        result = mock_coordinator._detect_fake_heating(5.0, "On")
        assert result is True

    def test_fake_heating_detected_pump_running_no_spike(self, mock_coordinator):
        """Test fake heating detected when pump runs (~50W) but no CWU heating spike."""
        now = datetime.now()
        mock_coordinator._cwu_heating_start = now - timedelta(minutes=15)
        # Pump running at ~50W but no spike >= 100W (not heating CWU)
        mock_coordinator._recent_power_readings = [
            (now - timedelta(minutes=9), 45.0),
            (now - timedelta(minutes=7), 50.0),
            (now - timedelta(minutes=5), 55.0),
            (now - timedelta(minutes=3), 48.0),
            (now - timedelta(minutes=1), 52.0),
        ]
        result = mock_coordinator._detect_fake_heating(52.0, "On")
        assert result is True

    def test_fake_heating_not_detected_short_duration(self, mock_coordinator):
        """Test fake heating not detected before timeout (10 min)."""
        now = datetime.now()
        mock_coordinator._cwu_heating_start = now - timedelta(minutes=2)  # Only 2 min
        mock_coordinator._recent_power_readings = [
            (now - timedelta(minutes=1), 5.0),
        ]
        result = mock_coordinator._detect_fake_heating(5.0, "On")
        assert result is False

    def test_fake_heating_not_detected_no_cwu_start(self, mock_coordinator):
        """Test no fake heating when CWU heating hasn't started."""
        now = datetime.now()
        mock_coordinator._cwu_heating_start = None
        mock_coordinator._recent_power_readings = [
            (now - timedelta(minutes=5), 5.0),
        ]
        result = mock_coordinator._detect_fake_heating(5.0, "On")
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


class TestEnergyPersistence:
    """Tests for energy data persistence (load/save)."""

    @pytest.mark.asyncio
    async def test_load_no_stored_data(self, mock_coordinator):
        """Test load when no stored data exists."""
        mock_coordinator._energy_tracker._store._data = None

        await mock_coordinator.async_load_energy_data()

        assert mock_coordinator._energy_tracker._data_loaded is True
        assert mock_coordinator._energy_tracker._cwu_cheap_today == 0.0
        assert mock_coordinator._energy_tracker._floor_cheap_today == 0.0

    @pytest.mark.asyncio
    async def test_load_same_day_restores_data(self, mock_coordinator):
        """Test load restores data when stored from same day."""
        today = datetime.now().date().isoformat()
        mock_coordinator._energy_tracker._store._data = {
            "date": today,
            "cwu_cheap_today": 2.5,
            "cwu_expensive_today": 1.0,
            "floor_cheap_today": 3.0,
            "floor_expensive_today": 0.5,
            "cwu_cheap_yesterday": 4.0,
            "cwu_expensive_yesterday": 2.0,
            "floor_cheap_yesterday": 5.0,
            "floor_expensive_yesterday": 1.0,
            "last_meter_reading": 150.0,
        }

        await mock_coordinator.async_load_energy_data()

        assert mock_coordinator._energy_tracker._data_loaded is True
        assert mock_coordinator._energy_tracker._cwu_cheap_today == 2.5
        assert mock_coordinator._energy_tracker._cwu_expensive_today == 1.0
        assert mock_coordinator._energy_tracker._floor_cheap_today == 3.0
        assert mock_coordinator._energy_tracker._floor_expensive_today == 0.5
        assert mock_coordinator._energy_tracker._cwu_cheap_yesterday == 4.0
        assert mock_coordinator._energy_tracker._floor_cheap_yesterday == 5.0
        assert mock_coordinator._energy_tracker._last_meter_reading == 150.0

    @pytest.mark.asyncio
    async def test_load_yesterday_data_moves_to_yesterday(self, mock_coordinator):
        """Test load from yesterday moves today's data to yesterday."""
        yesterday = (datetime.now() - timedelta(days=1)).date().isoformat()
        mock_coordinator._energy_tracker._store._data = {
            "date": yesterday,
            "cwu_cheap_today": 5.0,
            "cwu_expensive_today": 2.0,
            "floor_cheap_today": 6.0,
            "floor_expensive_today": 1.5,
        }

        await mock_coordinator.async_load_energy_data()

        assert mock_coordinator._energy_tracker._data_loaded is True
        # Yesterday's "today" should become today's "yesterday"
        assert mock_coordinator._energy_tracker._cwu_cheap_yesterday == 5.0
        assert mock_coordinator._energy_tracker._cwu_expensive_yesterday == 2.0
        assert mock_coordinator._energy_tracker._floor_cheap_yesterday == 6.0
        assert mock_coordinator._energy_tracker._floor_expensive_yesterday == 1.5
        # Today should be reset
        assert mock_coordinator._energy_tracker._cwu_cheap_today == 0.0
        assert mock_coordinator._energy_tracker._cwu_expensive_today == 0.0
        assert mock_coordinator._energy_tracker._floor_cheap_today == 0.0
        assert mock_coordinator._energy_tracker._floor_expensive_today == 0.0

    @pytest.mark.asyncio
    async def test_load_old_data_starts_fresh(self, mock_coordinator):
        """Test load from older than yesterday starts fresh."""
        old_date = (datetime.now() - timedelta(days=3)).date().isoformat()
        mock_coordinator._energy_tracker._store._data = {
            "date": old_date,
            "cwu_cheap_today": 10.0,
            "cwu_expensive_today": 5.0,
            "floor_cheap_today": 12.0,
            "floor_expensive_today": 3.0,
        }

        await mock_coordinator.async_load_energy_data()

        assert mock_coordinator._energy_tracker._data_loaded is True
        # Old data should be ignored - all values should be default (0)
        assert mock_coordinator._energy_tracker._cwu_cheap_today == 0.0
        assert mock_coordinator._energy_tracker._cwu_expensive_today == 0.0
        assert mock_coordinator._energy_tracker._floor_cheap_today == 0.0
        assert mock_coordinator._energy_tracker._floor_expensive_today == 0.0
        assert mock_coordinator._energy_tracker._cwu_cheap_yesterday == 0.0
        assert mock_coordinator._energy_tracker._floor_cheap_yesterday == 0.0

    @pytest.mark.asyncio
    async def test_save_stores_all_data(self, mock_coordinator):
        """Test save stores all energy tracking data."""
        mock_coordinator._energy_tracker._cwu_cheap_today = 3.5
        mock_coordinator._energy_tracker._cwu_expensive_today = 1.5
        mock_coordinator._energy_tracker._floor_cheap_today = 4.0
        mock_coordinator._energy_tracker._floor_expensive_today = 0.8
        mock_coordinator._energy_tracker._cwu_cheap_yesterday = 5.0
        mock_coordinator._energy_tracker._cwu_expensive_yesterday = 2.0
        mock_coordinator._energy_tracker._floor_cheap_yesterday = 6.0
        mock_coordinator._energy_tracker._floor_expensive_yesterday = 1.2
        mock_coordinator._energy_tracker._last_meter_reading = 200.0
        mock_coordinator._energy_tracker._last_meter_time = datetime.now()

        await mock_coordinator.async_save_energy_data()

        saved = mock_coordinator._energy_tracker._store._data
        assert saved is not None
        assert saved["cwu_cheap_today"] == 3.5
        assert saved["cwu_expensive_today"] == 1.5
        assert saved["floor_cheap_today"] == 4.0
        assert saved["floor_expensive_today"] == 0.8
        assert saved["cwu_cheap_yesterday"] == 5.0
        assert saved["floor_cheap_yesterday"] == 6.0
        assert saved["last_meter_reading"] == 200.0
        assert "date" in saved

    @pytest.mark.asyncio
    async def test_save_updates_last_save_time(self, mock_coordinator):
        """Test save updates the last save timestamp."""
        assert mock_coordinator._energy_tracker._last_save is None

        await mock_coordinator.async_save_energy_data()

        assert mock_coordinator._energy_tracker._last_save is not None

    @pytest.mark.asyncio
    async def test_maybe_save_first_call_saves(self, mock_coordinator):
        """Test _maybe_save_energy_data saves on first call."""
        mock_coordinator._energy_tracker._last_save = None

        await mock_coordinator._maybe_save_energy_data()

        # Should have saved
        assert mock_coordinator._energy_tracker._last_save is not None
        assert mock_coordinator._energy_tracker._store._data is not None

    @pytest.mark.asyncio
    async def test_maybe_save_skips_if_recent(self, mock_coordinator):
        """Test _maybe_save_energy_data skips if saved recently."""
        mock_coordinator._energy_tracker._last_save = datetime.now() - timedelta(seconds=60)
        mock_coordinator._energy_tracker._store._data = None  # Clear to check if save was called

        await mock_coordinator._maybe_save_energy_data()

        # Should not have saved (only 60s elapsed, threshold is 300s)
        assert mock_coordinator._energy_tracker._store._data is None

    @pytest.mark.asyncio
    async def test_maybe_save_saves_after_interval(self, mock_coordinator):
        """Test _maybe_save_energy_data saves after ENERGY_SAVE_INTERVAL."""
        mock_coordinator._energy_tracker._last_save = datetime.now() - timedelta(seconds=400)

        await mock_coordinator._maybe_save_energy_data()

        # Should have saved (400s > 300s threshold)
        assert mock_coordinator._energy_tracker._store._data is not None

    @pytest.mark.asyncio
    async def test_load_restores_meter_tracking_state(self, mock_coordinator):
        """Test load restores meter tracking state for gap calculation."""
        today = datetime.now().date().isoformat()
        meter_time = (datetime.now() - timedelta(minutes=30)).isoformat()
        mock_coordinator._energy_tracker._store._data = {
            "date": today,
            "cwu_cheap_today": 1.0,
            "cwu_expensive_today": 0.0,
            "floor_cheap_today": 0.0,
            "floor_expensive_today": 0.0,
            "last_meter_reading": 175.5,
            "last_meter_time": meter_time,
            "meter_tracking_date": datetime.now().isoformat(),
        }

        await mock_coordinator.async_load_energy_data()

        assert mock_coordinator._energy_tracker._last_meter_reading == 175.5
        assert mock_coordinator._energy_tracker._last_meter_time is not None


class TestHPReadyForCWU:
    """Tests for _is_hp_ready_for_cwu() - checks HP status before CWU restart."""

    def test_hp_ready_no_bsb_data(self, mock_coordinator):
        """Test HP is ready when no BSB data available."""
        mock_coordinator._bsb_lan_data = None
        ready, reason = mock_coordinator._is_hp_ready_for_cwu()
        assert ready is True
        assert "unavailable" in reason.lower() or "ready" in reason.lower()

    def test_hp_ready_normal_status(self, mock_coordinator):
        """Test HP is ready with normal status."""
        mock_coordinator._bsb_lan_data = {
            "hp_status": "Compressor",
            "dhw_status": "Charging, nominal setpoint",
        }
        ready, reason = mock_coordinator._is_hp_ready_for_cwu()
        assert ready is True
        assert reason == "HP ready"

    def test_hp_not_ready_compressor_off_time(self, mock_coordinator):
        """Test HP not ready during compressor off time."""
        mock_coordinator._bsb_lan_data = {
            "hp_status": "Compressor off time min active",
            "dhw_status": "Ready",
        }
        ready, reason = mock_coordinator._is_hp_ready_for_cwu()
        assert ready is False
        assert "off time" in reason.lower()

    def test_hp_not_ready_defrosting(self, mock_coordinator):
        """Test HP not ready during defrost cycle."""
        mock_coordinator._bsb_lan_data = {
            "hp_status": "Defrost active",
            "dhw_status": "Ready",
        }
        ready, reason = mock_coordinator._is_hp_ready_for_cwu()
        assert ready is False
        assert "defrost" in reason.lower()

    def test_hp_not_ready_overrun(self, mock_coordinator):
        """Test HP not ready during overrun."""
        mock_coordinator._bsb_lan_data = {
            "hp_status": "Overrun active",
            "dhw_status": "Ready",
        }
        ready, reason = mock_coordinator._is_hp_ready_for_cwu()
        assert ready is False
        assert "overrun" in reason.lower()

    def test_hp_not_ready_dhw_overrun(self, mock_coordinator):
        """Test HP not ready when DHW shows overrun."""
        mock_coordinator._bsb_lan_data = {
            "hp_status": "---",
            "dhw_status": "Overrun",
        }
        ready, reason = mock_coordinator._is_hp_ready_for_cwu()
        assert ready is False
        assert "overrun" in reason.lower()


class TestCanSwitchMode:
    """Tests for _can_switch_mode() - anti-oscillation with hold times."""

    def test_can_switch_no_previous_switch(self, mock_coordinator):
        """Test can switch when no previous mode switch."""
        mock_coordinator._last_mode_switch = None
        mock_coordinator._bsb_lan_data = {"hp_status": "---", "dhw_status": "Ready"}
        can_switch, reason = mock_coordinator._can_switch_mode(STATE_HEATING_FLOOR, STATE_HEATING_CWU)
        assert can_switch is True
        assert reason == "OK"

    def test_cannot_switch_cwu_hold_time(self, mock_coordinator):
        """Test cannot switch from CWU before hold time."""
        # MIN_CWU_HEATING_TIME is 15 minutes
        mock_coordinator._last_mode_switch = datetime.now() - timedelta(minutes=10)
        mock_coordinator._bsb_lan_data = {"hp_status": "---", "dhw_status": "Ready"}
        can_switch, reason = mock_coordinator._can_switch_mode(STATE_HEATING_CWU, STATE_HEATING_FLOOR)
        assert can_switch is False
        assert "cwu hold" in reason.lower()

    def test_can_switch_cwu_after_hold_time(self, mock_coordinator):
        """Test can switch from CWU after hold time."""
        mock_coordinator._last_mode_switch = datetime.now() - timedelta(minutes=20)
        mock_coordinator._bsb_lan_data = {"hp_status": "---", "dhw_status": "Ready"}
        can_switch, reason = mock_coordinator._can_switch_mode(STATE_HEATING_CWU, STATE_HEATING_FLOOR)
        assert can_switch is True

    def test_cannot_switch_floor_hold_time(self, mock_coordinator):
        """Test cannot switch from floor before hold time."""
        # MIN_FLOOR_HEATING_TIME is 20 minutes
        mock_coordinator._last_mode_switch = datetime.now() - timedelta(minutes=15)
        mock_coordinator._bsb_lan_data = {"hp_status": "---", "dhw_status": "Ready"}
        can_switch, reason = mock_coordinator._can_switch_mode(STATE_HEATING_FLOOR, STATE_HEATING_CWU)
        assert can_switch is False
        assert "floor hold" in reason.lower()

    def test_can_switch_floor_after_hold_time(self, mock_coordinator):
        """Test can switch from floor after hold time."""
        mock_coordinator._last_mode_switch = datetime.now() - timedelta(minutes=25)
        mock_coordinator._bsb_lan_data = {"hp_status": "---", "dhw_status": "Ready"}
        can_switch, reason = mock_coordinator._can_switch_mode(STATE_HEATING_FLOOR, STATE_HEATING_CWU)
        assert can_switch is True

    def test_cannot_switch_to_cwu_hp_not_ready(self, mock_coordinator):
        """Test cannot switch to CWU when HP not ready."""
        mock_coordinator._last_mode_switch = datetime.now() - timedelta(minutes=30)
        mock_coordinator._bsb_lan_data = {
            "hp_status": "Compressor off time min active",
            "dhw_status": "Ready",
        }
        can_switch, reason = mock_coordinator._can_switch_mode(STATE_HEATING_FLOOR, STATE_HEATING_CWU)
        assert can_switch is False
        assert "off time" in reason.lower()


class TestDetectRapidDrop:
    """Tests for _detect_rapid_drop() - detect bath/shower usage."""

    def test_no_drop_no_bsb_data(self, mock_coordinator):
        """Test no drop detected without BSB data."""
        mock_coordinator._bsb_lan_data = None
        detected, drop = mock_coordinator._detect_rapid_drop()
        assert detected is False
        assert drop == 0.0

    def test_no_drop_insufficient_history(self, mock_coordinator):
        """Test no drop detected with insufficient history."""
        mock_coordinator._bsb_lan_data = {"cwu_temp": 45.0}
        mock_coordinator._cwu_temp_history_bsb = []
        detected, drop = mock_coordinator._detect_rapid_drop()
        assert detected is False

    def test_rapid_drop_detected(self, mock_coordinator):
        """Test rapid drop detected (5°C in 15 min = bath)."""
        now = datetime.now()
        mock_coordinator._bsb_lan_data = {"cwu_temp": 40.0}  # Dropped from 45 to 40
        mock_coordinator._cwu_temp_history_bsb = [
            (now - timedelta(minutes=10), 45.0),
            (now - timedelta(minutes=5), 43.0),
        ]
        mock_coordinator._log_action = MagicMock()
        detected, drop = mock_coordinator._detect_rapid_drop()
        assert detected is True
        assert drop >= CWU_RAPID_DROP_THRESHOLD

    def test_no_drop_gradual_decrease(self, mock_coordinator):
        """Test no drop detected with gradual temperature decrease."""
        now = datetime.now()
        mock_coordinator._bsb_lan_data = {"cwu_temp": 43.0}  # Only 2°C drop
        mock_coordinator._cwu_temp_history_bsb = [
            (now - timedelta(minutes=10), 45.0),
            (now - timedelta(minutes=5), 44.0),
        ]
        detected, drop = mock_coordinator._detect_rapid_drop()
        assert detected is False
        assert drop < CWU_RAPID_DROP_THRESHOLD

    def test_history_cleanup_old_entries(self, mock_coordinator):
        """Test old history entries are cleaned up."""
        now = datetime.now()
        mock_coordinator._bsb_lan_data = {"cwu_temp": 44.0}
        # Include old entry that should be cleaned
        mock_coordinator._cwu_temp_history_bsb = [
            (now - timedelta(minutes=30), 50.0),  # Old - should be removed
            (now - timedelta(minutes=5), 45.0),
        ]
        detected, drop = mock_coordinator._detect_rapid_drop()
        # History should be cleaned
        assert len(mock_coordinator._cwu_temp_history_bsb) <= 3


class TestIsPumpCharged:
    """Tests for _is_pump_charged() - check if DHW reached target."""

    def test_pump_not_charged_no_data(self, mock_coordinator):
        """Test pump not charged without BSB data."""
        mock_coordinator._bsb_lan_data = None
        assert mock_coordinator._is_pump_charged() is False

    def test_pump_charged_status(self, mock_coordinator):
        """Test pump charged when DHW status contains 'Charged'."""
        mock_coordinator._bsb_lan_data = {"dhw_status": "Charged"}
        assert mock_coordinator._is_pump_charged() is True

    def test_pump_charged_case_insensitive(self, mock_coordinator):
        """Test pump charged detection is case insensitive."""
        mock_coordinator._bsb_lan_data = {"dhw_status": "CHARGED"}
        assert mock_coordinator._is_pump_charged() is True

    def test_pump_not_charged_charging(self, mock_coordinator):
        """Test pump not charged when still charging."""
        mock_coordinator._bsb_lan_data = {"dhw_status": "Charging, nominal setpoint"}
        assert mock_coordinator._is_pump_charged() is False

    def test_pump_not_charged_ready(self, mock_coordinator):
        """Test pump not charged when status is Ready."""
        mock_coordinator._bsb_lan_data = {"dhw_status": "Ready"}
        assert mock_coordinator._is_pump_charged() is False


class TestIsCWUTempAcceptable:
    """Tests for _is_cwu_temp_acceptable() - check if temp within acceptable range."""

    def test_temp_not_acceptable_none(self, mock_coordinator):
        """Test temp not acceptable when None."""
        assert mock_coordinator._is_cwu_temp_acceptable(None) is False

    def test_temp_not_acceptable_below_critical(self, mock_coordinator):
        """Test temp not acceptable below critical threshold."""
        # MAX_TEMP_CRITICAL_THRESHOLD is 38°C
        assert mock_coordinator._is_cwu_temp_acceptable(35.0) is False

    def test_temp_acceptable_above_critical_no_max(self, mock_coordinator):
        """Test temp acceptable above critical when no max recorded."""
        mock_coordinator._max_temp_achieved = None
        # Should check against target - 3°C margin
        # Target is 55, so >= 52 is acceptable
        assert mock_coordinator._is_cwu_temp_acceptable(53.0) is True

    def test_temp_acceptable_within_max_drop(self, mock_coordinator):
        """Test temp acceptable when within acceptable drop from max."""
        # MAX_TEMP_ACCEPTABLE_DROP is 5°C
        mock_coordinator._max_temp_achieved = 45.0
        assert mock_coordinator._is_cwu_temp_acceptable(41.0) is True  # 4°C drop

    def test_temp_not_acceptable_beyond_max_drop(self, mock_coordinator):
        """Test temp not acceptable when beyond acceptable drop from max."""
        mock_coordinator._max_temp_achieved = 45.0
        assert mock_coordinator._is_cwu_temp_acceptable(39.0) is False  # 6°C drop

    def test_temp_acceptable_at_max(self, mock_coordinator):
        """Test temp acceptable at max achieved."""
        mock_coordinator._max_temp_achieved = 45.0
        assert mock_coordinator._is_cwu_temp_acceptable(45.0) is True


class TestDetectMaxTempAchieved:
    """Tests for _detect_max_temp_achieved() - detect when pump can't heat more."""

    def test_no_detection_no_bsb_data(self, mock_coordinator):
        """Test no max temp detection without BSB data."""
        mock_coordinator._bsb_lan_data = None
        assert mock_coordinator._detect_max_temp_achieved() is False

    def test_no_detection_initial_tracking(self, mock_coordinator):
        """Test no detection on initial tracking setup."""
        mock_coordinator._bsb_lan_data = {
            "flow_temp": 50.0,
            "dhw_status": "Charging, nominal setpoint",
            "cwu_temp": 42.0,
        }
        mock_coordinator._flow_temp_at_max_check = None
        mock_coordinator._max_temp_at = None
        # First call initializes tracking
        assert mock_coordinator._detect_max_temp_achieved() is False
        assert mock_coordinator._flow_temp_at_max_check == 50.0

    def test_electric_fallback_counted(self, mock_coordinator):
        """Test electric fallback is counted."""
        mock_coordinator._bsb_lan_data = {
            "flow_temp": 50.0,
            "dhw_status": "Charging electric",  # Broken heater!
            "cwu_temp": 42.0,
        }
        mock_coordinator._flow_temp_at_max_check = 50.0
        mock_coordinator._max_temp_at = datetime.now()
        mock_coordinator._electric_fallback_count = 0
        mock_coordinator._detect_max_temp_achieved()
        assert mock_coordinator._electric_fallback_count == 1

    def test_max_detected_stagnation_plus_electric(self, mock_coordinator):
        """Test max temp detected with flow stagnation + electric fallback."""
        mock_coordinator._bsb_lan_data = {
            "flow_temp": 51.0,  # Only 1°C rise (< 2°C threshold)
            "dhw_status": "Charging electric",
            "cwu_temp": 43.0,
        }
        mock_coordinator._flow_temp_at_max_check = 50.0
        mock_coordinator._max_temp_at = datetime.now() - timedelta(minutes=35)  # > 30 min
        mock_coordinator._electric_fallback_count = 2  # Already 2x electric
        mock_coordinator._log_action = MagicMock()

        result = mock_coordinator._detect_max_temp_achieved()

        assert result is True
        assert mock_coordinator._max_temp_achieved == 43.0

    def test_no_max_flow_still_rising(self, mock_coordinator):
        """Test no max when flow temp still rising."""
        mock_coordinator._bsb_lan_data = {
            "flow_temp": 55.0,  # 5°C rise
            "dhw_status": "Charging, nominal setpoint",
            "cwu_temp": 44.0,
        }
        mock_coordinator._flow_temp_at_max_check = 50.0
        mock_coordinator._max_temp_at = datetime.now() - timedelta(minutes=35)
        mock_coordinator._electric_fallback_count = 0

        result = mock_coordinator._detect_max_temp_achieved()

        assert result is False


class TestResetMaxTempTracking:
    """Tests for _reset_max_temp_tracking() - reset for new session."""

    def test_reset_clears_all_fields(self, mock_coordinator):
        """Test reset clears all max temp tracking fields."""
        mock_coordinator._max_temp_achieved = 45.0
        mock_coordinator._max_temp_at = datetime.now()
        mock_coordinator._electric_fallback_count = 3
        mock_coordinator._flow_temp_at_max_check = 50.0

        mock_coordinator._reset_max_temp_tracking()

        assert mock_coordinator._max_temp_achieved is None
        assert mock_coordinator._max_temp_at is None
        assert mock_coordinator._electric_fallback_count == 0
        assert mock_coordinator._flow_temp_at_max_check is None
        # Note: _cwu_temp_history_bsb is NOT cleared - it's used for rapid drop detection


class TestGetTargetTemp:
    """Tests for _get_target_temp() - get CWU target from config (BSB-LAN only, no offset)."""

    def test_get_target_from_config(self, mock_coordinator):
        """Test getting target temp from configuration."""
        mock_coordinator.config["cwu_target_temp"] = 48.0
        assert mock_coordinator._get_target_temp() == 48.0

    def test_get_default_target(self, mock_coordinator):
        """Test getting default target when not in config."""
        # default_config fixture has cwu_target_temp set to DEFAULT_CWU_TARGET_TEMP (45.0)
        assert mock_coordinator._get_target_temp() == DEFAULT_CWU_TARGET_TEMP

    def test_get_min_temp_from_config(self, mock_coordinator):
        """Test getting min temp from configuration."""
        mock_coordinator.config["cwu_min_temp"] = 42.0
        assert mock_coordinator._get_min_temp() == 42.0

    def test_get_default_min_temp(self, mock_coordinator):
        """Test getting default min temp."""
        assert mock_coordinator._get_min_temp() == 40.0  # DEFAULT_CWU_MIN_TEMP

    def test_get_critical_temp_from_config(self, mock_coordinator):
        """Test getting critical temp from configuration."""
        mock_coordinator.config["cwu_critical_temp"] = 38.0
        assert mock_coordinator._get_critical_temp() == 38.0

    def test_get_default_critical_temp(self, mock_coordinator):
        """Test getting default critical temp."""
        assert mock_coordinator._get_critical_temp() == 35.0  # DEFAULT_CWU_CRITICAL_TEMP

class TestHoldTimeRemaining:
    """Tests for _get_hold_time_remaining helper method."""

    def test_hold_time_zero_when_no_switch(self, mock_coordinator):
        """Test hold time is 0 when no mode switch has occurred."""
        mock_coordinator._last_mode_switch = None
        assert mock_coordinator._get_hold_time_remaining() == 0.0

    def test_hold_time_zero_when_idle(self, mock_coordinator):
        """Test hold time is 0 when in idle state."""
        mock_coordinator._current_state = "idle"
        mock_coordinator._last_mode_switch = datetime.now()
        assert mock_coordinator._get_hold_time_remaining() == 0.0

    def test_hold_time_remaining_cwu_state(self, mock_coordinator):
        """Test hold time remaining in CWU heating state."""
        mock_coordinator._current_state = "heating_cwu"
        mock_coordinator._last_mode_switch = datetime.now() - timedelta(minutes=5)
        # MIN_CWU_HEATING_TIME is 15, so 15-5=10 minutes remaining
        remaining = mock_coordinator._get_hold_time_remaining()
        assert 9.9 <= remaining <= 10.1

    def test_hold_time_remaining_floor_state(self, mock_coordinator):
        """Test hold time remaining in floor heating state."""
        mock_coordinator._current_state = "heating_floor"
        mock_coordinator._last_mode_switch = datetime.now() - timedelta(minutes=10)
        # MIN_FLOOR_HEATING_TIME is 20, so 20-10=10 minutes remaining
        remaining = mock_coordinator._get_hold_time_remaining()
        assert 9.9 <= remaining <= 10.1

    def test_hold_time_zero_after_elapsed(self, mock_coordinator):
        """Test hold time is 0 after min time has elapsed."""
        mock_coordinator._current_state = "heating_cwu"
        mock_coordinator._last_mode_switch = datetime.now() - timedelta(minutes=20)
        # 20 > 15 (MIN_CWU_HEATING_TIME), so 0
        assert mock_coordinator._get_hold_time_remaining() == 0.0


class TestSwitchBlockedReason:
    """Tests for _get_switch_blocked_reason helper method."""

    def test_no_blocked_reason_when_can_switch(self, mock_coordinator):
        """Test empty reason when switch is allowed."""
        mock_coordinator._current_state = "idle"
        mock_coordinator._last_mode_switch = None
        mock_coordinator._bsb_lan_data = {"hp_status": "Compressor"}
        assert mock_coordinator._get_switch_blocked_reason() == ""

    def test_blocked_by_cwu_hold_time(self, mock_coordinator):
        """Test blocked reason shows CWU hold time."""
        mock_coordinator._current_state = "heating_cwu"
        mock_coordinator._last_mode_switch = datetime.now() - timedelta(minutes=5)
        reason = mock_coordinator._get_switch_blocked_reason()
        assert "CWU hold" in reason
        assert "10" in reason or "9" in reason  # ~10 minutes left

    def test_blocked_by_floor_hold_time(self, mock_coordinator):
        """Test blocked reason shows floor hold time."""
        mock_coordinator._current_state = "heating_floor"
        mock_coordinator._last_mode_switch = datetime.now() - timedelta(minutes=5)
        reason = mock_coordinator._get_switch_blocked_reason()
        assert "Floor hold" in reason
        assert "15" in reason or "14" in reason  # ~15 minutes left

    def test_blocked_by_hp_not_ready(self, mock_coordinator):
        """Test blocked reason shows HP status when hold time is satisfied."""
        mock_coordinator._current_state = "idle"
        mock_coordinator._last_mode_switch = None
        mock_coordinator._bsb_lan_data = {"hp_status": "Compressor off time min active"}
        reason = mock_coordinator._get_switch_blocked_reason()
        assert "Compressor off time" in reason
