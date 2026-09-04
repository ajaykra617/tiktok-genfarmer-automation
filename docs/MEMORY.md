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
- Treat broad Vue Flow node `type` values as rendering families. The first corpus proves that multiple different actions can share `type=custom`; semantic identification must include `data.action` and verified option fields.
- Exact raw flows remain local under ignored `evidence/`. Share only structural catalogs, safe internal action tokens, and masked differential reports.

## Verified milestones

- 20 Android devices were simultaneously visible to ADB in the client lab.
- Device #1 completed the safe Settings smoke workflow successfully with local evidence capture.
- GenFarmer root endpoint identifies the local service as version 2.6.1.
- The process listening on the GenFarmer API port is `GenFarmer.exe`, product version `2.6.1.0`.
- GenFarmer is Electron-packaged and includes `resources/app.asar`.
- The public GenFarmer API documentation provides Local API examples using `127.0.0.1:55554` and documents Automation Apps, Tasks, Runs and current-user operations.
- A reusable documented-API client and read-only compatibility smoke script exist in the repository.
- A lossless `script.flow` wrapper, round-trip gate, structural learner, semantic learner, private snapshot tool and privacy-safe diff tool exist.
- First flow corpus: one app, seven nodes, three edges, four broad families (`custom`, `custom-context-menu`, `helper`, `input`).
- Four observed nodes use `type=custom`, confirming that `node.type` alone is not the automation operation identity.
- First observed graph fields include success/failure routing, node sleep/timeouts, breakpoint/disabled flags, timeout modes/ranges, command/output-variable fields and source/target handle metadata.

## Script.flow learning strategy

1. Read existing apps GET-only.
2. Preserve exact raw flows locally.
3. Build shareable structural and semantic catalogs.
4. Create a dedicated `GF Lab - Node Catalog` app containing every visible palette node once.
5. Learn `data.action` values, option-key shapes, default values and edge handles.
6. For ambiguous options, take a private before snapshot, change one UI field, take an after snapshot, and produce a masked shareable diff.
7. Require exact Python round-trip equality before any flow PUT.
8. Add semantic Python helpers only after the relevant node action is proven on GenFarmer 2.6.1.
9. Run harmless generated/edit flows on Device #1 before using any authorized application workflow.

## Official API coverage

Documented read operations include current user, list/get Automation Apps, list Automation Runs, and run storage/output retrieval. Documented mutation operations include updating/deleting Automation Apps, creating/updating/deleting Tasks, assigning/removing devices, creating Runs and executing Runs.

The public API page does not clearly document creating a new Automation App, a generic device inventory API, direct fingerprint/change-device API, proxy update API, or a reliable GET task-list endpoint. These remain controlled discovery items.

## Device identity caution

Several devices report Android release values that do not naturally match SDK 35. Because fingerprint/profile manipulation is part of the GenFarmer environment, do not treat individual `getprop` identity fields as authoritative until we compare raw/system identity with the active GenFarmer profile.

## Remaining work

- Run the new semantic catalog against the current flow corpus and capture real `data.action` names.
- Create and populate `GF Lab - Node Catalog` with every visible palette node.
- Build the complete GenFarmer 2.6.1 node/action registry using differential learning.
- Prove a harmless Python edit and generated flow through GenFarmer.
- Resolve GenFarmer device ID mapping.
- Resolve undocumented fingerprint and proxy integration surfaces only as needed.
- Verify XProxy cellular egress and rotation.
- Build the authorized TikTok workflow.
- Scale to the full device farm only after the single-device lane is stable.
