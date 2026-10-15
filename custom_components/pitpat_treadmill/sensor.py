"""Sensors."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import EntityCategory, UnitOfLength, UnitOfSpeed, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import PitPatConfigEntry
from .device import PitPatDevice
from .entity import PitPatEntity


@dataclass(frozen=True, kw_only=True)
class PitPatSensorDescription(SensorEntityDescription):
    value_fn: Callable[[PitPatDevice], Any]
    always_available: bool = False


def _st(attr: str, scale: float | None = None):
    def get(dev: PitPatDevice) -> Any:
        if dev.status is None:
            return None
        v = getattr(dev.status, attr)
        return v if scale is None else round(v * scale, 2)
    return get


SENSORS: tuple[PitPatSensorDescription, ...] = (
    PitPatSensorDescription(
        key="state", device_class=SensorDeviceClass.ENUM,
        options=["stopped", "countdown", "running", "paused"],
        value_fn=lambda d: d.run_state),
    PitPatSensorDescription(
        key="speed", device_class=SensorDeviceClass.SPEED,
        native_unit_of_measurement=UnitOfSpeed.KILOMETERS_PER_HOUR,
        state_class=SensorStateClass.MEASUREMENT, suggested_display_precision=1,
        value_fn=_st("speed_raw", 0.001)),
    PitPatSensorDescription(
        key="target_speed", device_class=SensorDeviceClass.SPEED,
        native_unit_of_measurement=UnitOfSpeed.KILOMETERS_PER_HOUR,
        state_class=SensorStateClass.MEASUREMENT, suggested_display_precision=1,
        value_fn=_st("target_speed_raw", 0.001)),
    PitPatSensorDescription(
        key="distance", device_class=SensorDeviceClass.DISTANCE,
        native_unit_of_measurement=UnitOfLength.METERS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=_st("distance_m")),
    PitPatSensorDescription(
        key="workout_time", device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda d: int(d.status.time_s) if d.status else None),
    PitPatSensorDescription(
        key="calories", native_unit_of_measurement="kcal",
        state_class=SensorStateClass.TOTAL_INCREASING, value_fn=_st("calories")),
    PitPatSensorDescription(
        key="error", entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_st("error_code")),
    PitPatSensorDescription(
        key="connection_drops", entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.TOTAL_INCREASING, always_available=True,
        icon="mdi:bluetooth-off", value_fn=lambda d: d.drops),
    PitPatSensorDescription(
        key="incline", entity_registry_enabled_default=False, value_fn=_st("incline")),
    PitPatSensorDescription(
        key="steps", state_class=SensorStateClass.TOTAL_INCREASING,
        entity_registry_enabled_default=False, value_fn=_st("steps")),
    PitPatSensorDescription(
        key="heart_rate", native_unit_of_measurement="bpm",
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False, value_fn=_st("heart_rate")),
)


async def async_setup_entry(hass: HomeAssistant, entry: PitPatConfigEntry,
                            async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    async_add_entities(PitPatSensor(entry.runtime_data, d) for d in SENSORS)


class PitPatSensor(PitPatEntity, SensorEntity):
    entity_description: PitPatSensorDescription

    def __init__(self, device: PitPatDevice, description: PitPatSensorDescription) -> None:
        super().__init__(device, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self.device)

    @property
    def available(self) -> bool:
        return True if self.entity_description.always_available else self.device.connected

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.entity_description.key != "connection_drops":
            return None
        return {
            "last_drop_reason": self.device.last_drop_reason,
            "last_drop": self.device.last_drop_at,
            "failed_connect_attempts": self.device.connect_failures,
        }
