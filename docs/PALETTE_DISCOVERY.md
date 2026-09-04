# GenFarmer 2.6.1 palette discovery

## Status

Structured Electron/ASAR inspection has now recovered the Automation palette registry directly from renderer JavaScript ASTs.

The strongest current source result is `scripts/genfarmer_palette_registry_ast.py`, which found **42 distinct direct `label + action + icon` registry rows** across renderer assets. This is materially stronger than regex/proximity scanning because each row is an actual JavaScript object containing those three direct properties.

The extractor also proved that many strings named `action*` are **icon identifiers**, not the semantic action. In 28/42 rows, the `icon` field contains values such as `actionPressBack`, `actionPause`, `actionScreenshot`, or `actionTypeText`, while the actual `action` field is a constant expression such as `H.PRESS_BACK`, `H.PAUSE`, `H.SCREENSHOT`, or `H.TYPE_TEXT`.

## Live-observed saved actions

These serialized `data.action` values have already been observed in real saved `script.flow` nodes and therefore remain the highest-confidence semantic evidence:

- `Start`
- `Variables`
- `ContextMenu`
- `Adb`
- `DeepSeek`
- `Pause`
- `Screenshot`

## AST-extracted palette registry

The following direct palette rows are source-proven in GenFarmer 2.6.1:

| UI label | Source action constant | Icon |
|---|---|---|
| ADB shell command | `H.ADB` | `terminal` |
| Backup/Restore v2 | `H.BACKUP_RESTORE_V2` | `backupManager` |
| Break Loop | `H.BREAK` | `actionBreak` |
| Case Path | `H.CASE_PATH` | `actionCasePath` |
| Change device | `H.CHANGE_DEVICE` | `deviceUnknown` |
| Check Account Status | `H.CHECK_PLATFORM_ACCOUNT` | `search` |
| Check activity | `H.CHECK_ACTIVITY` | `actionCheckActivity` |
| Check network | `H.CHECK_NETWORK` | `globe` |
| Clear App Data | `H.CLEAR_APP_DATA` | `clear` |
| DeepSeek | `H.DEEPSEEK` | `tableAdd` |
| Device actions | `H.DEVICE_ACTION` | `actionDeviceAction` |
| Element exists | `H.ELEMENT_EXISTS` | `actionElementExists` |
| Generate 2FA | `H.TWO_FA` | `actionTwoFA` |
| Get attribute | `H.GET_ATTRIBUTE_VALUE` | `actionGetAttributeValue` |
| Get property | `H.GET_PROPERTY` | `actionGetProperty` |
| Group Node | `Ht.GROUP_NODE` | `fileZip` |
| Image search | `H.IMAGE` | `actionImageSearch` |
| IMAP (Read mail) | `H.IMAP` | `actionImap` |
| Insert data | `H.INSERT_DATA` | `tableAdd` |
| Install App | `H.INSTALL_APP` | `actionInstallApp` |
| Is installed App | `H.IS_INSTALLED_APP` | `actionIsInstalledApp` |
| Loop V2 | `H.LOOPV2` | `actionLoop` |
| Multi Element exists | `H.MULTI_ELEMENT_EXISTS` | `actionElementExists` |
| Open AI | `H.OPEN_AI` | `tableAdd` |
| Press Back | `H.PRESS_BACK` | `actionPressBack` |
| Press Home | `H.PRESS_HOME` | `actionPressHome` |
| Press key | `H.PRESS` | `actionPress` |
| Press Menu | `H.PRESS_MENU` | `actionPressMenu` |
| Read file / variable | `H.READ_FILE` | `actionReadFile` |
| RegExp (Data extraction) | `H.RegEx` | `actionRegExp` |
| Save assets | `H.SAVE_ASSETS` | `actionSaveAssets` |
| Screenshot | `H.SCREENSHOT` | `actionScreenshot` |
| Set variable | `H.SET_VARIABLE` | `actionVariables` |
| Sleep | `H.PAUSE` | `actionPause` |
| Start App | `H.START_APP` | `play` |
| Stop App | `H.STOP_APP` | `stop` |
| Toggle service | `H.TOGGLE_SERVICE` | `actionToggleServiceAction` |
| Transfer File | `H.TRANSFER_FILE` | `actionTransferFile` |
| Type text | `H.TYPE_TEXT` | `actionTypeText` |
| Uninstall App | `H.UNINSTALL_APP` | `trash` |
| Update field | `H.UPDATE_FIELD` | `edit` |
| Write file | `H.WRITE_FILE` | `actionWriteFile` |

This is the first source-derived exact palette registry. It does **not** yet prove the final serialized `data.action` literal for every constant, nor the exact `script.flow` payload or settings schema for every node.

## Corrected interpretation of `action*` tokens

Earlier proximity probes treated tokens such as `actionTypeText`, `actionPause`, and `actionScreenshot` as possible semantic action identifiers. AST evidence corrects that interpretation: for many palette rows they are direct **icon values**.

The action field instead points at constants under namespaces such as `H` and `Ht`. The current task is therefore to resolve:

```text
H.PAUSE      -> ?
H.SCREENSHOT -> ?
H.ADB        -> ?
H.TYPE_TEXT  -> ?
...
```

and validate those resolutions against live saved `script.flow` values where available.

## Constant resolver

`scripts/genfarmer_action_constant_resolver.py` dynamically discovers the constants used by the palette registry and scans all renderer assets for their backing string mappings. It aggregates only constant/literal evidence and cross-checks known live anchors:

- `ADB` expected live literal: `Adb`
- `DEEPSEEK` expected live literal: `DeepSeek`
- `PAUSE` expected live literal: `Pause`
- `SCREENSHOT` expected live literal: `Screenshot`

No unresolved constant is guessed.

## Settings-form controls

The renderer also contains generic controls such as `Input`, `Input Number`, `Select`, `Switch`, `CheckBox`, `Radio`, `Slider`, `TextArea`, `File`, `Grid`, `Group`, `Layout`, `Divider`, `Alert`, and `HTML`.

These are settings UI primitives, not Automation nodes. Previous regex-based per-action settings probes were intentionally classified as noisy because shared editor/form code contaminated action neighborhoods. Settings attribution must now anchor on resolved semantic constants and/or exact saved GenFarmer nodes.

## Evidence hierarchy

1. **Live saved `script.flow` template** — strongest; exact serialization observed.
2. **AST palette row + resolved action constant** — strong source evidence for label-to-semantic-action mapping.
3. **AST palette row with unresolved action constant** — exact palette membership, serialization still unknown.
4. **Source-only token/proximity result** — discovery lead only.

## Next steps

1. Run `scripts/genfarmer_action_constant_resolver.py` and resolve `H.*` / `Ht.*` constants to literals where the bundle proves them.
2. Compare resolved literals against the seven live-observed `data.action` values.
3. Produce a confidence-ranked label -> source constant -> serialized action catalog.
4. Create `GF Lab - Node Catalog` only for nodes whose exact saved payload or settings remain unverified.
5. Learn ambiguous settings with one-field-at-a-time private snapshots and masked diffs.
6. Promote a node into the Python authoring registry only after exact GenFarmer-generated serialization is verified.
