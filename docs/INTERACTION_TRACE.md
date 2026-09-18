# High-resolution TikTok interaction tracing

## Goal

When a physical phone freezes, a single message such as `adb action timed out`
or `FYP remained loading` is not enough to identify the failing layer. Diagnostic
mode records the complete sequence from workflow intent through Android/ADB
transport, TikTok runtime state, accessibility hierarchy, FYP classification,
LIVE hints, and recovery decisions.

Trace evidence is private. It can contain raw UI text and ADB arguments and is
therefore kept under each persistent-worker private evidence directory.

## What is recorded

- workflow stage begin/end and watch ticks;
- every tap, swipe, keyevent, force-stop and app launch intent;
- every device-scoped ADB command, timeout, duration and return code;
- post-timeout ADB transport health;
- lightweight and deep Android observations, foreground package/activity and ANR state;
- hierarchy provider, port and helper/fallback attempts;
- full FYP hierarchy XML samples;
- strict candidate gate counts;
- FYP classification and semantic signals;
- LIVE-related hierarchy nodes, including bare `LIVE` / French `en direct` hints;
- whether LIVE hints were actually recognized as a `live-card`;
- checkpoint restart reason and budget;
- persistent-worker recovery, cooldown and reboot-recommendation state.

## LIVE diagnosis

The current runner already has bounded handling for recognized alternate FYP
content and one strict English LIVE-rating survey. We intentionally do not
broaden LIVE mutations from diagnostic hints alone.

The trace emits:

- `live.live-hints` when LIVE-related hierarchy nodes are present;
- `live.live-hints-unclassified` when the hierarchy looks LIVE-related but the
  FYP classifier did not identify a qualified LIVE card;
- `live.variant-advance.begin` before the skip swipe;
- exact `action` / `adb` events for the swipe;
- `live.variant-advance.end` only after TikTok runtime health is proven again.

This lets us determine whether a freeze begins before the LIVE swipe, inside the
Android input command, after the swipe, or during the next accessibility read.

## Parallel diagnostic run

Use the dedicated launcher rather than manually starting two jobs:

```powershell
python scripts\tiktok_parallel_diagnostic.py `
  "evidence\tiktok-feed-anchor-ranking-20260913T040840Z\private\ranked-candidates.private.json" `
  --device "GF1=192.168.4.138:5555" `
  --device "GF7=192.168.4.143:5555" `
  --candidate 8 `
  --proxy-id "xproxy-pos-1" `
  --media "C:\genfarmer-lab\boost-test.mp4" `
  --keyword "technology" `
  --hashtag "technology" `
  --videos 3 `
  --watch-min 4 `
  --watch-max 7 `
  --dwell 3 `
  --seed 43 `
  --max-app-restarts 3 `
  --max-cycles 2
```

Every console line is prefixed with `GF1` or `GF7`. Each underlying persistent
worker also enables structured tracing for its child and nested subprocesses.

## Trace report

Each worker cycle prints its private interaction-trace directory. To merge all
process trace files for one cycle:

```powershell
python scripts\interaction_trace_report.py `
  "<cycle interaction-trace directory>" `
  --focus-errors-live `
  --tail 250
```

Use the full JSONL + hierarchy artifacts for root-cause work; the report is only
a readable time-sorted view.

## Safety boundary

Diagnostic tracing does not add engagement or publishing actions. It does not
reboot devices, clear TikTok data/cache, kill the global ADB server, or replay
ambiguous mutations. LIVE diagnostic hints are observation-only until a
specific UI state is qualified.
