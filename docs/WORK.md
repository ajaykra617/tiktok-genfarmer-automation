# Work

## Current milestone

Learn the exact GenFarmer 2.6.1 live node settings/default schema and then verify non-default modes with small differential tests.

## Completed

- [x] Establish project architecture, public repository and private client configuration boundary.
- [x] Confirm 20 Android devices are simultaneously visible to ADB and pass the safe Device #1 Settings smoke test.
- [x] Confirm GenFarmer Local API is reachable and identify version 2.6.1.
- [x] Add fail-closed documented-API client, lossless `script.flow` tooling, snapshots/diffs and local-only template registry.
- [x] Recover the renderer palette registry with AST tooling.
- [x] Recover 60 exact source `label + action + icon` registry rows.
- [x] Resolve all 60 source action constants with unique source evidence or live-flow anchors.
- [x] Stop source-side default mining after the node-factory probe yielded `0/60` usable default-object candidates.
- [x] Create and populate `GF Lab - Node Catalog` with every available standalone node.
- [x] Resolve live ambiguity exactly: `H.HTTP -> HTTP`, `H.LOG -> Log`, `H.RANDOM -> Random`, `H.STOP -> Stop`.
- [x] Full live lab capture: 62 nodes, 0 edges, 62 distinct `data.action` values, no nodes without safe `data.action`.
- [x] Confirm all 59 ordinary `H.*` palette action rows are represented by live saved action-node templates.
- [x] Confirm the three special editor nodes `Start`, `Variables`, `ContextMenu` are present.
- [x] Reclassify `Group Node` (`Ht.GROUP_NODE -> GroupNode`) as an editor-structural source row rather than a missing standalone `data.action` node; it is the only `Ht.*` row and was not instantiated by the exhaustive live node capture.
- [x] Capture the exact 62-node flow privately under ignored evidence and emit a privacy-safe structural inventory.
- [x] Add `genfarmer_lab_schema_matrix.py` to extract complete live `data`/`options` field-type schemas, action-specific settings and safe primitive defaults.

## In progress

- [ ] Pull the latest catalog classification and run `python -m pytest tests/test_palette_catalog_261.py`.
- [ ] Run `scripts/genfarmer_lab_catalog_audit.py` and confirm 59/59 standalone action-node coverage.
- [ ] Run `scripts/genfarmer_lab_schema_matrix.py` and inspect all 62 live action schemas.
- [ ] Separate common runtime controls from action-specific settings for every node.
- [ ] Rank settings/modes that require one-field-at-a-time before/after diffs because default templates alone cannot prove every enum or selector variant.
- [ ] Extend the local `TemplateRegistry` to load the exact private flow file directly and verify all 62 live semantic kinds are cloneable.
- [ ] Create a separate tiny routing lab for success/failure/branch edge semantics so the full catalog corpus remains stable and unconnected.
- [ ] Run the official Postman analyzer and compare the API contract against our client.
- [ ] Prove exact round-trip equality for the completed lab app.
- [ ] Perform one harmless Python-generated edit and verify GenFarmer reloads it correctly.
- [ ] Generate and execute one harmless verified-template flow on Device #1.

## Current evidence levels

- **Live-verified serialization:** exact node exists in saved GenFarmer `script.flow`.
- **AST source registry row:** renderer object directly contains `label`, `action`, `icon`.
- **Source-resolved literal:** source action constant maps unambiguously to a literal.
- **Live-flow anchor:** saved lab flow resolves a source-ambiguous action literal.
- **Lab-captured template:** exact GenFarmer-generated node object exists in the ignored private lab flow.
- **Editor-structural source row:** source UI/editor operation not expected as a standalone serialized action node; currently `Group Node`.
- **Differentially verified setting:** one UI setting changed in isolation and the before/after flow diff proves its serialized semantics.

## Specific semantics still to learn

- [ ] app launch/stop/install/uninstall/data-clear non-default options;
- [ ] touch selector modes and coordinates/text/resource-id/class/XPath behavior;
- [ ] random/range semantics;
- [ ] swipe/scroll gesture modes;
- [ ] type/clipboard/input details;
- [ ] variables and output/storage behavior;
- [ ] conditions/branches/case-path handles;
- [ ] loops/retry/failure paths;
- [ ] file/spreadsheet/HTTP/IMAP/AI options;
- [ ] screenshot/image-search/asset-storage behavior;
- [ ] network/device/system node options;
- [ ] required fields, optional fields and enum values for every action.

## External hardware dependency

- [ ] Ensure SIM is present/active in the first modem.
- [ ] Verify real mobile public IP.
- [ ] Verify XProxy IP rotation.

## Later

- [ ] Add proxy-aware preflight/fail-closed behavior.
- [ ] Build the authorized TikTok workflow using verified GenFarmer templates.
- [ ] Add multi-device orchestration.
- [ ] Scale only after the single-device lane is stable.
