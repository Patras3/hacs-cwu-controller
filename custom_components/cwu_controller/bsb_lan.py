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
    BSB_LAN_STATE_VERIFY_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)


class BSBLanClient:
    """BSB-LAN communication client with health tracking."""

    def __init__(self, host: str) -> None:
        """Initialize BSB-LAN client."""
        self.host = host
        _LOGGER.info("BSB-LAN client initialized for host: %s", host)

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
        """Read multiple parameters in one batch request.

        Args:
            params: Comma-separated parameter IDs (e.g., "8003,8006,8830").
                   If None, uses default BSB_LAN_READ_PARAMS.

        Returns:
            Raw JSON response from BSB-LAN or empty dict on failure.
        """
        if params is None:
            params = BSB_LAN_READ_PARAMS

        url = f"http://{self.host}/JQ={params}"
        try:
            timeout = aiohttp.ClientTimeout(total=BSB_LAN_READ_TIMEOUT)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        data = await response.json()
                        self._handle_success()
                        return data
                    else:
                        self._handle_failure(Exception(f"HTTP {response.status}"))
                        return {}
        except asyncio.TimeoutError:
            self._handle_failure(Exception("Timeout"))
            return {}
        except aiohttp.ClientError as e:
            self._handle_failure(e)
            return {}
        except Exception as e:
            self._handle_failure(e)
            return {}

    async def async_write_parameter(self, param: int, value: int) -> bool:
        """Write a single parameter value.

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
        try:
            timeout = aiohttp.ClientTimeout(total=BSB_LAN_WRITE_TIMEOUT)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        # BSB-LAN returns HTML - check for error message in body
                        body = await response.text()
                        if "ERROR" in body:
                            self._handle_failure(Exception(f"BSB-LAN set failed for {param}={value}"))
                            return False
                        self._handle_success()
                        return True
                    else:
                        self._handle_failure(Exception(f"HTTP {response.status}"))
                        return False
        except asyncio.TimeoutError:
            self._handle_failure(Exception("Timeout"))
            return False
        except aiohttp.ClientError as e:
            self._handle_failure(e)
            return False
        except Exception as e:
            self._handle_failure(e)
            return False

    async def async_set_cwu_mode(self, mode: int) -> bool:
        """Set CWU mode (0=Off, 1=On, 2=Eco)."""
        return await self.async_write_parameter(BSB_LAN_PARAM_CWU_MODE, mode)

    async def async_set_floor_mode(self, mode: int) -> bool:
        """Set floor heating mode (0=Protection, 1=Automatic)."""
        return await self.async_write_parameter(BSB_LAN_PARAM_FLOOR_MODE, mode)

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
                    "BSB-LAN marked UNAVAILABLE after %d consecutive failures - falling back to HA cloud",
                    self._consecutive_failures
                )
