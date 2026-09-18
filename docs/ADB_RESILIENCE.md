# ADB resilience plan

ADB is a shared infrastructure dependency for the device farm. The reliability
target is not "ADB can never fail"; no network/device process can provide that
guarantee. The target is: **no silent hang, bounded self-healing for safe
operations, per-device isolation, and precise failure classification.**

## Failure domains

Treat these as different failures instead of reporting all of them as
`adb ... timed out`:

1. Host adb binary/server unavailable.
2. One TCP device transport is offline, unauthorized, or stale.
3. The Android shell channel is unhealthy even though the transport exists.
4. A read-only Android command is slow/wedged.
5. A mutating Android command such as `input swipe` is wedged while ADB itself
   is still healthy. This commonly happens when Android input dispatch or the
   target app is ANR.
6. GenFarmer/helper accessibility state is unhealthy while ADB remains healthy.

## Production rules

### One process-safe lane per physical device

Repository workers serialize their own ADB commands for the same device using a
cross-process file lock. Different devices retain parallelism. This prevents two
Python workers from issuing overlapping mutations/observations to one serial.

GenFarmer is a separate process and does not honor this lock, so a timed-out UI
mutation is still treated as ambiguous.

### Never kill the shared adb server from a device worker

`adb kill-server` would interrupt every phone. Device workers may call the
idempotent `adb start-server`, but a destructive host-server restart must only
happen in a future fleet coordinator when no device mutation is in flight.

### Health proof

A device transport is healthy only when both checks pass within a short deadline:

- `adb -s SERIAL get-state` returns `device`.
- `adb -s SERIAL shell echo __GF_ADB_OK__` returns the marker.

This distinguishes a registered transport from a usable shell channel.

### Per-device recovery ladder

For read-only commands only:

1. Retry after health classification.
2. Ensure the host adb server is running.
3. Re-prove `get-state` and the shell channel.
4. For a TCP serial that remains unhealthy, disconnect/reconnect only that
   serial.
5. Retry the read-only operation once.
6. Fail with typed evidence if the channel is still unhealthy.

There is no unbounded retry loop.

### Mutations are never blindly replayed

Tap, swipe, keyevent, text input, force-stop, and launch are mutations. If one
times out or returns an uncertain failure, the transport immediately probes ADB
health but **does not send the mutation again**.

The result explicitly says whether:

- ADB transport remained healthy, which points toward Android input/app stall; or
- ADB transport was unhealthy, which points toward transport recovery.

The workflow must then prove a semantic postcondition or recover from a known
checkpoint.

## Fleet diagnostics

Use the read-only concurrent probe before a client run:

```powershell
python scripts\adb_fleet_probe.py `
  --device "GF1=192.168.4.138:5555" `
  --device "GF7=192.168.4.143:5555" `
  --cycles 60 `
  --interval 0.25 `
  --timeout 5
```

It records per-device pass/failure counts, recovery counts, latency p50/p95/max,
and detailed cycle evidence under `evidence/adb-fleet-probe-*/`.

Interpretation:

- both devices fail read-only probes together: investigate host adb server,
  Windows host load, or LAN;
- one device fails while the peer remains healthy: investigate that phone,
  adbd, cable/network path, or IP stability;
- read-only probe is clean but `input swipe` times out: ADB is not the primary
  failure; diagnose Android input dispatch/TikTok ANR;
- reconnect recovery succeeds: count it as a degraded transport event, not a
  clean pass.

## Fleet target

Before scaling beyond the current two-device test:

- 60 concurrent read-only cycles per active phone;
- zero unrecovered transport failures;
- no global adb-server restart;
- p95 latency comfortably below the command deadline;
- production mutation timeouts include post-timeout transport health;
- one device failure must not interrupt another device.

For a 20-device farm, add a dedicated fleet coordinator that owns host-server
maintenance and consumes persistent `adb track-devices` state. Worker processes
must never independently restart the global adb server.
