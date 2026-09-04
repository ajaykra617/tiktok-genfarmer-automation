# Work

## Current milestone

Move from proven single-device control into verified GenFarmer API integration.

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
- [x] Confirm common Swagger/OpenAPI/health/version metadata paths are not exposed.
- [x] Identify the API listener process as `GenFarmer.exe` version `2.6.1.0`.
- [x] Identify the local install root under the user's Local Programs directory.
- [x] Confirm loose text assets do not expose route-like strings.
- [x] Confirm GenFarmer is Electron-packaged and contains `resources/app.asar`.
- [x] Discover 69 route-like candidates from the packaged application, including `/api/devices`, `/devices`, `/devices/details`, `/automation/runs`, `/tasks`, `/apps`, and `/api/update_proxy`.
- [x] Add a GET-only route verifier for high-confidence local endpoints.

## In progress

- [ ] Verify which discovered route candidates are actually served by the local GenFarmer API.
- [ ] Capture response schemas for device-list/read-only endpoints.
- [ ] Map GenFarmer device IDs to local ADB devices.
- [ ] Build the first reusable GenFarmer Python client.
- [ ] Convert the safe smoke workflow from direct ADB orchestration to GenFarmer orchestration where supported.

## External hardware dependency

- [ ] Ensure SIM is present/active in the first modem.
- [ ] Verify real mobile public IP.
- [ ] Verify XProxy IP rotation.

## Later

- [ ] Build local 20-device mapping without committing client IPs publicly.
- [ ] Add proxy-aware preflight/fail-closed behavior.
- [ ] Build authorized application workflow.
- [ ] Multi-device orchestration.
- [ ] Scale production workflows only after single-device stability.
