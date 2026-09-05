# Work

## Current milestone

Learn GenFarmer 2.6.1 non-default node settings with targeted one-setting differentials, then verify routing and generate a harmless flow from exact templates.

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
- [x] Reclassify `Group Node` (`Ht.GROUP_NODE -> GroupNode`) as an editor-structural source row rather than a missing standalone `data.action` node.
- [x] Capture the exact 62-node flow privately under ignored evidence and emit a privacy-safe structural inventory.
- [x] Execute `genfarmer_lab_schema_matrix.py` across all 62 live actions.
- [x] Confirm the common runtime option set is exactly `breakpoint`, `disabled`, `nodeLog`, `nodeSleep`, `nodeTimeout`, `timeoutAdbReconnect`, `timeoutNextNode`.
- [x] Confirm untouched configurable custom nodes generally contain only those seven runtime options; action-specific settings are not serialized until configured.
- [x] Confirm structural exceptions: `ContextMenu` exposes `options.casePaths`; `Loop` is family `loop` with `data.startLoopNode`; `Comment`/`Variables` are helper family; `Start` is input family; `Stop` is output family.
- [x] Add `genfarmer_setting_probe.py` for action-scoped GET-only before/after learning of exactly one UI setting while masking sensitive values.

## In progress

- [ ] Learn the first high-value action-specific setting with `genfarmer_setting_probe.py`.
- [ ] Prioritize `Touch`, `TypeText`, `Swipe`, `StartApp`, `ElementExists`, `Press`, `Pause`, `Random`, `Clipboard`, `CheckActivity`, `ClearAppData`, `GetProperty`, `GetAttributeValue`, `Xpath`.
- [ ] For each action, change only one setting per experiment, save, compare, record exact field path/type/enum semantics, then reset the baseline.
- [ ] Learn selector modes, app/package/activity fields, input modes, gestures, range/wait semantics and output-variable behavior without guessing.
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
- **Differentially verified setting:** one UI setting changed in isolation and the targeted before/after diff proves its serialized semantics.

## Specific semantics still to learn

- [ ] app launch/stop/install/uninstall/data-clear non-default options;
- [ ] touch selector modes and coordinates/text/resource-id/class/XPath behavior;
- [ ] random/range and Sleep timeout-mode semantics beyond observed defaults;
- [ ] swipe/scroll gesture modes;
- [ ] type/clipboard/input details;
- [ ] variables and output/storage behavior;
- [ ] conditions/branches/case-path handles;
- [ ] loops/retry/failure paths;
- [ ] file/spreadsheet/HTTP/IMAP/AI options;
- [ ] screenshot/image-search/asset-storage behavior;
- [ ] network/device/system node options;
- [ ] required fields, optional fields and enum values for every configurable action.

## External hardware dependency

- [ ] Ensure SIM is present/active in the first modem.
- [ ] Verify real mobile public IP.
- [ ] Verify XProxy IP rotation.

## Later

- [ ] Add proxy-aware preflight/fail-closed behavior.
- [ ] Build the authorized TikTok workflow using verified GenFarmer templates.
- [ ] Add multi-device orchestration.
- [ ] Scale only after the single-device lane is stable.
