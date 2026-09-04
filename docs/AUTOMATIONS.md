# Automations

## Phase 1 — Safe smoke test

Purpose:
- prove deterministic device control;
- launch Android Settings;
- inspect UI hierarchy;
- optionally perform one safe read-only navigation;
- return Home;
- save evidence.

## Phase 2 — GenFarmer-driven smoke test

Replace direct orchestration with GenFarmer API calls while preserving evidence and deterministic validation.

## Phase 3 — Proxy-aware run

Before app launch:
1. verify XProxy position;
2. resolve current mobile public IP;
3. optionally rotate;
4. wait until ready;
5. confirm egress IP;
6. start device workflow.

## Phase 4 — Authorized TikTok workflow

To be defined after:
- device smoke test passes;
- GenFarmer API control is understood;
- proxy is healthy;
- required account/app authorization is confirmed.

## Run state model

`PRECHECK -> DEVICE_READY -> PROXY_READY -> APP_READY -> EXECUTING -> VERIFYING -> COMPLETE`

Any failed mandatory precondition transitions to `FAILED` and stops the run.
