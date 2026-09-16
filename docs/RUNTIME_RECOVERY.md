# Runtime recovery policy

The Android/TikTok automation supervisor must distinguish transient runtime faults from genuine automation failures. Recovery is bounded and evidence-driven; unknown or semantic failures remain fail-closed.

## Failure classes

| Class | Example evidence | Default action |
|---|---|---|
| `app_hung` | Android `APP_NOT_RESPONDING` / ANR evidence | one bounded TikTok process restart, then prove foreground again |
| `hierarchy_temporarily_unavailable` | helper/uiautomator capture temporarily unavailable | retry read-only hierarchy capture within budget |
| `adb_transient` | bounded ADB timeout / transport interruption | retry the read/observation within budget |
| `ui_state_recoverable` | TikTok backgrounded with no blocking interrupt, or supported permission dialog | restore qualified foreground state / existing permission recovery |
| `device_unavailable` | ADB device not ready/offline | fail closed |
| `automation_failure` | duplicate/missing semantic control, selector mismatch, unknown interrupt | fail closed; do not retry as infrastructure noise |

## Recovery budgets

`src/genfarmer_automation/runtime_recovery.py` owns the shared classification and budget primitives. A recovery decision is consumed from a per-session budget before any mutation/retry. This prevents unstable devices from looping forever.

The Boost warm-scroll controller currently uses these session bounds:

- app restarts: 1
- hierarchy retries: 2
- ADB retries: 1
- foreground restores: 2
- permission recoveries: 2

A TikTok ANR recovery uses `am force-stop` for the allowlisted TikTok package followed by the already-qualified launcher component. It does not clear app data, reinstall the app, bypass a checkpoint, or guess UI coordinates. The run must prove healthy foreground state again after the restart.

## Evidence semantics

Successful semantic gates are not erased by failure of optional evidence collection. For example, a trailing screenshot is useful evidence but is not itself the warm-scroll correctness gate when the qualified selector was already proven before and after every swipe.

Shareable warm-scroll evidence records recovery counts without exposing private selectors or account/device data. A run that exhausts a recovery budget terminates as `BLOCKED`.

## Qualification status

The shared recovery policy and ANR restart path are implemented and unit-tested. Live qualification of the new recovery-aware controller is still required on the primary healthy device before treating the recovery behavior as qualified across the fleet.
