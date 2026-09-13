# TikTok Automation / GenFarmer

Canonical codebase for authorized Android automation using GenFarmer, Python, XProxy, and real Android devices.

## Current phase

- TikTok Warm-up end-to-end qualification
- TikTok Boost Explore + approved-media Post qualification
- GenFarmer API integration with bounded ADB fallback
- XProxy health/mobile-IP integration
- barrier scheduler and same-app proxy-identity policy
- local Python operator UI
- evidence-driven automation runs
- authorized application workflows only

## Project principles

1. Authorized devices/accounts/apps only.
2. No secrets or client-specific network details committed to source control.
3. Qualify one healthy device before scaling.
4. Fail closed when required infrastructure or postconditions are unhealthy.
5. Every automation run should produce evidence.
6. Keep documentation synchronized with implementation.
7. Do not automate DMs, mass follow/unfollow, coordinated engagement, checkpoint/captcha bypass, or proxy rotation during login/upload.

## Local client configuration

Copy:

```text
.env.example -> .env
config/device-map.example.yaml -> config/device-map.local.yaml
```

Then populate the local files on the client PC. Both local files are ignored by Git.

## Desktop control center

The local operator UI uses Python/Tkinter and launches the same tested scripts used from PowerShell:

```powershell
python scripts/automation_console.py
```

Tabs currently cover:

- Dashboard / ADB devices
- Warm-up presets and launch
- Boost Explore + approved-media Post
- scheduler-plan validation
- live output and audit logs

No credentials are stored in the UI.

## Structure

- `docs/` — architecture, client-requirement map, API notes, runbook, work log, decisions
- `config/` — safe examples; local client config is ignored
- `src/` — Python automation/control-plane code
- `scripts/` — Windows/bootstrap/automation/diagnostic scripts and local UI
- `tests/` — automated tests
- `evidence/` — local screenshots/UI dumps/results; ignored
- `logs/` — local logs; ignored
