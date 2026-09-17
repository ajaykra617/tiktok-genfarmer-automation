# TikTok stall / crash recovery

TikTok must be treated as a process that can occasionally wedge, crash, be killed by Android, or temporarily stop producing a healthy accessibility hierarchy. The automation must recover from those runtime faults without turning every semantic failure into a blind retry loop.

## Recovery ladder

1. **Observe first** — prove ADB state, foreground package and known Android interrupt state.
2. **Read-only retry** — retry only classified hierarchy/ADB observation failures within the shared budget.
3. **Foreground restore** — if TikTok is merely backgrounded, relaunch the already-qualified component.
4. **Clean app-process restart** — at an explicit workflow checkpoint, force-stop only TikTok, wait briefly, relaunch the qualified component, and independently prove healthy foreground again.
5. **Replay only the checkpoint-safe stage** — passive warm-scroll/profile/comments/Explore stages may be replayed once after the clean restart because restart returns the workflow to a known app checkpoint.
6. **Fail closed / quarantine** — if the global hard-restart budget is exhausted, stop the session rather than looping forever.

## What a clean restart does

`am force-stop com.zhiliaoapp.musically` terminates the TikTok process, allowing Android to reclaim that app process's private RAM. The controller then launches the already-qualified TikTok component and proves healthy foreground state before continuing.

The controller deliberately does **not**:

- clear TikTok app data;
- clear TikTok cache as a routine recovery action;
- reinstall TikTok;
- run a global Android RAM cleaner / kill unrelated applications;
- replay an unknown mutation after a timeout;
- bypass checkpoints, captcha or account verification.

Clearing app data is especially unsafe because it can destroy login/session state. Global RAM cleaners can destabilize GenFarmer helpers and unrelated applications. Force-stopping only the stalled app is the narrowest useful process reset.

## Client demo behavior

`tiktok_client_demo.py` uses a global app-restart budget (default: 3) and at most one checkpoint restart for each replayable stage. If TikTok stalls during warm scroll, FYP restore, passive profile/comments, niche Explore, or Boost Explore, the runner can:

```
checkpoint failure
  -> classify as restart-worthy
  -> force-stop TikTok only
  -> relaunch qualified component
  -> prove healthy foreground
  -> return to the stage checkpoint
  -> replay that passive stage once
```

Unknown semantic failures such as an ambiguous control still fail closed. Boost preparation is replayed only for known runtime/Explore failures; the preparation child releases its atomic media lease on a blocked run, so a safe retry can reacquire it.

The final Post action remains outside this replay mechanism. Final publishing must never be blindly repeated because its completion could be ambiguous.
