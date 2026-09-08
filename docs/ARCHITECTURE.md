# Architecture

## Target topology

```text
Python Controller
        |
        +--> GenFarmer API
        |       |
        |       +--> Android Device(s)
        |       +--> fingerprint/profile operations
        |       +--> device/app automation
        |
        +--> XProxy
                |
                +--> per-position HTTP proxy
                +--> per-position SOCKS5 proxy
                +--> cellular modem/SIM
                +--> mobile public IP
```

## Configuration policy

Client-specific IP addresses, device IDs, credentials, and account data are local-only and must not be committed to this public repository.

Use:
- `.env`
- `config/device-map.local.yaml`

Both are Git-ignored.

## Execution phases

1. Device connectivity
2. Safe Android smoke automation
3. GenFarmer API-driven control
4. XProxy mobile-IP verification and rotation
5. Reusable workflow engine
6. Authorized application workflow
7. Multi-device scaling

## Supervisory execution model

GenFarmer is the Android action executor. Python is the supervisor.

Production sessions should not be one long linear GenFarmer graph. Python should execute short deterministic modules, observe the device between modules, handle known interrupts, verify preconditions/postconditions, checkpoint progress and enforce bounded retry/deadline policies.

Core control loop:

```text
observe
  -> classify/handle global interrupts
  -> verify precondition
  -> execute short GenFarmer module
  -> verify postcondition
  -> checkpoint
  -> continue/recover/stop
```

A successful ADB/GenFarmer gesture is not by itself proof that the intended app state changed. See `docs/RESILIENCE.md` for false-success protection, interrupt handling, recovery tiers and circuit-breaker policy.

## Failure policy

A workflow that requires a mobile proxy must not start unless a verified cellular exit IP is available.

Unknown UI states, repeated failed postconditions, login/challenge states and exhausted retry budgets must fail closed with local evidence rather than continuing with blind taps or assumed state.
