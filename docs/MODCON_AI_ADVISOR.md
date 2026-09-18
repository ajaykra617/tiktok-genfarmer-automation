# ModCon constrained recovery advisor

## Purpose

The ModCon integration is an optional decision layer for ambiguous recovery cases.
It is not an execution engine and it never receives authority to issue arbitrary
ADB commands, taps, coordinates, reboots, data clears, engagement actions, or
publishing actions.

The deterministic automation remains responsible for:

- proving ADB health;
- enforcing mutation ambiguity rules;
- semantic UI selection;
- checkpoint safety;
- app-only recovery;
- restart/cooldown budgets;
- no-reboot policy;
- no-final-publish policy.

The AI advisor is called only after a bounded client cycle blocks. It sees a
privacy-reduced structured summary of the trace and returns one allowlisted
recommendation.

## Security

Never commit or paste a real ModCon API key into the repository.

Required environment variable:

- `MODCON_API_KEY`

Optional environment variables:

- `MODCON_BASE_URL` (default: `https://modcon.top/v1`)
- `MODCON_MODEL` (default: `gpt-5.6-sol`)

The device serial is SHA-256 hashed before it is sent to the remote advisor.
Raw hierarchy XML, screenshots, stdout/stderr, account names, UI text and trace
artifact paths are not sent. Only a bounded structured summary is included.

## What the advisor may recommend

The remote model can recommend only:

- `app_recovery`
- `cooldown_only`
- `fresh_cycle`
- `recommend_reboot_approval`

`recommend_reboot_approval` is advisory only. The code still does not contain
a device reboot action.

The model cannot stop a run as configuration-invalid. That boundary remains
deterministic.

## Deterministic overrides

Some failure domains are handled without consulting the model:

### Configuration

Examples:

- missing media file;
- invalid candidate input;
- invalid runtime arguments.

Action: stop non-retryable. Restarting TikTok cannot repair configuration.

### Shared media resource

Example:

`no pending unreserved approved media is available`

Action: cooldown/fresh cycle only. Do not force-stop TikTok because app recovery
cannot create a new approved media reservation.

### ADB transport

If the failure is clearly an unhealthy ADB transport, the transport layer owns
reconnection. The worker does not force-stop TikTok merely because ADB is
offline/unhealthy.

## Why not call the model for every tap?

A remote model in the inner mutation loop would add latency and another failure
domain. High-confidence deterministic UI operations remain local.

The intended intelligence hierarchy is:

1. deterministic fast path for known, proven UI;
2. richer deterministic runtime/trace classification;
3. ModCon advisor only at uncertainty/recovery boundaries;
4. deterministic safety envelope applies the selected safe action.

A later phase may add an observation-only UI-state advisor for unclassified
TikTok surfaces such as new LIVE variants. Any resulting action would still have
to map to an allowlisted deterministic primitive.

## Install

The integration is optional:

```powershell
python -m pip install -e ".[ai,dev]"
```

or install the compatible client directly:

```powershell
python -m pip install openai
```

## Credential setup

Rotate any key that has been pasted into chat, shell history, tickets or logs.
Use a newly issued key.

Set it only in the local environment. Do not put it in committed files.

For the current PowerShell session:

```powershell
$env:MODCON_API_KEY = "<NEW_ROTATED_KEY>"
$env:MODCON_BASE_URL = "https://modcon.top/v1"
$env:MODCON_MODEL = "gpt-5.6-sol"
```

## Harmless API smoke test

Before giving the advisor access to a device worker:

```powershell
python scripts\modcon_advisor_smoke.py
```

This sends one synthetic recovery context. It performs no ADB/device action.

Expected output includes the endpoint, model ID and a validated JSON decision.

## Single-device worker

Enable the advisor only after the smoke test succeeds:

```powershell
python scripts\tiktok_persistent_device_worker.py `
  "evidence\tiktok-feed-anchor-ranking-20260913T040840Z\private\ranked-candidates.private.json" `
  --candidate 8 `
  --device "192.168.4.138:5555" `
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
  --max-cycles 2 `
  --ai-advisor
```

When a cycle blocks, the console prints:

```text
Decision brain: domain=<domain> action=<action> source=<source>
Decision rationale: <short evidence-based rationale>
```

The complete decision is also written into the worker shareable evidence.

## Parallel GF1/GF7 test

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
  --max-cycles 2 `
  --ai-advisor
```

Do not enable persistent/unbounded mode until the bounded advisor run has been
reviewed.
