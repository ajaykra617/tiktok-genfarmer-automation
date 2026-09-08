# TikTok feed-anchor qualification

## Why this lane exists

Whole-screen visual transition evidence is only secondary evidence. On Device #1,
a supervised browse-one dry-run later measured only 3.4% temporally stable screen
area, so the controller correctly failed closed with
`INCONCLUSIVE_CONTROL_BASELINE` instead of executing a GenFarmer swipe.

The next gate is therefore a native GenFarmer selector for a stable, feed-specific
anchor. Public source must not invent or store private selector values.

## Qualification workflow

1. Compile the read-only feed-anchor lab flow:
   `Start -> StartApp -> Pause -> ElementExists -> Screenshot -> Stop`.
2. Deploy that flow to the known qualification app using the documented API helper.
3. In GenFarmer, open the `ElementExists` node and use GenFarmer's native element
   inspector/selector UI to choose one stable feed-specific element.
4. Prefer resource-id/accessibility/content-description based selectors when
   GenFarmer exposes them. Avoid coordinates and avoid dynamic video/caption/user
   content. Visible localized text should not be the first choice when a stable
   native identifier exists.
5. Save/export the app after GenFarmer serializes the selector configuration.
6. Run `genfarm_capture_configured_action.py --action ElementExists --require-change`
   and write the exact options only under ignored `evidence/private`.
7. Restore the short browse-one module after the selector capture.
8. The next compiler/supervisor stage will use the captured selector as the feed
   precondition and combine selector evidence with the already-qualified
   GenFarmer Simple/Up Swipe and optional visual transition evidence.

## Fail-closed rules

- Never guess selector field names or values.
- Never use hard-coded screen coordinates for the feed anchor.
- Unknown/challenge/captcha/checkpoint states stop the module.
- A GenFarmer node reporting success is not sufficient application-level proof.
- If the configured `ElementExists` options are byte-for-byte identical to the raw
  palette template, selector configuration is not proven and qualification stops.
