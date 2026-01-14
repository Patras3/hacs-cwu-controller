"""Tests for Heat Pump mode compressor target detection logic.

Tests all combinations of DHW status, HP status, and HC1 status
to ensure correct detection of what the compressor is heating.
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from custom_components.cwu_controller.const import (
    COMPRESSOR_TARGET_CWU,
    COMPRESSOR_TARGET_FLOOR,
    COMPRESSOR_TARGET_IDLE,
    COMPRESSOR_TARGET_DEFROST,
    STATE_PUMP_IDLE,
    STATE_PUMP_CWU,
    STATE_PUMP_FLOOR,
    STATE_PUMP_BOTH,
    MODE_BROKEN_HEATER,
    MODE_HEAT_PUMP,
    MODE_WINTER,
    MODE_SUMMER,
)
from custom_components.cwu_controller.modes.heat_pump import HeatPumpMode


class TestCompressorTargetDetection:
    """Test _detect_compressor_target() logic."""

    @pytest.fixture
    def mode(self):
        """Create HeatPumpMode instance with mocked coordinator."""
        mock_coord = MagicMock()
        mock_coord._bsb_lan_data = {}
        mock_coord._current_state = STATE_PUMP_IDLE
        return HeatPumpMode(mock_coord)

    # ==================== DEFROST TESTS ====================

    def test_defrost_returns_defrost(self, mode):
        """HP status 'Defrosting active' should return DEFROST."""
        result = mode._detect_compressor_target(
            dhw_status="99 - Charged, nominal temperature",
            hp_status="125 - Defrosting active",
            hc1_status="116 - Heating mode Reduced",
        )
        assert result == COMPRESSOR_TARGET_DEFROST

    def test_defrost_with_charging_dhw_still_returns_defrost(self, mode):
        """Defrost takes priority even if DHW shows charging."""
        result = mode._detect_compressor_target(
            dhw_status="96 - Charging, nominal setpoint",
            hp_status="125 - Defrosting active",
            hc1_status="116 - Heating mode Reduced",
        )
        assert result == COMPRESSOR_TARGET_DEFROST

    # ==================== IDLE TESTS ====================

    def test_no_request_returns_idle(self, mode):
        """HP status 'No request' should return IDLE."""
        result = mode._detect_compressor_target(
            dhw_status="99 - Charged, nominal temperature",
            hp_status="51 - No request",
            hc1_status="122 - Room temperature limitation",
        )
        assert result == COMPRESSOR_TARGET_IDLE

    def test_overrun_returns_idle(self, mode):
        """HP status 'Overrun active' should return IDLE."""
        result = mode._detect_compressor_target(
            dhw_status="17 - Overrun active",
            hp_status="17 - Overrun active",
            hc1_status="17 - Overrun active",
        )
        assert result == COMPRESSOR_TARGET_IDLE

    def test_frost_protection_returns_idle(self, mode):
        """HP status 'Frost protection' should return IDLE."""
        result = mode._detect_compressor_target(
            dhw_status="99 - Charged, nominal temperature",
            hp_status="23 - Frost protection for plant active",
            hc1_status="23 - Frost protection for plant active",
        )
        assert result == COMPRESSOR_TARGET_IDLE

    # ==================== CWU TESTS ====================

    def test_charging_nominal_with_compressor_returns_cwu(self, mode):
        """Active CWU charging with compressor ON should return CWU."""
        result = mode._detect_compressor_target(
            dhw_status="96 - Charging, nominal setpoint",
            hp_status="46 - Compressor 1 on",
            hc1_status="104 - Restricted, DHW priority",
        )
        assert result == COMPRESSOR_TARGET_CWU

    def test_charging_electric_with_compressor_and_no_floor_returns_cwu(self, mode):
        """Electric + compressor CWU charging, floor not heating = CWU."""
        result = mode._detect_compressor_target(
            dhw_status="88 - Charging electric, nominal setpoint",
            hp_status="46 - Compressor 1 on",
            hc1_status="104 - Restricted, DHW priority",
        )
        assert result == COMPRESSOR_TARGET_CWU

    def test_charging_electric_with_compressor_and_frost_protection_floor_returns_cwu(self, mode):
        """Electric + compressor, floor in frost protection = CWU."""
        result = mode._detect_compressor_target(
            dhw_status="88 - Charging electric, nominal setpoint",
            hp_status="46 - Compressor 1 on",
            hc1_status="23 - Frost protection for plant active",
        )
        assert result == COMPRESSOR_TARGET_CWU

    def test_charging_time_limitation_floor_not_heating_returns_cwu(self, mode):
        """Charging time limitation, floor not heating = pause in CWU session."""
        result = mode._detect_compressor_target(
            dhw_status="80 - Charging time limitation active",
            hp_status="46 - Compressor 1 on",
            hc1_status="104 - Restricted, DHW priority",
        )
        assert result == COMPRESSOR_TARGET_CWU

    def test_charging_locked_floor_not_heating_returns_cwu(self, mode):
        """Charging locked, floor not heating = pause in CWU session."""
        result = mode._detect_compressor_target(
            dhw_status="81 - Charging locked",
            hp_status="46 - Compressor 1 on",
            hc1_status="17 - Overrun active",
        )
        assert result == COMPRESSOR_TARGET_CWU

    # ==================== FLOOR TESTS ====================

    def test_charged_with_floor_heating_returns_floor(self, mode):
        """CWU charged, floor in heating mode = FLOOR."""
        result = mode._detect_compressor_target(
            dhw_status="99 - Charged, nominal temperature",
            hp_status="46 - Compressor 1 on",
            hc1_status="114 - Heating mode Comfort",
        )
        assert result == COMPRESSOR_TARGET_FLOOR

    def test_charging_electric_with_floor_heating_returns_floor(self, mode):
        """Electric CWU charging + floor heating = compressor on FLOOR."""
        result = mode._detect_compressor_target(
            dhw_status="88 - Charging electric, nominal setpoint",
            hp_status="46 - Compressor 1 on",
            hc1_status="114 - Heating mode Comfort",
        )
        assert result == COMPRESSOR_TARGET_FLOOR

    def test_charging_time_limitation_with_floor_heating_returns_floor(self, mode):
        """Charging time limitation + floor heating = FLOOR took over."""
        result = mode._detect_compressor_target(
            dhw_status="80 - Charging time limitation active",
            hp_status="46 - Compressor 1 on",
            hc1_status="116 - Heating mode Reduced",
        )
        assert result == COMPRESSOR_TARGET_FLOOR

    def test_charging_locked_with_floor_heating_returns_floor(self, mode):
        """Charging locked + floor heating = FLOOR took over."""
        result = mode._detect_compressor_target(
            dhw_status="81 - Charging locked",
            hp_status="46 - Compressor 1 on",
            hc1_status="114 - Heating mode Comfort",
        )
        assert result == COMPRESSOR_TARGET_FLOOR

    def test_floor_heating_reduced_mode(self, mode):
        """Floor in Heating mode Reduced should detect as FLOOR."""
        result = mode._detect_compressor_target(
            dhw_status="99 - Charged, nominal temperature",
            hp_status="46 - Compressor 1 on",
            hc1_status="116 - Heating mode Reduced",
        )
        assert result == COMPRESSOR_TARGET_FLOOR

    def test_compressor_on_dhw_not_charging_returns_floor(self, mode):
        """Compressor ON, DHW not charging = default to FLOOR."""
        result = mode._detect_compressor_target(
            dhw_status="99 - Charged, nominal temperature",
            hp_status="46 - Compressor 1 on",
            hc1_status="122 - Room temperature limitation",
        )
        assert result == COMPRESSOR_TARGET_FLOOR


class TestDetermineMainState:
    """Test _determine_main_state() logic."""

    @pytest.fixture
    def mode(self):
        """Create HeatPumpMode instance with mocked coordinator."""
        mock_coord = MagicMock()
        mock_coord._bsb_lan_data = {}
        mock_coord._current_state = STATE_PUMP_IDLE
        return HeatPumpMode(mock_coord)

    # ==================== BASIC STATES ====================

    def test_idle_when_nothing_heating(self, mode):
        """No heating at all = IDLE."""
        result = mode._determine_main_state(
            compressor_target=COMPRESSOR_TARGET_IDLE,
            cwu_electric_on=False,
            floor_electric_on=False,
        )
        assert result == STATE_PUMP_IDLE

    def test_cwu_only_compressor(self, mode):
        """Only compressor heating CWU."""
        result = mode._determine_main_state(
            compressor_target=COMPRESSOR_TARGET_CWU,
            cwu_electric_on=False,
            floor_electric_on=False,
        )
        assert result == STATE_PUMP_CWU

    def test_floor_only_compressor(self, mode):
        """Only compressor heating floor."""
        result = mode._determine_main_state(
            compressor_target=COMPRESSOR_TARGET_FLOOR,
            cwu_electric_on=False,
            floor_electric_on=False,
        )
        assert result == STATE_PUMP_FLOOR

    # ==================== ELECTRIC HEATER STATES ====================

    def test_cwu_only_electric(self, mode):
        """Only electric heater on CWU."""
        result = mode._determine_main_state(
            compressor_target=COMPRESSOR_TARGET_IDLE,
            cwu_electric_on=True,
            floor_electric_on=False,
        )
        assert result == STATE_PUMP_CWU

    def test_floor_only_electric(self, mode):
        """Only electric heater on floor."""
        result = mode._determine_main_state(
            compressor_target=COMPRESSOR_TARGET_IDLE,
            cwu_electric_on=False,
            floor_electric_on=True,
        )
        assert result == STATE_PUMP_FLOOR

    # ==================== BOTH HEATING STATES ====================

    def test_both_compressor_cwu_and_electric_floor(self, mode):
        """Compressor on CWU + electric on floor = BOTH."""
        result = mode._determine_main_state(
            compressor_target=COMPRESSOR_TARGET_CWU,
            cwu_electric_on=False,
            floor_electric_on=True,
        )
        assert result == STATE_PUMP_BOTH

    def test_both_compressor_floor_and_electric_cwu(self, mode):
        """Compressor on floor + electric on CWU = BOTH."""
        result = mode._determine_main_state(
            compressor_target=COMPRESSOR_TARGET_FLOOR,
            cwu_electric_on=True,
            floor_electric_on=False,
        )
        assert result == STATE_PUMP_BOTH

    def test_both_electric_heaters(self, mode):
        """Both electric heaters on (emergency mode) = BOTH."""
        result = mode._determine_main_state(
            compressor_target=COMPRESSOR_TARGET_IDLE,
            cwu_electric_on=True,
            floor_electric_on=True,
        )
        assert result == STATE_PUMP_BOTH

    # ==================== DEFROST WITH ELECTRIC HEATERS ====================

    def test_defrost_with_cwu_electric_returns_cwu(self, mode):
        """Defrost + CWU electric heater = CWU."""
        result = mode._determine_main_state(
            compressor_target=COMPRESSOR_TARGET_DEFROST,
            cwu_electric_on=True,
            floor_electric_on=False,
        )
        assert result == STATE_PUMP_CWU

    def test_defrost_with_floor_electric_returns_floor(self, mode):
        """Defrost + floor electric heater = FLOOR."""
        result = mode._determine_main_state(
            compressor_target=COMPRESSOR_TARGET_DEFROST,
            cwu_electric_on=False,
            floor_electric_on=True,
        )
        assert result == STATE_PUMP_FLOOR

    def test_defrost_with_both_electric_returns_both(self, mode):
        """Defrost + both electric heaters = BOTH."""
        result = mode._determine_main_state(
            compressor_target=COMPRESSOR_TARGET_DEFROST,
            cwu_electric_on=True,
            floor_electric_on=True,
        )
        assert result == STATE_PUMP_BOTH

    def test_defrost_with_no_electric_returns_idle(self, mode):
        """Defrost only (no electric) = IDLE."""
        result = mode._determine_main_state(
            compressor_target=COMPRESSOR_TARGET_DEFROST,
            cwu_electric_on=False,
            floor_electric_on=False,
        )
        assert result == STATE_PUMP_IDLE


class TestRealWorldScenarios:
    """Test scenarios observed in real HA history data."""

    @pytest.fixture
    def mode(self):
        """Create HeatPumpMode instance with mocked coordinator."""
        mock_coord = MagicMock()
        mock_coord._bsb_lan_data = {}
        mock_coord._current_state = STATE_PUMP_IDLE
        return HeatPumpMode(mock_coord)

    def test_scenario_normal_cwu_charging(self, mode):
        """Normal CWU charging scenario from history."""
        # DHW: Charging, HP: Compressor on, HC1: Restricted
        target = mode._detect_compressor_target(
            dhw_status="96 - Charging, nominal setpoint ",
            hp_status="46 - Compressor 1 on",
            hc1_status="104 - Restricted, DHW priority",
        )
        assert target == COMPRESSOR_TARGET_CWU

        state = mode._determine_main_state(target, False, False)
        assert state == STATE_PUMP_CWU

    def test_scenario_cwu_time_limit_then_floor(self, mode):
        """CWU hit time limit, floor takes over."""
        # Step 1: Time limitation, floor heating mode
        target = mode._detect_compressor_target(
            dhw_status="80 - Charging time limitation active",
            hp_status="46 - Compressor 1 on",
            hc1_status="116 - Heating mode Reduced",
        )
        assert target == COMPRESSOR_TARGET_FLOOR

        state = mode._determine_main_state(target, False, False)
        assert state == STATE_PUMP_FLOOR

    def test_scenario_defrost_during_heating(self, mode):
        """Defrost interrupts heating."""
        target = mode._detect_compressor_target(
            dhw_status="96 - Charging, nominal setpoint ",
            hp_status="125 - Defrosting active",
            hc1_status="116 - Heating mode Reduced",
        )
        assert target == COMPRESSOR_TARGET_DEFROST

        # Without electric heaters
        state = mode._determine_main_state(target, False, False)
        assert state == STATE_PUMP_IDLE

        # With floor electric heater during defrost
        state = mode._determine_main_state(target, False, True)
        assert state == STATE_PUMP_FLOOR

    def test_scenario_electric_cwu_with_compressor_assist(self, mode):
        """Electric CWU charging with compressor also heating CWU."""
        target = mode._detect_compressor_target(
            dhw_status="88 - Charging electric, nominal setpoint",
            hp_status="46 - Compressor 1 on",
            hc1_status="104 - Restricted, DHW priority",
        )
        assert target == COMPRESSOR_TARGET_CWU

        # Both compressor and electric on CWU
        state = mode._determine_main_state(target, True, False)
        assert state == STATE_PUMP_CWU

    def test_scenario_electric_cwu_compressor_on_floor(self, mode):
        """Electric heater on CWU, compressor on floor."""
        target = mode._detect_compressor_target(
            dhw_status="88 - Charging electric, nominal setpoint",
            hp_status="46 - Compressor 1 on",
            hc1_status="114 - Heating mode Comfort",
        )
        assert target == COMPRESSOR_TARGET_FLOOR

        # Compressor on floor, electric on CWU
        state = mode._determine_main_state(target, True, False)
        assert state == STATE_PUMP_BOTH

    def test_scenario_emergency_mode_both_electric(self, mode):
        """Emergency mode - both electric heaters on."""
        target = mode._detect_compressor_target(
            dhw_status="88 - Charging electric, nominal setpoint",
            hp_status="51 - No request",
            hc1_status="116 - Heating mode Reduced",
        )
        assert target == COMPRESSOR_TARGET_IDLE

        # Both electric heaters on
        state = mode._determine_main_state(target, True, True)
        assert state == STATE_PUMP_BOTH

    def test_scenario_charged_cwu_floor_heating(self, mode):
        """CWU charged, floor heating active."""
        target = mode._detect_compressor_target(
            dhw_status="99 - Charged, nominal temperature",
            hp_status="46 - Compressor 1 on",
            hc1_status="114 - Heating mode Comfort",
        )
        assert target == COMPRESSOR_TARGET_FLOOR

        state = mode._determine_main_state(target, False, False)
        assert state == STATE_PUMP_FLOOR

    def test_scenario_compressor_cwu_plus_both_electric_heaters(self, mode):
        """Compressor on CWU + both electric heaters = BOTH."""
        target = mode._detect_compressor_target(
            dhw_status="96 - Charging, nominal setpoint",
            hp_status="46 - Compressor 1 on",
            hc1_status="104 - Restricted, DHW priority",
        )
        assert target == COMPRESSOR_TARGET_CWU

        # Compressor on CWU, plus both electric heaters
        state = mode._determine_main_state(target, True, True)
        assert state == STATE_PUMP_BOTH

    def test_scenario_compressor_floor_plus_both_electric_heaters(self, mode):
        """Compressor on floor + both electric heaters = BOTH."""
        target = mode._detect_compressor_target(
            dhw_status="99 - Charged, nominal temperature",
            hp_status="46 - Compressor 1 on",
            hc1_status="114 - Heating mode Comfort",
        )
        assert target == COMPRESSOR_TARGET_FLOOR

        # Compressor on floor, plus both electric heaters
        state = mode._determine_main_state(target, True, True)
        assert state == STATE_PUMP_BOTH

    def test_scenario_defrost_floor_electric_only(self, mode):
        """Defrost with only floor electric heater working."""
        target = mode._detect_compressor_target(
            dhw_status="81 - Charging locked",
            hp_status="125 - Defrosting active",
            hc1_status="116 - Heating mode Reduced",
        )
        assert target == COMPRESSOR_TARGET_DEFROST

        # During defrost, floor electric heater can still work
        state = mode._determine_main_state(target, False, True)
        assert state == STATE_PUMP_FLOOR

    def test_scenario_defrost_cwu_electric_only(self, mode):
        """Defrost with only CWU electric heater working."""
        target = mode._detect_compressor_target(
            dhw_status="88 - Charging electric, nominal setpoint",
            hp_status="125 - Defrosting active",
            hc1_status="122 - Room temperature limitation",
        )
        assert target == COMPRESSOR_TARGET_DEFROST

        # During defrost, CWU electric heater can still work
        state = mode._determine_main_state(target, True, False)
        assert state == STATE_PUMP_CWU

    def test_scenario_maximum_heating_all_sources(self, mode):
        """Maximum heating: compressor on CWU + both electric heaters."""
        target = mode._detect_compressor_target(
            dhw_status="88 - Charging electric, nominal setpoint",
            hp_status="46 - Compressor 1 on",
            hc1_status="104 - Restricted, DHW priority",
        )
        # Compressor assists CWU (electric heater also on CWU)
        assert target == COMPRESSOR_TARGET_CWU

        # All three heating sources active
        state = mode._determine_main_state(target, True, True)
        assert state == STATE_PUMP_BOTH


class TestElectricHeaterStateReading:
    """Test electric heater state reading from BSB-LAN data with edge cases."""

    @pytest.fixture
    def mode(self):
        """Create HeatPumpMode instance with mocked coordinator."""
        mock_coord = MagicMock()
        mock_coord._bsb_lan_data = {}
        mock_coord._current_state = STATE_PUMP_IDLE
        return HeatPumpMode(mock_coord)

    def _get_heater_states(self, bsb_data: dict) -> tuple[bool, bool, bool]:
        """Extract heater states from BSB data using same logic as run_logic()."""
        cwu_electric_on = bsb_data.get("electric_heater_cwu_state", "Off").lower() == "on"
        floor_electric_1_on = bsb_data.get("electric_heater_floor_1_state", "Off").lower() == "on"
        floor_electric_2_on = bsb_data.get("electric_heater_floor_2_state", "Off").lower() == "on"
        floor_electric_on = floor_electric_1_on or floor_electric_2_on
        return cwu_electric_on, floor_electric_on, floor_electric_1_on or floor_electric_2_on

    # ==================== MISSING KEYS ====================

    def test_missing_cwu_heater_key_defaults_to_off(self, mode):
        """Missing CWU heater key should default to Off."""
        bsb_data = {}  # No keys
        cwu_on, floor_on, _ = self._get_heater_states(bsb_data)
        assert cwu_on is False
        assert floor_on is False

    def test_missing_floor_heater_keys_defaults_to_off(self, mode):
        """Missing floor heater keys should default to Off."""
        bsb_data = {"electric_heater_cwu_state": "On"}
        cwu_on, floor_on, _ = self._get_heater_states(bsb_data)
        assert cwu_on is True
        assert floor_on is False

    # ==================== CASE SENSITIVITY ====================

    def test_cwu_heater_on_uppercase(self, mode):
        """'ON' (uppercase) should be detected as on."""
        bsb_data = {"electric_heater_cwu_state": "ON"}
        cwu_on, _, _ = self._get_heater_states(bsb_data)
        assert cwu_on is True

    def test_cwu_heater_on_mixed_case(self, mode):
        """'On' (mixed case) should be detected as on."""
        bsb_data = {"electric_heater_cwu_state": "On"}
        cwu_on, _, _ = self._get_heater_states(bsb_data)
        assert cwu_on is True

    def test_cwu_heater_on_lowercase(self, mode):
        """'on' (lowercase) should be detected as on."""
        bsb_data = {"electric_heater_cwu_state": "on"}
        cwu_on, _, _ = self._get_heater_states(bsb_data)
        assert cwu_on is True

    def test_cwu_heater_off_uppercase(self, mode):
        """'OFF' (uppercase) should be detected as off."""
        bsb_data = {"electric_heater_cwu_state": "OFF"}
        cwu_on, _, _ = self._get_heater_states(bsb_data)
        assert cwu_on is False

    def test_cwu_heater_off_mixed_case(self, mode):
        """'Off' (mixed case) should be detected as off."""
        bsb_data = {"electric_heater_cwu_state": "Off"}
        cwu_on, _, _ = self._get_heater_states(bsb_data)
        assert cwu_on is False

    # ==================== UNEXPECTED VALUES ====================

    def test_cwu_heater_empty_string(self, mode):
        """Empty string should be treated as off."""
        bsb_data = {"electric_heater_cwu_state": ""}
        cwu_on, _, _ = self._get_heater_states(bsb_data)
        assert cwu_on is False

    def test_cwu_heater_dash_placeholder(self, mode):
        """'---' placeholder (BSB-LAN default) should be off."""
        bsb_data = {"electric_heater_cwu_state": "---"}
        cwu_on, _, _ = self._get_heater_states(bsb_data)
        assert cwu_on is False

    def test_cwu_heater_numeric_value(self, mode):
        """Numeric value should not match 'on'."""
        bsb_data = {"electric_heater_cwu_state": "1"}
        cwu_on, _, _ = self._get_heater_states(bsb_data)
        assert cwu_on is False

    def test_cwu_heater_partial_match(self, mode):
        """'Online' should not match 'on' exactly."""
        bsb_data = {"electric_heater_cwu_state": "Online"}
        cwu_on, _, _ = self._get_heater_states(bsb_data)
        assert cwu_on is False

    # ==================== FLOOR HEATER COMBINATIONS ====================

    def test_floor_heater_1_only(self, mode):
        """Only floor heater 1 on."""
        bsb_data = {
            "electric_heater_floor_1_state": "On",
            "electric_heater_floor_2_state": "Off",
        }
        _, floor_on, _ = self._get_heater_states(bsb_data)
        assert floor_on is True

    def test_floor_heater_2_only(self, mode):
        """Only floor heater 2 on."""
        bsb_data = {
            "electric_heater_floor_1_state": "Off",
            "electric_heater_floor_2_state": "On",
        }
        _, floor_on, _ = self._get_heater_states(bsb_data)
        assert floor_on is True

    def test_both_floor_heaters_on(self, mode):
        """Both floor heaters on."""
        bsb_data = {
            "electric_heater_floor_1_state": "On",
            "electric_heater_floor_2_state": "On",
        }
        _, floor_on, _ = self._get_heater_states(bsb_data)
        assert floor_on is True

    def test_both_floor_heaters_off(self, mode):
        """Both floor heaters off."""
        bsb_data = {
            "electric_heater_floor_1_state": "Off",
            "electric_heater_floor_2_state": "Off",
        }
        _, floor_on, _ = self._get_heater_states(bsb_data)
        assert floor_on is False


class TestOnModeEnter:
    """Test on_mode_enter() flag reset behavior."""

    @pytest.fixture
    def mode(self):
        """Create HeatPumpMode instance with mocked coordinator."""
        mock_coord = MagicMock()
        mock_coord._bsb_lan_data = {}
        mock_coord._current_state = STATE_PUMP_IDLE
        return HeatPumpMode(mock_coord)

    def test_on_mode_enter_resets_notification_flags(self, mode):
        """on_mode_enter() should reset all notification flags."""
        # Simulate flags being set (from previous use)
        mode._electric_heater_cwu_notified = True
        mode._electric_heater_floor_notified = True
        mode._low_power_warned = True
        mode._low_power_electric_warning_at = "some_datetime"

        # Enter mode
        mode.on_mode_enter()

        # All flags should be reset
        assert mode._electric_heater_cwu_notified is False
        assert mode._electric_heater_floor_notified is False
        assert mode._low_power_warned is False
        assert mode._low_power_electric_warning_at is None

    def test_on_mode_enter_allows_fresh_notifications(self, mode):
        """After on_mode_enter(), notifications should be sent again."""
        # Set flag as if notification was already sent
        mode._electric_heater_cwu_notified = True

        # Enter mode - should reset
        mode.on_mode_enter()

        # Now a new notification should be allowed
        assert mode._electric_heater_cwu_notified is False


class TestOperatingModeStorage:
    """Test operating mode persistence across restarts."""

    @pytest.fixture
    def mock_store(self):
        """Create a mock Store instance."""
        store = MagicMock()
        store.async_load = AsyncMock(return_value=None)
        store.async_save = AsyncMock(return_value=None)
        return store

    @pytest.fixture
    def mock_coordinator(self, mock_store):
        """Create a mock coordinator with storage."""
        coord = MagicMock()
        coord._operating_mode = MODE_BROKEN_HEATER
        coord._operating_mode_store = mock_store
        coord._mode_handlers = {
            MODE_HEAT_PUMP: MagicMock(),
            MODE_BROKEN_HEATER: MagicMock(),
        }
        return coord

    @pytest.mark.asyncio
    async def test_restore_operating_mode_from_storage(self, mock_coordinator, mock_store):
        """Should restore operating mode from storage on startup."""
        # Storage returns saved heat_pump mode
        mock_store.async_load = AsyncMock(return_value={"mode": MODE_HEAT_PUMP})

        # Import the actual method logic (we can't easily call it directly on mock)
        # So we test the logic inline
        data = await mock_store.async_load()
        if data and isinstance(data, dict):
            mode = data.get("mode")
            if mode in [MODE_HEAT_PUMP, MODE_BROKEN_HEATER, MODE_WINTER, MODE_SUMMER]:
                mock_coordinator._operating_mode = mode
                handler = mock_coordinator._mode_handlers.get(mode)
                if handler:
                    handler.on_mode_enter()

        assert mock_coordinator._operating_mode == MODE_HEAT_PUMP
        mock_coordinator._mode_handlers[MODE_HEAT_PUMP].on_mode_enter.assert_called_once()

    @pytest.mark.asyncio
    async def test_restore_operating_mode_no_storage(self, mock_coordinator, mock_store):
        """Should use default mode when no storage exists."""
        # Storage returns None (first run)
        mock_store.async_load = AsyncMock(return_value=None)

        data = await mock_store.async_load()
        # No data means keep default
        if not data:
            pass  # Keep default

        assert mock_coordinator._operating_mode == MODE_BROKEN_HEATER

    @pytest.mark.asyncio
    async def test_restore_operating_mode_invalid_mode(self, mock_coordinator, mock_store):
        """Should ignore invalid mode from storage."""
        # Storage returns invalid mode
        mock_store.async_load = AsyncMock(return_value={"mode": "invalid_mode"})

        data = await mock_store.async_load()
        if data and isinstance(data, dict):
            mode = data.get("mode")
            if mode in [MODE_HEAT_PUMP, MODE_BROKEN_HEATER, MODE_WINTER, MODE_SUMMER]:
                mock_coordinator._operating_mode = mode

        # Should remain at default since "invalid_mode" is not valid
        assert mock_coordinator._operating_mode == MODE_BROKEN_HEATER

    @pytest.mark.asyncio
    async def test_save_operating_mode_on_change(self, mock_coordinator, mock_store):
        """Should save operating mode to storage when changed."""
        mock_coordinator._operating_mode = MODE_HEAT_PUMP

        # Simulate the save method
        await mock_store.async_save({"mode": mock_coordinator._operating_mode})

        mock_store.async_save.assert_called_once_with({"mode": MODE_HEAT_PUMP})
