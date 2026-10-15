"""Test harness: real Home Assistant core, fake Bluetooth radio."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from bleak.backends.device import BLEDevice
import pytest

from custom_components.pitpat_treadmill import device as dev_mod
from custom_components.pitpat_treadmill.protocol import (
    OLD_NOTIFY,
    OLD_SERVICE,
    OLD_WRITE,
    TAIL,
    xor_crc,
)

pytest_plugins = "pytest_homeassistant_custom_component"

ADDRESS = "48:CA:43:ED:E9:0E"


@pytest.fixture(autouse=True)
def _enable_custom_integrations(enable_custom_integrations):
    yield


def status_frame(state="stopped", speed=0, target=0, dist=0, t_ms=0, kcal=0) -> bytes:
    f = bytearray(52)
    f[0], f[1] = 0x68, 52
    f[3:5] = speed.to_bytes(2, "big")
    f[5:7] = target.to_bytes(2, "big")
    f[7:11] = dist.to_bytes(4, "big")
    f[18:20] = kcal.to_bytes(2, "big")
    f[20:24] = t_ms.to_bytes(4, "big")
    f[25] = 27
    f[26] = {"stopped": 0, "running": 8, "paused": 16, "countdown": 24}[state]
    f[27:29] = (6000).to_bytes(2, "big")
    f[50] = xor_crc(bytes(f), 50)
    f[51] = TAIL
    return bytes(f)


class FakeClient:
    """Stands in for BleakClientWithServiceCache."""

    def __init__(self, disconnected_callback):
        self.cb = disconnected_callback
        self.is_connected = True
        self.services = [type("S", (), {"uuid": OLD_SERVICE})()]
        self.notify_cb = None
        self.writes: list[bytes] = []   # unwrapped payloads, heartbeats excluded
        self.heartbeats = 0
        self.disconnect_calls = 0

    async def start_notify(self, uuid, cb):
        assert uuid == OLD_NOTIFY
        self.notify_cb = cb

    async def write_gatt_char(self, uuid, data, response=True):
        assert self.is_connected, "write on a dead link"
        assert uuid == OLD_WRITE and data[0] == 0x4D and data[3] == len(data) - 4
        p = bytes(data[4:])
        if p[:3] == bytes([0x6A, 5, 0xFD]):
            self.heartbeats += 1
        else:
            self.writes.append(p)

    async def disconnect(self):
        self.disconnect_calls += 1
        self.is_connected = False

    # test helpers
    def emit(self, frame: bytes):
        self.notify_cb(None, bytearray(b"\x4d\x00\x00" + bytes([len(frame)]) + frame))

    def drop(self):
        """Link lost from the treadmill's side."""
        self.is_connected = False
        self.cb(self)

    @property
    def commands(self):
        """(mode, speed_raw) of every run command written."""
        return [(p[12] & 7, int.from_bytes(p[6:8], "big")) for p in self.writes]


class Radio:
    """Fake Bluetooth layer: what the HA bluetooth integration + bleak would give us."""

    def __init__(self):
        self.present = True
        self.clients: list[FakeClient] = []
        self.adv_cbs = []
        self.now = 1000.0
        self.refuse = 0

    @property
    def client(self) -> FakeClient:
        return self.clients[-1]

    def advertise(self):
        for cb in list(self.adv_cbs):
            cb(None, None)


@pytest.fixture(autouse=True)
def frontend(hass):
    """The card is served through http/frontend; fake both (the real ones are not under test)."""
    hass.config.components.update({"http", "frontend"})
    hass.http = MagicMock(async_register_static_paths=AsyncMock())
    with patch("homeassistant.components.frontend.add_extra_js_url") as add_js:
        yield add_js


@pytest.fixture
def radio(monkeypatch):
    r = Radio()

    def ble_device(hass, address, connectable=True):
        return BLEDevice(address, "PitPat-T01", {}) if r.present else None

    def register(hass, cb, matcher, mode):
        r.adv_cbs.append(cb)
        return lambda: r.adv_cbs.remove(cb)

    async def establish(cls, device, name, disconnected_callback=None, **kw):
        if r.refuse:
            r.refuse -= 1
            raise TimeoutError("fake: connect failed")
        c = FakeClient(disconnected_callback)
        r.clients.append(c)
        return c

    class Clock:
        @staticmethod
        def monotonic():
            return r.now

    monkeypatch.setattr(dev_mod, "time", Clock)
    monkeypatch.setattr(dev_mod, "RETRY_SECONDS", 0)
    with patch("homeassistant.components.bluetooth.async_ble_device_from_address", ble_device), \
         patch("homeassistant.components.bluetooth.async_register_callback", register), \
         patch.object(dev_mod, "establish_connection", establish), \
         patch.object(dev_mod, "COMMAND_GAP", 0):
        yield r
