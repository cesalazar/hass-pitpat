"""Base entity."""
from __future__ import annotations

from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH, DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import DOMAIN
from .device import PitPatDevice


class PitPatEntity(Entity):
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, device: PitPatDevice, key: str) -> None:
        self.device = device
        self._attr_unique_id = f"{device.address}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device.address)},
            connections={(CONNECTION_BLUETOOTH, device.address)},
            name=device.entry.title,
            manufacturer="PitPat",
            model="Walking pad",
        )

    @property
    def available(self) -> bool:
        return self.device.connected

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self.device.async_add_listener(self.async_write_ha_state))
