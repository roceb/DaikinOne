"""Config flow for Daikin One+."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import DaikinOneApi, DaikinOneApiError, DaikinOneAuthError, DaikinOneConnectionError
from .const import (
    DOMAIN,
    CONF_INTEGRATOR_TOKEN,
    CONF_EMAIL,
    CONF_API_KEY,
    DEFAULT_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_EMAIL): str,
        vol.Required(CONF_API_KEY): str,
        vol.Required(CONF_INTEGRATOR_TOKEN): str,
    }
)


async def validate_input(
    hass: HomeAssistant, data: dict[str, Any]
) -> dict[str, Any]:
    """Validate the user input allows us to connect."""
    session = async_get_clientsession(hass)

    api = DaikinOneApi(
        session=session,
        integrator_token=data[CONF_INTEGRATOR_TOKEN],
        api_key=data[CONF_API_KEY],
        email=data[CONF_EMAIL],
    )

    _LOGGER.debug("Validating Daikin One+ credentials for %s", data[CONF_EMAIL])

    if not await api.authenticate():
        raise DaikinOneAuthError("Invalid credentials")

    _LOGGER.debug("Authentication successful, fetching locations")

    try:
        devices = await api.get_devices()
        _LOGGER.debug("Found %d devices", len(devices) if devices else 0)
    except DaikinOneApiError as err:
        _LOGGER.warning("Authenticated but failed to fetch devices: %s", err)
        devices = []

    devices_count = len(devices) if devices else 0
    return {
        "title": f"Daikin One+ ({devices_count} device(s))",
    }


class DaikinOneConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Daikin One+."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            _LOGGER.debug(
                "Config flow user step received input for %s",
                user_input.get(CONF_EMAIL),
            )

            try:
                info = await validate_input(self.hass, user_input)
            except DaikinOneAuthError as err:
                _LOGGER.error("Authentication failed: %s", err)
                errors["base"] = "invalid_auth"
            except DaikinOneConnectionError as err:
                _LOGGER.error("Connection error during setup: %s", err)
                errors["base"] = "cannot_connect"
            except DaikinOneApiError as err:
                _LOGGER.error("API error during setup: %s", err)
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected exception during config flow")
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(user_input[CONF_EMAIL].lower())
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=info["title"],
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_import(
        self, import_data: dict[str, Any]
    ) -> FlowResult:
        """Handle import from configuration.yaml."""
        _LOGGER.info(
            "Importing Daikin One+ config from YAML for %s",
            import_data.get(CONF_EMAIL),
        )

        await self.async_set_unique_id(import_data[CONF_EMAIL].lower())
        self._abort_if_unique_id_configured()

        try:
            info = await validate_input(self.hass, import_data)
        except DaikinOneAuthError:
            _LOGGER.error(
                "Invalid Daikin One+ credentials in configuration.yaml"
            )
            return self.async_abort(reason="invalid_auth")
        except (DaikinOneConnectionError, DaikinOneApiError) as err:
            _LOGGER.error(
                "Cannot connect to Daikin One+ API from configuration.yaml: %s",
                err,
            )
            return self.async_abort(reason="cannot_connect")
        except Exception:
            _LOGGER.exception(
                "Unexpected error importing Daikin One+ YAML configuration"
            )
            return self.async_abort(reason="unknown")

        data = {
            CONF_EMAIL: import_data[CONF_EMAIL],
            CONF_API_KEY: import_data[CONF_API_KEY],
            CONF_INTEGRATOR_TOKEN: import_data[CONF_INTEGRATOR_TOKEN],
        }

        options = {}
        if CONF_SCAN_INTERVAL in import_data:
            options[CONF_SCAN_INTERVAL] = import_data[CONF_SCAN_INTERVAL]

        _LOGGER.info("Successfully importing Daikin One+ YAML config")

        return self.async_create_entry(
            title=info["title"],
            data=data,
            options=options,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> DaikinOneOptionsFlow:
        """Get the options flow for this handler."""
        return DaikinOneOptionsFlow(config_entry)


class DaikinOneOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for Daikin One+."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_SCAN_INTERVAL,
                        default=self.config_entry.options.get(
                            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                        ),
                    ): vol.All(
                        vol.Coerce(int), vol.Range(min=MIN_SCAN_INTERVAL)
                    ),
                }
            ),
        )
