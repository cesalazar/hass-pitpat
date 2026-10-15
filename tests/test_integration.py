from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

import pytest

from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData
from habluetooth import BluetoothServiceInfoBleak
from homeassistant.components.bluetooth.match import ble_device_matches
from homeassistant.config_entries import SOURCE_BLUETOOTH, SOURCE_USER
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.pitpat_treadmill.const import DOMAIN

from .conftest import ADDRESS, status_frame

P = "PitPat-T01"


def info(name=P, address=ADDRESS) -> BluetoothServiceInfoBleak:
    dev = BLEDevice(address, name, {})
    return BluetoothServiceInfoBleak(
        name=name, address=address, rssi=-60, manufacturer_data={}, service_data={},
        service_uuids=[], source="local", device=dev,
        advertisement=AdvertisementData(name, {}, {}, [], -60, -127, ()),
        connectable=True, time=0, tx_power=None)




async def setup_entry(hass: HomeAssistant, options=None) -> MockConfigEntry:
    # the Bluetooth radio layer is faked, so mark its components as already set up
    hass.config.components.update({"bluetooth", "bluetooth_adapters"})
    entry = MockConfigEntry(domain=DOMAIN, title="PitPat treadmill", unique_id=ADDRESS,
                            data={CONF_ADDRESS: ADDRESS}, options=options or {})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def st(hass, key):
    return hass.states.get(f"{key.split('.')[0]}.pitpat_treadmill_{key.split('.')[1]}")


async def press(hass, name):
    await hass.services.async_call("button", "press",
                                   {"entity_id": f"button.pitpat_treadmill_{name}"}, blocking=True)


async def set_speed(hass, v):
    await hass.services.async_call("number", "set_value",
                                   {"entity_id": "number.pitpat_treadmill_speed_setting", "value": v},
                                   blocking=True)


# ------------------------------------------------------------------ discovery
async def test_manifest_matchers_match_real_names(hass):
    from homeassistant.loader import async_get_integration
    integ = await async_get_integration(hass, DOMAIN)
    matchers = integ.manifest["bluetooth"]
    for name in ("PitPat-T01", "PITPAT-X2"):
        assert any(ble_device_matches(m, info(name)) for m in matchers), name
    assert not any(ble_device_matches(m, info("LEDnet-1")) for m in matchers)


async def test_bluetooth_flow_creates_entry(hass, radio):
    hass.config.components.update({"bluetooth", "bluetooth_adapters"})
    r = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_BLUETOOTH}, data=info())
    assert r["type"] is FlowResultType.FORM and r["step_id"] == "bluetooth_confirm"
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {})
    assert r["type"] is FlowResultType.CREATE_ENTRY
    assert r["data"] == {CONF_ADDRESS: ADDRESS} and r["title"] == "PitPat treadmill"
    await hass.async_block_till_done()
    # already configured -> second discovery aborts
    r = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_BLUETOOTH}, data=info())
    assert r["type"] is FlowResultType.ABORT and r["reason"] == "already_configured"


async def test_user_flow_lists_only_pitpat(hass, radio):
    hass.config.components.update({"bluetooth", "bluetooth_adapters"})
    found = [info("LEDnet-1", "11:11:11:11:11:11"), info()]
    with patch("custom_components.pitpat_treadmill.config_flow.async_discovered_service_info",
               return_value=found):
        r = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
        assert r["type"] is FlowResultType.FORM
        assert list(r["data_schema"].schema[CONF_ADDRESS].container) == [ADDRESS]
        r = await hass.config_entries.flow.async_configure(r["flow_id"], {CONF_ADDRESS: ADDRESS})
    assert r["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()


async def test_user_flow_nothing_found(hass, radio):
    hass.config.components.update({"bluetooth", "bluetooth_adapters"})
    with patch("custom_components.pitpat_treadmill.config_flow.async_discovered_service_info",
               return_value=[info("LEDnet-1", "11:11:11:11:11:11")]):
        r = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert r["type"] is FlowResultType.ABORT and r["reason"] == "no_devices_found"


# ------------------------------------------------------------------ entities
async def test_entities_and_live_values(hass, radio):
    entry = await setup_entry(hass)
    reg = er.async_get(hass)
    ids = {e.entity_id for e in er.async_entries_for_config_entry(reg, entry.entry_id)}
    for want in ["sensor.pitpat_treadmill_state", "sensor.pitpat_treadmill_speed",
                 "sensor.pitpat_treadmill_distance", "sensor.pitpat_treadmill_workout_time",
                 "number.pitpat_treadmill_speed_setting", "switch.pitpat_treadmill_bluetooth_connection",
                 *[f"button.pitpat_treadmill_{b}" for b in ("start", "stop", "pause", "faster", "slower")]]:
        assert want in ids, (want, sorted(ids))
    assert len(radio.clients) == 1                     # connected by itself
    c = radio.client
    c.emit(status_frame("stopped"))
    await hass.async_block_till_done()
    assert st(hass, "sensor.state").state == "stopped"
    assert c.heartbeats >= 1                           # keep-alive after each status frame
    c.emit(status_frame("running", speed=2000, target=2000, dist=15, t_ms=12000, kcal=3))
    await hass.async_block_till_done()
    assert st(hass, "sensor.state").state == "running"
    assert float(st(hass, "sensor.speed").state) == 2.0
    assert st(hass, "sensor.distance").state == "15"
    assert st(hass, "sensor.workout_time").state == "12"
    assert st(hass, "sensor.calories").state == "3"
    # incline / steps / heart rate are registered but disabled by default
    assert st(hass, "sensor.steps") is None


async def test_commands(hass, radio):
    await setup_entry(hass)
    c = radio.client
    c.emit(status_frame("stopped"))
    await hass.async_block_till_done()

    await press(hass, "start")
    assert c.commands[-1] == (4, 1000)                 # default start speed 1.0 km/h

    await set_speed(hass, 3.2)                         # not running yet: stored, not sent
    assert c.commands == [(4, 1000)]
    assert float(st(hass, "number.speed_setting").state) == 3.2
    await press(hass, "start")
    assert c.commands[-1] == (4, 3200)

    c.emit(status_frame("running", speed=3200, target=3200))
    await hass.async_block_till_done()
    await set_speed(hass, 2.5)                         # running: sent live
    assert c.commands[-1] == (4, 2500)
    # rapid presses must build on our own setting, not the pad's lagging target (still 3200)
    await press(hass, "faster")
    await press(hass, "faster")
    assert c.commands[-2:] == [(4, 3000), (4, 3500)]
    await press(hass, "slower")
    assert c.commands[-1] == (4, 3000)
    for _ in range(10):
        await press(hass, "faster")
    assert c.commands[-1] == (4, 6000)                 # clamped at the maximum
    assert all(m in (0, 2, 4) and (m == 0 or 500 <= s <= 6000) for m, s in c.commands)

    await press(hass, "pause")
    assert c.commands[-1][0] == 2
    await press(hass, "stop")
    assert c.commands[-1] == (0, 0)
    assert c.writes[-1][13:21] == bytes(8)             # stop carries no user id


async def test_remote_control_changes_follow(hass, radio):
    await setup_entry(hass)
    c = radio.client
    c.emit(status_frame("running", speed=1000, target=1000))
    await hass.async_block_till_done()
    radio.now += 5                                     # past the post-command grace window
    c.emit(status_frame("running", speed=1000, target=4000))   # user pressed the physical remote
    await hass.async_block_till_done()
    assert float(st(hass, "number.speed_setting").state) == 4.0


async def test_commands_fail_cleanly_when_offline(hass, radio):
    from homeassistant.exceptions import HomeAssistantError
    import pytest
    radio.present = False
    await setup_entry(hass)
    assert radio.clients == []
    assert st(hass, "sensor.state").state == "unavailable"
    assert st(hass, "button.start").state == "unavailable"
    device = hass.config_entries.async_entries(DOMAIN)[0].runtime_data
    for call in (device.async_start_belt, device.async_stop_belt, device.async_pause_belt):
        with pytest.raises(HomeAssistantError):
            await call()


# ---------------------------------------------------------------- reconnecting
async def test_drop_then_reconnect_on_advertisement(hass, radio):
    await setup_entry(hass)
    c1 = radio.client
    c1.emit(status_frame("running", speed=1000, target=1000))
    await hass.async_block_till_done()
    c1.drop()
    await hass.async_block_till_done()
    assert st(hass, "sensor.state").state == "unavailable"
    drops = hass.states.get("sensor.pitpat_treadmill_connection_drops")
    assert drops.state == "1" and "link lost" in drops.attributes["last_drop_reason"]
    radio.advertise()
    await hass.async_block_till_done()
    assert len(radio.clients) == 2
    radio.client.emit(status_frame("running", speed=1000, target=1000))
    await hass.async_block_till_done()
    assert st(hass, "sensor.state").state == "running"


async def test_failed_connect_is_retried(hass, radio):
    radio.refuse = 2
    await setup_entry(hass)
    assert radio.clients == []
    for _ in range(3):
        radio.advertise()
        await hass.async_block_till_done()
    assert len(radio.clients) == 1


async def test_watchdog_reconnects_silent_link(hass, radio):
    await setup_entry(hass)
    c1 = radio.client
    c1.emit(status_frame("stopped"))
    await hass.async_block_till_done()
    radio.now += 21                                    # no data for 21 s
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=3))
    await hass.async_block_till_done()
    assert c1.disconnect_calls == 1
    drops = hass.states.get("sensor.pitpat_treadmill_connection_drops")
    assert drops.state == "1" and "no data" in drops.attributes["last_drop_reason"]
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=6))
    await hass.async_block_till_done()
    assert len(radio.clients) == 2                     # reconnected by the periodic check


async def test_connection_switch_releases_the_pad(hass, radio):
    entry = await setup_entry(hass)
    c1 = radio.client
    sw = "switch.pitpat_treadmill_bluetooth_connection"
    await hass.services.async_call("switch", "turn_off", {"entity_id": sw}, blocking=True)
    await hass.async_block_till_done()
    assert c1.disconnect_calls == 1 and hass.states.get(sw).state == "off"
    assert entry.options["connect"] is False           # remembered across restarts
    radio.advertise()
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=3))
    await hass.async_block_till_done()
    assert len(radio.clients) == 1                     # does not grab it back
    await hass.services.async_call("switch", "turn_on", {"entity_id": sw}, blocking=True)
    await hass.async_block_till_done()
    assert len(radio.clients) == 2 and hass.states.get(sw).state == "on"


async def test_switch_off_state_survives_restart(hass, radio):
    await setup_entry(hass, options={"connect": False})
    assert radio.clients == []
    assert hass.states.get("switch.pitpat_treadmill_bluetooth_connection").state == "off"


# -------------------------------------------------------------------- safety
async def test_unload_while_running_stops_belt(hass, radio):
    entry = await setup_entry(hass)
    c = radio.client
    c.emit(status_frame("running", speed=2000, target=2000))
    await hass.async_block_till_done()
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert c.commands[-1] == (0, 0), c.commands
    assert c.disconnect_calls == 1


async def test_unload_while_stopped_sends_nothing(hass, radio):
    entry = await setup_entry(hass)
    c = radio.client
    c.emit(status_frame("stopped"))
    await hass.async_block_till_done()
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert c.commands == [] and c.disconnect_calls == 1


async def test_options_limit_speed_and_reload(hass, radio):
    entry = await setup_entry(hass)
    r = await hass.config_entries.options.async_init(entry.entry_id)
    r = await hass.config_entries.options.async_configure(
        r["flow_id"], {"max_speed": 4.0, "start_speed": 1.5, "step": 1.0})
    assert r["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    c = radio.client
    assert len(radio.clients) == 2                     # reloaded
    assert hass.states.get("number.pitpat_treadmill_speed_setting").attributes["max"] == 4.0
    c.emit(status_frame("running", speed=1500, target=1500))
    await hass.async_block_till_done()
    for _ in range(5):
        await press(hass, "faster")
    assert c.commands[-1] == (4, 4000)                 # never above the configured maximum


# ---------------------------------------------------------------- dashboard card
async def test_card_is_served_and_loaded(hass, radio, frontend):
    from pathlib import Path
    await setup_entry(hass)
    (cfgs,), _ = hass.http.async_register_static_paths.call_args
    assert cfgs[0].url_path == "/pitpat_treadmill/pitpat-treadmill-card.js"
    assert Path(cfgs[0].path).is_file()
    (_, url), _ = frontend.call_args
    assert url.startswith("/pitpat_treadmill/pitpat-treadmill-card.js?v=")
