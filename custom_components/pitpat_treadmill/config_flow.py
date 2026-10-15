"""Config flow: Bluetooth auto-discovery, or pick the treadmill from a list."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
)

from .const import (
    CONF_MAX_SPEED,
    CONF_START_SPEED,
    CONF_STEP,
    DEFAULT_MAX_SPEED,
    DEFAULT_START_SPEED,
    DEFAULT_STEP,
    DOMAIN,
    NAME,
)


def _is_pitpat(info: BluetoothServiceInfoBleak) -> bool:
    return (info.name or "").lower().startswith("pitpat")


class PitPatConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._discovery: BluetoothServiceInfoBleak | None = None
        self._devices: dict[str, BluetoothServiceInfoBleak] = {}

    async def async_step_bluetooth(self, discovery_info: BluetoothServiceInfoBleak) -> ConfigFlowResult:
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()
        self._discovery = discovery_info
        self.context["title_placeholders"] = {"name": discovery_info.name or NAME}
        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        assert self._discovery is not None
        if user_input is not None:
            return self.async_create_entry(title=NAME, data={CONF_ADDRESS: self._discovery.address})
        self._set_confirm_only()
        return self.async_show_form(
            step_id="bluetooth_confirm",
            description_placeholders={"name": self._discovery.name or NAME},
        )

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            address = user_input[CONF_ADDRESS]
            await self.async_set_unique_id(address, raise_on_progress=False)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title=NAME, data={CONF_ADDRESS: address})

        current = self._async_current_ids(include_ignore=False)
        for info in async_discovered_service_info(self.hass):
            if _is_pitpat(info) and info.address not in current:
                self._devices[info.address] = info
        if not self._devices:
            return self.async_abort(reason="no_devices_found")
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_ADDRESS): vol.In(
                    {a: f"{i.name} ({a})" for a, i in self._devices.items()})
            }),
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlowWithReload:
        return PitPatOptionsFlow()


def _num(min_: float, max_: float, step: float) -> NumberSelector:
    return NumberSelector(NumberSelectorConfig(
        min=min_, max=max_, step=step, mode=NumberSelectorMode.BOX,
        unit_of_measurement="km/h"))


class PitPatOptionsFlow(OptionsFlowWithReload):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data={**self.config_entry.options, **user_input})
        o = self.config_entry.options
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required(CONF_MAX_SPEED, default=o.get(CONF_MAX_SPEED, DEFAULT_MAX_SPEED)): _num(1, 6, 0.1),
                vol.Required(CONF_START_SPEED, default=o.get(CONF_START_SPEED, DEFAULT_START_SPEED)): _num(0.5, 6, 0.1),
                vol.Required(CONF_STEP, default=o.get(CONF_STEP, DEFAULT_STEP)): _num(0.1, 2, 0.1),
            }),
        )
