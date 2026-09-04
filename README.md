# TikTok Automation / GenFarmer

Canonical codebase for authorized Android automation using GenFarmer, Python, XProxy, and real Android devices.

## Current phase

- Single-device automation foundation
- GenFarmer API discovery/integration
- XProxy health and mobile-IP integration
- Evidence-driven automation runs
- Authorized application workflows only

## Project principles

1. Authorized devices/accounts/apps only.
2. No secrets or client-specific network details committed to source control.
3. One-device smoke tests before scaling.
4. Fail closed when required infrastructure is unhealthy.
5. Every automation run should produce evidence.
6. Keep documentation synchronized with implementation.

## Local client configuration

Copy:

```text
.env.example -> .env
config/device-map.example.yaml -> config/device-map.local.yaml
```

Then populate the local files on the client PC. Both local files are ignored by Git.

## Structure

- `docs/` — architecture, API notes, runbook, work log, decisions
- `config/` — safe examples; local client config is ignored
- `src/` — Python automation code
- `scripts/` — Windows/bootstrap/diagnostic scripts
- `tests/` — automated tests
- `evidence/` — local screenshots/UI dumps/results; ignored
- `logs/` — local logs; ignored
