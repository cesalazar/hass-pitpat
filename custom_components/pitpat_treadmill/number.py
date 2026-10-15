"""Speed slider."""
from __future__ import annotations

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.const import UnitOfSpeed
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import PitPatConfigEntry
from .const import MIN_SPEED
from .entity import PitPatEntity


async def async_setup_entry(hass: HomeAssistant, entry: PitPatConfigEntry,
                            async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    async_add_entities([PitPatSpeedSetting(entry.runtime_data)])


class PitPatSpeedSetting(PitPatEntity, NumberEntity):
    """Changes the belt speed live while running; otherwise sets the speed Start will use."""

    _attr_device_class = NumberDeviceClass.SPEED
    _attr_native_unit_of_measurement = UnitOfSpeed.KILOMETERS_PER_HOUR
    _attr_native_min_value = MIN_SPEED
    _attr_native_step = 0.1
    _attr_mode = NumberMode.SLIDER

    def __init__(self, device) -> None:
        super().__init__(device, "speed_setting")
        self._attr_native_max_value = device.max_speed

    @property
    def native_value(self) -> float:
        return self.device.setpoint

    async def async_set_native_value(self, value: float) -> None:
        await self.device.async_set_speed(value)
