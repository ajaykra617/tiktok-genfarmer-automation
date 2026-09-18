# Persistent device self-healing (reboot disabled)

## Purpose

Some physical phones can repeatedly ANR or fail accessibility even while ADB remains healthy.
The fleet therefore needs a persistent per-device worker that can keep trying without
turning one bad phone into a failure for the other devices.

This design keeps every recovery cycle bounded while allowing the worker itself to
run indefinitely when explicitly started with `--persistent`.

## Recovery boundary

Implemented now:

- detect/record the client failure;
- capture private runtime diagnostics;
- prove ADB health;
- force-stop only TikTok;
- wait and prove the TikTok process actually disappeared;
- retry force-stop once only when the process is positively still alive;
- relaunch the qualified TikTok component;
- require multiple stable foreground observations;
- retry the passive/pre-publish client demo from a fresh checkpoint;
- increase cooldown after consecutive failures;
- recommend reboot approval after repeated failures, but do not reboot.

Explicitly disabled:

- device reboot;
- `pm clear` / TikTok data or cache clearing;
- global `adb kill-server`;
- arbitrary app killing;
- automatic final publishing or engagement.

## Cooldown policy

Consecutive failures currently use capped cooldowns:

`2s -> 5s -> 10s -> 20s -> 30s -> 60s -> 60s ...`

After the third consecutive failure the worker emits
`REBOOT_APPROVAL_RECOMMENDED`, but continues app-only recovery and never issues
a reboot command.

## Usage

Bounded validation:

```powershell
python scripts\tiktok_persistent_device_worker.py `
  "evidence\tiktok-feed-anchor-ranking-20260913T040840Z\private\ranked-candidates.private.json" `
  --candidate 8 `
  --device "192.168.4.138:5555" `
  --proxy-id "xproxy-pos-1" `
  --media "C:\genfarmer-lab\boost-test.mp4" `
  --keyword "technology" `
  --hashtag "technology" `
  --videos 3 `
  --watch-min 4 `
  --watch-max 7 `
  --dwell 3 `
  --seed 43 `
  --max-app-restarts 3 `
  --max-cycles 6
```

Persistent mode, only after bounded validation:

```powershell
...same command... --persistent
```

Stop persistent mode with Ctrl+C. The worker writes cycle logs and a shareable
state file under `evidence/persistent-device-worker-*`.

## Future reboot escalation

Do not add a reboot action until the client explicitly approves it. If approved,
implement it as a separate opt-in escalation with its own limits, ADB-return
deadline, network/proxy revalidation, and audit evidence. It must never be an
implicit side effect of ordinary app recovery.
