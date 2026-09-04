# Runbook

## Recommended Windows checkout

`C:\genfarmer-lab\tiktok-genfarmer-automation`

## First-time setup

1. Clone the repository.
2. Create `.env` from `.env.example`.
3. Create `config/device-map.local.yaml` from `config/device-map.example.yaml`.
4. Fill client-specific local values.
5. Create a Python virtual environment.
6. Install project dependencies.
7. Run the safe single-device smoke test.

## Start-of-session checks

- ADB device reachable.
- GenFarmer API reachable.
- XProxy reachable when proxy is required.
- Required mobile public IP is verified.

## Evidence

Each run should record:
- timestamp
- logical device name
- workflow name
- success/failure
- screenshots/UI dumps where useful
- public IP when proxy is involved
- sanitized error information

Never commit account credentials or sensitive evidence.
