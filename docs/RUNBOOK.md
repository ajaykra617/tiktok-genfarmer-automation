# Runbook

## Recommended Windows checkout

`C:\genfarmer-lab\tiktok-genfarmer-automation`

## Normal update cycle in VS Code

From the VS Code terminal:

```powershell
git pull --ff-only origin main
git log -1 --oneline
```

The client PC does not need GitHub authentication for clone/pull because the repository is public. Local-only files remain ignored by Git.

## Local configuration

Create once:

```powershell
Copy-Item .env.example .env
Copy-Item config\device-map.example.yaml config\device-map.local.yaml
```

Populate `.env` and `config/device-map.local.yaml` with client-specific values. Never commit those files.

## Device checks

Inventory all attached Android devices:

```powershell
python scripts/device_inventory.py
```

Run the safe single-device Settings smoke test:

```powershell
python scripts/device_smoke.py --device <ADB_DEVICE_ID>
```

## GenFarmer discovery

First perform conventional GET-only metadata discovery:

```powershell
python scripts/genfarmer_discovery.py
```

If no Swagger/OpenAPI documentation is exposed, inspect the local Windows listener and nearby application assets read-only:

```powershell
python scripts/genfarmer_local_inspect.py
```

The local-inspection script:

- identifies the process bound to the configured GenFarmer port;
- records executable/product/version metadata;
- sanitizes credential-like command-line arguments;
- lists candidate application roots/files;
- scans only nearby non-secret text assets for route-like strings;
- writes results under ignored `evidence/`;
- modifies no GenFarmer files.

To identify only the process without scanning assets:

```powershell
python scripts/genfarmer_local_inspect.py --no-scan
```

## Start-of-session checks

- Repository is up to date.
- ADB target is reachable.
- GenFarmer API is reachable.
- XProxy is reachable when proxy is required.
- A required mobile public IP is verified before proxy-required application workflows.

## Evidence

Each run should record:

- timestamp;
- logical device/workflow;
- success/failure;
- screenshots/UI dumps where useful;
- public IP when proxy is involved;
- sanitized diagnostic information.

Never commit account credentials or sensitive evidence.
