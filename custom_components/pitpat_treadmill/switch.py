"""Connection switch: let go of the treadmill so the PitPat phone app can use it."""
from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import PitPatConfigEntry
from .entity import PitPatEntity


async def async_setup_entry(hass: HomeAssistant, entry: PitPatConfigEntry,
                            async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    async_add_entities([PitPatConnectionSwitch(entry.runtime_data)])


class PitPatConnectionSwitch(PitPatEntity, SwitchEntity):
    _attr_icon = "mdi:bluetooth-connect"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, device) -> None:
        super().__init__(device, "connection")

    @property
    def available(self) -> bool:
        return True

    @property
    def is_on(self) -> bool:
        return self.device.enabled

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.device.async_set_enabled(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.device.async_set_enabled(False)
