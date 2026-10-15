"""PitPat Treadmill: control and monitor a PitPat walking pad over Bluetooth."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, EVENT_HOMEASSISTANT_STOP, Platform
from homeassistant.core import Event, HomeAssistant

from .device import PitPatDevice

PLATFORMS = [Platform.SENSOR, Platform.NUMBER, Platform.BUTTON, Platform.SWITCH]

type PitPatConfigEntry = ConfigEntry[PitPatDevice]


async def async_setup_entry(hass: HomeAssistant, entry: PitPatConfigEntry) -> bool:
    device = PitPatDevice(hass, entry, entry.data[CONF_ADDRESS], entry.title)
    entry.runtime_data = device
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await device.async_start()

    async def _async_stop(_event: Event) -> None:
        await device.async_shutdown()

    entry.async_on_unload(hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _async_stop))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: PitPatConfigEntry) -> bool:
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        await entry.runtime_data.async_shutdown()
    return unload_ok
