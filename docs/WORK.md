# Work

## Current milestone

Learn the GenFarmer 2.6.1 `script.flow` language exhaustively enough to create and edit Automation Apps from Python without guessing undocumented node payloads.

## Completed

- [x] Establish project architecture and documentation.
- [x] Create canonical public GitHub repository.
- [x] Clone repository onto client Windows PC.
- [x] Keep client-specific network/device values out of the public repository.
- [x] Confirm 20 Android devices are simultaneously visible to ADB.
- [x] Run safe Device #1 Android Settings smoke test successfully.
- [x] Confirm GenFarmer local service is reachable and identifies as 2.6.1.
- [x] Locate the official GenFarmer Local API documentation.
- [x] Add reusable `GenFarmerClient` based on the documented API.
- [x] Keep all mutation methods fail-closed unless explicitly enabled.
- [x] Add lossless `script.flow` reader/editor and round-trip tests.
- [x] Run first read-only `script.flow` corpus pass.
- [x] First corpus: 1 app, 7 nodes, 3 edges, 4 broad Vue Flow families.
- [x] Identify that `type=custom` is a rendering family, not a unique automation action.
- [x] Identify `data.action` as a key semantic discriminator to catalog next.
- [x] Add privacy-safe semantic catalog tooling.
- [x] Add private before/after flow snapshots and shareable masked differential tooling.

## In progress

- [ ] Run `scripts/genfarmer_flow_semantics.py` against the existing app corpus.
- [ ] Capture the distinct `data.action` operations hidden under `type=custom`.
- [ ] Create `GF Lab - Node Catalog` in the GenFarmer UI.
- [ ] Add every visible node-palette item once using harmless synthetic configuration.
- [ ] Run structural + semantic learners against the Node Catalog app.
- [ ] Build a versioned node-template registry for GenFarmer 2.6.1.
- [ ] Learn every ambiguous option using one-field-at-a-time snapshots/diffs.
- [ ] Prove exact round-trip equality for the lab app.
- [ ] Perform one harmless Python-generated edit and verify GenFarmer UI reloads it correctly.
- [ ] Generate a harmless flow from verified templates and execute it on Device #1.

## Specific semantics to learn

- [ ] start/end/helper/context nodes;
- [ ] app launch/stop/actions;
- [ ] tap/click selector modes;
- [ ] text/resource-id/XPathLite/class/coordinates selectors;
- [ ] wait/sleep/timeout modes;
- [ ] swipe/scroll/gesture nodes;
- [ ] input/type/paste nodes;
- [ ] variables/input/output/storage nodes;
- [ ] conditions/branches/case paths;
- [ ] loops/retry/failure paths;
- [ ] module/context/function nodes;
- [ ] screenshot/image/vision nodes if present;
- [ ] network/device/system nodes if present;
- [ ] edge handle semantics and success/failure routing;
- [ ] defaults, required fields, optional fields and enum values for every action.

## Official-doc gaps to resolve later

- [ ] Generic device inventory endpoint is not clearly documented.
- [ ] Fingerprint/change-device/profile API is not clearly documented.
- [ ] Proxy update/assignment API is not clearly documented.
- [ ] GET task-list endpoint is not clearly documented.

## External hardware dependency

- [ ] Ensure SIM is present/active in the first modem.
- [ ] Verify real mobile public IP.
- [ ] Verify XProxy IP rotation.

## Later

- [ ] Add proxy-aware preflight/fail-closed behavior.
- [ ] Build authorized TikTok workflow using verified GenFarmer flow templates.
- [ ] Multi-device orchestration.
- [ ] Scale production workflows only after single-device stability.
