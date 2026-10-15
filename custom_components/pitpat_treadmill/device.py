"""Bluetooth connection and command logic for one PitPat treadmill."""
from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime, timedelta
import logging
import time

from bleak import BleakClient
from bleak.exc import BleakError
from bleak_retry_connector import (
    BLEAK_EXCEPTIONS,
    BleakClientWithServiceCache,
    establish_connection,
)

from homeassistant.components import bluetooth
from homeassistant.components.bluetooth.match import ADDRESS, CONNECTABLE
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_track_time_interval

from .const import (
    COMMAND_GAP,
    CONF_CONNECT,
    CONF_MAX_SPEED,
    CONF_START_SPEED,
    CONF_STEP,
    DEFAULT_MAX_SPEED,
    DEFAULT_START_SPEED,
    DEFAULT_STEP,
    MIN_SPEED,
    RETRY_SECONDS,
    WATCHDOG_SECONDS,
)
from .protocol import (
    MODE_PAUSE,
    MODE_START,
    MODE_STOP,
    NEW_NOTIFY,
    NEW_SERVICE,
    NEW_WRITE,
    OLD_NOTIFY,
    OLD_SERVICE,
    OLD_WRITE,
    Status,
    heartbeat,
    parse_status,
    run_frame,
    wrap_blufi,
)

_LOGGER = logging.getLogger(__name__)

ACTIVE = ("running",)                       # states in which a speed change is sent
LIVE = ("running", "countdown", "paused")   # states in which unloading sends a stop
IO_ERRORS = (*BLEAK_EXCEPTIONS, BleakError, TimeoutError)


class PitPatDevice:
    """Owns the single Bluetooth connection the treadmill allows."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, address: str, name: str) -> None:
        self.hass, self.entry, self.address, self.name = hass, entry, address, name
        opts = entry.options
        self.max_speed: float = float(opts.get(CONF_MAX_SPEED, DEFAULT_MAX_SPEED))
        self.step: float = float(opts.get(CONF_STEP, DEFAULT_STEP))
        self.setpoint: float = self._clamp(float(opts.get(CONF_START_SPEED, DEFAULT_START_SPEED)))
        self.enabled: bool = bool(opts.get(CONF_CONNECT, True))
        self.status: Status | None = None
        self._client: BleakClient | None = None
        self._variant = "old"
        self._write_uuid = OLD_WRITE
        self._seq = 0
        self._last_rx = 0.0
        self._last_attempt = float("-inf")
        self._last_cmd = 0.0
        self._cmd_until = 0.0
        self._closing = False
        self._connect_lock = asyncio.Lock()
        self._write_lock = asyncio.Lock()
        self._cmd_lock = asyncio.Lock()
        self._listeners: set[Callable[[], None]] = set()
        self._unsubs: list[Callable[[], None]] = []
        self._connect_task: asyncio.Task | None = None
        self._tasks: set[asyncio.Task] = set()
        self._last_snapshot: tuple | None = None
        self._last_notify = 0.0

    # ----------------------------------------------------------- listeners
    @callback
    def async_add_listener(self, update: Callable[[], None]) -> Callable[[], None]:
        self._listeners.add(update)
        return lambda: self._listeners.discard(update)

    @callback
    def _notify(self) -> None:
        for update in list(self._listeners):
            update()

    @property
    def connected(self) -> bool:
        return self._client is not None and self._client.is_connected

    @property
    def run_state(self) -> str | None:
        return self.status.run_state if self.status else None

    # ------------------------------------------------------------ lifecycle
    async def async_start(self) -> None:
        self._unsubs.append(
            bluetooth.async_register_callback(
                self.hass,
                self._on_advertisement,
                {ADDRESS: self.address, CONNECTABLE: True},
                bluetooth.BluetoothScanningMode.ACTIVE,
            )
        )
        self._unsubs.append(
            async_track_time_interval(self.hass, self._tick, timedelta(seconds=2))
        )
        self._schedule_connect()

    async def async_shutdown(self) -> None:
        """Stop the belt if it is moving, then release the Bluetooth link."""
        self._closing = True
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()
        if self._connect_task and not self._connect_task.done():
            self._connect_task.cancel()
        for task in list(self._tasks):
            task.cancel()
        if self.connected and self.run_state in LIVE:
            _LOGGER.info("Stopping the treadmill before unloading (state %s)", self.run_state)
            try:
                await asyncio.wait_for(self._send(run_frame(0, MODE_STOP)), 5)
                await asyncio.sleep(1.0)
            except (*IO_ERRORS, HomeAssistantError) as err:
                _LOGGER.error("Could not stop the treadmill on unload: %s", err)
        await self._disconnect()

    async def async_set_enabled(self, enabled: bool) -> None:
        """Switch: release the Bluetooth link (e.g. for the phone app) or take it."""
        self.enabled = enabled
        self.hass.config_entries.async_update_entry(
            self.entry, options={**self.entry.options, CONF_CONNECT: enabled}
        )
        if enabled:
            self._last_attempt = float("-inf")
            self._schedule_connect()
        else:
            await self._disconnect()
        self._notify()

    # ----------------------------------------------------------- connecting
    @callback
    def _on_advertisement(self, _info, _change) -> None:
        if self.enabled and not self.connected:
            self._schedule_connect()

    @callback
    def _tick(self, _now: datetime) -> None:
        if self.connected and time.monotonic() - self._last_rx > WATCHDOG_SECONDS:
            _LOGGER.warning("No data from the treadmill for %ss, reconnecting", WATCHDOG_SECONDS)
            self._spawn(self._disconnect())
        elif self.enabled and not self.connected:
            self._schedule_connect()

    @callback
    def _spawn(self, coro) -> None:
        task = self.entry.async_create_background_task(self.hass, coro, f"{self.name} task")
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    @callback
    def _schedule_connect(self) -> None:
        if self._closing or not self.enabled:
            return
        if self._connect_task and not self._connect_task.done():
            return
        self._connect_task = self.entry.async_create_background_task(
            self.hass, self._async_connect(), f"{self.name} connect"
        )

    async def _async_connect(self) -> None:
        async with self._connect_lock:
            if self.connected or not self.enabled or self._closing:
                return
            if time.monotonic() - self._last_attempt < RETRY_SECONDS:
                return
            self._last_attempt = time.monotonic()
            ble_device = bluetooth.async_ble_device_from_address(self.hass, self.address, True)
            if ble_device is None:
                return  # not advertising (treadmill off or out of range); retried on advertisement
            try:
                client = await establish_connection(
                    BleakClientWithServiceCache,
                    ble_device,
                    self.name,
                    self._on_disconnect,
                    max_attempts=3,
                    ble_device_callback=lambda: bluetooth.async_ble_device_from_address(
                        self.hass, self.address, True
                    ),
                )
            except IO_ERRORS as err:
                _LOGGER.debug("Could not connect to %s: %s", self.address, err)
                return
            uuids = {s.uuid.lower() for s in client.services}
            if NEW_SERVICE in uuids:
                self._variant, self._write_uuid, notify = "new", NEW_WRITE, NEW_NOTIFY
            elif OLD_SERVICE in uuids:
                self._variant, self._write_uuid, notify = "old", OLD_WRITE, OLD_NOTIFY
            else:
                _LOGGER.error("%s offers no known PitPat service: %s", self.address, sorted(uuids))
                await client.disconnect()
                return
            self._last_rx = time.monotonic()
            self._seq = 0
            self.status = None
            self._last_snapshot = None
            try:
                await asyncio.wait_for(client.start_notify(notify, self._on_data), 10)
            except IO_ERRORS as err:
                _LOGGER.warning("Could not enable notifications: %s", err)
                await client.disconnect()
                return
            self._client = client
            _LOGGER.info("Connected to treadmill %s", self.address)
            self._notify()

    @callback
    def _on_disconnect(self, client: BleakClient) -> None:
        if client is self._client:
            _LOGGER.info("Treadmill %s disconnected", self.address)
            self._client = None
            self._notify()

    async def _disconnect(self) -> None:
        client, self._client = self._client, None
        if client is None:
            return
        self._notify()
        try:
            await asyncio.wait_for(client.disconnect(), 8)
        except IO_ERRORS as err:
            _LOGGER.debug("Disconnect: %s", err)

    # ------------------------------------------------------------ receiving
    @callback
    def _on_data(self, _char, data: bytearray) -> None:
        self._last_rx = time.monotonic()
        raw = bytes(data)
        if self._variant == "old":
            raw = raw[4:]
        st = parse_status(raw)
        if st is None:
            return
        self.status = st
        # follow speed changes made with the physical remote, but not the lagging echo of ours
        if (st.run_state in ACTIVE and st.target_speed_raw and time.monotonic() > self._cmd_until
                and abs(st.target_speed_raw / 1000.0 - self.setpoint) > 0.04):
            self.setpoint = self._clamp(st.target_speed_raw / 1000.0)
        if st.firmware > 3:
            self._spawn(self._heartbeat())
        snap = (st.run_state, st.speed_raw, st.target_speed_raw, st.distance_m, st.time_s,
                st.calories, st.error_code, st.incline, st.steps, st.heart_rate, self.setpoint)
        if snap != self._last_snapshot:
            self._last_snapshot = snap
            self._notify()

    async def _heartbeat(self) -> None:
        try:
            await self._send(heartbeat())
        except (*IO_ERRORS, HomeAssistantError) as err:
            _LOGGER.debug("Heartbeat failed: %s", err)

    # -------------------------------------------------------------- sending
    async def _send(self, payload: bytes) -> None:
        client = self._client
        if client is None or not client.is_connected:
            raise HomeAssistantError("The treadmill is not connected")
        async with self._write_lock:
            data = payload if self._variant == "new" else wrap_blufi(payload, self._seq)
            self._seq = (self._seq + 1) & 0xFF
            try:
                await asyncio.wait_for(
                    client.write_gatt_char(self._write_uuid, data, response=True), 8)
            except IO_ERRORS as err:
                raise HomeAssistantError(f"Could not talk to the treadmill: {err}") from err

    async def _command(self, payload: bytes) -> None:
        async with self._cmd_lock:
            wait = COMMAND_GAP - (time.monotonic() - self._last_cmd)
            if wait > 0:
                await asyncio.sleep(wait)
            try:
                await self._send(payload)
            finally:
                self._last_cmd = time.monotonic()

    def _clamp(self, kmh: float) -> float:
        return round(min(max(kmh, MIN_SPEED), self.max_speed) * 10) / 10

    async def _apply_setpoint(self) -> None:
        if self.connected and self.run_state in ACTIVE:
            self._cmd_until = time.monotonic() + 2.0
            await self._command(run_frame(int(round(self.setpoint * 1000)), MODE_START))

    # ----------------------------------------------------- public commands
    async def async_start_belt(self) -> None:
        if not self.connected:
            raise HomeAssistantError("The treadmill is not connected")
        self._cmd_until = time.monotonic() + 2.0
        await self._command(run_frame(int(round(self.setpoint * 1000)), MODE_START))

    async def async_stop_belt(self) -> None:
        if not self.connected:
            raise HomeAssistantError("The treadmill is not connected")
        await self._command(run_frame(0, MODE_STOP))

    async def async_pause_belt(self) -> None:
        if not self.connected:
            raise HomeAssistantError("The treadmill is not connected")
        raw = self.status.target_speed_raw if self.status and self.status.target_speed_raw else 1000
        await self._command(run_frame(raw, MODE_PAUSE))

    async def async_set_speed(self, kmh: float) -> None:
        """Speed slider: stored always, sent to the belt only while running."""
        self.setpoint = self._clamp(kmh)
        self._notify()
        await self._apply_setpoint()

    async def async_change_speed(self, delta: float) -> None:
        self.setpoint = self._clamp(self.setpoint + delta)
        self._notify()
        await self._apply_setpoint()
