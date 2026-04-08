from __future__ import annotations

import asyncio
import logging
import time
from typing import Any
from dataclasses import dataclass, field

import aiohttp
from aiohttp import ClientSession, ClientTimeout, ClientResponseError

from .const import (
    API_BASE_URL,
    API_TIMEOUT,
    SCHEDULE_MODE_AWAY,
    SCHEDULE_MODE_MANUAL,
    SCHEDULE_MODE_SCHEDULED,
)

_LOGGER = logging.getLogger(__name__)


class DaikinOneApiError(Exception):
    """Base exception for Daikin One API errors."""


class DaikinOneAuthError(DaikinOneApiError):
    """Authentication error."""


class DaikinOneConnectionError(DaikinOneApiError):
    """Connection error."""


def f_to_c(f: float) -> float:
    return (f-32) * 5/9

def c_to_f(c: float) -> float:
    return (c * 9/5) + 32

@dataclass
class DaikinDevice:
    """Representation of a Daikin device."""

    id: str
    name: str
    model: str
    firmware_version: str
    location_id: str
    data: dict[str, Any] = field(default_factory=dict)

    # Mode: 0=Off, 1=Heat, 2=Cool, 3=Auto, 4=Emergency Heat
    MODE_MAP = {0: "off", 1: "heat", 2: "cool", 3: "auto", 4: "emergency_heat"}
    MODE_MAP_REV = {v: k for k, v in MODE_MAP.items()}
    # Fan Mode: 0=Auto, 1=On, 2=Circulate
    FAN_MODE_MAP = {0: "auto", 1: "on", 2: "circulate"}
    FAN_MODE_MAP_REV = {v: k for k, v in FAN_MODE_MAP.items()}

    # Equipment Status: 0=Idle, 1=Heat, 2=Cool, 3=Fan, 4=Dehumidify
    EQUIPMENT_STATUS_MAP = {0: "idle", 1: "heating", 2: "cooling", 3: "fan", 4: "dehumidifying"}

    @property
    def is_online(self) -> bool:
        return self.data.get("isOnline", True)

    @property
    def temperature_unit(self) -> str:
        return "C" if self.data.get("tempUnit") == 1 else "F"

    @property
    def current_temperature(self) -> float | None:
        return self.data.get("tempIndoor")

    @property
    def outdoor_temperature(self) -> float | None:
        return self.data.get("tempOutdoor")

    @property
    def humidity(self) -> int | None:
        return self.data.get("humIndoor")

    @property
    def outdoor_humidity(self) -> int | None:
        return self.data.get("humOutdoor")

    @property
    def mode(self) -> str:
        return self.data.get("mode", 0)

    @property
    def supported_modes(self) -> list[int]:
        return [0,1,2,3]
    @property
    def target_temperature_heat(self) -> float | None:
        return self.heat_setpoint

    @property
    def target_temperature_cool(self) -> float | None:
        return self.cool_setpoint

    @property
    def target_temperature_high(self) -> float | None:
        return self.cool_setpoint

    @property
    def target_temperature_low(self) -> float | None:
        return self.heat_setpoint

    @property
    def heat_setpoint(self) -> float | None:
        return self.data.get("heatSetpoint")

    @property
    def cool_setpoint(self) -> float | None:
        return self.data.get("coolSetpoint")

    @property
    def fan_mode(self) -> str:
        return self.data.get("fanMode", 0)

    @property
    def equipment_status(self) -> int:
        status = self.data.get("equipmentStatus")
        if status is None:
            return 0
        try:
            return int(status)
        except (ValueError, TypeError):
            return 0

    @property
    def schedule_enabled(self) -> bool:
        # schedEnabled: 0=Off, 1=On
        return self.data.get("schedEnabled") == 1
    @property
    def schedule_mode(self) -> str:
        # Mapping API holdStatus/schedEnabled to HA presets
        # holdStatus: 0=No Hold, 1=Permanent Hold, 2=Temporary, 3=Away
        hold = self.data.get("holdStatus", 0)
        if hold == 0: return SCHEDULE_MODE_SCHEDULED
        if hold == 3: return SCHEDULE_MODE_AWAY
        return SCHEDULE_MODE_MANUAL
    @property
    def air_quality_index(self) -> int | None:
        return self.data.get("aqiIndoor")

    @property
    def filter_remaining(self) -> int | None:
        return self.data.get("filterRemaining")

    @property
    def uv_lamp_remaining(self) -> int | None:
        return self.data.get("uvLampRemaining")

    @property
    def humidifier_mode(self) -> str | None:
        # 0=Off, 1=On/Auto
        val = self.data.get("humMode")
        return "off" if val == 0 else "auto" if val is not None else None

    @property
    def dehumidifier_mode(self) -> str | None:
        val = self.data.get("dehumMode")
        return "off" if val == 0 else "auto" if val is not None else None

    @property
    def humidifier_setpoint(self) -> int | None:
        return self.data.get("spHum")

    @property
    def dehumidifier_setpoint(self) -> int | None:
        return self.data.get("spDehum")

    @property
    def has_emergency_heat(self) -> bool:
        return self.data.get("canSearchForEmergencyHeat", False)

class DaikinOneApi:
    """Daikin One+ API client."""

    def __init__(
        self,
        session: ClientSession,
        api_key: str,
        integrator_token: str,
        email: str,
    ) -> None:
        """Initialize the API client."""
        self._session = session
        self._integrator_token = integrator_token
        self._apikey = api_key
        self._email = email
        self._access_token: str | None = None
        self._token_expiry: float = 0

    @property
    def _headers(self) -> dict[str, str]:
        """Return request headers."""
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "x-api-key": self._apikey,
        }
        if self._access_token:
            headers["Authorization"] = f"Bearer {self._access_token}"
            # headers["Authorization"] = f"{self._access_token}"
        return headers

    def _is_token_expired(self) -> bool:
        """Check if the access token is expired."""
        return time.time() >= self._token_expiry

    async def _ensure_authenticated(self) -> None:
        """Ensure we have a valid access token."""
        if self._access_token is None or self._is_token_expired():
            _LOGGER.debug("Access token missing or expired, authenticating")
            await self.authenticate()

    async def _request(
        self,
        method: str,
        endpoint: str,
        data: dict[str, Any] | None = None,
        _retry_auth: bool = True,
    ) -> dict[str, Any]:
        """Make an API request."""
        await self._ensure_authenticated()

        url = f"{API_BASE_URL}{endpoint}"
        timeout = ClientTimeout(total=API_TIMEOUT)

        try:
            async with self._session.request(
                method,
                url,
                headers=self._headers,
                json=data,
                timeout=timeout,
            ) as response:
                res_text = await response.text()
                _LOGGER.debug(
                    f"Auth response status: {response.status}, body: {res_text[:500]}"
                    )
                if response.status == 401:  # ONLY retry on 401
                    if _retry_auth:
                        _LOGGER.debug("Received 401 from API, re-authenticating")
                        self._access_token = None
                        await self.authenticate()
                        return await self._request(method, endpoint, data, _retry_auth=False)
                if response.status == 403:
                    # Get the error body to see WHY it is forbidden
                    error_body = await response.text()
                    _LOGGER.error("Action Forbidden (403): %s", error_body)
                    raise DaikinOneAuthError(f"Forbidden: {error_body}")
                response.raise_for_status()

                if response.content_type == "application/json":
                    return await response.json()
                return {}

        except DaikinOneApiError:
            # Re-raise our own exceptions as-is
            raise
        except aiohttp.ClientConnectionError as err:
            raise DaikinOneConnectionError(f"Connection error: {err}") from err
        except asyncio.TimeoutError as err:
            raise DaikinOneConnectionError("Connection timeout") from err
        except ClientResponseError as err:
            raise DaikinOneApiError(f"API error: {err}") from err

    async def authenticate(self) -> bool:
        """Authenticate with the API."""
        try:
            url = f"{API_BASE_URL}/token"

            headers = {
                "Content-Type": "application/json",
                "x-api-key": self._apikey,
            }

            _LOGGER.debug("Authenticating with Daikin One+ API for %s", self._email)

            async with self._session.post(
                url,
                headers=headers,
                json={"email": self._email, "integratorToken": self._integrator_token},
                timeout=ClientTimeout(total=API_TIMEOUT)
            ) as response:
                response_text = await response.text()
                _LOGGER.debug(
                    "Auth response status: %s, body: %s",
                    response.status,
                    response_text[:500],
                )

                if response.status in (401, 403):
                    raise DaikinOneAuthError(
                        f"Invalid credentials (HTTP {response.status}): {response_text[:200]}"
                    )

                response.raise_for_status()

                result = await response.json(content_type=None)

                self._access_token = result.get("accessToken")
                expires_in = result.get("accessTokenExpiresIn", 3600)
                self._token_expiry = time.time() + expires_in - 60

                _LOGGER.debug(
                    "Authentication successful, token expires in %s seconds",
                    expires_in,
                )

                return self._access_token is not None

        except aiohttp.ClientConnectionError as err:
            _LOGGER.error("Connection error during auth: %s", err)
            raise DaikinOneConnectionError(f"Connection error: {err}") from err
        except asyncio.TimeoutError as err:
            _LOGGER.error("Timeout during auth")
            raise DaikinOneConnectionError("Connection timeout") from err
        except ClientResponseError as err:
            if err.status in (401, 403):
                raise DaikinOneAuthError(f"Invalid integrator token (HTTP {err.status})") from err
            raise DaikinOneApiError(f"API error: {err}") from err

    async def set_schedule_mode(self, device_id: str, mode: str) -> bool:
        """Set schedule mode."""
        hold_status_map = {
        "manual": "permanent",
        "scheduled": "off",
        "away": "away",
        "vacation": "vacation",
        }
        hold_status = hold_status_map.get(mode, "permanent")
        return await self.set_hold_status(device_id, hold_status)

    async def get_devices(self) -> list[DaikinDevice]:
        """Get devices for a location."""

        response = await self._request("GET", "/devices")
        devices = []

        for location_data in response:
            location = location_data.get("locationName", "Unknown")
            for d in location_data.get("devices", []):
                dev_id = d.get("id") or d.get("deviceId")
                if not dev_id:
                    continue
                device = DaikinDevice(
                    id=dev_id,
                    name=d.get("name", "Thermostat"),
                    model=d.get("model", "Daikin One+"),
                    firmware_version=d.get("firmwareVersion", ""),
                    location_id=location,
                    data=d,
                )
                devices.append(device)

        return devices



    async def get_device(self, device_id: str) -> DaikinDevice | None:
        """Get a specific device."""
        try:
            response = await self._request("GET", f"/devices/{device_id}")
            device_data = response

            return DaikinDevice(
                id=device_data.get("deviceId", device_data.get("id", device_id)),
                name=device_data.get("name", "Thermostat"),
                model=device_data.get("model", "Daikin One+"),
                firmware_version=device_data.get("firmwareVersion", ""),
                location_id=device_data.get("locationId", ""),
                data=device_data,
            )
        except DaikinOneApiError as err:
            _LOGGER.error("Failed to get device %s: %s", device_id, err)
            return None

    async def get_device_data(self, device_id: str) -> dict[str, Any]:
        """Get device data/status."""
        response = await self._request("GET", f"/devices/{device_id}")
        return response

    async def set_device_data(
        self, device_id: str, data: dict[str, Any]
    ) -> bool:
        """Set device data."""
        try:
            await self._request("PUT", f"/devices/{device_id}/msp", data=data)
            return True
        except DaikinOneApiError as err:
            _LOGGER.error("Failed to set device data: %s", err)
            return False

    async def update_device(self, device_id: str, data: dict[str, Any]) -> bool:
        """Update device state using PUT."""
        # Get the device to check its native unit
        device = await self.get_device(device_id)
        if not device: return False
        payload = {}
        # Preserve existing mode/fan if not provided
        payload["mode"] = data.get("mode", device.data.get("mode"))
        # payload["fanMode"] = data.get("fanMode", device.data.get("fanMode"))
        h_set = data.get("heatSetpoint", data.get("spHeat", device.data.get("heatSetpoint")))
        c_set = data.get("coolSetpoint", data.get("spCool", device.data.get("coolSetpoint")))
        # _LOGGER.error(f"This is the temp heat {h_set} and the cool {c_set}")
        if h_set is not None:
            payload["heatSetpoint"] = round(float(h_set), 1)
        if c_set is not None:
            payload["coolSetpoint"] = round(float(c_set), 1)
        if "holdStatus" in data:
            payload["holdStatus"] = data["holdStatus"]

        _LOGGER.debug(f"This is the payload to Daikin: {payload}")
        await self._request("PUT", f"/devices/{device_id}/msp", data=payload)
        return True

    async def set_mode(self, device_id: str, mode_int: int) -> bool:
        return await self.update_device(device_id, {"mode": mode_int})

    async def set_heat_setpoint(self, device_id: str, temp: float) -> bool:
        return await self.update_device(device_id, {"heatSetpoint": temp})

    async def set_cool_setpoint(self, device_id: str, temp: float) -> bool:
        return await self.update_device(device_id, {"coolSetpoint": temp})

    async def set_fan_mode(self, device_id: str, fan_mode_int: int) -> bool:
        return await self.update_device(device_id, {"fanMode": fan_mode_int})

    async def set_hold_status(self, device_id: str, hold_status: int) -> bool:
        """Set hold status: 0=Schedule, 1=Permanent, 3=Away."""
        return await self.update_device(device_id, {"holdStatus": hold_status})

    async def set_humidifier_mode(self, device_id: str, mode_int: int) -> bool:
        """0=Off, 1=On/Auto."""
        return await self.update_device(device_id, {"humMode": mode_int})

    async def set_dehumidifier_mode(self, device_id: str, mode_int: int) -> bool:
        """0=Off, 1=On/Auto."""
        return await self.update_device(device_id, {"dehumMode": mode_int})
    # Helper methods with correct integer mapping
    async def set_humidifier_setpoint(self, device_id: str, setpoint: int) -> bool:
        """Set humidifier setpoint."""
        return await self.set_device_data(
            device_id, {"ctSystemHumidifierRequestedHumidity": setpoint}
        )

    async def set_dehumidifier_setpoint(self, device_id: str, setpoint: int) -> bool:
        """Set dehumidifier setpoint."""
        return await self.set_device_data(
            device_id, {"ctSystemDehumidifierRequestedHumidity": setpoint}
        )
