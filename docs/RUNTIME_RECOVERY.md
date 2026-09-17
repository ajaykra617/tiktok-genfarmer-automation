# Runtime recovery policy

The Android/TikTok automation supervisor must distinguish transient runtime faults from genuine automation failures. Recovery is bounded and evidence-driven; unknown or semantic failures remain fail-closed.

## Failure classes

| Class | Example evidence | Default action |
|---|---|---|
| `app_hung` | Android `APP_NOT_RESPONDING`, ANR window evidence, or TikTok `ProcessRecord` not-responding evidence | bounded TikTok process restart, then prove stable foreground again |
| `hierarchy_temporarily_unavailable` | helper/uiautomator capture temporarily unavailable | retry read-only hierarchy capture within budget |
| `adb_transient` | bounded ADB timeout / transport interruption | retry the read/observation within budget |
| `ui_state_recoverable` | TikTok backgrounded with no blocking interrupt, or supported permission dialog | restore qualified foreground state / existing permission recovery |
| `device_unavailable` | ADB device not ready/offline | fail closed |
| `automation_failure` | duplicate/missing semantic control, selector mismatch, unknown interrupt | fail closed; do not retry as infrastructure noise |

## Two observation levels

`AdbObserver.observe()` is the lightweight check used frequently while watching content. It inspects ADB readiness plus window/activity state.

`AdbObserver.observe_deep()` is used at checkpoints and after process recovery. It additionally inspects TikTok's Android `ProcessRecord` so a visible or framework-level ANR cannot be missed merely because TikTok still appears to be the top activity.

`TikTokRuntimeSupervisor.ensure_stable()` requires multiple consecutive healthy checkpoint observations. A single momentary foreground sample is no longer sufficient after a restart.

## Recovery budgets

`src/genfarmer_automation/runtime_recovery.py` owns the shared classification and budget primitives. A recovery decision is consumed from a per-session budget before any mutation/retry. This prevents unstable devices from looping forever.

The client-demo controller may allow up to three checkpoint-level TikTok process restarts for a full Warm-up + Boost rehearsal. Individual passive stages are replayed at most once after a clean restart. Unknown semantic failures are not converted into generic retries.

A TikTok ANR recovery uses `am force-stop` for the allowlisted TikTok package followed by the already-qualified launcher component. It does not clear app data/cache, reinstall the app, kill unrelated apps, bypass checkpoints, or guess UI coordinates.

## FYP state machine

The strict qualified selector remains the primary proof for ordinary TikTok video cards. The resilient demo also classifies legitimate alternate For You states so they are not mistaken for application failure:

- ordinary video card: continue;
- LIVE card: valid FYP content, advance to another card when an ordinary-video checkpoint is required;
- photo/image carousel: valid FYP content;
- sponsored/paid-partnership card: valid FYP content;
- shop/product card: valid FYP content;
- explicit/bare loading shell: wait read-only for bounded settle time;
- profile/search/comments or another non-FYP screen: use bounded navigation recovery;
- real ANR/background/crash-like runtime failure: use classified process recovery.

Loading/error language is evaluated before weak content hints. Short substring collisions such as `ad` inside `loading` are explicitly avoided by phrase/token-aware matching.

## Recovery diagnostics

`src/genfarmer_automation/runtime_diagnostics.py` captures best-effort private Android evidence around a hard restart:

- TikTok PID;
- window/activity state;
- TikTok process state;
- `dumpsys meminfo`;
- bounded recent logcat;
- summarized ANR/crash/low-memory hints.

The production demo wrapper `scripts/tiktok_client_demo_production.py` captures this evidence immediately before and after every hard TikTok restart under `evidence/runtime-recovery-diagnostics/`. Diagnostic collection is read-only, private, and non-blocking: collection failures are recorded instead of preventing recovery.

## Evidence semantics

Successful semantic gates are not erased by failure of optional evidence collection. For example, a trailing screenshot is useful evidence but is not itself the warm-scroll correctness gate when the qualified selector was already proven before and after every swipe.

Shareable evidence records recovery counts without exposing private selectors or raw diagnostic material. A run that exhausts a recovery budget terminates as `BLOCKED`.

## Qualification status

The shared recovery policy, deep ANR observation, stable-post-restart gate, FYP variant classification, checkpoint-safe stage replay, and private runtime diagnostic capture are implemented and unit-tested. Live runs on the primary device remain the source of truth for qualifying real TikTok behavior; every newly observed state should be added as explicit evidence and regression coverage rather than handled by unbounded retries.
