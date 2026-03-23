"""Sensor platform for Daikin One+."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import DaikinDevice
from .const import DOMAIN
from .coordinator import DaikinOneDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


SENSOR_DESCRIPTIONS: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(
        key="indoor_temperature",
        name="Indoor Temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="outdoor_temperature",
        name="Outdoor Temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="indoor_humidity",
        name="Indoor Humidity",
        device_class=SensorDeviceClass.HUMIDITY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
    ),
    SensorEntityDescription(
        key="outdoor_humidity",
        name="Outdoor Humidity",
        device_class=SensorDeviceClass.HUMIDITY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
    ),
    SensorEntityDescription(
        key="air_quality_index",
        name="Air Quality Index",
        device_class=SensorDeviceClass.AQI,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:air-filter",
    ),
    SensorEntityDescription(
        key="filter_remaining",
        name="Filter Remaining",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:air-filter",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key="uv_lamp_remaining",
        name="UV Lamp Remaining",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:lightbulb-on",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key="equipment_status",
        name="Equipment Status",
        icon="mdi:hvac",
    ),
    SensorEntityDescription(
        key="schedule_mode",
        name="Schedule Mode",
        icon="mdi:calendar-clock",
    ),
    SensorEntityDescription(
        key="fan_mode",
        name="Fan Mode",
        icon="mdi:fan",
    ),
    SensorEntityDescription(
        key="heat_setpoint",
        name="Heat Setpoint",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key="cool_setpoint",
        name="Cool Setpoint",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key="humidifier_setpoint",
        name="Humidifier Setpoint",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:water-percent",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key="dehumidifier_setpoint",
        name="Dehumidifier Setpoint",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:water-percent",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Daikin One+ sensor entities."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator: DaikinOneDataUpdateCoordinator = data["coordinator"]

    entities: list[DaikinOneSensor] = []

    for device_id in coordinator.device_ids:
        device = coordinator.get_device(device_id)
        if device:
            for description in SENSOR_DESCRIPTIONS:
                # Only add sensors that have data available
                if _has_sensor_data(device, description.key):
                    entities.append(
                        DaikinOneSensor(coordinator, device_id, description)
                    )

    async_add_entities(entities)


def _has_sensor_data(device: DaikinDevice, key: str) -> bool:
    """Check if device has data for the sensor."""
    value_map = {
        "indoor_temperature": device.current_temperature,
        "outdoor_temperature": device.outdoor_temperature,
        "indoor_humidity": device.humidity,
        "outdoor_humidity": device.outdoor_humidity,
        "air_quality_index": device.air_quality_index,
        "filter_remaining": device.filter_remaining,
        "uv_lamp_remaining": device.uv_lamp_remaining,
        "equipment_status": device.equipment_status,
        "schedule_mode": device.schedule_mode,
        "fan_mode": device.fan_mode,
        "heat_setpoint": device.heat_setpoint,
        "cool_setpoint": device.cool_setpoint,
        "humidifier_setpoint": device.humidifier_setpoint,
        "dehumidifier_setpoint": device.dehumidifier_setpoint,
    }
    # Always include status sensors, check None for others
    if key in ("equipment_status", "schedule_mode", "fan_mode"):
        return True
    return value_map.get(key) is not None


class DaikinOneSensor(CoordinatorEntity[DaikinOneDataUpdateCoordinator], SensorEntity):
    """Representation of a Daikin One+ sensor."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: DaikinOneDataUpdateCoordinator,
        device_id: str,
        description: SensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
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
        return device is not None and device.is_online

    @property
    def native_value(self) -> Any:
        device = self._device
        if not device:
            return None

        key = self.entity_description.key

        # Temperature
        if key == "indoor_temperature": return device.current_temperature
        if key == "outdoor_temperature": return device.outdoor_temperature
        if key == "heat_setpoint": return device.heat_setpoint
        if key == "cool_setpoint": return device.cool_setpoint

        # Humidity
        if key == "indoor_humidity": return device.humidity
        if key == "outdoor_humidity": return device.outdoor_humidity
        if key == "humidifier_setpoint": return device.humidifier_setpoint
        if key == "dehumidifier_setpoint": return device.dehumidifier_setpoint

        # Air Quality / Maintenance
        if key == "air_quality_index": return device.air_quality_index
        if key == "filter_remaining": return device.filter_remaining
        if key == "uv_lamp_remaining": return device.uv_lamp_remaining

        # Status Strings
        if key == "equipment_status":
            # Map the integer status to a readable string
            status_map = {0: "Idle", 1: "Heating", 2: "Cooling", 3: "Fan", 4: "Dehumidifying"}
            return status_map.get(device.data.get("equipmentStatus"), "Unknown")

        if key == "schedule_mode": return device.schedule_mode
        if key == "fan_mode":
            fan_map = {0: "Auto", 1: "On", 2: "Circulate"}
            return fan_map.get(device.data.get("fanMode"), "Unknown")

        return None

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Dynamically return the unit from the device."""
        if self.entity_description.device_class == SensorDeviceClass.TEMPERATURE:
            return UnitOfTemperature.CELSIUS
        return self.entity_description.native_unit_of_measurement
