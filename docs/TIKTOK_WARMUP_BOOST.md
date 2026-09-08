# TikTok Warm-up and Boost Qualification

This lane starts with one authorized TikTok account on one test device. Account creation/login/reset workflows are intentionally out of scope for this phase.

## Client requirements captured

The client specification defines two relevant modes:

### Warm-up

Saveable settings/presets are required. Relevant TikTok capabilities include:

- browse FYP / Following / a configured feed source;
- spend time viewing content rather than immediately advancing;
- optionally open creator profiles or comments and return;
- explore a configured niche through keyword / hashtag / sound inputs;
- bounded session length with explicit stop conditions;
- optional inactive/rest sessions;
- logging of every action/result.

### Boost

Boost is allowed only after the account/device state is explicitly marked ready. Relevant TikTok capabilities include:

- explore by configured source such as keyword, link, hashtag or account list;
- publish authorized media from an approved input set with duplicate-content safeguards;
- optional scheduled publishing;
- log every attempted action and its outcome.

Engagement actions such as likes, follows or replies must not be used for coordinated engagement, artificial metric inflation, spam, or to evade platform enforcement. If such actions are later enabled, they require a separate policy/authorization gate and must remain bounded, auditable and account-local.

## Hard guardrails

Do not automate:

- DMs;
- mass follow/unfollow;
- cross-liking/coordination between controlled accounts;
- reuse of the same media across many accounts without explicit content-distribution approval;
- proxy rotation during login or upload;
- captcha/checkpoint bypass;
- any workflow whose purpose is to hide coordinated automation or defeat platform enforcement.

## Qualification sequence

### TT-Q0 — installation and native selector discovery

1. Confirm TikTok package, version and launcher activity.
2. Launch TikTok on Device #1.
3. Capture the initial native UI state through GenFarmer's inspector/selector tooling.
4. Record stable selectors for Home/FYP, search/discover entry, profile entry and any relevant content containers.
5. Prefer resource-id/content-desc/text/class-based relative XPath. Do not use guessed coordinates.

### TT-W1 — read-only warm-up qualification

1. Start TikTok.
2. Wait for a known FYP/Home element.
3. Perform a bounded feed browse with deterministic upper limits.
4. Pause on content for configured durations.
5. Optionally open a profile/comments view and return.
6. Capture screenshot/evidence.
7. Stop TikTok and finish the run.

No likes, follows, replies, posting or account changes are part of TT-W1.

### TT-B1 — boost explore/publish qualification

After TT-W1 is stable and the test account is marked ready:

1. Explore from one configured source (keyword/link/hashtag/account list).
2. Verify the target content context before any write action.
3. For publishing, select only an explicitly approved local media input.
4. Require an idempotency/content-history check before upload.
5. Capture success/failure evidence and stop cleanly.

The first Boost qualification should prove Explore and an approved publish path before considering any engagement actions.

## Logging contract

Every action record should include at least:

- time;
- account identifier (local/private evidence, not public repo);
- app;
- mode;
- action;
- proxy identifier (not raw credential/URL);
- result: ok / skip / paused / error;
- generated text/caption only when applicable and safe to retain.

## Selector policy

Priority order:

1. resource-id / accessibility identifier;
2. content-desc / text / class combination;
3. stable relative XPath;
4. visual/image locator that returns a runtime bounding box;
5. measured runtime coordinates derived from a locator.

Never use visually guessed fixed coordinates as a production selector.

## Scaling gate

Do not scale past Device #1 until:

- native selectors are repeatable across multiple runs;
- every run has a bounded timeout and clean termination;
- proxy readiness is independently verified when proxy use is enabled;
- failure paths are explicit and logged;
- no account-mode or credential workflow is mixed into the warm-up/boost lane.
