"""PitPat BLE protocol (reverse-engineered from the com.linzi.sport Android app).

Pure functions, no Bluetooth or Home Assistant imports. Verified on a PitPat-T01
(old "FFFF" chip family): status frames 0x68, commands wrapped in a BluFi header.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

# "New" chip family: raw frames. "Old" chip family (PitPat-T01): 4-byte BluFi header.
NEW_SERVICE = "0000fba0-0000-1000-8000-00805f9b34fb"
NEW_WRITE = "0000fba1-0000-1000-8000-00805f9b34fb"
NEW_NOTIFY = "0000fba2-0000-1000-8000-00805f9b34fb"
OLD_SERVICE = "0000ffff-0000-1000-8000-00805f9b34fb"
OLD_WRITE = "0000ff01-0000-1000-8000-00805f9b34fb"
OLD_NOTIFY = "0000ff02-0000-1000-8000-00805f9b34fb"

HEADER = 0x6A
TAIL = 0x43
MODE_STOP, MODE_PAUSE, MODE_START = 0, 2, 4


def xor_crc(frame: bytes, end: int) -> int:
    c = frame[1]
    for b in frame[2:end]:
        c ^= b
    return c & 0xFF


def heartbeat() -> bytes:
    f = bytearray([HEADER, 5, 0xFD, 0, TAIL])
    f[3] = xor_crc(bytes(f), 3)
    return bytes(f)


def run_frame(speed_raw: int, mode: int, *, speedup_s: int = 5, incline: int = 0,
              weight_kg: int = 70, miles: bool = False,
              user_id: int = 58965456623) -> bytes:
    f = bytearray(23)
    f[0], f[1] = HEADER, 23
    f[6], f[7] = (speed_raw >> 8) & 0xFF, speed_raw & 0xFF
    f[8] = speedup_s & 0xFF
    f[9] = incline & 0xFF
    f[10] = weight_kg & 0xFF
    f[12] = (mode | 8) if miles else (mode & 0xF7)
    uid = 0 if mode == MODE_STOP else user_id
    f[13:21] = uid.to_bytes(8, "big")
    f[21] = xor_crc(bytes(f), 21)
    f[22] = TAIL
    return bytes(f)


def wrap_blufi(payload: bytes, seq: int) -> bytes:
    return bytes([0x4D, 0x00, seq & 0xFF, len(payload)]) + payload


RUN_STATES = {0: "countdown", 1: "running", 2: "paused", 3: "stopped"}
_STATE_BY_MASK = {24: 0, 8: 1, 16: 2, 0: 3}


def _be(b: bytes) -> int:
    return int.from_bytes(b, "big")


@dataclass
class Status:
    kind: int
    error_code: int
    speed_raw: int
    target_speed_raw: int
    distance_m: int
    incline: int
    heart_rate: int
    steps: int
    calories: int
    time_raw: int
    firmware: int
    run_state: Optional[str]   # countdown / running / paused / stopped, None if unknown
    max_speed_raw: int
    crc_ok: bool = True

    @property
    def speed_kmh(self) -> float:
        return self.speed_raw / 1000.0

    @property
    def time_s(self) -> float:
        return self.time_raw / 1000.0 if self.firmware > 19 else float(self.time_raw)


def parse_status(f: bytes) -> Optional[Status]:
    if len(f) < 32 or f[0] not in (0x66, 0x67, 0x68):
        return None
    flags = f[26]
    state = _STATE_BY_MASK.get(flags & 56)
    return Status(
        kind=f[0], error_code=f[2], speed_raw=_be(f[3:5]),
        target_speed_raw=_be(f[5:7]), distance_m=_be(f[7:11]), incline=f[11],
        heart_rate=f[13], steps=_be(f[14:18]), calories=_be(f[18:20]),
        time_raw=_be(f[20:24]), firmware=f[25],
        run_state=RUN_STATES.get(state) if state is not None else None,
        max_speed_raw=_be(f[27:29]),
        crc_ok=f[-1] == TAIL and xor_crc(f, len(f) - 2) == f[-2])
