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
- [x] Add read-only GenFarmer process/route discovery tooling.

## In progress

- [ ] Identify the Windows process/executable serving the GenFarmer API.
- [ ] Discover route candidates from local GenFarmer assets without modifying them.
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
