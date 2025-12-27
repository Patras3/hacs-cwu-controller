"""BSB-LAN communication client for CWU Controller."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any

import aiohttp

from .const import (
    BSB_LAN_READ_TIMEOUT,
    BSB_LAN_WRITE_TIMEOUT,
    BSB_LAN_FAILURES_THRESHOLD,
    BSB_LAN_READ_PARAMS,
    BSB_LAN_PARAM_CWU_MODE,
    BSB_LAN_PARAM_FLOOR_MODE,
    BSB_LAN_PARAM_CWU_TARGET_NOMINAL,
    BSB_LAN_CWU_MAX_TEMP,
    BSB_LAN_STATE_VERIFY_INTERVAL,
    MANUAL_HEAT_TO_MIN_TEMP,
)

_LOGGER = logging.getLogger(__name__)


class BSBLanClient:
    """BSB-LAN communication client with health tracking."""

    def __init__(self, host: str) -> None:
        """Initialize BSB-LAN client."""
        self.host = host
        _LOGGER.info("BSB-LAN client initialized for host: %s", host)

        # Request serialization - BSB-LAN handles only one request at a time
        self._request_lock: asyncio.Lock = asyncio.Lock()

        # Health tracking
        self._consecutive_failures: int = 0
        self._last_success: datetime | None = None
        self._last_failure: datetime | None = None
        self._is_available: bool = True
        self._first_connection: bool = True

    @property
    def is_available(self) -> bool:
        """Return if BSB-LAN is considered available."""
        return self._is_available and self._consecutive_failures < BSB_LAN_FAILURES_THRESHOLD

    @property
    def last_success(self) -> datetime | None:
        """Return last successful communication time."""
        return self._last_success

    @property
    def last_failure(self) -> datetime | None:
        """Return last failed communication time."""
        return self._last_failure

    @property
    def consecutive_failures(self) -> int:
        """Return number of consecutive failures."""
        return self._consecutive_failures

    async def async_read_parameters(self, params: str | None = None) -> dict[str, Any]:
        """Read multiple parameters in one batch request with retry.

        Args:
            params: Comma-separated parameter IDs (e.g., "8003,8006,8830").
                   If None, uses default BSB_LAN_READ_PARAMS.

        Returns:
            Raw JSON response from BSB-LAN or empty dict on failure.
        """
        if params is None:
            params = BSB_LAN_READ_PARAMS

        url = f"http://{self.host}/JQ={params}"
        max_retries = 3
        retry_delay = 1.0  # seconds

        # Serialize requests - BSB-LAN handles only one request at a time
        async with self._request_lock:
            last_error = None
            for attempt in range(max_retries):
                try:
                    timeout = aiohttp.ClientTimeout(total=BSB_LAN_READ_TIMEOUT)
                    async with aiohttp.ClientSession(timeout=timeout) as session:
                        async with session.get(url) as response:
                            if response.status == 200:
                                data = await response.json()
                                if attempt > 0:
                                    _LOGGER.info(f"BSB-LAN read succeeded on retry {attempt + 1}")
                                self._handle_success()
                                return data
                            else:
                                last_error = Exception(f"HTTP {response.status}")
                except asyncio.TimeoutError:
                    last_error = Exception("Timeout")
                except aiohttp.ClientError as e:
                    last_error = e
                except Exception as e:
                    last_error = e

                # Retry if not last attempt
                if attempt < max_retries - 1:
                    _LOGGER.debug(f"BSB-LAN read failed (attempt {attempt + 1}/{max_retries}): {last_error}, retrying in {retry_delay}s...")
                    await asyncio.sleep(retry_delay)

            # All retries failed
            self._handle_failure(last_error)
            return {}

    async def async_write_parameter(self, param: int, value: int) -> bool:
        """Write a single parameter value with retry.

        Args:
            param: Parameter ID (e.g., 1600 for CWU mode).
            value: Value to set.

        Returns:
            True if successful, False otherwise.

        Note:
            BSB-LAN returns HTTP 200 even on errors, with error message in HTML body.
            We check for "ERROR" in response to detect failures.
        """
        url = f"http://{self.host}/S{param}={value}"
        max_retries = 3
        retry_delay = 1.0  # seconds

        # Serialize requests - BSB-LAN handles only one request at a time
        async with self._request_lock:
            last_error = None
            for attempt in range(max_retries):
                try:
                    timeout = aiohttp.ClientTimeout(total=BSB_LAN_WRITE_TIMEOUT)
                    async with aiohttp.ClientSession(timeout=timeout) as session:
                        async with session.get(url) as response:
                            if response.status == 200:
                                # BSB-LAN returns HTML - check for error message in body
                                body = await response.text()
                                if "ERROR" in body:
                                    last_error = Exception(f"BSB-LAN set failed for {param}={value}")
                                else:
                                    if attempt > 0:
                                        _LOGGER.info(f"BSB-LAN write succeeded on retry {attempt + 1}")
                                    self._handle_success()
                                    return True
                            else:
                                last_error = Exception(f"HTTP {response.status}")
                except asyncio.TimeoutError:
                    last_error = Exception("Timeout")
                except aiohttp.ClientError as e:
                    last_error = e
                except Exception as e:
                    last_error = e

                # Retry if not last attempt
                if attempt < max_retries - 1:
                    _LOGGER.debug(f"BSB-LAN write failed (attempt {attempt + 1}/{max_retries}): {last_error}, retrying in {retry_delay}s...")
                    await asyncio.sleep(retry_delay)

            # All retries failed
            self._handle_failure(last_error)
            return False

    async def async_set_cwu_mode(self, mode: int) -> bool:
        """Set CWU mode (0=Off, 1=On, 2=Eco)."""
        return await self.async_write_parameter(BSB_LAN_PARAM_CWU_MODE, mode)

    async def async_set_floor_mode(self, mode: int) -> bool:
        """Set floor heating mode (0=Protection, 1=Automatic)."""
        return await self.async_write_parameter(BSB_LAN_PARAM_FLOOR_MODE, mode)

    async def async_set_cwu_target_temp(self, temp: float) -> bool:
        """Set CWU target temperature (param 1610).

        Args:
            temp: Target temperature in °C (36-55).

        Returns:
            True if successful, False otherwise.
        """
        if temp < MANUAL_HEAT_TO_MIN_TEMP or temp > BSB_LAN_CWU_MAX_TEMP:
            _LOGGER.warning(
                "CWU target temp %s°C out of range (%s-%s°C)",
                temp, MANUAL_HEAT_TO_MIN_TEMP, BSB_LAN_CWU_MAX_TEMP
            )
            return False
        return await self.async_write_parameter(BSB_LAN_PARAM_CWU_TARGET_NOMINAL, int(temp))

    async def async_write_and_verify(
        self, param: int, value: int, verify_delay: float = 1.0
    ) -> tuple[bool, str]:
        """Write a parameter and verify it was set correctly.

        Args:
            param: Parameter ID to write.
            value: Value to set.
            verify_delay: Seconds to wait before verification read.

        Returns:
            Tuple of (success: bool, message: str).
            If verification fails, message contains the error details.
        """
        # Write the value
        write_success = await self.async_write_parameter(param, value)
        if not write_success:
            return (False, f"Write failed for param {param}={value}")

        # Wait before verification
        await asyncio.sleep(verify_delay)

        # Read back to verify
        read_data = await self.async_read_parameters(str(param))
        if not read_data:
            return (False, f"Verification read failed for param {param}")

        # Parse the actual value
        param_data = read_data.get(str(param), {})
        actual_value = param_data.get("value")

        if actual_value is None:
            return (False, f"No value in response for param {param}")

        # Compare (allow for float/int differences)
        try:
            if abs(float(actual_value) - float(value)) > 0.5:
                return (
                    False,
                    f"Param {param}: expected {value}, got {actual_value}"
                )
        except (ValueError, TypeError):
            # For non-numeric values, do string comparison
            if str(actual_value) != str(value):
                return (
                    False,
                    f"Param {param}: expected {value}, got {actual_value}"
                )

        return (True, f"Param {param}={value} verified OK")

    def _handle_success(self) -> None:
        """Called after successful communication."""
        was_unavailable = not self._is_available
        self._consecutive_failures = 0
        self._last_success = datetime.now()
        if self._first_connection:
            self._first_connection = False
            _LOGGER.info("BSB-LAN first connection successful to %s", self.host)
        if was_unavailable:
            self._is_available = True
            _LOGGER.info("BSB-LAN connection restored after being unavailable")

    def _handle_failure(self, error: Exception) -> None:
        """Called after failed communication."""
        self._consecutive_failures += 1
        self._last_failure = datetime.now()

        if self._first_connection:
            _LOGGER.warning(
                "BSB-LAN first connection FAILED to %s: %s (attempt %d/%d)",
                self.host, error, self._consecutive_failures, BSB_LAN_FAILURES_THRESHOLD
            )
        else:
            _LOGGER.warning(
                "BSB-LAN failure %d/%d: %s",
                self._consecutive_failures,
                BSB_LAN_FAILURES_THRESHOLD,
                error
            )

        if self._consecutive_failures >= BSB_LAN_FAILURES_THRESHOLD:
            if self._is_available:
                self._is_available = False
                _LOGGER.error(
                    "BSB-LAN marked UNAVAILABLE after %d consecutive failures - safe mode may activate",
                    self._consecutive_failures
                )
