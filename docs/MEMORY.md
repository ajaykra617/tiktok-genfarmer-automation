# Project Memory / Decisions

## Decisions

- GitHub repository is the canonical source of truth.
- Client PC keeps environment-specific configuration locally.
- Public repository must not contain client IPs, device IDs, credentials, account data, or secrets.
- Start with one device and scale only after deterministic success.
- Keep implementation, runbook, work log, and architecture synchronized.
- Basic device automation can proceed while modem/SIM hardware is repaired.
- Proxy-required application jobs fail closed unless a verified cellular public IP exists.

## Remaining work

- Complete GenFarmer API inventory.
- Implement deterministic Android smoke workflow.
- Convert orchestration to GenFarmer API.
- Verify XProxy cellular egress and rotation.
- Build authorized application workflow.
- Scale to the full device farm.
