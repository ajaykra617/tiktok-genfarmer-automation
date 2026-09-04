# Project Memory / Decisions

## Decisions

- GitHub repository is the canonical source of truth.
- Client PC keeps environment-specific configuration locally.
- Public repository must not contain client IPs, device IDs, credentials, account data, or secrets.
- Start with one device and scale only after deterministic success.
- Keep implementation, runbook, work log, and architecture synchronized.
- Basic device automation can proceed while modem/SIM hardware is repaired.
- Proxy-required application jobs fail closed unless a verified cellular public IP exists.
- GenFarmer endpoint discovery must be read-only until endpoint semantics are confirmed.

## Verified milestones

- 20 Android devices were simultaneously visible to ADB on the client workstation.
- The selected Device #1 passed the safe Android Settings smoke test.
- The smoke test verified app launch, UI hierarchy inspection, local evidence capture, and return to Home.

## Important observation

The selected device reported an internally inconsistent Android identity: release `10` while SDK reported `35`. This may be related to fingerprint/property manipulation and must be investigated before relying on build identity for application workflows.

## Remaining work

- Complete GenFarmer API inventory.
- Review Android identity coherence and decide which properties are authoritative.
- Convert orchestration to GenFarmer API.
- Verify XProxy cellular egress and rotation.
- Build authorized application workflow.
- Scale to the full device farm.
