# Project Memory / Decisions

## Decisions

- GitHub repository is the canonical source of truth.
- Client PC keeps environment-specific configuration locally.
- Public repository must not contain client IPs, device IDs, credentials, account data, or secrets.
- Start with one device and scale only after deterministic success.
- Keep implementation, runbook, work log, and architecture synchronized.
- Basic device automation can proceed while modem/SIM hardware is repaired.
- Proxy-required application jobs fail closed unless a verified cellular public IP exists.
- Prefer observation and read-only discovery before guessing GenFarmer API routes.

## Verified milestones

- 20 Android devices were simultaneously visible to ADB in the client lab.
- Device #1 completed the safe Settings smoke workflow successfully with local evidence capture.
- Device #1 UI was readable through UiAutomator; the visible Settings UI was French-localized.
- GenFarmer root endpoint identifies the local service as version 2.6.1.
- Common health/version/Swagger/OpenAPI paths tested by the read-only discovery script returned 404.

## Device identity caution

Several devices report an Android release value that does not naturally match SDK 35 (for example Android 10 with SDK 35). Because fingerprint/profile manipulation is part of the GenFarmer environment, do not treat individual `getprop` identity fields as authoritative until we compare raw/system identity with the active GenFarmer profile.

## Remaining work

- Discover the GenFarmer listener process and local route surface.
- Complete GenFarmer endpoint inventory.
- Map GenFarmer device identifiers to ADB devices.
- Implement reusable GenFarmer client/orchestration.
- Verify XProxy cellular egress and rotation.
- Build authorized application workflow.
- Scale to the full device farm only after the single-device lane is stable.
