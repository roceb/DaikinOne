from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .api import (
    DaikinOneApi,
    DaikinDevice,
    DaikinOneApiError,
    DaikinOneAuthError,
)
from .const import DOMAIN, DEFAULT_SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)


class DaikinOneDataUpdateCoordinator(DataUpdateCoordinator[dict[str, DaikinDevice]]):
    """Class to manage fetching Daikin One+ data."""

    def __init__(
        self,
        hass: HomeAssistant,
        api: DaikinOneApi,
        update_interval: int = DEFAULT_SCAN_INTERVAL,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=update_interval),
        )
        self.api = api

    async def _async_update_data(self) -> dict[str, DaikinDevice]:
        """Fetch data from API."""
        try:
            _LOGGER.debug("Fetching Daikin One+ data")
            devices_list = await self.api.get_devices()
            data ={}
            for d in devices_list:
                try:
                    detailed_dev = await self.api.get_device(d.id)
                    if detailed_dev:
                        data[detailed_dev.id] = detailed_dev
                    else:
                        data[d.id] = d
                except DaikinOneApiError as err:
                    _LOGGER.warning("Could not fetch details for %s, using summary: %s", d.id, err)
                    data[d.id] = d
            return data

        except DaikinOneAuthError as err:
            # Raise ConfigEntryAuthFailed to trigger a reauth flow
            raise ConfigEntryAuthFailed(
                f"Authentication failed: {err}"
            ) from err

        except DaikinOneApiError as err:
            raise UpdateFailed(f"Error communicating with API: {err}") from err

    def get_device(self, device_id: str) -> DaikinDevice | None:
        """Get a device by ID."""
        if self.data:
            return self.data.get(device_id)
        return None

    @property
    def device_ids(self) -> list[str]:
        """Return list of device IDs."""
        return list(self.data.keys()) if self.data else []
