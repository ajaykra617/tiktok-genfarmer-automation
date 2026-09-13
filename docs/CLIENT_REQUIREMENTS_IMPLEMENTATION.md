# Client requirements implementation map

Source: client Android automation specification supplied during TikTok GenFarmer work.

## Scope decision

Account Mode is intentionally deferred. The active delivery lanes are:

1. device/proxy scheduler and logging control plane;
2. TikTok Warm-up;
3. TikTok Boost Explore + approved-media Post;
4. local Python operator UI;
5. later Instagram/Reddit/X adapters using the same control-plane contracts.

## General scheduler / proxy requirements

Client requirement | Implementation status
---|---
Multiple devices with fewer mobile proxies | Modeled by barrier scheduler plan
Same application cannot concurrently share one proxy identity | Enforced by `schedule_policy.validate_wave`
Different apps may reuse one proxy identity concurrently | Allowed by policy validator
Group/wave synchronization | Explicit barrier between waves
Random interval range between scheduled work | Stored in plan as configurable min/max; execution integration pending
Proxy assignment/rotation | XProxy execution integration still pending; validator never claims an IP was changed
Wait for all tasks in a wave before advancing | Control-plane contract defined; executor pending

The scheduler must fail closed if it cannot prove the same-app proxy uniqueness rule before a concurrent wave starts.

## Warm-up

Requirement | TikTok status
---|---
Saveable presets | Implemented: short / standard / long JSON presets
FYP / Following / Random | FYP qualified; Following/Random source switching pending
Watch/read time | Implemented with bounded configurable ranges
Open profile and return | Pending end-to-end qualification
Read/open comments and return | Pending end-to-end qualification
Niche keyword / hashtag / sound | Keyword/hashtag exploration primitives exist in Boost lane; Warm-up integration pending
Rest day | Implemented as no-action rest session
Random session length, never above one hour | Enforced by planner, max 60 minutes
Checkpoints / resume | Implemented
Permission-dialog recovery | Implemented for TikTok Android runtime permission dialogs; deny-only/no permission grant
Logging/evidence | Implemented per step/session

### Engagement boundary

Light likes, follows, replies, mass follow/unfollow, coordinated engagement and cross-account interaction are not part of the active Warm-up implementation. Passive browsing, niche exploration, profile/comments viewing and owned-account posting are the supported lanes.

## Boost

Requirement | TikTok status
---|---
READY gate | Implemented
Optional warm scroll before Boost | Pending orchestration integration
Explore Random | Pending
Explore Keywords | Implemented path, live qualification pending
Explore Link | Implemented path, live qualification pending
Explore Hashtag | Implemented path, live qualification pending
Explore Account list | Implemented path, live qualification pending
Approved video/photo input | Video publish path implemented; photo-set qualification pending
One creation per device | Controller performs one publish transaction per invocation
Never same creation on same account | SHA-256 duplicate-history guard implemented
Never same creation across devices | History model supports shared duplicate guard; multi-device qualification pending
Allow same creation across accounts | Explicit override exists; should be enabled only when content-distribution approval exists
Schedule post | Pending TikTok UI qualification
Randomized schedule window | Pending after schedule-post qualification
Unique caption/text | Caption input supported; AI generation not required for initial qualification
Distribution interval | Scheduler lane will own spacing/barriers

### Engagement boundary

Reply automation, like/upvote/downvote automation, first-comment automation and coordinated interaction between controlled accounts are not part of the active Boost lane. The current Boost scope is Explore + approved-media publishing.

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

## Local Python UI

`scripts/automation_console.py` is the operator surface. It is standard-library Tkinter so the client machine does not need another web stack.

Current tabs:

- Dashboard — ADB device health/status
- Warm-up — preset/device/compiler/candidate controls and launch
- Boost — media, Explore, READY and final-publish controls
- Scheduler — validates barrier waves and same-app proxy uniqueness
- Logs — live child-process output and append-only audit logs

The UI launches the same tested Python scripts used from PowerShell rather than creating a second automation implementation.

## Next qualification order

1. Finish 24-video TikTok Warm-up soak on GF#7.
2. Qualify Warm-up profile/comments/source switching.
3. Run Boost Explore to `READY_TO_PUBLISH` with disposable owned media.
4. Run one disposable real publish and verify return-to-feed.
5. Qualify scheduling and photo-set posting.
6. Add XProxy assignment/readiness executor behind the scheduler policy.
7. Add a real barrier-wave scheduler executor.
8. Scale TikTok to a second healthy device, then more devices.
9. Build Instagram/Reddit/X adapters against the same UI/scheduler/log contracts.
