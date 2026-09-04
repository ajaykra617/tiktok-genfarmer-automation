# Runbook

## Recommended Windows checkout

`C:\genfarmer-lab\tiktok-genfarmer-automation`

## Client Git model

The client PC does not need GitHub authentication for this public repository.
Clone once, then update with:

```bash
cd /c/genfarmer-lab/tiktok-genfarmer-automation
git pull --ff-only origin main
```

Do not repeatedly delete/re-clone the repository because local ignored configuration and evidence should remain in place.

## First-time local configuration

1. Copy `.env.example` to `.env`.
2. Copy `config/device-map.example.yaml` to `config/device-map.local.yaml`.
3. Fill client-specific values locally.
4. Never commit those local files.

## Runtime discovery

List live devices plus basic Android information:

```bash
python scripts/device_inventory.py
```

JSON output is also available:

```bash
python scripts/device_inventory.py --json
```

## Safe single-device smoke test

Choose exactly one ADB device from the inventory and run:

```bash
python scripts/device_smoke.py --device DEVICE_IP:5555
```

For launch/read-only verification without the optional Settings navigation tap:

```bash
python scripts/device_smoke.py --device DEVICE_IP:5555 --no-navigation
```

The smoke test:
- verifies ADB state;
- reads basic device properties;
- opens Android Settings;
- captures screenshot and UI hierarchy evidence;
- optionally performs one deliberately limited read-only navigation tap;
- returns Home;
- writes `result.json` under the ignored `evidence/` directory.

## Start-of-session checks

- Git checkout is current.
- ADB device(s) reachable.
- GenFarmer API reachable.
- XProxy reachable when proxy is required.
- Required mobile public IP is verified before proxy-required workflows.

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
