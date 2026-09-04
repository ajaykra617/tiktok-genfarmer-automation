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
- [x] Run semantic learner and identify seven real serialized semantic actions: `Start`, `Variables`, `ContextMenu`, `Adb`, `DeepSeek`, `Pause`, `Screenshot`.
- [x] Record `Pause.timeoutType=fixed` as an observed enum value.
- [x] Record success-edge handle patterns and prove all observed non-null `successNode` pointers match outgoing edge targets.
- [x] Add privacy-safe semantic catalog, snapshots, masked differential tooling and local-only node template registry.
- [x] Confirm official GitBook API page publishes a downloadable `GenFarmer.postman_collection.json` collection and add an offline analyzer.
- [x] Attempt Chromium remote debugging and confirm GenFarmer rejects `--remote-debugging-port` with its own argument parser.
- [x] Add structured ASAR source inspection and scan 16,170 text-bearing files.
- [x] Identify `dist/render/assets/useScriptEditor-HioTuYH4.js` as the primary Automation editor source bundle and confirm it has no source map.
- [x] Separate settings-form controls (`Input`, `Select`, `Switch`, `Slider`, `TextArea`, `Grid`, etc.) from Automation node candidates.
- [x] Run regex/proximity settings probes v1/v2 and classify them as too noisy for trustworthy per-node settings attribution.
- [x] Add AST-based JavaScript probes and prove many `action*` tokens are icon values, not serialized actions.
- [x] Add exact AST `label` + `action` + `icon` palette extraction.
- [x] Expand exact source-derived palette coverage to 60 direct registry rows, including additional rows such as Clipboard, Cmd, Comment, Gemini, GenRouter, Grok, HTTP, If, Javascript, Log, Loop, Random, Reconnect, Spreadsheet, Stop, Swipe/Scroll, Touch and Xpath.
- [x] Resolve 55 of 60 source action constants directly to literals in the first resolver pass.
- [x] Cross-check live saved flow anchors: `H.ADB -> Adb`, `H.DEEPSEEK -> DeepSeek`, `H.PAUSE -> Pause`; `SCREENSHOT` remains source-ambiguous in V1 but exact live serialization is independently known as `Screenshot`.
- [x] Add `genfarmer_action_constant_resolver_v2.py` to use fail-closed canonical-map consensus for ambiguous constants and explicit live-flow provenance where exact saved evidence already exists.

## In progress

- [ ] Run `scripts/genfarmer_action_constant_resolver_v2.py` and determine whether a canonical constant map resolves the remaining source ambiguity.
- [ ] Keep `HTTP`, `LOG`, `RANDOM`, and `STOP` unresolved unless V2 finds conflict-free canonical evidence; do not infer values from names.
- [ ] Build the confidence-ranked label -> source constant -> serialized `data.action` catalog.
- [ ] Use exact action literals as anchors for per-node settings discovery.
- [ ] Download the official `GenFarmer.postman_collection.json` to ignored local evidence and run `scripts/genfarmer_postman_analyze.py`.
- [ ] Create `GF Lab - Node Catalog` only for actions/settings that still lack exact saved templates after source mining.
- [ ] Run structural + semantic + routing learners against the Node Catalog app.
- [ ] Learn one harmless failure route and every ambiguous option with one-field-at-a-time snapshots/diffs.
- [ ] Prove exact round-trip equality for the lab app.
- [ ] Perform one harmless Python-generated edit and verify GenFarmer UI reloads it correctly.
- [ ] Generate a harmless flow from verified templates and execute it on Device #1.

## Current evidence levels

- **Live-verified serialization:** exact node exists in a saved GenFarmer `script.flow`.
- **AST palette-registry row:** renderer object directly contains `label`, `action` and `icon` properties; strong source evidence for palette membership/action constant.
- **Source-resolved literal:** source action constant is mapped to exactly one string literal by structural evidence.
- **Canonical-map resolution:** V2 may resolve an otherwise ambiguous constant only from a large constant map that has zero conflicts with unique source evidence and live anchors.
- **Source-discovered candidate:** token exists in the real editor source but lacks exact registry/serialization evidence.
- **Ambiguous token:** useful lead only; not promoted to the authoring registry.

## Specific semantics still to learn

- [ ] app launch/stop/install/uninstall/data-clear actions;
- [ ] tap/touch selector modes;
- [ ] text/resource-id/XPathLite/class/coordinates selectors;
- [ ] random/range wait semantics;
- [ ] swipe/scroll/gesture nodes;
- [ ] input/type/clipboard nodes;
- [ ] variables/input/output/storage details;
- [ ] conditions/branches/case-path handle semantics;
- [ ] loops/retry/failure paths;
- [ ] file/spreadsheet/HTTP/IMAP/AI nodes;
- [ ] screenshot/image-search/asset-storage behavior;
- [ ] network/device/system nodes;
- [ ] defaults, required fields, optional fields and enum values for every action.

## External hardware dependency

- [ ] Ensure SIM is present/active in the first modem.
- [ ] Verify real mobile public IP.
- [ ] Verify XProxy IP rotation.

## Later

- [ ] Add proxy-aware preflight/fail-closed behavior.
- [ ] Build authorized TikTok workflow using verified GenFarmer flow templates.
- [ ] Multi-device orchestration.
- [ ] Scale production workflows only after single-device stability.
