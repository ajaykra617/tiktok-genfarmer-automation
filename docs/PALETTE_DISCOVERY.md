# GenFarmer 2.6.1 palette discovery

## Status

The Automation editor bundle `dist/render/assets/useScriptEditor-HioTuYH4.js` is now the primary source-discovery target. It contains every originally known Automation palette label and additional real-looking palette labels.

Static raw-token scanning of the whole `app.asar` was too noisy. Structured ASAR reading plus focused editor-bundle mining is materially better.

## Live-observed actions

These actions have been observed in a real saved `script.flow` and are therefore stronger than source-only candidates:

- `Start`
- `Variables`
- `ContextMenu`
- `Adb`
- `DeepSeek`
- `Pause`
- `Screenshot`

## Source-confirmed palette labels

The editor bundle contains all of these known labels:

- Press Back
- Press Home
- Press Menu
- Change device
- Start App
- Stop App
- Install App
- Uninstall App
- Variables
- Context Menu
- ADB shell command
- Sleep
- Screenshot
- DeepSeek

`Uninstall App` was discovered from source rather than supplied as an initial anchor, proving that the bundle can reveal additional palette entries.

## Strong additional source-discovered candidates

The palette cluster probe surfaced these human-facing labels with stronger evidence than generic UI controls:

- Is installed App
- Clear App Data
- Transfer File
- Device actions
- Toggle service
- Check activity
- Press key
- Type text
- Update field
- Get property
- Element exists
- Multi Element exists
- Get attribute
- Write file
- Save assets
- Set variable
- Insert data
- Open AI
- Case Path

These are **source-discovered candidates**, not yet serialized-template verified. They must not be treated as fully supported Python authoring primitives until a real GenFarmer-generated node/template confirms the exact `script.flow` payload.

## Ambiguous implementation/palette tokens

The same editor cluster also contains tokens such as:

- Cmd
- Touch
- Random
- HTTP
- Comment
- Loop
- While
- Stop
- Clipboard
- Spreadsheet
- Gemini
- Grok
- Javascript
- Reconnect
- Log
- Xpath
- GenRouter

These may be node names, internal action names, categories, settings modes, or helper implementations. They require action/label correlation before classification.

## Internal action evidence

The editor bundle contains implementation-looking identifiers including:

- `actionElementExists`
- `actionVariables`
- `actionLoop`

This is important because it provides a path to correlate human-facing palette labels with internal semantic action identifiers. `scripts/genfarmer_action_label_probe.py` performs that correlation without publishing raw GenFarmer source.

## Settings-form controls

The editor bundle also contains generic form-builder controls such as:

- Input
- Input Number
- Select
- Switch
- CheckBox
- Radio
- Slider
- TextArea
- File
- Grid
- Group
- Layout
- Divider
- Alert
- HTML

These should not be counted as Automation nodes. They are useful because they likely describe the schema used to render per-node settings panels.

## Evidence hierarchy

Use this confidence order:

1. **Live saved `script.flow` template** — strongest; exact serialization observed.
2. **Source label + internal action correlation** — useful for palette discovery, but payload still unverified.
3. **Source-only human label** — likely palette candidate.
4. **Ambiguous token** — discovery lead only.

## Next steps

1. Run `scripts/genfarmer_action_label_probe.py` and correlate `action*` identifiers with human labels.
2. Use resulting mappings to produce the first source-derived full palette catalog.
3. Mine settings-property keys around each action and compare them with live `script.flow` option shapes.
4. Create `GF Lab - Node Catalog` only for source-discovered nodes that still lack exact saved templates.
5. Promote a node into the Python authoring registry only after its exact GenFarmer-generated template and required settings are verified.
