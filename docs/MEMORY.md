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
- Packaged-app route discovery is retained only as a fallback for gaps not covered by official documentation.
- All GenFarmer POST/PUT/DELETE methods in our Python client are fail-closed by default and require explicit mutation opt-in.
- Use a hybrid architecture: GenFarmer Automation Apps/no-code flows execute device actions, while Python orchestrates devices, inputs, runs, retries, evidence, XProxy checks, and higher-level workflow state.
- Learn `script.flow` from GenFarmer-generated graphs before Python authors them. Clone verified templates and patch only fields whose semantics are proven.
- Treat broad Vue Flow `type` values as rendering families. The first semantic pass proves the actual operation identity is `type + data.action`.
- Exact raw flows remain local under ignored `evidence/`. Share only structural catalogs, safe internal action tokens, and masked differential reports.
- The local Python template registry must load exact node templates only from the private raw corpus. It must never embed or publish raw client flows in Git.
- Static `app.asar` scans are candidate discovery only. The first broad scan returned obvious generic-code false positives, so package-only tokens are never treated as verified nodes without a live GenFarmer-generated flow.
- Versioned semantic registries may contain only privacy-safe action names, field/type shapes, observed enum values and handle semantics.

## Verified milestones

- 20 Android devices were simultaneously visible to ADB in the client lab.
- Device #1 completed the safe Settings smoke workflow successfully with local evidence capture.
- GenFarmer root endpoint identifies the local service as version 2.6.1.
- The process listening on the GenFarmer API port is `GenFarmer.exe`, product version `2.6.1.0`.
- GenFarmer is Electron-packaged and includes `resources/app.asar`.
- The public GenFarmer API documentation provides Local API examples using `127.0.0.1:55554` and documents Automation Apps, Tasks, Runs and current-user operations.
- A reusable documented-API client and read-only compatibility smoke script exist in the repository.
- A lossless `script.flow` wrapper, round-trip gate, structural learner, semantic learner, private snapshot tool and privacy-safe diff tool exist.
- First flow corpus: one app, seven nodes, three edges and four broad families (`custom`, `custom-context-menu`, `helper`, `input`).
- Seven semantic actions are now live-observed: `Start`, `Variables`, `ContextMenu`, `Adb`, `DeepSeek`, `Pause`, `Screenshot`.
- `Pause` has an observed `timeoutType` value of `fixed`.
- Normal custom nodes use left target/right source positions in this corpus.
- Observed edges use a generated Start source handle into `successNode`, then `successNode` -> `successNode` for normal success chaining.
- A local-only `TemplateRegistry` indexes exact observed node templates by `type + data.action`.
- A versioned privacy-safe GenFarmer 2.6.1 semantic registry records the seven observed actions.
- The original broad package scanner produced false positives such as generic authentication/version/post-style tokens and is not authoritative.
- A stricter PascalCase/runtime-marker package scanner has been added for the next discovery pass.

## Script.flow learning strategy

1. Read existing apps GET-only.
2. Preserve exact raw flows locally.
3. Build shareable structural and semantic catalogs.
4. Record only live-observed actions in the versioned semantic registry.
5. Run the strict packaged scanner only to generate a targeted list of possible missing actions.
6. Create `GF Lab - Node Catalog` only for visible palette nodes that still have no verified live template.
7. Learn `data.action`, option-key shapes, defaults and edge handles from GenFarmer-generated nodes.
8. Load exact templates into the local-only template registry; do not fabricate undocumented node payloads.
9. For ambiguous options, snapshot before, change exactly one UI field, snapshot after, and produce a masked shareable diff.
10. Require exact Python round-trip equality before any flow PUT.
11. Add semantic Python helpers only after the relevant action behavior is proven on GenFarmer 2.6.1.
12. Run harmless generated/edit flows on Device #1 before using any authorized application workflow.

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

The public API page does not clearly document creating a new Automation App, a generic device inventory API, direct fingerprint/change-device API, proxy update API, or a reliable GET task-list endpoint. These remain controlled discovery items.

## Device identity caution

Several devices report Android release values that do not naturally match SDK 35. Because fingerprint/profile manipulation is part of the GenFarmer environment, do not treat individual `getprop` identity fields as authoritative until we compare raw/system identity with the active GenFarmer profile.

## Remaining work

- Run the strict package scanner and compare it with the seven live actions.
- Create/populate `GF Lab - Node Catalog` only for actions still lacking a real saved template.
- Build the complete GenFarmer 2.6.1 node/action registry using differential learning.
- Prove a harmless Python edit and generated flow through GenFarmer.
- Resolve GenFarmer device ID mapping.
- Resolve undocumented fingerprint and proxy integration surfaces only as needed.
- Verify XProxy cellular egress and rotation.
- Build the authorized TikTok workflow.
- Scale to the full device farm only after the single-device lane is stable.
