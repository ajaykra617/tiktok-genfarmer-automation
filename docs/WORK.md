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
- [x] Prove `type=custom` is a rendering family rather than a unique automation action.
- [x] Run semantic learner and identify seven real semantic actions: `Start`, `Variables`, `ContextMenu`, `Adb`, `DeepSeek`, `Pause`, `Screenshot`.
- [x] Record `Pause.timeoutType=fixed` as an observed enum value.
- [x] Record two observed edge-handle patterns: generated Start handle -> `successNode`, and `successNode` -> `successNode`.
- [x] Add privacy-safe semantic catalog tooling.
- [x] Add private before/after flow snapshots and shareable masked differential tooling.
- [x] Add local-only node template registry keyed by `type + data.action` and structural variant.
- [x] Add read-only `app.asar` palette/action scanners.
- [x] Classify the first broad static palette scan as noisy/insufficient for action discovery.
- [x] Run the strict V2 package scan: only 3 raw action-syntax matches, zero verified live actions recovered, zero package-only candidates.
- [x] Add a versioned GenFarmer 2.6.1 semantic action registry for the seven observed actions.
- [x] Run privacy-safe routing analysis against the private exact-flow corpus.
- [x] Prove all 3 observed non-null `data.successNode` pointers match an outgoing edge target.
- [x] Confirm no non-null `data.failNode` route exists yet in the current sample, so failure routing remains unproven.
- [x] Confirm official GitBook API page publishes a downloadable `GenFarmer.postman_collection.json` collection.
- [x] Add offline privacy-safe Postman collection analyzer.
- [x] Attempt Chromium remote debugging and confirm GenFarmer rejects `--remote-debugging-port` with its own `Invalid args. Exiting...` handling.
- [x] Add a structured ASAR source probe that reads the Electron archive as files instead of one opaque 248 MB byte stream.
- [x] Scan 16,170 text-bearing ASAR files and recover all 13 known Automation palette labels.
- [x] Identify `dist/render/assets/useScriptEditor-HioTuYH4.js` as the strongest Automation editor bundle: it contains all 13 known palette anchors in one file.
- [x] Add focused `genfarmer_node_registry_probe.py` to mine that bundle for likely node label/action/type/category associations and runtime option keys without emitting raw proprietary source.

## In progress

- [ ] Run `scripts/genfarmer_node_registry_probe.py` against `dist/render/assets/useScriptEditor-HioTuYH4.js`.
- [ ] Determine whether the bundle exposes the complete sidebar node registry in one pass.
- [ ] Pair palette labels with internal `data.action`/type/category identifiers where source evidence supports it.
- [ ] Recover generic per-node configuration-key sets from the editor bundle and compare them with live `script.flow` templates.
- [ ] Download the official `GenFarmer.postman_collection.json` to ignored local evidence and run `scripts/genfarmer_postman_analyze.py`.
- [ ] Compare collection endpoints/request schemas against the public GitBook baseline and our Python client.
- [ ] Create `GF Lab - Node Catalog` only for nodes/settings that remain unverified after source-registry mining.
- [ ] Run structural + semantic + routing learners against the Node Catalog app.
- [ ] Populate the local template registry from the private exact-flow corpus.
- [ ] Learn failure routing with one harmless failure edge.
- [ ] Learn every ambiguous option using one-field-at-a-time snapshots/diffs.
- [ ] Prove exact round-trip equality for the lab app.
- [ ] Perform one harmless Python-generated edit and verify GenFarmer UI reloads it correctly.
- [ ] Generate a harmless flow from verified templates and execute it on Device #1.

## Currently verified semantic actions

| Semantic kind | Family | Key observed options/behavior |
|---|---|---|
| `input:Start` | `input` | graph entry; generated Start handle routes into target `successNode` |
| `helper:Variables` | `helper` | empty options object in first corpus |
| `custom-context-menu:ContextMenu` | `custom-context-menu` | `casePaths` object observed |
| `custom:Adb` | `custom` | command/outputVariable plus common runtime controls |
| `custom:DeepSeek` | `custom` | common runtime controls observed |
| `custom:Pause` | `custom` | timeout/fixed-range fields; `timeoutType=fixed` observed |
| `custom:Screenshot` | `custom` | common runtime controls observed |

These are structurally verified, not fully behaviorally modeled. Unknown options remain template-clone-only until differential tests prove their semantics.

## Specific semantics still to learn

- [ ] app launch/stop/actions;
- [ ] tap/click selector modes;
- [ ] text/resource-id/XPathLite/class/coordinates selectors;
- [ ] random/range wait semantics;
- [ ] swipe/scroll/gesture nodes;
- [ ] input/type/paste nodes;
- [ ] variables/input/output/storage details;
- [ ] conditions/branches/case-path handle semantics;
- [ ] loops/retry/failure paths;
- [ ] module/context/function nodes;
- [ ] screenshot output/storage behavior;
- [ ] image/vision nodes if present;
- [ ] network/device/system nodes if present;
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
