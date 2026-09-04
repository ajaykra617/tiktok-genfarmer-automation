# Project Memory / Decisions

## Decisions

- GitHub repository is the canonical source of truth.
- Client PC keeps environment-specific configuration locally.
- Public repository must not contain client IPs, device IDs, credentials, account data, selectors, purchased flow logic, or secrets.
- Start with one device and scale only after deterministic success.
- Keep implementation, runbook, work log, and architecture synchronized.
- Basic device automation can proceed while modem/SIM hardware is repaired.
- Proxy-required application jobs fail closed unless a verified cellular public IP exists.
- The official GenFarmer API documentation is the primary contract for supported Local API calls.
- The official GitBook API page also publishes a downloadable `GenFarmer.postman_collection.json`; treat that collection as an additional official API-contract source and compare it against the prose page before extending our client.
- Never assume the Postman collection enumerates the no-code node palette. It is primarily an API contract source unless it contains real non-empty `script.flow` examples.
- All GenFarmer POST/PUT/DELETE methods in our Python client are fail-closed by default and require explicit mutation opt-in.
- Use a hybrid architecture: GenFarmer Automation Apps/no-code flows execute device actions, while Python orchestrates devices, inputs, runs, retries, evidence, XProxy checks, and higher-level workflow state.
- Learn `script.flow` from GenFarmer-generated graphs before Python authors them. Clone verified templates and patch only fields whose semantics are proven.
- Treat broad Vue Flow `type` values as rendering families. Exact operation identity in saved flows is `type + data.action`.
- Exact raw flows remain local under ignored `evidence/`. Share only structural catalogs, safe action tokens and masked differential reports.
- The local Python template registry must load exact node templates only from the private raw corpus. It must never embed or publish raw client flows in Git.
- Source mining is discovery evidence, not serialization authority. Only a saved GenFarmer `script.flow` proves the exact `data.action` and option payload for authoring.
- Do not treat `action*` renderer tokens as serialized actions without AST proof. The AST run showed several of them are `icon` values in palette-registry-shaped objects.
- Use exact renderer objects containing direct `label`, `action` and `icon` properties as the strongest source-level palette registry evidence.
- Before authoring edges, prove routing relationships from the private corpus: specifically whether `data.successNode`/`data.failNode` correspond to outgoing edge targets and which handle names are used.
- Versioned semantic registries may contain only privacy-safe action names, field/type shapes, observed enum values and handle semantics.

## Verified milestones

- 20 Android devices were simultaneously visible to ADB in the client lab.
- Device #1 completed the safe Settings smoke workflow successfully with local evidence capture.
- GenFarmer root endpoint identifies the local service as version 2.6.1.
- The process listening on the GenFarmer API port is `GenFarmer.exe`, product version `2.6.1.0`.
- GenFarmer is Electron-packaged and includes `resources/app.asar`.
- The public GenFarmer API documentation provides Local API examples using `127.0.0.1:55554` and documents Automation Apps, Tasks, Runs and current-user operations.
- The official API page publishes a Postman collection named `GenFarmer.postman_collection.json`.
- A reusable documented-API client and read-only compatibility smoke script exist in the repository.
- A lossless `script.flow` wrapper, round-trip gate, structural learner, semantic learner, private snapshot tool and privacy-safe diff tool exist.
- First flow corpus: one app, seven nodes, three edges and four broad families (`custom`, `custom-context-menu`, `helper`, `input`).
- Seven semantic actions are live-observed: `Start`, `Variables`, `ContextMenu`, `Adb`, `DeepSeek`, `Pause`, `Screenshot`.
- `Pause` has an observed `timeoutType` value of `fixed`.
- Normal custom nodes use left target/right source positions in this corpus.
- Observed edges use a generated Start source handle into `successNode`, then `successNode` -> `successNode` for normal success chaining.
- All three observed non-null `data.successNode` pointers match an outgoing edge target exactly.
- No non-null `data.failNode` route exists in the current sample, so failure routing remains unproven.
- A local-only `TemplateRegistry` indexes exact observed node templates by `type + data.action`.
- Structured ASAR inspection scanned 16,170 text-bearing files and identified `dist/render/assets/useScriptEditor-HioTuYH4.js` as the primary Automation editor bundle.
- The editor bundle has no source map.
- Source mining surfaced additional likely palette labels beyond the original live sample, including app/system, interaction, data, file, AI and branching nodes.
- Regex/proximity settings probes v1 and v2 were deliberately rejected as too noisy for trustworthy per-node settings attribution.
- AST analysis parsed 18 renderer assets without parse-error roots and classified 63 `action*` tokens.
- AST contexts show several `action*` values are icons, not semantic actions. Examples: `actionPressBack`, `actionPressHome`, `actionPressMenu`, `actionScreenshot`, `actionTypeText`, and `actionMouseMove`.
- Stronger source action constants visible alongside labels include `PRESS_BACK`, `PRESS_HOME`, `PRESS_MENU`, `PRESS`, `TYPE_TEXT`, `TOUCH`, `SWIPE`, `SCREENSHOT`, `CHANGE_DEVICE`, `START_APP`, `STOP_APP`, `INSTALL_APP`, `UNINSTALL_APP`, `ADB`, `CHECK_NETWORK`, `BACKUP_RESTORE_V2`, `GEN_ROUTER`, and `CMD`.
- `genfarmer_palette_registry_ast.py` now extracts exact source rows shaped as `label` + `action` + `icon` and resolves simple local uppercase action bindings where possible.

## Script.flow learning strategy

1. Read existing apps GET-only.
2. Preserve exact raw flows locally.
3. Build shareable structural and semantic catalogs.
4. Record only live-observed serialized actions in the versioned semantic registry.
5. Mine the private corpus for routing semantics before generating edges.
6. Analyze the official Postman collection for API-contract details and any real flow examples.
7. Mine the Electron renderer using AST, prioritizing exact `label/action/icon` palette rows over proximity heuristics.
8. Cross-map source action constants to exact saved `script.flow data.action` values.
9. Create `GF Lab - Node Catalog` only for actions/settings that remain unverified.
10. Load exact templates into the local-only template registry; do not fabricate undocumented node payloads.
11. For ambiguous options, snapshot before, change exactly one UI field, snapshot after, and produce a masked shareable diff.
12. Require exact Python round-trip equality before any flow PUT.
13. Add semantic Python helpers only after the relevant action behavior is proven on GenFarmer 2.6.1.
14. Run harmless generated/edit flows on Device #1 before using any authorized application workflow.

## Current verified semantic actions

- `input:Start`
- `helper:Variables`
- `custom-context-menu:ContextMenu`
- `custom:Adb`
- `custom:DeepSeek`
- `custom:Pause`
- `custom:Screenshot`

These are structurally verified. Their complete runtime semantics are not assumed.

## Official API coverage

Documented read operations include current user, list/get Automation Apps, list Automation Runs, and run storage/output retrieval. Documented mutation operations include updating/deleting Automation Apps, creating/updating/deleting Tasks, assigning/removing devices, creating Runs and executing Runs.

The public API page does not clearly document creating a new Automation App, a generic device inventory API, direct fingerprint/change-device API, proxy update API, or a reliable GET task-list endpoint. The official Postman collection still needs to be checked for additional or corrected endpoints before those are classified as true API gaps.

## Device identity caution

Several devices report Android release values that do not naturally match SDK 35. Because fingerprint/profile manipulation is part of the GenFarmer environment, do not treat individual `getprop` identity fields as authoritative until we compare raw/system identity with the active GenFarmer profile.

## Remaining work

- Run `scripts/genfarmer_palette_registry_ast.py` and capture the exact source-derived palette table.
- Cross-map source action constants to saved `script.flow data.action` values.
- Download and analyze the official Postman collection.
- Create/populate `GF Lab - Node Catalog` only for nodes still lacking exact templates.
- Learn one real failure route and every ambiguous option through differential tests.
- Build the complete GenFarmer 2.6.1 Python authoring registry from verified templates.
- Prove a harmless Python edit and generated flow through GenFarmer.
- Resolve GenFarmer device ID mapping.
- Resolve undocumented fingerprint and proxy integration surfaces only as needed.
- Verify XProxy cellular egress and rotation.
- Build the authorized TikTok workflow.
- Scale to the full device farm only after the single-device lane is stable.
