# Work

## Current milestone

Learn GenFarmer 2.6.1 `script.flow` exhaustively enough that Python can round-trip, generate and safely edit no-code Automation Apps without guessing undocumented node JSON.

## Completed

- [x] Establish project architecture and documentation.
- [x] Create canonical public GitHub repository.
- [x] Clone repository onto client Windows PC.
- [x] Keep client-specific network/device values out of the public repository.
- [x] Confirm 20 Android devices are simultaneously visible to ADB.
- [x] Add live ADB inventory script.
- [x] Run safe Device #1 Android Settings smoke test successfully.
- [x] Capture local screenshots/UI hierarchy/result JSON for the smoke run.
- [x] Confirm GenFarmer local service is reachable.
- [x] Identify GenFarmer service version as 2.6.1 from `GET /`.
- [x] Identify the API listener process as `GenFarmer.exe` version `2.6.1.0`.
- [x] Confirm GenFarmer is Electron-packaged and contains `resources/app.asar`.
- [x] Locate the official GenFarmer Local API documentation.
- [x] Confirm the official API documents Automation Apps, Tasks, Runs and current-user endpoints.
- [x] Add reusable `GenFarmerClient` based on the official API contract.
- [x] Keep all mutation methods fail-closed unless explicitly enabled.
- [x] Add a read-only official API compatibility smoke test.
- [x] Confirm official docs expose `script.flow` as `nodes` + `edges` but do not publish every node JSON schema.
- [x] Add lossless `FlowDocument` model that preserves unknown node/edge fields.
- [x] Add GET-only corpus learner for all accessible Automation Apps.
- [x] Add a shareable structural node catalog format that strips node values/client logic.
- [x] Add exact flow round-trip verification before any Python flow mutation is allowed.
- [x] Add tests for nested flow discovery, lossless round-trip, kind detection, template cloning and graph cleanup.
- [x] Document the full script.flow learning/completion protocol in `docs/SCRIPT_FLOW.md`.

## In progress

- [ ] Run `scripts/genfarmer_api_smoke.py` against GenFarmer 2.6.1.
- [ ] Run `scripts/genfarmer_flow_learn.py` to inventory every node kind already present in accessible apps.
- [ ] Upload/share `flow-catalog.shareable.json` back into the engineering conversation for schema analysis.
- [ ] Choose one harmless lab Automation App and prove exact Python round-trip equality.
- [ ] Create `GF Lab - Node Catalog` in the GenFarmer UI if the existing app corpus does not cover the full visible node palette.
- [ ] Add every missing palette node once using harmless/synthetic values so the learner can capture its real template.
- [ ] Differentially learn field semantics one field at a time for ambiguous nodes.
- [ ] Build versioned semantic Python adapters only after each node kind is proven.
- [ ] Determine the supported device ID / serial mapping required by task assignment.
- [ ] Execute one controlled harmless GenFarmer automation on Device #1 through the documented Task/Run API.

## Script.flow completion gate

We do not call script.flow support complete until all visible GenFarmer 2.6.1 node kinds are cataloged, edge/handle variants are known, exact round-trip is green, Python can perform a harmless edit that GenFarmer UI reloads correctly, and Python can generate/run a harmless flow from verified templates.

## Official-doc gaps to resolve

- [ ] Complete per-node `script.flow` JSON schemas are not publicly documented.
- [ ] Creating a brand-new Automation App through Local API is not clearly documented.
- [ ] Generic device inventory endpoint is not clearly documented.
- [ ] Fingerprint/change-device/profile API is not clearly documented.
- [ ] Proxy update/assignment API is not clearly documented.
- [ ] GET task-list endpoint is not clearly documented; the public page contains a mislabeled run-list cURL example.

For these gaps only, use observation/read-only inspection and verify against GenFarmer 2.6.1 before adding support.

## External hardware dependency

- [ ] Ensure SIM is present/active in the first modem.
- [ ] Verify real mobile public IP.
- [ ] Verify XProxy IP rotation.

## Later

- [ ] Add proxy-aware preflight/fail-closed behavior.
- [ ] Build authorized TikTok workflow.
- [ ] Multi-device orchestration.
- [ ] Scale production workflows only after single-device stability.
