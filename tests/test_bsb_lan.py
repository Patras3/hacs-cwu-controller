"""Tests for BSB-LAN integration in CWU Controller."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.cwu_controller.coordinator import BSBLanClient, CWUControllerCoordinator
from custom_components.cwu_controller.const import (
    BSB_LAN_FAILURES_THRESHOLD,
    BSB_CWU_MODE_ON,
    BSB_CWU_MODE_OFF,
    BSB_FLOOR_MODE_AUTOMATIC,
    BSB_FLOOR_MODE_PROTECTION,
    BSB_DHW_STATUS_CHARGING,
    BSB_DHW_STATUS_CHARGING_ELECTRIC,
    BSB_HP_COMPRESSOR_ON,
    BSB_FAKE_HEATING_DETECTION_TIME,
    CONTROL_SOURCE_BSB_LAN,
    CONTROL_SOURCE_HA_CLOUD,
    WH_MODE_HEAT_PUMP,
    WH_MODE_OFF,
)


class TestBSBLanClient:
    """Tests for BSBLanClient class."""

    def test_init(self):
        """Test client initialization."""
        client = BSBLanClient("192.168.1.100")
        assert client.host == "192.168.1.100"
        assert client._consecutive_failures == 0
        assert client._is_available is True
        assert client.is_available is True

    def test_is_available_initially_true(self):
        """Test client is available by default."""
        client = BSBLanClient("192.168.1.100")
        assert client.is_available is True

    def test_is_available_after_failures(self):
        """Test client becomes unavailable after threshold failures."""
        client = BSBLanClient("192.168.1.100")

        # Simulate failures up to threshold - 1
        for _ in range(BSB_LAN_FAILURES_THRESHOLD - 1):
            client._handle_failure(Exception("Test error"))
        assert client.is_available is True

        # One more failure triggers unavailable
        client._handle_failure(Exception("Test error"))
        assert client.is_available is False
        assert client._is_available is False

    def test_handle_success_resets_failures(self):
        """Test successful communication resets failure count."""
        client = BSBLanClient("192.168.1.100")

        # Accumulate some failures
        for _ in range(2):
            client._handle_failure(Exception("Test error"))
        assert client._consecutive_failures == 2

        # Success resets the counter
        client._handle_success()
        assert client._consecutive_failures == 0
        assert client._last_success is not None

    def test_handle_success_restores_availability(self):
        """Test successful communication restores availability."""
        client = BSBLanClient("192.168.1.100")

        # Make client unavailable
        for _ in range(BSB_LAN_FAILURES_THRESHOLD):
            client._handle_failure(Exception("Test error"))
        assert client.is_available is False

        # Success restores availability
        client._handle_success()
        assert client.is_available is True
        assert client._is_available is True

    def test_handle_failure_tracks_last_failure(self):
        """Test failure tracking records timestamp."""
        client = BSBLanClient("192.168.1.100")

        before = datetime.now()
        client._handle_failure(Exception("Test error"))
        after = datetime.now()

        assert client._last_failure is not None
        assert before <= client._last_failure <= after

    @pytest.mark.asyncio
    async def test_async_read_parameters_success(self):
        """Test successful parameter read."""
        client = BSBLanClient("192.168.1.100")

        mock_response = {
            "8003": {"desc": "Charging"},
            "8006": {"desc": "Compressor 1 on"},
            "8830": {"value": "45.2"},
        }

        with patch("aiohttp.ClientSession") as mock_session_class:
            mock_response_obj = AsyncMock()
            mock_response_obj.status = 200
            mock_response_obj.json = AsyncMock(return_value=mock_response)

            mock_session = MagicMock()
            mock_session.get = MagicMock(return_value=AsyncMock(__aenter__=AsyncMock(return_value=mock_response_obj)))
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            mock_session_class.return_value = mock_session

            result = await client.async_read_parameters("8003,8006,8830")

            assert result == mock_response
            assert client._consecutive_failures == 0

    @pytest.mark.asyncio
    async def test_async_read_parameters_failure(self):
        """Test parameter read failure."""
        client = BSBLanClient("192.168.1.100")

        with patch("aiohttp.ClientSession") as mock_session_class:
            mock_response_obj = AsyncMock()
            mock_response_obj.status = 500

            mock_session = MagicMock()
            mock_session.get = MagicMock(return_value=AsyncMock(__aenter__=AsyncMock(return_value=mock_response_obj)))
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            mock_session_class.return_value = mock_session

            result = await client.async_read_parameters()

            assert result == {}
            assert client._consecutive_failures == 1

    @pytest.mark.asyncio
    async def test_async_write_parameter_success(self):
        """Test successful parameter write."""
        client = BSBLanClient("192.168.1.100")

        with patch("aiohttp.ClientSession") as mock_session_class:
            mock_response_obj = AsyncMock()
            mock_response_obj.status = 200
            # BSB-LAN returns HTML on success (no ERROR in body)
            mock_response_obj.text = AsyncMock(return_value="<html>1600 set to 1</html>")

            mock_session = MagicMock()
            mock_session.get = MagicMock(return_value=AsyncMock(__aenter__=AsyncMock(return_value=mock_response_obj)))
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            mock_session_class.return_value = mock_session

            result = await client.async_write_parameter(1600, 1)

            assert result is True
            assert client._consecutive_failures == 0

    @pytest.mark.asyncio
    async def test_async_write_parameter_failure_http_error(self):
        """Test parameter write failure with HTTP error."""
        client = BSBLanClient("192.168.1.100")

        with patch("aiohttp.ClientSession") as mock_session_class:
            mock_response_obj = AsyncMock()
            mock_response_obj.status = 500

            mock_session = MagicMock()
            mock_session.get = MagicMock(return_value=AsyncMock(__aenter__=AsyncMock(return_value=mock_response_obj)))
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            mock_session_class.return_value = mock_session

            result = await client.async_write_parameter(1600, 1)

            assert result is False
            assert client._consecutive_failures == 1

    @pytest.mark.asyncio
    async def test_async_write_parameter_failure_error_in_body(self):
        """Test parameter write failure when ERROR in response body."""
        client = BSBLanClient("192.168.1.100")

        with patch("aiohttp.ClientSession") as mock_session_class:
            mock_response_obj = AsyncMock()
            mock_response_obj.status = 200
            # BSB-LAN returns HTTP 200 but with ERROR in body
            mock_response_obj.text = AsyncMock(return_value="<html>ERROR: set failed!</html>")

            mock_session = MagicMock()
            mock_session.get = MagicMock(return_value=AsyncMock(__aenter__=AsyncMock(return_value=mock_response_obj)))
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            mock_session_class.return_value = mock_session

            result = await client.async_write_parameter(1600, 1)

            assert result is False
            assert client._consecutive_failures == 1

    @pytest.mark.asyncio
    async def test_async_set_cwu_mode(self):
        """Test setting CWU mode."""
        client = BSBLanClient("192.168.1.100")

        with patch.object(client, "async_write_parameter", new_callable=AsyncMock) as mock_write:
            mock_write.return_value = True
            result = await client.async_set_cwu_mode(BSB_CWU_MODE_ON)

            mock_write.assert_called_once_with(1600, BSB_CWU_MODE_ON)
            assert result is True

    @pytest.mark.asyncio
    async def test_async_set_floor_mode(self):
        """Test setting floor mode."""
        client = BSBLanClient("192.168.1.100")

        with patch.object(client, "async_write_parameter", new_callable=AsyncMock) as mock_write:
            mock_write.return_value = True
            result = await client.async_set_floor_mode(BSB_FLOOR_MODE_AUTOMATIC)

            mock_write.assert_called_once_with(700, BSB_FLOOR_MODE_AUTOMATIC)
            assert result is True


class TestBSBLanFallbackLogic:
    """Tests for BSB-LAN primary with HA cloud fallback."""

    @pytest.fixture
    def mock_coordinator(self):
        """Create mock coordinator with BSB-LAN client."""
        hass = MagicMock()
        hass.services = MagicMock()
        hass.services.async_call = AsyncMock()
        hass.states = MagicMock()

        config = {
            "water_heater": "water_heater.test",
            "climate": "climate.test",
        }

        coordinator = CWUControllerCoordinator(hass, config)
        coordinator._bsb_client = BSBLanClient("192.168.1.100")
        return coordinator

    @pytest.mark.asyncio
    async def test_cwu_on_bsb_lan_success(self, mock_coordinator):
        """Test CWU on via BSB-LAN when available."""
        mock_coordinator._bsb_client._is_available = True

        with patch.object(mock_coordinator._bsb_client, "async_set_cwu_mode", new_callable=AsyncMock) as mock_bsb:
            mock_bsb.return_value = True

            result = await mock_coordinator._async_set_cwu_on()

            assert result is True
            assert mock_coordinator._control_source == CONTROL_SOURCE_BSB_LAN
            mock_bsb.assert_called_once_with(BSB_CWU_MODE_ON)

    @pytest.mark.asyncio
    async def test_cwu_on_bsb_lan_unavailable_fallback(self, mock_coordinator):
        """Test CWU on falls back to HA cloud when BSB-LAN unavailable."""
        # Make BSB-LAN unavailable
        for _ in range(BSB_LAN_FAILURES_THRESHOLD):
            mock_coordinator._bsb_client._handle_failure(Exception("Test"))

        with patch.object(mock_coordinator, "_async_set_water_heater_mode", new_callable=AsyncMock) as mock_ha:
            mock_ha.return_value = True

            result = await mock_coordinator._async_set_cwu_on()

            assert result is True
            assert mock_coordinator._control_source == CONTROL_SOURCE_HA_CLOUD
            mock_ha.assert_called_once_with(WH_MODE_HEAT_PUMP)

    @pytest.mark.asyncio
    async def test_cwu_on_bsb_lan_fails_fallback(self, mock_coordinator):
        """Test CWU on falls back to HA cloud when BSB-LAN call fails."""
        mock_coordinator._bsb_client._is_available = True

        with patch.object(mock_coordinator._bsb_client, "async_set_cwu_mode", new_callable=AsyncMock) as mock_bsb:
            mock_bsb.return_value = False  # BSB-LAN call fails

            with patch.object(mock_coordinator, "_async_set_water_heater_mode", new_callable=AsyncMock) as mock_ha:
                mock_ha.return_value = True

                result = await mock_coordinator._async_set_cwu_on()

                assert result is True
                assert mock_coordinator._control_source == CONTROL_SOURCE_HA_CLOUD
                mock_bsb.assert_called_once()
                mock_ha.assert_called_once_with(WH_MODE_HEAT_PUMP)

    @pytest.mark.asyncio
    async def test_cwu_off_bsb_lan_success(self, mock_coordinator):
        """Test CWU off via BSB-LAN when available."""
        mock_coordinator._bsb_client._is_available = True

        with patch.object(mock_coordinator._bsb_client, "async_set_cwu_mode", new_callable=AsyncMock) as mock_bsb:
            mock_bsb.return_value = True

            result = await mock_coordinator._async_set_cwu_off()

            assert result is True
            assert mock_coordinator._control_source == CONTROL_SOURCE_BSB_LAN
            mock_bsb.assert_called_once_with(BSB_CWU_MODE_OFF)

    @pytest.mark.asyncio
    async def test_cwu_off_fallback(self, mock_coordinator):
        """Test CWU off falls back to HA cloud."""
        for _ in range(BSB_LAN_FAILURES_THRESHOLD):
            mock_coordinator._bsb_client._handle_failure(Exception("Test"))

        with patch.object(mock_coordinator, "_async_set_water_heater_mode", new_callable=AsyncMock) as mock_ha:
            mock_ha.return_value = True

            result = await mock_coordinator._async_set_cwu_off()

            assert result is True
            assert mock_coordinator._control_source == CONTROL_SOURCE_HA_CLOUD
            mock_ha.assert_called_once_with(WH_MODE_OFF)

    @pytest.mark.asyncio
    async def test_floor_on_bsb_lan_success(self, mock_coordinator):
        """Test floor on via BSB-LAN when available."""
        mock_coordinator._bsb_client._is_available = True

        with patch.object(mock_coordinator._bsb_client, "async_set_floor_mode", new_callable=AsyncMock) as mock_bsb:
            mock_bsb.return_value = True

            result = await mock_coordinator._async_set_floor_on()

            assert result is True
            assert mock_coordinator._control_source == CONTROL_SOURCE_BSB_LAN
            mock_bsb.assert_called_once_with(BSB_FLOOR_MODE_AUTOMATIC)

    @pytest.mark.asyncio
    async def test_floor_on_fallback(self, mock_coordinator):
        """Test floor on falls back to HA cloud."""
        for _ in range(BSB_LAN_FAILURES_THRESHOLD):
            mock_coordinator._bsb_client._handle_failure(Exception("Test"))

        with patch.object(mock_coordinator, "_async_set_climate", new_callable=AsyncMock) as mock_ha:
            mock_ha.return_value = True

            result = await mock_coordinator._async_set_floor_on()

            assert result is True
            assert mock_coordinator._control_source == CONTROL_SOURCE_HA_CLOUD
            mock_ha.assert_called_once_with(True)

    @pytest.mark.asyncio
    async def test_floor_off_bsb_lan_success(self, mock_coordinator):
        """Test floor off via BSB-LAN when available."""
        mock_coordinator._bsb_client._is_available = True

        with patch.object(mock_coordinator._bsb_client, "async_set_floor_mode", new_callable=AsyncMock) as mock_bsb:
            mock_bsb.return_value = True

            result = await mock_coordinator._async_set_floor_off()

            assert result is True
            assert mock_coordinator._control_source == CONTROL_SOURCE_BSB_LAN
            mock_bsb.assert_called_once_with(BSB_FLOOR_MODE_PROTECTION)

    @pytest.mark.asyncio
    async def test_floor_off_fallback(self, mock_coordinator):
        """Test floor off falls back to HA cloud."""
        for _ in range(BSB_LAN_FAILURES_THRESHOLD):
            mock_coordinator._bsb_client._handle_failure(Exception("Test"))

        with patch.object(mock_coordinator, "_async_set_climate", new_callable=AsyncMock) as mock_ha:
            mock_ha.return_value = True

            result = await mock_coordinator._async_set_floor_off()

            assert result is True
            assert mock_coordinator._control_source == CONTROL_SOURCE_HA_CLOUD
            mock_ha.assert_called_once_with(False)


class TestBSBLanFakeHeatingDetection:
    """Tests for BSB-LAN based fake heating detection."""

    @pytest.fixture
    def mock_coordinator(self):
        """Create mock coordinator with BSB-LAN client."""
        hass = MagicMock()
        hass.services = MagicMock()
        hass.states = MagicMock()

        config = {}
        coordinator = CWUControllerCoordinator(hass, config)
        coordinator._bsb_client = BSBLanClient("192.168.1.100")
        return coordinator

    def test_no_data_returns_false(self, mock_coordinator):
        """Test no fake heating detected when BSB-LAN data unavailable."""
        mock_coordinator._bsb_lan_data = {}
        assert mock_coordinator._detect_fake_heating_bsb() is False

    def test_electric_charging_detected(self, mock_coordinator):
        """Test electric heater charging triggers fake heating."""
        mock_coordinator._bsb_lan_data = {
            "dhw_status": "Charging electric, nominal setpoint",
            "hp_status": "---",
        }
        assert mock_coordinator._detect_fake_heating_bsb() is True

    def test_electric_charging_case_insensitive(self, mock_coordinator):
        """Test electric heater detection is case insensitive."""
        mock_coordinator._bsb_lan_data = {
            "dhw_status": "CHARGING ELECTRIC",
            "hp_status": "---",
        }
        assert mock_coordinator._detect_fake_heating_bsb() is True

    def test_normal_charging_with_compressor_ok(self, mock_coordinator):
        """Test normal charging with compressor running is not fake heating."""
        mock_coordinator._bsb_lan_data = {
            "dhw_status": "Charging, nominal setpoint",
            "hp_status": "Compressor 1 on",
        }
        result = mock_coordinator._detect_fake_heating_bsb()
        assert result is False
        # Tracking should be reset
        assert mock_coordinator._bsb_dhw_charging_no_compressor_since is None

    def test_charging_no_compressor_starts_tracking(self, mock_coordinator):
        """Test charging without compressor starts time tracking."""
        mock_coordinator._bsb_lan_data = {
            "dhw_status": "Charging, nominal setpoint",
            "hp_status": "---",
        }
        mock_coordinator._bsb_dhw_charging_no_compressor_since = None

        result = mock_coordinator._detect_fake_heating_bsb()

        # Should start tracking but not trigger yet
        assert result is False
        assert mock_coordinator._bsb_dhw_charging_no_compressor_since is not None

    def test_charging_no_compressor_threshold_reached(self, mock_coordinator):
        """Test charging without compressor triggers after threshold."""
        mock_coordinator._bsb_lan_data = {
            "dhw_status": "Charging, nominal setpoint",
            "hp_status": "Frost protection",
        }
        # Set start time in the past beyond threshold
        mock_coordinator._bsb_dhw_charging_no_compressor_since = (
            datetime.now() - timedelta(minutes=BSB_FAKE_HEATING_DETECTION_TIME + 1)
        )

        result = mock_coordinator._detect_fake_heating_bsb()
        assert result is True

    def test_charging_no_compressor_under_threshold(self, mock_coordinator):
        """Test charging without compressor doesn't trigger before threshold."""
        mock_coordinator._bsb_lan_data = {
            "dhw_status": "Charging, nominal setpoint",
            "hp_status": "Pump overrun",
        }
        # Set start time just under threshold
        mock_coordinator._bsb_dhw_charging_no_compressor_since = (
            datetime.now() - timedelta(minutes=BSB_FAKE_HEATING_DETECTION_TIME - 1)
        )

        result = mock_coordinator._detect_fake_heating_bsb()
        assert result is False

    def test_ready_status_resets_tracking(self, mock_coordinator):
        """Test Ready status resets charging tracking."""
        mock_coordinator._bsb_dhw_charging_no_compressor_since = datetime.now() - timedelta(minutes=10)
        mock_coordinator._bsb_lan_data = {
            "dhw_status": "Ready",
            "hp_status": "---",
        }

        result = mock_coordinator._detect_fake_heating_bsb()

        assert result is False
        assert mock_coordinator._bsb_dhw_charging_no_compressor_since is None

    def test_compressor_starts_resets_tracking(self, mock_coordinator):
        """Test compressor starting resets tracking."""
        mock_coordinator._bsb_dhw_charging_no_compressor_since = datetime.now() - timedelta(minutes=10)
        mock_coordinator._bsb_lan_data = {
            "dhw_status": "Charging, nominal setpoint",
            "hp_status": "Compressor 1 on",
        }

        result = mock_coordinator._detect_fake_heating_bsb()

        assert result is False
        assert mock_coordinator._bsb_dhw_charging_no_compressor_since is None


class TestBSBLanTemperature:
    """Tests for BSB-LAN temperature reading with fallback."""

    @pytest.fixture
    def mock_coordinator(self):
        """Create mock coordinator."""
        hass = MagicMock()
        hass.states = MagicMock()

        config = {"cwu_temp_sensor": "sensor.cwu_temp_external"}
        coordinator = CWUControllerCoordinator(hass, config)
        coordinator._bsb_client = BSBLanClient("192.168.1.100")
        return coordinator

    def test_bsb_lan_temp_preferred(self, mock_coordinator):
        """Test BSB-LAN temperature is used when available."""
        mock_coordinator._bsb_lan_data = {"cwu_temp": 45.5}

        result = mock_coordinator._get_cwu_temperature()

        assert result == 45.5

    def test_external_sensor_fallback(self, mock_coordinator):
        """Test external sensor is used when BSB-LAN unavailable."""
        mock_coordinator._bsb_lan_data = {}

        # Mock external sensor
        mock_state = MagicMock()
        mock_state.state = "42.3"
        mock_coordinator.hass.states.get.return_value = mock_state

        result = mock_coordinator._get_cwu_temperature()

        assert result == 42.3

    def test_external_sensor_fallback_bsb_none(self, mock_coordinator):
        """Test external sensor fallback when BSB-LAN returns None temp."""
        mock_coordinator._bsb_lan_data = {"cwu_temp": None}

        mock_state = MagicMock()
        mock_state.state = "41.0"
        mock_coordinator.hass.states.get.return_value = mock_state

        result = mock_coordinator._get_cwu_temperature()

        assert result == 41.0

    def test_no_data_available(self, mock_coordinator):
        """Test None returned when no data available."""
        mock_coordinator._bsb_lan_data = {}
        mock_coordinator.hass.states.get.return_value = None

        result = mock_coordinator._get_cwu_temperature()

        assert result is None


class TestBSBLanDataRefresh:
    """Tests for BSB-LAN data refresh."""

    @pytest.fixture
    def mock_coordinator(self):
        """Create mock coordinator."""
        hass = MagicMock()
        hass.states = MagicMock()

        config = {}
        coordinator = CWUControllerCoordinator(hass, config)
        coordinator._bsb_client = BSBLanClient("192.168.1.100")
        return coordinator

    @pytest.mark.asyncio
    async def test_refresh_parses_data_correctly(self, mock_coordinator):
        """Test BSB-LAN data is parsed correctly."""
        raw_response = {
            "700": {"desc": "Automatic"},
            "1600": {"desc": "On"},
            "8000": {"desc": "Comfort"},
            "8003": {"desc": "Charging, nominal setpoint"},
            "8006": {"desc": "Compressor 1 on"},
            "8412": {"value": "35.5"},
            "8410": {"value": "32.0"},
            "8830": {"value": "45.2"},
            "8700": {"value": "-2.5"},
        }

        with patch.object(mock_coordinator._bsb_client, "async_read_parameters", new_callable=AsyncMock) as mock_read:
            mock_read.return_value = raw_response

            await mock_coordinator._async_refresh_bsb_lan_data()

            assert mock_coordinator._bsb_lan_data["floor_mode"] == "Automatic"
            assert mock_coordinator._bsb_lan_data["cwu_mode"] == "On"
            assert mock_coordinator._bsb_lan_data["hc1_status"] == "Comfort"
            assert mock_coordinator._bsb_lan_data["dhw_status"] == "Charging, nominal setpoint"
            assert mock_coordinator._bsb_lan_data["hp_status"] == "Compressor 1 on"
            assert mock_coordinator._bsb_lan_data["flow_temp"] == 35.5
            assert mock_coordinator._bsb_lan_data["return_temp"] == 32.0
            assert mock_coordinator._bsb_lan_data["cwu_temp"] == 45.2
            assert mock_coordinator._bsb_lan_data["outside_temp"] == -2.5
            assert mock_coordinator._bsb_lan_data["delta_t"] == 3.5  # 35.5 - 32.0

    @pytest.mark.asyncio
    async def test_refresh_handles_empty_response(self, mock_coordinator):
        """Test empty response clears BSB-LAN data."""
        mock_coordinator._bsb_lan_data = {"cwu_temp": 45.0}  # Pre-existing data

        with patch.object(mock_coordinator._bsb_client, "async_read_parameters", new_callable=AsyncMock) as mock_read:
            mock_read.return_value = {}

            await mock_coordinator._async_refresh_bsb_lan_data()

            assert mock_coordinator._bsb_lan_data == {}

    @pytest.mark.asyncio
    async def test_delta_t_calculation_missing_data(self, mock_coordinator):
        """Test delta T is None when flow or return temp missing."""
        raw_response = {
            "8412": {"value": "35.5"},
            # Missing 8410 (return temp)
        }

        with patch.object(mock_coordinator._bsb_client, "async_read_parameters", new_callable=AsyncMock) as mock_read:
            mock_read.return_value = raw_response

            await mock_coordinator._async_refresh_bsb_lan_data()

            assert mock_coordinator._bsb_lan_data.get("delta_t") is None


class TestWinterModeWithUnavailableTemp:
    """Tests for winter mode behavior when CWU temperature is unavailable.

    This is a critical scenario that can happen when:
    1. BSB-LAN ESP is still booting after HA restart
    2. External HA sensor is unavailable (zigbee hub not ready)
    3. Both sources return None

    The controller should enable both floor+CWU (safe mode) and let
    the heat pump decide what to heat.
    """

    @pytest.fixture
    def mock_coordinator(self):
        """Create mock coordinator in winter mode."""
        hass = MagicMock()
        hass.services = MagicMock()
        hass.states = MagicMock()

        config = {
            "cwu_temp_sensor": "sensor.cwu_temp_external",
        }
        coordinator = CWUControllerCoordinator(hass, config)
        coordinator._bsb_client = BSBLanClient("192.168.1.100")
        coordinator._operating_mode = "winter"
        return coordinator

    @pytest.mark.asyncio
    async def test_safe_mode_when_temp_unavailable_during_window(self, mock_coordinator):
        """Test that safe mode (both floor+CWU) is enabled during window when temp unknown."""
        from custom_components.cwu_controller.const import STATE_IDLE, STATE_SAFE_MODE

        mock_coordinator._current_state = STATE_IDLE
        mock_coordinator._bsb_lan_data = {}  # No BSB-LAN data

        # Mock external sensor also unavailable
        mock_coordinator.hass.states.get.return_value = None

        # Mock is_winter_cwu_heating_window to return True
        with patch.object(mock_coordinator, "is_winter_cwu_heating_window", return_value=True):
            with patch.object(mock_coordinator, "_enter_safe_mode", new_callable=AsyncMock) as mock_safe:
                await mock_coordinator._run_winter_mode_logic(
                    cwu_urgency=2,  # medium
                    floor_urgency=1,  # low
                    cwu_temp=None,  # CRITICAL: temp unavailable
                    salon_temp=20.0,
                )

                # Should have entered safe mode (both floor+CWU enabled)
                mock_safe.assert_called_once()
                assert mock_coordinator._current_state == STATE_SAFE_MODE

    @pytest.mark.asyncio
    async def test_stays_in_safe_mode_when_temp_remains_unavailable(self, mock_coordinator):
        """Test that safe mode continues if temp remains unavailable."""
        from custom_components.cwu_controller.const import STATE_SAFE_MODE

        mock_coordinator._current_state = STATE_SAFE_MODE
        mock_coordinator._bsb_lan_data = {}

        mock_coordinator.hass.states.get.return_value = None

        with patch.object(mock_coordinator, "is_winter_cwu_heating_window", return_value=True):
            with patch.object(mock_coordinator, "_enter_safe_mode", new_callable=AsyncMock) as mock_safe:
                await mock_coordinator._run_winter_mode_logic(
                    cwu_urgency=2,
                    floor_urgency=1,
                    cwu_temp=None,
                    salon_temp=20.0,
                )

                # Should NOT call enter_safe_mode again (already in safe mode)
                mock_safe.assert_not_called()
                # Should stay in safe mode
                assert mock_coordinator._current_state == STATE_SAFE_MODE

    @pytest.mark.asyncio
    async def test_safe_mode_when_temp_unavailable_outside_window(self, mock_coordinator):
        """Test that safe mode is also used outside window when temp unavailable."""
        from custom_components.cwu_controller.const import STATE_IDLE, STATE_SAFE_MODE

        mock_coordinator._current_state = STATE_IDLE
        mock_coordinator._bsb_lan_data = {}
        mock_coordinator.hass.states.get.return_value = None

        with patch.object(mock_coordinator, "is_winter_cwu_heating_window", return_value=False):
            with patch.object(mock_coordinator, "_enter_safe_mode", new_callable=AsyncMock) as mock_safe:
                await mock_coordinator._run_winter_mode_logic(
                    cwu_urgency=2,
                    floor_urgency=1,
                    cwu_temp=None,  # temp unavailable
                    salon_temp=20.0,
                )

                # Should enter safe mode (pump decides)
                mock_safe.assert_called_once()
                assert mock_coordinator._current_state == STATE_SAFE_MODE
