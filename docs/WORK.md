# Work

## Current milestone

Integrate the documented GenFarmer Local API and prove the official contract against the installed 2.6.1 service.

## Completed

- [x] Establish project architecture and documentation.
- [x] Create canonical public GitHub repository.
- [x] Clone repository onto client Windows PC.
- [x] Keep client-specific network/device values out of the public repository.
- [x] Confirm 20 Android devices are simultaneously visible to ADB.
- [x] Add live ADB inventory script.
- [x] Run safe Device #1 Android Settings smoke test successfully.
- [x] Capture local screenshots/UI hierarchy/result JSON for the smoke run.
- [x] Confirm GenFarmer local service is reachable.
- [x] Identify GenFarmer service version as 2.6.1 from `GET /`.
- [x] Identify the API listener process as `GenFarmer.exe` version `2.6.1.0`.
- [x] Confirm GenFarmer is Electron-packaged and contains `resources/app.asar`.
- [x] Locate the official GenFarmer Local API documentation.
- [x] Confirm the official API documents Automation Apps, Tasks, Runs and current-user endpoints.
- [x] Add reusable `GenFarmerClient` based on the official API contract.
- [x] Keep all mutation methods fail-closed unless explicitly enabled.
- [x] Add a read-only official API compatibility smoke test.

## In progress

- [ ] Run `scripts/genfarmer_api_smoke.py` against GenFarmer 2.6.1.
- [ ] Capture actual response shapes for current user, apps and runs.
- [ ] Identify an existing Automation App suitable for our harmless first API-driven test.
- [ ] Determine the supported device ID / serial mapping required by task assignment.
- [ ] Map GenFarmer device identities to local ADB devices without committing client IPs publicly.
- [ ] Execute one controlled harmless GenFarmer automation on Device #1.

## Official-doc gaps to resolve

- [ ] Generic device inventory endpoint is not clearly documented.
- [ ] Fingerprint/change-device/profile API is not clearly documented.
- [ ] Proxy update/assignment API is not clearly documented.
- [ ] GET task-list endpoint is not clearly documented; the public page contains a mislabeled run-list cURL example.

For these gaps only, use observation/read-only inspection and verify against GenFarmer 2.6.1 before adding support.

## External hardware dependency

- [ ] Ensure SIM is present/active in the first modem.
- [ ] Verify real mobile public IP.
- [ ] Verify XProxy IP rotation.

## Later

- [ ] Add proxy-aware preflight/fail-closed behavior.
- [ ] Build authorized TikTok workflow.
- [ ] Multi-device orchestration.
- [ ] Scale production workflows only after single-device stability.
