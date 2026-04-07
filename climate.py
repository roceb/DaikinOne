"""Climate platform for Daikin One+."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
    HVACAction,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_TEMPERATURE,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import DaikinDevice, DaikinOneApi
# from .const import (
#     DOMAIN, HVAC_MODE_MAPPING, REVERSE_HVAC_MODE_MAPPING, HVAC_ACTION_MAPPING,
#     MODE_AUTO, MODE_HEAT, MODE_COOL, MODE_EMERGENCY_HEAT,
#     FAN_MODE_AUTO, FAN_MODE_ON, FAN_MODE_CIRCULATE,
#     HOLD_NONE, HOLD_PERMANENT, HOLD_AWAY,
#     TEMP_STEP_FAHRENHEIT, TEMP_STEP_CELSIUS,
# )
from .const import (
    DOMAIN, HVAC_MODE_MAPPING, REVERSE_HVAC_MODE_MAPPING, HVAC_ACTION_MAPPING,
    MODE_OFF, MODE_AUTO,
    HOLD_NONE, HOLD_PERMANENT, HOLD_AWAY,
    MIN_DEADBAND_CELSIUS,
    MIN_TEMP_CELSIUS, MAX_TEMP_CELSIUS,
)
from .coordinator import DaikinOneDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

FAN_MODES = ["auto", "on", "circulate"]
PRESET_AWAY = "away"
PRESET_SCHEDULE = "schedule"
PRESET_MANUAL = "manual"

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    api = data["api"]
    async_add_entities([DaikinOneClimate(coordinator, api, dev_id) for dev_id in coordinator.device_ids])

class DaikinOneClimate(CoordinatorEntity[DaikinOneDataUpdateCoordinator], ClimateEntity):
    _attr_has_entity_name = True
    _attr_name = None

    def __init__(self, coordinator: DaikinOneDataUpdateCoordinator, api: DaikinOneApi, device_id: str) -> None:
        super().__init__(coordinator)
        self._api = api
        self._device_id = device_id
        self._attr_unique_id = f"{device_id}_climate"

    @property
    def _device(self) -> DaikinDevice:
        return self.coordinator.data[self._device_id]

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            name=self._device.name,
            manufacturer="Daikin",
            model=self._device.model,
        )

    @property
    def supported_features(self) -> ClimateEntityFeature:
        features = (
            ClimateEntityFeature.TARGET_TEMPERATURE
            | ClimateEntityFeature.FAN_MODE
            | ClimateEntityFeature.PRESET_MODE
            | ClimateEntityFeature.TURN_ON
            | ClimateEntityFeature.TURN_OFF
        )
        # OpenAPI docs: Heat/Cool (Auto) mode uses both setpoints
        if self._device.mode == MODE_AUTO:
            features |= ClimateEntityFeature.TARGET_TEMPERATURE_RANGE
        return features

    @property
    def temperature_unit(self) -> str:
        return UnitOfTemperature.CELSIUS

    @property
    def current_temperature(self) -> float | None:
        return self._device.current_temperature

    @property
    def target_temperature(self) -> float | None:
        """Return the temperature we try to reach."""
        if self.hvac_mode == HVACMode.HEAT:
            return self._device.heat_setpoint
        if self.hvac_mode == HVACMode.COOL:
            return self._device.cool_setpoint
        return None

    @property
    def target_temperature_high(self) -> float | None:
        return self._device.cool_setpoint if self._device.mode == MODE_AUTO else None

    @property
    def target_temperature_low(self) -> float | None:
        return self._device.heat_setpoint if self._device.mode == MODE_AUTO else None

    @property
    def hvac_mode(self) -> HVACMode:
        return HVAC_MODE_MAPPING.get(self._device.mode, HVACMode.OFF)

    @property
    def hvac_modes(self) -> list[HVACMode]:
        return [HVACMode.OFF, HVACMode.HEAT, HVACMode.COOL, HVACMode.HEAT_COOL]

    @property
    def hvac_action(self) -> HVACAction:
        status = self._device.equipment_status
        return HVAC_ACTION_MAPPING.get(status, HVACAction.IDLE)

    @property
    def fan_mode(self) -> str:
        return self._device.fan_mode

    @property
    def fan_modes(self) -> list[str]:
        return FAN_MODES

    @property
    def preset_mode(self) -> str:
        status = self._device.data.get("holdStatus")
        if status == HOLD_AWAY: return PRESET_AWAY
        if status == HOLD_NONE: return PRESET_SCHEDULE
        return PRESET_MANUAL

    @property
    def preset_modes(self) -> list[str]:
        return [PRESET_SCHEDULE, PRESET_MANUAL, PRESET_AWAY]

    @property
    def min_temp(self) -> float:
        return MIN_TEMP_CELSIUS

    @property
    def max_temp(self) -> float:
        return MAX_TEMP_CELSIUS

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set new target hvac mode."""
        daikin_mode = REVERSE_HVAC_MODE_MAPPING.get(hvac_mode, MODE_OFF)

        payload = {"mode": daikin_mode}

        await self._api.update_device(self._device_id, payload)
        await self.coordinator.async_request_refresh()

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature."""
        payload = {}
        # Get current setpoints as defaults
        current_heat = self._device.heat_setpoint
        current_cool = self._device.cool_setpoint

        if self.hvac_mode == HVACMode.HEAT_COOL:
            # Handle Range (Auto Mode)
            low = kwargs.get("target_temp_low")
            high = kwargs.get("target_temp_high")

            # If only one was provided (common in some UI interactions),
            # use the current value for the other
            target_low = low if low is not None else current_heat
            target_high = high if high is not None else current_cool

            # Enforce 5°F (2.8°C) Deadband
            if (target_high - target_low) < MIN_DEADBAND_CELSIUS:
                _LOGGER.debug("Enforcing 5F deadband for Daikin API")
                # If user moved the HEAT setpoint UP
                if low is not None and high is None:
                    target_high = round(target_low + MIN_DEADBAND_CELSIUS,1)
                # If user moved the COOL setpoint DOWN
                elif high is not None and low is None:
                    target_low = round(target_high - MIN_DEADBAND_CELSIUS,1)
                # If both changed or some other state, ensure high is at least low + deadband
                else:
                    target_high = round(target_low + MIN_DEADBAND_CELSIUS,1)

            payload["heatSetpoint"] = round(target_low,1)
            payload["coolSetpoint"] = round(target_high,1)

        elif self.hvac_mode == HVACMode.HEAT:
            if (temp := kwargs.get(ATTR_TEMPERATURE)) is not None:
                payload["heatSetpoint"] = temp
                payload["coolSetpoint"] = round(temp - MIN_DEADBAND_CELSIUS,1)
            elif (low := kwargs.get("target_temp_low")) is not None:
                payload["heatSetpoint"] = low
                payload["coolSetpoint"] = round(low - MIN_DEADBAND_CELSIUS,1)

        elif self.hvac_mode == HVACMode.COOL:
            if (temp := kwargs.get(ATTR_TEMPERATURE)) is not None:
                payload["coolSetpoint"] = temp
                payload["heatSetpoint"] = round(temp + MIN_DEADBAND_CELSIUS,1)
            elif (high := kwargs.get("target_temp_high")) is not None:
                payload["coolSetpoint"] = high
                payload["heatSetpoint"] = round(high + MIN_DEADBAND_CELSIUS,1)

        if payload:
            _LOGGER.debug("Sending temperature update to Daikin: %s", payload)
            success = await self._api.update_device(self._device_id, payload)
            if success:
                if "heatSetpoint" in payload:
                    self._device.data["heatSetpoint"] = payload["heatSetpoint"]
                if "coolSetpoint" in payload:
                    self._device.data["coolSetpoint"] = payload["coolSetpoint"]
                self.async_write_ha_state()
                _LOGGER.debug(f"Updating ui manually, {self._device.data.get("coolSetpoint")}")
            await self.coordinator.async_request_refresh()

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        fan_map = {"auto": 0, "on": 1, "circulate": 2}
        await self._api.update_device(self._device_id, {"fanMode": fan_map.get(fan_mode, 0)})
        await self.coordinator.async_request_refresh()

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        hold_map = {PRESET_SCHEDULE: HOLD_NONE, PRESET_MANUAL: HOLD_PERMANENT, PRESET_AWAY: HOLD_AWAY}
        await self._api.update_device(self._device_id, {"holdStatus": hold_map.get(preset_mode, HOLD_PERMANENT)})
        await self.coordinator.async_request_refresh()

    async def async_turn_on(self) -> None:
        await self.async_set_hvac_mode(HVACMode.HEAT_COOL)

    async def async_turn_off(self) -> None:
        await self.async_set_hvac_mode(HVACMode.OFF)
