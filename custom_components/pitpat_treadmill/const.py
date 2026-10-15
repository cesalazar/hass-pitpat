"""Constants for the PitPat Treadmill integration."""
from __future__ import annotations

DOMAIN = "pitpat_treadmill"

CONF_CONNECT = "connect"          # option: keep the Bluetooth connection (switch state)
CONF_MAX_SPEED = "max_speed"      # option: upper speed limit, km/h
CONF_START_SPEED = "start_speed"  # option: speed used by "Start" until changed, km/h
CONF_STEP = "step"                # option: km/h per Faster / Slower press

DEFAULT_MAX_SPEED = 6.0
DEFAULT_START_SPEED = 1.0
DEFAULT_STEP = 0.5
MIN_SPEED = 0.5

NAME = "PitPat treadmill"
CARD_FILE = "pitpat-treadmill-card.js"
CARD_URL = f"/{DOMAIN}/{CARD_FILE}"
WATCHDOG_SECONDS = 30      # no data for this long = dead link, reconnect
RETRY_SECONDS = 15         # minimum time between connection attempts
COMMAND_GAP = 0.3          # minimum seconds between commands sent to the pad
