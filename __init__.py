from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, SOURCE_IMPORT
from homeassistant.const import Platform, CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.typing import ConfigType

from .api import DaikinOneApi, DaikinOneAuthError, DaikinOneConnectionError
from .const import (
    CONF_EMAIL,
    DOMAIN,
    CONF_INTEGRATOR_TOKEN,
    CONF_API_KEY,
    DEFAULT_SCAN_INTERVAL,
)
from .coordinator import DaikinOneDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.CLIMATE,
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.SWITCH,
]

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Required(CONF_EMAIL): cv.string,
                vol.Required(CONF_API_KEY): cv.string,
                vol.Required(CONF_INTEGRATOR_TOKEN): cv.string,
                vol.Optional(
                    CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL
                ): vol.All(vol.Coerce(int), vol.Range(min=30)),
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up Daikin One+ from YAML configuration."""
    _LOGGER.debug("Daikin One+: async_setup called")
    hass.data.setdefault(DOMAIN, {})

    if DOMAIN not in config:
        _LOGGER.debug("Daikin One+: No YAML configuration found")
        return True

    conf = config[DOMAIN]
    _LOGGER.debug("Daikin One+: Found YAML configuration for %s", conf[CONF_EMAIL])

    # Check if already configured via UI
    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.data.get(CONF_EMAIL) == conf[CONF_EMAIL]:
            _LOGGER.debug(
                "Daikin One+ already configured for %s, skipping YAML import",
                conf[CONF_EMAIL],
            )
            return True

    _LOGGER.info("Importing Daikin One+ configuration from YAML")

    hass.async_create_task(
        hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_IMPORT},
            data={
                CONF_EMAIL: conf[CONF_EMAIL],
                CONF_API_KEY: conf[CONF_API_KEY],
                CONF_INTEGRATOR_TOKEN: conf[CONF_INTEGRATOR_TOKEN],
                CONF_SCAN_INTERVAL: conf.get(
                    CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                ),
            },
        )
    )

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Daikin One+ from a config entry."""
    _LOGGER.debug("Daikin One+: Setting up config entry %s", entry.entry_id)
    hass.data.setdefault(DOMAIN, {})

    session = async_get_clientsession(hass)

    api = DaikinOneApi(
        session=session,
        integrator_token=entry.data[CONF_INTEGRATOR_TOKEN],
        api_key=entry.data[CONF_API_KEY],
        email=entry.data[CONF_EMAIL],
    )

    try:
        if not await api.authenticate():
            raise ConfigEntryAuthFailed(
                "Failed to authenticate with Daikin One+ API"
            )
    except DaikinOneAuthError as err:
        raise ConfigEntryAuthFailed(str(err)) from err
    except DaikinOneConnectionError as err:
        raise ConfigEntryNotReady(str(err)) from err
    except Exception as err:
        _LOGGER.exception("Unexpected error during Daikin One+ setup")
        raise ConfigEntryNotReady(f"Unexpected error: {err}") from err

    scan_interval = entry.options.get(
        CONF_SCAN_INTERVAL,
        entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
    )
    coordinator = DaikinOneDataUpdateCoordinator(hass, api, scan_interval)

    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception as err:
        _LOGGER.error("Failed first data refresh: %s", err)
        raise ConfigEntryNotReady(f"Failed to fetch initial data: {err}") from err

    hass.data[DOMAIN][entry.entry_id] = {
        "api": api,
        "coordinator": coordinator,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(async_update_options))

    _LOGGER.debug("Daikin One+: Setup complete for %s", entry.entry_id)
    return True


async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Update options."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(
        entry, PLATFORMS
    ):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry."""
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)
