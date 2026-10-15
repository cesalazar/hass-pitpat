"""Buttons."""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import PitPatConfigEntry
from .device import PitPatDevice
from .entity import PitPatEntity


@dataclass(frozen=True, kw_only=True)
class PitPatButtonDescription(ButtonEntityDescription):
    press_fn: Callable[[PitPatDevice], Awaitable[None]]


BUTTONS: tuple[PitPatButtonDescription, ...] = (
    PitPatButtonDescription(key="start", icon="mdi:play", press_fn=lambda d: d.async_start_belt()),
    PitPatButtonDescription(key="stop", icon="mdi:stop", press_fn=lambda d: d.async_stop_belt()),
    PitPatButtonDescription(key="pause", icon="mdi:pause", press_fn=lambda d: d.async_pause_belt()),
    PitPatButtonDescription(key="faster", icon="mdi:plus",
                            press_fn=lambda d: d.async_change_speed(d.step)),
    PitPatButtonDescription(key="slower", icon="mdi:minus",
                            press_fn=lambda d: d.async_change_speed(-d.step)),
)


async def async_setup_entry(hass: HomeAssistant, entry: PitPatConfigEntry,
                            async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    async_add_entities(PitPatButton(entry.runtime_data, d) for d in BUTTONS)


class PitPatButton(PitPatEntity, ButtonEntity):
    entity_description: PitPatButtonDescription

    def __init__(self, device: PitPatDevice, description: PitPatButtonDescription) -> None:
        super().__init__(device, description.key)
        self.entity_description = description

    async def async_press(self) -> None:
        await self.entity_description.press_fn(self.device)
