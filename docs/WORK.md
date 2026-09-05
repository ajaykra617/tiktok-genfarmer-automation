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
- [x] Expand exact source-derived palette coverage to 60 direct registry rows, including Clipboard, Cmd, Comment, Gemini, GenRouter, Grok, HTTP, If, Javascript, Log, Loop, Random, Reconnect, Spreadsheet, Stop, Swipe/Scroll, Touch and Xpath.
- [x] Run fail-closed action constant resolver V2 across 199 renderer assets.
- [x] Resolve 56/60 palette actions with explicit provenance: 55 `unique-source` plus live `Screenshot` anchor.
- [x] Validate all four live-known resolver anchors: `ADB -> Adb`, `DEEPSEEK -> DeepSeek`, `PAUSE -> Pause`, `SCREENSHOT -> Screenshot`.
- [x] Keep ambiguous `HTTP`, `LOG`, `RANDOM`, and `STOP` unresolved; V2 correctly rejected conflicting candidate literals and accepted no canonical map.
- [x] Run `genfarmer_node_factory_ast.py` across 199 renderer assets.
- [x] Confirm source factory/default mining produced `0/60` usable candidates at score >=20; only sparse switch evidence exists for Case Path, Comment, Loop, Multi Element exists and Stop.
- [x] Adopt stopping rule: do not spend more time broad-mining minified renderer code for default node payloads unless a new high-confidence source path appears.
- [x] Add versioned `palette_catalog_261.py` containing all 60 source-proven rows, 56 resolved actions and four explicit unresolved rows.
- [x] Add GET-only `genfarmer_lab_catalog_audit.py` to measure live template coverage and report privacy-safe data/option field-type shapes.

## In progress

- [ ] Create a dedicated GenFarmer Automation App named `GF Lab - Node Catalog`.
- [ ] Add source-proven palette nodes to the lab app in manageable batches, save, and run `scripts/genfarmer_lab_catalog_audit.py` after each batch.
- [ ] Capture exact GenFarmer-generated `script.flow` templates for all 60 palette actions without fabricating payloads.
- [ ] Resolve `HTTP`, `LOG`, `RANDOM`, and `STOP` from live saved nodes.
- [ ] Run structural + semantic + routing learners against the lab app as coverage grows.
- [ ] Populate the local-only template registry from exact private raw-flow evidence.
- [ ] Learn one harmless failure route and every ambiguous option with one-field-at-a-time snapshots/diffs.
- [ ] Download the official `GenFarmer.postman_collection.json` to ignored local evidence and run `scripts/genfarmer_postman_analyze.py`.
- [ ] Prove exact round-trip equality for the lab app.
- [ ] Perform one harmless Python-generated edit and verify GenFarmer UI reloads it correctly.
- [ ] Generate a harmless flow from verified templates and execute it on Device #1.

## Current evidence levels

- **Live-verified serialization:** exact node exists in a saved GenFarmer `script.flow`.
- **AST palette-registry row:** renderer object directly contains `label`, `action` and `icon` properties; strong source evidence for palette membership/action constant.
- **Source-resolved literal:** source action constant is mapped to exactly one string literal by structural evidence.
- **Live-flow anchor:** exact saved `script.flow` resolves an otherwise source-ambiguous constant.
- **Lab-captured template:** exact GenFarmer-generated node object exists in the dedicated lab flow and can be loaded into the private template registry.
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
