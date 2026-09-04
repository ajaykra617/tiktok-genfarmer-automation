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
- Treat `script.flow` node schemas as version-specific and empirically verified. Do not invent undocumented node JSON from labels alone.
- Learn `script.flow` exhaustively from three sources in order: official docs, the user's own accessible Automation App corpus, then a dedicated harmless `GF Lab - Node Catalog` app containing every missing visible palette node.
- Raw client app flows remain local under git-ignored evidence and must not be committed. Only generic structural schemas, our own lab templates and reusable code belong in the public repository.
- Python flow editing must be lossless: unknown node, edge and top-level flow fields are preserved exactly. New nodes should initially be cloned from real GenFarmer-generated templates of the same kind and only verified fields changed.

## Verified milestones

- 20 Android devices were simultaneously visible to ADB in the client lab.
- Device #1 completed the safe Settings smoke workflow successfully with local evidence capture.
- Device #1 UI was readable through UiAutomator; the visible Settings UI was French-localized.
- GenFarmer root endpoint identifies the local service as version 2.6.1.
- The process listening on the GenFarmer API port is `GenFarmer.exe`, product version `2.6.1.0`.
- GenFarmer is Electron-packaged and includes `resources/app.asar`.
- The public GenFarmer API documentation provides Local API examples using `127.0.0.1:55554` and documents Automation Apps, Tasks, Runs and current-user operations.
- A reusable official-API client and read-only compatibility smoke script exist in the repository.
- The official API confirms that `script.flow` contains graph `nodes` and `edges`, but does not publish complete per-node JSON schemas.
- A lossless Python `FlowDocument`, GET-only flow-corpus learner, shareable structural catalog, round-trip verifier and unit tests now exist.

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

The public API page does not clearly document creating a new Automation App, a generic device inventory API, direct fingerprint/change-device API, proxy update API, a reliable GET task-list endpoint, or the complete schema of every no-code node. These remain controlled discovery items.

## Script.flow completion rule

For GenFarmer 2.6.1, do not claim full Python flow generation/editing support until the full visible node palette has been cataloged, structural variants and edge/handle behavior are known, exact round-trip equality is proven, a harmless Python edit reloads correctly in the GenFarmer UI, and a harmless Python-generated flow executes successfully from verified templates.

## Device identity caution

Several devices report an Android release value that does not naturally match SDK 35 (for example Android 10 with SDK 35). Because fingerprint/profile manipulation is part of the GenFarmer environment, do not treat individual `getprop` identity fields as authoritative until we compare raw/system identity with the active GenFarmer profile.

## Remaining work

- Run the official read-only API smoke against the installed 2.6.1 service.
- Run the GET-only `script.flow` learner across accessible apps and inspect the shareable structural catalog.
- Create `GF Lab - Node Catalog` if existing apps do not cover every visible palette node.
- Learn missing node defaults and field semantics one field at a time with harmless UI diffs.
- Add versioned semantic Python adapters only after each node kind is verified.
- Capture actual response schemas and existing app/run IDs.
- Resolve GenFarmer device ID and serial mapping for Device #1.
- Execute one harmless authorized GenFarmer automation through the documented API.
- Resolve undocumented fingerprint and proxy integration surfaces only as needed.
- Verify XProxy cellular egress and rotation.
- Build the authorized TikTok workflow.
- Scale to the full device farm only after the single-device lane is stable.
