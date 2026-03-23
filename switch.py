"""Switch platform for Daikin One+."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import DaikinDevice, DaikinOneApi
from .const import (
    DOMAIN,
    SCHEDULE_MODE_SCHEDULED,
    SCHEDULE_MODE_AWAY,
    HOLD_NONE,HOLD_AWAY,FAN_MODE_CIRCULATE,FAN_MODE_AUTO, HOLD_PERMANENT
)
from .coordinator import DaikinOneDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


SWITCH_DESCRIPTIONS: tuple[SwitchEntityDescription, ...] = (
    SwitchEntityDescription(
        key="schedule_enabled",
        name="Schedule",
        icon="mdi:calendar-clock",
    ),
    SwitchEntityDescription(
        key="away_mode",
        name="Away Mode",
        icon="mdi:home-export-outline",
    ),
    SwitchEntityDescription(
        key="humidifier",
        name="Humidifier",
        icon="mdi:water",
    ),
    SwitchEntityDescription(
        key="dehumidifier",
        name="Dehumidifier",
        icon="mdi:water-off",
    ),
    SwitchEntityDescription(
        key="fan_circulate",
        name="Fan Circulate",
        icon="mdi:fan",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Daikin One+ switch entities."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator: DaikinOneDataUpdateCoordinator = data["coordinator"]
    api: DaikinOneApi = data["api"]

    entities: list[DaikinOneSwitch] = []

    for device_id in coordinator.device_ids:
        device = coordinator.get_device(device_id)
        if device:
            for description in SWITCH_DESCRIPTIONS:
                if _has_switch_feature(device, description.key):
                    entities.append(
                        DaikinOneSwitch(coordinator, api, device_id, description)
                    )

    async_add_entities(entities)


def _has_switch_feature(device: DaikinDevice, key: str) -> bool:
    """Check if device supports the switch feature."""
    if key in ("schedule_enabled", "away_mode"):
        return True  # All devices support schedule

    if key == "humidifier":
        return device.humidifier_mode is not None

    if key == "dehumidifier":
        return device.dehumidifier_mode is not None

    if key == "fan_circulate":
        return True  # All devices support fan control

    return False


class DaikinOneSwitch(CoordinatorEntity[DaikinOneDataUpdateCoordinator], SwitchEntity):
    """Representation of a Daikin One+ switch."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: DaikinOneDataUpdateCoordinator,
        api: DaikinOneApi,
        device_id: str,
        description: SwitchEntityDescription,
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator)
        self._api = api
        self._device_id = device_id
        self.entity_description = description
        self._attr_unique_id = f"{device_id}_{description.key}"

    @property
    def _device(self) -> DaikinDevice | None:
        """Return the device."""
        return self.coordinator.get_device(self._device_id)

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        device = self._device
        return DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            name=device.name if device else "Daikin One+",
            manufacturer="Daikin",
            model=device.model if device else "One+",
            sw_version=device.firmware_version if device else None,
        )

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        device = self._device
        return device is not None and device.is_online

    @property
    def is_on(self) -> bool | None:
        """Return true if the switch is on."""
        device = self._device
        if not device:
            return None

        key = self.entity_description.key

        if key == "schedule_enabled":
            return device.schedule_mode == SCHEDULE_MODE_SCHEDULED

        if key == "away_mode":
            return device.schedule_mode == SCHEDULE_MODE_AWAY

        if key == "humidifier":
            humidifier_mode = device.humidifier_mode
            return humidifier_mode is not None and humidifier_mode != "off"

        if key == "dehumidifier":
            dehumidifier_mode = device.dehumidifier_mode
            return dehumidifier_mode is not None and dehumidifier_mode != "off"

        if key == "fan_circulate":
            return device.fan_mode == "circulate"

        return None
    async def async_turn_on(self, **kwargs: Any) -> None:
        key = self.entity_description.key
        success = False
        if key == "schedule_enabled":
            success = await self._api.set_hold_status(self._device_id, HOLD_NONE)
        elif key == "away_mode":
            success = await self._api.set_hold_status(self._device_id, HOLD_AWAY)
        elif key == "humidifier":
            success = await self._api.set_humidifier_mode(self._device_id, 1)
        elif key == "dehumidifier":
            success = await self._api.set_dehumidifier_mode(self._device_id, 1)
        elif key == "fan_circulate":
            success = await self._api.set_fan_mode(self._device_id, FAN_MODE_CIRCULATE)

        if success:
            await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        key = self.entity_description.key
        if key == "schedule_enabled":
            success = await self._api.set_hold_status(self._device_id, HOLD_PERMANENT)
        elif key == "away_mode":
            success = await self._api.set_hold_status(self._device_id, HOLD_NONE)
        elif key == "humidifier":
            success = await self._api.set_humidifier_mode(self._device_id, 0)
        elif key == "dehumidifier":
            success = await self._api.set_dehumidifier_mode(self._device_id, 0)
        elif key == "fan_circulate":
            success = await self._api.set_fan_mode(self._device_id, FAN_MODE_AUTO)

        if success:
            await self.coordinator.async_request_refresh()
