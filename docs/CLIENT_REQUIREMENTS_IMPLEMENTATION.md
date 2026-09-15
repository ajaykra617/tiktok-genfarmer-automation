# Client requirements implementation map

Source: client Android automation specification supplied during TikTok GenFarmer work.

## Scope decision

Account Mode is intentionally deferred. The active delivery lanes are:

1. device/proxy scheduler and logging control plane;
2. TikTok Warm-up;
3. TikTok Boost Phase A (Explore + approved-media preparation);
4. deferred TikTok publishing UI qualification;
5. later Instagram/Reddit/X adapters using the same control-plane contracts.

The local Tkinter UI remains intentionally frozen until the automation engine is complete enough to justify polishing the operator surface.

## General scheduler / proxy requirements

Client requirement | Implementation status
---|---
Multiple devices with fewer mobile proxies | Modeled by barrier scheduler plan
Same application cannot concurrently share one proxy identity | Enforced by `schedule_policy.validate_wave`
Different apps may reuse one proxy identity concurrently | Allowed by policy validator
Group/wave synchronization | Implemented by `run_boost_phase_a_waves.py`
Random interval range between scheduled work | Implemented as configurable min/max wait between waves; qualification can explicitly skip waits
Proxy readiness | Implemented: TCP reachability is separated from real HTTP(S) egress/public-IP proof
Proxy assignment/rotation | Vendor-specific assignment/rotation executor still pending
Wait for all tasks in a wave before advancing | Implemented and live-qualified on the primary healthy device

The scheduler fails closed if it cannot prove same-app proxy uniqueness or, in apply mode, real proxy egress before device work starts.

### Current XProxy blocker

The tested proxy listener is reachable, but real external egress is not currently qualified. Standalone Python and curl checks failed to obtain a usable public IP through the proxy, while the XProxy dashboard reported an upstream internet/connectivity error state. Apply-mode proxy-required waves therefore remain blocked by design until the modem/SIM/upstream data path is healthy.

Host-to-proxy qualification is also not sufficient to prove Android application routing. A later device-route qualification must prove that TikTok traffic on the selected Android device actually exits through the assigned proxy.

## Warm-up

Requirement | TikTok status
---|---
Saveable presets | Implemented
FYP / Following / Random | FYP live-qualified; Following correctly prerequisite-skips when the account follows nobody; mixed/random source orchestration still pending
Watch/read time | Implemented with bounded configurable ranges
Open profile and return | Live-qualified
Read/open comments and return | Live-qualified
Niche keyword / hashtag | Live-qualified
Rest day | Implemented as no-action rest session
Random session length, never above one hour | Enforced by planner, max 60 minutes
Checkpoints / resume | Implemented and qualified
Permission-dialog recovery | Implemented with conservative bounded recovery
Logging/evidence | Implemented per step/session

### Qualification evidence

The standard TikTok FYP session completed a full 24-video live soak on the primary healthy Pixel test device:

- 24/24 requested videos completed;
- 24/24 steps used full selector verification;
- zero continuity-only steps;
- zero failed attempts in the standard run;
- bounded watch-time variation was active throughout;
- the Python fallback action backend was used for all 24 swipes while independent selector gates proved feed state before/after each action.

The feature matrix also live-qualified For You, comments, creator profile, keyword exploration and hashtag exploration. Following was skipped only because the account had no followed creators, which is treated as an account-data prerequisite rather than an automation failure.

### Engagement boundary

Likes, follows, replies, DMs, mass follow/unfollow and coordinated/cross-account engagement are not part of the active Warm-up implementation. Passive browsing, niche exploration and profile/comments viewing are the supported lanes.

## Boost

Publishing is intentionally split from the reliable preparation lane.

### Phase A — implemented and live-qualified

Requirement | TikTok status
---|---
READY gate | Implemented and live-qualified
Saved presets | Implemented and live-qualified
Optional warm scroll before Boost | Implemented in preset/prepare orchestration; warm variant still needs a dedicated live qualification run
Explore Random | Implemented as deterministic seeded selection from configured source pools; preset selection live-qualified
Explore Keywords | Implemented and live-qualified
Explore Link | Implemented; live qualification pending
Explore Hashtag | Implemented; underlying hashtag navigation is qualified, Boost-specific run still pending
Explore Account list | Implemented as configured account sources; live qualification pending
Approved video/photo input | File/folder discovery supports approved video and image formats
One media preparation per device/job | Implemented
Never same media concurrently across devices | Enforced by atomic SHA-256 preparation leases
Never reuse a successfully published hash | Enforced by shared history guard
Cross-account duplicate reuse | Not enabled in the current safe default; shared history is intentionally stricter
MediaStore staging | Implemented and live-qualified for video
Audit logging/evidence | Implemented
Multi-device wave/barrier execution | Implemented; single-device live qualification passed
Distribution spacing between waves | Implemented as configurable randomized interval

The live Phase A terminal state is `READY_FOR_PUBLISH`. At that point the selected media remains reserved until a later publish succeeds or an operator explicitly releases the preparation lease.

### Phase B — deliberately deferred

These UI-heavy pieces remain research/qualification work:

- TikTok Create/Upload gallery navigation;
- exact media selection in the normal TikTok gallery;
- editor/Next/caption/final Post controls;
- photo-set posting;
- TikTok-native schedule-post UI;
- final publish verification and history promotion.

The earlier Android `ACTION_SEND` handoff was rejected as the production path after live tests showed unreliable TikTok file loading. The normal in-app Create -> Upload/Gallery path remains the intended future route.

### Engagement boundary

Reply automation, like/upvote/downvote automation, first-comment automation and coordinated interaction between controlled accounts are not part of the active Boost lane. Current Boost scope is passive Explore + approved-media preparation, with owned-account publishing deferred until the UI path is qualified.

## Never-automate controls

The control plane must continue to reject or leave unsupported:

- DMs;
- mass follow/unfollow;
- cross-likes / controlled-account coordination;
- indiscriminate same-media distribution;
- proxy rotation during login or upload;
- captcha/checkpoint bypass;
- Reddit vote/comment brigading.

## Logging contract

`src/genfarmer_automation/audit_log.py` implements append-only JSONL and CSV records with:

- time
- account
- app
- mode
- action
- proxy
- result
- ai_text

Runtime/private logs may contain account or device identifiers and remain ignored by Git.

## Current qualification order

1. Keep the XProxy apply lane blocked until real external egress/public IP returns.
2. Qualify the Boost warm-scroll preset and remaining Link/Account/Boost-specific Hashtag Explore variants.
3. Exercise a multi-device dry-run with separate approved media per device to prove concurrent reservation/barrier behavior without requiring proxy egress.
4. Finish mixed Warm-up orchestration (mainly FYP plus occasional passive excursions).
5. Return to normal TikTok Create -> Upload/Gallery publishing after additional UI research.
6. Once XProxy is healthy, qualify host proxy egress, then Android device routing, then multi-device apply waves.
