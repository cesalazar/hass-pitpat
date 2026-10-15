# PitPat Treadmill for Home Assistant

Monitor and control a PitPat walking pad / treadmill (tested on the **PitPat-T01**)
from Home Assistant over Bluetooth. No PitPat cloud, no MQTT broker, no extra
program: it uses Home Assistant's own Bluetooth, so a Raspberry Pi running Home
Assistant OS with its built-in Bluetooth works, as does an ESPHome Bluetooth proxy.

## Install (HACS, no terminal)

1. HACS → ⋮ (top right) → **Custom repositories** → paste this repository's URL,
   category **Integration** → Add.
2. Open "PitPat Treadmill" in HACS → **Download**.
3. Restart Home Assistant (Settings → System → Restart).
4. Turn the treadmill on and **close the PitPat app on your phone** (the treadmill
   accepts only one Bluetooth connection).
5. Home Assistant announces the discovered treadmill under Settings → Devices &
   services → click **Add**. If it doesn't show up: Add integration → PitPat Treadmill.

## What you get

- **Sensors:** State (stopped / countdown / running / paused), Speed, Target speed,
  Distance (m), Workout time (s), Calories, Error code. Incline, Steps and Heart
  rate exist but are disabled by default (the T01 reports 0 for steps and heart rate).
- **Speed setting** slider (0.5 to 6.0 km/h).
- **Buttons:** Start, Stop, Pause, Faster, Slower.
- **Bluetooth connection** switch (see below).

Everything shows *unavailable* while the treadmill is off or out of range, and
reconnects by itself when it comes back.

## How it behaves

- Speed slider and Faster/Slower change the speed live while the belt is running.
  In any other state they only change the stored speed that **Start** uses (also
  after Pause). Default 1.0 km/h, changeable under Configure.
- The pad counts down with beeps for about 4 s after Start. That cannot be muted on
  the T01.
- Moving the speed with the physical remote updates the slider.
- Speed is limited to 0.5 up to the configured maximum (default 6.0).

## Safety

- If Home Assistant restarts, the integration is reloaded or removed while the belt
  is moving or paused, it sends **Stop** first, then disconnects.
- If Bluetooth drops while the belt runs, the belt keeps going (the pad is not known
  to stop on its own). Home Assistant reconnects and shows the real state; use the
  physical remote or the Stop button.
- Treat this like any remote control for a moving belt: do not start it unattended.

## Using the phone app too

While Home Assistant is connected the phone app cannot connect. Turn the
**Bluetooth connection** switch off to release the treadmill, use the app, then turn
it back on. The switch position is remembered across restarts.

## Configure

Settings → Devices & services → PitPat Treadmill → Configure: maximum speed, the
speed used by Start, and the Faster/Slower step. Saving reloads the integration
(a moving belt is stopped first).

## Dashboard example

```yaml
type: entities
title: Treadmill
entities:
  - sensor.pitpat_treadmill_state
  - sensor.pitpat_treadmill_speed
  - number.pitpat_treadmill_speed_setting
  - sensor.pitpat_treadmill_distance
  - sensor.pitpat_treadmill_workout_time
  - type: buttons
    entities:
      - button.pitpat_treadmill_start
      - button.pitpat_treadmill_pause
      - button.pitpat_treadmill_stop
      - button.pitpat_treadmill_slower
      - button.pitpat_treadmill_faster
```

## Troubleshooting

- *Not discovered / unavailable:* treadmill on, close to the Pi or Bluetooth proxy,
  phone app closed (and the app's Bluetooth connection off).
- *Debug log:* add to `configuration.yaml` (File editor add-on) and restart:
  ```yaml
  logger:
    logs:
      custom_components.pitpat_treadmill: debug
  ```
- The old MQTT bridge (`pitpat_mqtt.py`) and this integration must not run at the
  same time, they would fight for the single Bluetooth connection.

## Development

`pip install pytest-homeassistant-custom-component` and run `pytest`. The tests run
against Home Assistant core with a simulated Bluetooth radio; the protocol was
reverse-engineered from the PitPat Android app and verified on a PitPat-T01.
