# TikTok Automation - Client Demo Runbook

**Milestone:** Warm-up + Boost Preparation

This runbook is aligned to the client's `Android automation(1).pdf` requirements and is intentionally limited to the capabilities already live-qualified on the working TikTok device.

## Demo scope

Use **GF#7 / Pixel 4 XL / `192.168.4.143:5555`** for the demonstration. Keep GF#1 out of the client demo because TikTok has repeatedly become unstable on that device.

Current validated baseline:

- 257 automated tests passing.
- Warm-up passive features qualified on GF#7.
- Boost Explore qualified for keyword, hashtag, account and link.
- Boost warm-scroll + Explore preset reaches `READY_FOR_PUBLISH`.
- Bounded runtime recovery has live evidence: a transient hierarchy bootstrap failure recovered on one retry and the Explore matrix still passed 4/4.
- Engagement actions remain `NONE` in the current demo.

## Requirement coverage for this milestone

| Client requirement | Demo status | Demo behavior |
|---|---|---|
| Proxy + scheduler, distinct same-app IPs, group barriers | Deferred | Do not claim live mobile proxy routing or multi-device scheduler qualification yet. |
| Account Mode | Deferred | Not part of this milestone. |
| Warm-up FYP / Following / watch-read / profile / comments / niche | Live | Passive FYP browsing, dwell time, profile/comments and keyword/hashtag exploration. Following may be a prerequisite skip because the demo account follows nobody. |
| Warm-up likes/follows | Deferred | Not performed in this demo. |
| Boost READY gate + optional warm scroll | Live | Three-video warm scroll before Explore. |
| Boost Explore: keyword / hashtag / account / link | Live | All four sources live-qualified. |
| Boost post preparation | Partial | Duplicate guard, atomic media reservation and exact staging through `READY_FOR_PUBLISH`. Final TikTok Create/Gallery/Post is not entered. |
| Boost reply / likes | Deferred | Not performed in this milestone. |
| Logging | Live | Shareable JSON, private evidence and terminal summaries are produced. |
| Never automate boundaries | Live | No DMs, mass follow/unfollow, cross-account engagement, captcha/checkpoint bypass, or proxy rotation mid-upload. |

## Presentation layout

Use a split screen:

- Left: GenFarmer / live Android device view.
- Right: PowerShell.

Keep the client focused on visible device behavior and concise `PASS` / `READY_FOR_PUBLISH` summaries. Do not open raw XML, selector files, private screenshots, ADB diagnostics or proxy-debug output unless specifically asked.

## Part A - Warm-up Mode

Run:

```powershell
python scripts/tiktok_warmup_feature_matrix.py `
  "evidence\tiktok-feed-anchor-ranking-20260913T040840Z\private\ranked-candidates.private.json" `
  --candidate 8 `
  --device "192.168.4.143:5555" `
  --keyword "technology" `
  --hashtag "technology" `
  --dwell-min 3 `
  --dwell-max 6 `
  --apply
```

Expected client-facing summary:

```text
TIKTOK WARM-UP FEATURE MATRIX
Status:                     PASS
Features qualified:         5/6
Prerequisite skips:         1
Engagement actions:         NONE
```

Explain the Following skip as a valid prerequisite condition: the current demo account follows nobody, so the automation skips an empty Following feed rather than manufacturing follow activity.

## Part B - Boost Mode

Run:

```powershell
python scripts/tiktok_boost_prepare_preset.py `
  --preset "phase_a_warm_then_explore" `
  --device "192.168.4.143:5555" `
  --proxy-id "xproxy-pos-1" `
  --media "C:\genfarmer-lab\boost-test.mp4" `
  --candidates "evidence\tiktok-feed-anchor-ranking-20260913T040840Z\private\ranked-candidates.private.json" `
  --seed 42 `
  --ready `
  --apply
```

Expected client-facing summary:

```text
TIKTOK BOOST PHASE A PRESET
Status:                     READY_FOR_PUBLISH
Preset:                     phase_a_warm_then_explore
Explore source:             keyword
Warm scroll videos:         3
Warm scroll status:         PASS
Publishing UI:              DEFERRED / NOT ENTERED
Final Post action:          NONE
```

Client story:

`warm scroll -> Explore -> duplicate guard -> exclusive media reservation -> exact Android media staging -> READY_FOR_PUBLISH`

State clearly that final publishing is the next module, so this demo stops intentionally before `Post`.

## Demo acceptance criteria

The demo is successful when:

- Warm-up matrix finishes `PASS`.
- Following is either `PASS` or the known `following_feed_empty` prerequisite skip.
- Engagement actions remain `NONE`.
- Boost warm scroll completes.
- Explore source is verified.
- Duplicate guard, reservation and media staging pass.
- Final Boost status is `READY_FOR_PUBLISH`.
- Final Post action is `NONE`.

## Cleanup after Boost

```powershell
python scripts/tiktok_boost_release_preparation.py `
  --media "C:\genfarmer-lab\boost-test.mp4" `
  --device "192.168.4.143:5555" `
  --apply
```

A successful cleanup should return either `RELEASED` or `NOT_RESERVED` without changing media/history/evidence.

## Client talk track

1. **Context:** this is the first qualified TikTok engine milestone on the working device.
2. **Warm-up:** demonstrate passive browsing, watch time, profile/comments and niche exploration.
3. **Reliability:** explain that known ANR/hierarchy/ADB/background issues are classified and recovered only within bounded budgets; unknown semantic failures still stop the run.
4. **Boost:** demonstrate warm scroll, Explore, duplicate protection, reservation and staging.
5. **Safety gate:** stop at `READY_FOR_PUBLISH` and explain final publish is the next module.
6. **Roadmap:** next complete final publishing, prove Android traffic uses the assigned mobile proxy with unique same-app external IPs, qualify scheduler/barriers, then scale to more devices and Account Mode.

## Positioning

Call this demo:

**TikTok Automation - Milestone 1: Warm-up + Boost Preparation**

Do not present it as the full client delivery until final publishing, Android proxy-route proof, scheduler/group barriers, multi-device qualification and Account Mode are completed.
