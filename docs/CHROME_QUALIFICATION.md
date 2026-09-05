# Chrome Qualification Lane

Purpose: prove the GenFarmer + Python control plane end to end on one Android device before introducing TikTok-specific UI/state.

## Phase A — deterministic browser launch/routing

Use a dedicated Automation App named exactly:

`GF Lab - Chrome Qualification`

Run the local fixture server on the Windows automation host:

```powershell
python scripts/chrome_fixture_server.py --public-host <THIS-PC-LAN-IP>
```

Default fixture URL:

`http://<THIS-PC-LAN-IP>:8765/`

The page is self-contained and exposes stable controls:

- title: `GF Browser Qualification`
- input id: `gf-message`
- button id: `gf-submit`
- success id: `gf-success`
- scroll target id: `gf-scroll-target`
- expected test text: `GENFARMER-OK`

Recommended first GenFarmer chain:

`Start -> Start App -> ADB shell command -> Sleep -> Screenshot -> Stop App -> Stop`

The ADB node should open the fixture URL in the installed browser using an Android VIEW intent. Keep the exact command local/private; do not commit client/device-specific values.

After saving the flow, run:

```powershell
python scripts/genfarmer_chrome_qualification_audit.py
```

The audit is GET-only, stores the exact flow under ignored private evidence, and reports action-level routing only.

## Phase B — UI primitives

Once Phase A runs successfully several times, extend the same flow with the minimum UI primitives needed later by TikTok:

- Touch
- Type text
- Press key
- Element exists
- Swipe/Scroll

Use the fixture page rather than a third-party site so failures are attributable to our automation stack, not an external page.

For any action whose exact option serialization is still unknown, use:

```powershell
python scripts/genfarmer_setting_probe.py before --action <Action>
# change exactly one setting in GenFarmer and save
python scripts/genfarmer_setting_probe.py after --action <Action>
```

Do not scale beyond Device #1 until the qualification flow is repeatable.

## Qualification gate

Move to TikTok only after:

1. GenFarmer reloads the saved qualification flow correctly.
2. Device #1 opens the fixture page reliably.
3. Routing executes in the intended order.
4. Touch/type/press/swipe primitives work on the fixture.
5. Screenshot evidence is captured.
6. The flow succeeds repeatedly without manual intervention.
