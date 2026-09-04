# Work

## Current milestone

Build a deterministic single-device automation foundation before scaling.

## Completed

- [x] Establish project architecture and documentation.
- [x] Confirm single-device ADB control in the client lab.
- [x] Confirm GenFarmer API availability in the client lab.
- [x] Confirm GenFarmer fingerprint rotation.
- [x] Confirm XProxy service and first-position proxy listeners.
- [x] Separate public source code from client-specific local configuration.
- [x] Create canonical public GitHub repository.
- [x] Clone repository onto client Windows PC.
- [x] Confirm client Python runtime is available.
- [x] Confirm 20 Android devices are simultaneously visible to ADB.
- [x] Add live ADB inventory script.
- [x] Add safe single-device Android Settings smoke test with local evidence capture.
- [x] Run the first safe smoke test against selected Device #1: PASS.
- [x] Verify Settings launch, UI hierarchy read, evidence capture, and return-to-Home behavior.
- [x] Add read-only GenFarmer API discovery probe.

## In progress

- [ ] Run GenFarmer read-only API discovery on the client PC.
- [ ] Capture confirmed endpoint inventory and schemas.
- [ ] Investigate Android identity coherence: reported release and SDK values were inconsistent in the smoke result.
- [ ] Convert smoke workflow to GenFarmer API orchestration.

## External hardware dependency

- [ ] Ensure SIM is present/active in the first modem.
- [ ] Verify real mobile public IP.
- [ ] Verify XProxy IP rotation.

## Later

- [ ] Build local 20-device mapping without committing client IPs publicly.
- [ ] Authorized application workflow.
- [ ] Multi-device orchestration.
- [ ] Scale production workflows only after single-device stability.
