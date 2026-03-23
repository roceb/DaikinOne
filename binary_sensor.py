"""Binary sensor platform for Daikin One+."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import DaikinDevice
from .const import (
    DOMAIN,
    EQUIPMENT_STATUS_COOLING,
    EQUIPMENT_STATUS_HEATING,
    EQUIPMENT_STATUS_FAN,
)
from .coordinator import DaikinOneDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


BINARY_SENSOR_DESCRIPTIONS: tuple[BinarySensorEntityDescription, ...] = (
    BinarySensorEntityDescription(
        key="online",
        name="Online",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    BinarySensorEntityDescription(
        key="cooling",
        name="Cooling",
        device_class=BinarySensorDeviceClass.RUNNING,
        icon="mdi:snowflake",
    ),
    BinarySensorEntityDescription(
        key="heating",
        name="Heating",
        device_class=BinarySensorDeviceClass.RUNNING,
        icon="mdi:fire",
    ),
    BinarySensorEntityDescription(
        key="fan_running",
        name="Fan Running",
        device_class=BinarySensorDeviceClass.RUNNING,
        icon="mdi:fan",
    ),
    BinarySensorEntityDescription(
        key="has_alert",
        name="Alert Active",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    BinarySensorEntityDescription(
        key="filter_alert",
        name="Filter Alert",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:air-filter",
    ),
    BinarySensorEntityDescription(
        key="humidifier_active",
        name="Humidifier Active",
        device_class=BinarySensorDeviceClass.RUNNING,
        icon="mdi:water",
    ),
    BinarySensorEntityDescription(
        key="dehumidifier_active",
        name="Dehumidifier Active",
        device_class=BinarySensorDeviceClass.RUNNING,
        icon="mdi:water-off",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Daikin One+ binary sensor entities."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator: DaikinOneDataUpdateCoordinator = data["coordinator"]

    entities: list[DaikinOneBinarySensor] = []

    for device_id in coordinator.device_ids:
        device = coordinator.get_device(device_id)
        if device:
            for description in BINARY_SENSOR_DESCRIPTIONS:
                # Always add connectivity sensor, check availability for others
                if description.key == "online" or _has_binary_sensor_data(device, description.key):
                    entities.append(
                        DaikinOneBinarySensor(coordinator, device_id, description)
                    )

    async_add_entities(entities)


def _has_binary_sensor_data(device: DaikinDevice, key: str) -> bool:
    """Check if device has data for the binary sensor."""
    # Equipment status sensors are always available
    if key in ("cooling", "heating", "fan_running"):
        return True

    # Check for specific features
    if key == "humidifier_active":
        return device.humidifier_mode is not None
    if key == "dehumidifier_active":
        return device.dehumidifier_mode is not None
    if key == "filter_alert":
        return device.filter_remaining is not None
    if key == "has_alert":
        return True  # Always show alert status

    return True


class DaikinOneBinarySensor(
    CoordinatorEntity[DaikinOneDataUpdateCoordinator], BinarySensorEntity
):
    """Representation of a Daikin One+ binary sensor."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: DaikinOneDataUpdateCoordinator,
        device_id: str,
        description: BinarySensorEntityDescription,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)
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
        # Online sensor is always "available" to report connectivity
        if self.entity_description.key == "online":
            return device is not None
        return device is not None and device.is_online

    @property
    def is_on(self) -> bool | None:
        """Return true if the binary sensor is on."""
        device = self._device
        if not device:
            return None

        key = self.entity_description.key

        if key == "online":
            return self._device.is_online

        if key == "cooling":
            return self._device.equipment_status == EQUIPMENT_STATUS_COOLING

        if key == "heating":
            return self._device.equipment_status == EQUIPMENT_STATUS_HEATING

        if key == "fan_running":
            return self._device.equipment_status in (
                EQUIPMENT_STATUS_FAN,
                EQUIPMENT_STATUS_COOLING,
                EQUIPMENT_STATUS_HEATING,
            )

        if key == "has_alert":
            # Check if device has any active alerts
            return device.data.get("hasAlert", False)

        if key == "filter_alert":
            # Alert if filter remaining is below threshold (e.g., 10%)
            filter_remaining = device.filter_remaining
            if filter_remaining is not None:
                return filter_remaining < 10
            return False

        if key == "humidifier_active":
            humidifier_mode = device.humidifier_mode
            return humidifier_mode is not None and humidifier_mode != "off"

        if key == "dehumidifier_active":
            dehumidifier_mode = device.dehumidifier_mode
            return dehumidifier_mode is not None and dehumidifier_mode != "off"

        return None
