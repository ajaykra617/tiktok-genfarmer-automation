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
- [x] Add read-only `app.asar` palette/action scanner.
- [x] Classify the first broad static palette scan as noisy/insufficient for action discovery.
- [x] Add a stricter package scanner that only considers PascalCase `action:` tokens and scores GenFarmer runtime markers.
- [x] Add a versioned GenFarmer 2.6.1 semantic action registry for the seven observed actions.

## In progress

- [ ] Run `scripts/genfarmer_palette_scan_v2.py` against GenFarmer 2.6.1.
- [ ] Compare strict package-only candidates with the seven verified live actions.
- [ ] Create `GF Lab - Node Catalog` only for actions still lacking a live saved template.
- [ ] Add every still-unobserved visible node-palette item once using harmless synthetic configuration.
- [ ] Run structural + semantic learners against the Node Catalog app.
- [ ] Populate the local template registry from the private exact-flow corpus.
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
