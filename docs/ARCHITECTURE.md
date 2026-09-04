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

## Failure policy

A workflow that requires a mobile proxy must not start unless a verified cellular exit IP is available.
