# Project Memory / Decisions

## Decisions

- GitHub repository is the canonical source of truth.
- Client PC keeps environment-specific configuration locally.
- Public repository must not contain client IPs, device IDs, credentials, account data, or secrets.
- Start with one device and scale only after deterministic success.
- Keep implementation, runbook, work log, and architecture synchronized.
- Basic device automation can proceed while modem/SIM hardware is repaired.
- Proxy-required application jobs fail closed unless a verified cellular public IP exists.
- The official GenFarmer API documentation is the primary contract for supported Local API calls.
- Packaged-app route discovery is retained only as a fallback for gaps not covered by official documentation.
- All GenFarmer POST/PUT/DELETE methods in our Python client are fail-closed by default and require explicit mutation opt-in.
- Use a hybrid architecture: GenFarmer Automation Apps/no-code flows execute device actions, while Python orchestrates devices, inputs, runs, retries, evidence, XProxy checks, and higher-level workflow state.
- The public API documents updating an Automation App's `script.flow`, but does not document a POST endpoint for creating a new Automation App. Safest bootstrap is to create one harmless app in the GenFarmer UI, read its app details, then learn/generate compatible flow JSON from Python.
- Direct Python ADB/Appium-style automation remains possible, but it bypasses GenFarmer's native Automation App/Task/Run engine and is not the preferred primary execution path for this project.

## Verified milestones

- 20 Android devices were simultaneously visible to ADB in the client lab.
- Device #1 completed the safe Settings smoke workflow successfully with local evidence capture.
- Device #1 UI was readable through UiAutomator; the visible Settings UI was French-localized.
- GenFarmer root endpoint identifies the local service as version 2.6.1.
- The process listening on the GenFarmer API port is `GenFarmer.exe`, product version `2.6.1.0`.
- GenFarmer is Electron-packaged and includes `resources/app.asar`.
- The public GenFarmer API documentation provides Local API examples using `127.0.0.1:55554` and documents Automation Apps, Tasks, Runs and current-user operations.
- A reusable official-API client and read-only compatibility smoke script now exist in the repository.

## Official API coverage

Documented read operations include:

- current user;
- list/get Automation Apps;
- list Automation Runs;
- retrieve run storage/output.

Documented mutation operations include:

- update/delete Automation Apps;
- create/update/delete Tasks;
- assign/remove devices on Tasks;
- create and execute Runs.

The public API page does not clearly document creating a new Automation App, a generic device inventory API, direct fingerprint/change-device API, proxy update API, or a reliable GET task-list endpoint. These remain controlled discovery items.

## Device identity caution

Several devices report an Android release value that does not naturally match SDK 35 (for example Android 10 with SDK 35). Because fingerprint/profile manipulation is part of the GenFarmer environment, do not treat individual `getprop` identity fields as authoritative until we compare raw/system identity with the active GenFarmer profile.

## Remaining work

- Run the official read-only API smoke against the installed 2.6.1 service.
- Create one harmless GenFarmer Automation App in the UI if no suitable existing app is available.
- Read that app back through the official API and capture its real `script.flow` node/edge schema.
- Generate/update compatible no-code flows from Python once the schema is proven.
- Capture actual response schemas and existing app/run IDs.
- Resolve GenFarmer device ID and serial mapping for Device #1.
- Execute one harmless authorized GenFarmer automation through the documented API.
- Resolve undocumented fingerprint and proxy integration surfaces only as needed.
- Verify XProxy cellular egress and rotation.
- Build the authorized TikTok workflow.
- Scale to the full device farm only after the single-device lane is stable.
