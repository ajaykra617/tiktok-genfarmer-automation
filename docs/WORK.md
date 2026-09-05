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
- [x] Run first structural/semantic/routing corpus passes and identify the original seven live semantic actions.
- [x] Add privacy-safe semantic catalogs, snapshots, masked differential tooling and local-only node template registry.
- [x] Identify the Automation editor renderer bundle and recover the exact source palette registry with AST tooling.
- [x] Recover 60 exact `label + action + icon` palette rows.
- [x] Resolve source action literals with fail-closed provenance and stop source-side default mining after it yielded `0/60` usable factory/default candidates.
- [x] Add versioned `palette_catalog_261.py` and GET-only live catalog auditor.
- [x] Create/populate `GF Lab - Node Catalog` with every available palette node.
- [x] Full lab audit: 62 nodes, 0 edges, 56/57 then-current resolved actions captured; only Group Node was absent from `data.action` coverage.
- [x] Resolve all four previously ambiguous source constants from exact saved lab evidence: `H.HTTP -> HTTP`, `H.LOG -> Log`, `H.RANDOM -> Random`, `H.STOP -> Stop`.
- [x] Palette catalog is now 60/60 resolved actions with explicit source/live provenance.
- [x] Add `genfarmer_lab_template_capture.py` to save the exact lab flow privately and emit a shareable per-node structural/options inventory, including nodes without `data.action`.

## In progress

- [ ] Run `python -m pytest tests/test_palette_catalog_261.py` after pulling the 60/60 catalog update.
- [ ] Run `scripts/genfarmer_lab_template_capture.py` against the completed lab app.
- [ ] Identify `Group Node` from the no-`data.action` structural fingerprint and distinguish it from Start/Variables/Context Menu helpers.
- [ ] Load the private exact 62-node lab flow into the local-only `TemplateRegistry` and inventory every distinct node template/variant.
- [ ] Rank actions requiring one-field-at-a-time setting diffs; default shapes alone do not prove every selector/mode/enum.
- [ ] Create a separate tiny routing lab for success/failure/branch edges so the full catalog corpus remains unconnected and stable.
- [ ] Run structural + semantic learners against the completed lab app and compare with the versioned catalog.
- [ ] Download the official `GenFarmer.postman_collection.json` to ignored local evidence and run `scripts/genfarmer_postman_analyze.py`.
- [ ] Prove exact round-trip equality for the completed lab app.
- [ ] Perform one harmless Python-generated edit and verify GenFarmer UI reloads it correctly.
- [ ] Generate a harmless flow from verified templates and execute it on Device #1.

## Current evidence levels

- **Live-verified serialization:** exact node exists in a saved GenFarmer `script.flow`.
- **AST palette-registry row:** renderer object directly contains `label`, `action` and `icon` properties.
- **Source-resolved literal:** source action constant maps unambiguously to a literal.
- **Live-flow anchor:** saved lab flow resolves a source-ambiguous action literal.
- **Lab-captured template:** exact GenFarmer-generated node object exists in the private lab flow and can be cloned by the private template registry.
- **Differentially verified setting:** one UI setting was changed in isolation and the before/after flow diff proves its serialized field/value semantics.

## Specific semantics still to learn

- [ ] identify Group Node's exact structural serialization;
- [ ] app launch/stop/install/uninstall/data-clear option/default behavior;
- [ ] tap/touch selector modes;
- [ ] text/resource-id/XPathLite/class/coordinates selectors;
- [ ] random/range semantics;
- [ ] swipe/scroll/gesture modes;
- [ ] input/type/clipboard nodes;
- [ ] variables/input/output/storage details;
- [ ] conditions/branches/case-path handles;
- [ ] loops/retry/failure paths;
- [ ] file/spreadsheet/HTTP/IMAP/AI options;
- [ ] screenshot/image-search/asset-storage behavior;
- [ ] network/device/system nodes;
- [ ] required fields, optional fields and enum values for every action.

## External hardware dependency

- [ ] Ensure SIM is present/active in the first modem.
- [ ] Verify real mobile public IP.
- [ ] Verify XProxy IP rotation.

## Later

- [ ] Add proxy-aware preflight/fail-closed behavior.
- [ ] Build authorized TikTok workflow using verified GenFarmer flow templates.
- [ ] Multi-device orchestration.
- [ ] Scale production workflows only after single-device stability.
