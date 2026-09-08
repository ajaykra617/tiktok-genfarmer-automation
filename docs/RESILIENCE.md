# Resilient automation execution model

The automation must not treat a successfully executed gesture or node as proof that the intended application state changed. Mobile apps can display permission dialogs, update prompts, network errors, overlays, login challenges, crashes, and other unexpected states while the underlying ADB/GenFarmer command still succeeds.

## Core loop

Use an observe -> classify -> act -> verify -> recover loop around every meaningful module.

1. Observe the current state.
2. Handle known global interrupts before doing app-specific work.
3. Verify the module precondition.
4. Execute a short GenFarmer action block.
5. Verify the postcondition.
6. If verification fails, recover with a bounded retry budget.
7. Save a checkpoint and evidence before continuing.

A run is successful only when the postcondition is proven. A node log saying that `Swipe` ran is not sufficient by itself.

## Global interrupt layer

Known interruptions should be classified independently from the current TikTok module. Examples:

- Android permission dialogs;
- app update or notification prompts;
- network/offline messages;
- app crash or app no longer in foreground;
- unexpected navigation state;
- login-required state;
- challenge/captcha/checkpoint state;
- unknown system or app overlay.

Each interrupt handler has an explicit policy and a bounded retry count. Unknown screens must not trigger blind taps. Capture evidence and stop/quarantine the run instead.

For the current warm-up lab, notifications are not required. The notification permission prompt should therefore be handled by an explicit configured policy (for example dismiss/deny), using a verified selector rather than guessed coordinates. The policy remains configurable because other workflows may have different requirements.

## Recovery tiers

### Tier 1: local retry

Use when the expected state is still present but an action did not achieve its postcondition.

- short wait;
- re-observe;
- retry the same idempotent action;
- maximum small retry budget.

### Tier 2: application recovery

Use when TikTok is no longer in the expected foreground/state.

- capture screenshot/state evidence;
- press back only when the recovery route is verified;
- relaunch TikTok when safe;
- return to the latest checkpoint;
- continue only after the checkpoint precondition is proven again.

### Tier 3: stop/quarantine

Use for states that should not be guessed through.

- repeated recovery failure;
- unknown overlay;
- login/account state mismatch;
- captcha/challenge/checkpoint;
- device offline;
- proxy-required job without verified proxy egress;
- invariant or postcondition failure after the retry budget.

Record the stop reason and preserve evidence for operator review.

## Short modules, not one long brittle graph

GenFarmer should execute short deterministic action modules. Python remains the outer supervisor.

Examples:

- `ensure_ready`
- `browse_one`
- `browse_n`
- `open_profile_and_return`
- `open_comments_and_return`
- `search_niche`
- `finish_session`

Python chooses and repeats modules until the bounded session budget is reached. Between modules it can re-observe state, process interrupts, enforce retry/circuit-breaker limits, and checkpoint progress.

This is safer than compiling a 30-60 minute linear graph where an early unexpected popup could invalidate every later action while the nodes still appear to execute successfully.

## Preconditions and postconditions

Every module needs both.

Examples for passive feed browsing:

Precondition:
- TikTok is foreground;
- expected feed anchor is visible;
- no known system/app interrupt is blocking the screen.

Action:
- one verified Swipe/Scroll action.

Postcondition:
- expected feed state changed using the strongest available evidence, preferably selector/accessibility-derived identity or state;
- screenshot/visual comparison is fallback evidence, not the only proof where animated content can create false positives.

## Checkpoint state

The Python controller should persist enough state to resume safely:

- session id;
- device id;
- GenFarmer app id;
- current module;
- last completed checkpoint;
- module attempt count;
- interrupt count by type;
- last stop/recovery reason;
- evidence directory;
- proxy assignment when required;
- session deadline.

A recovery must resume from a known checkpoint, not from an assumed UI state.

## Bounded retries and circuit breakers

Never retry forever.

Recommended initial lab policy:

- local action retry: 2 attempts;
- app recovery/relaunch: 1 attempt per module;
- same interrupt repeatedly seen: stop after 2-3 occurrences;
- hard session deadline always wins;
- unknown state: no blind recovery, capture evidence and stop.

Tune these only from measured evidence.

## Evidence and false-success protection

For each meaningful module capture structured evidence:

- timestamp;
- module/action;
- precondition result;
- interrupt handler result if any;
- GenFarmer node/run result;
- postcondition result;
- retry/recovery count;
- screenshot or selector evidence reference;
- final outcome.

A module must report success only when the postcondition passes. This prevents a gesture intercepted by a permission dialog from being counted as a successful feed swipe.

## Current lab incident

The first Python-generated TikTok warm-up exposed an Android TikTok notification permission dialog while the run was executing. This is the exact class of event the resilience layer is intended to handle: ADB/GenFarmer can continue issuing Swipe nodes even though the feed is blocked by the dialog.

Next implementation step is a reusable `ensure_ready`/interrupt-handling module in the Python compiler/controller, followed by postcondition validation around `browse_one`.
