"""Versioned source-derived GenFarmer 2.6.1 Automation palette catalog.

This module records only privacy-safe palette metadata recovered from the
installed GenFarmer 2.6.1 renderer AST.  It is *not* a node-template registry:
exact node payloads still come from live saved ``script.flow`` documents.

Evidence levels used here:
- ``unique-source``: one unambiguous literal was structurally resolved for the
  palette action constant;
- ``live-flow-anchor``: exact ``data.action`` was independently observed in a
  saved GenFarmer flow, including the dedicated lab catalog flow;
- ``unresolved``: source evidence was ambiguous and no guess is made.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PaletteAction261:
    label: str
    constant: str
    action: str | None
    provenance: str


PALETTE_261: tuple[PaletteAction261, ...] = (
    PaletteAction261("ADB shell command", "H.ADB", "Adb", "unique-source"),
    PaletteAction261("Backup/Restore v2", "H.BACKUP_RESTORE_V2", "BackupRestoreV2", "unique-source"),
    PaletteAction261("Break Loop", "H.BREAK", "Break", "unique-source"),
    PaletteAction261("Case Path", "H.CASE_PATH", "CasePath", "unique-source"),
    PaletteAction261("Change device", "H.CHANGE_DEVICE", "ChangeDevice", "unique-source"),
    PaletteAction261("Check Account Status", "H.CHECK_PLATFORM_ACCOUNT", "CheckPlatformAccount", "unique-source"),
    PaletteAction261("Check activity", "H.CHECK_ACTIVITY", "CheckActivity", "unique-source"),
    PaletteAction261("Check network", "H.CHECK_NETWORK", "CheckNetwork", "unique-source"),
    PaletteAction261("Clear App Data", "H.CLEAR_APP_DATA", "ClearAppData", "unique-source"),
    PaletteAction261("Clipboard", "H.CLIPBOARD", "Clipboard", "unique-source"),
    PaletteAction261("Cmd", "H.CMD", "Cmd", "unique-source"),
    PaletteAction261("Comment", "H.COMMENT", "Comment", "unique-source"),
    PaletteAction261("DeepSeek", "H.DEEPSEEK", "DeepSeek", "unique-source"),
    PaletteAction261("Device actions", "H.DEVICE_ACTION", "DeviceAction", "unique-source"),
    PaletteAction261("Element exists", "H.ELEMENT_EXISTS", "ElementExists", "unique-source"),
    PaletteAction261("Gemini", "H.GEMINI", "Gemini", "unique-source"),
    PaletteAction261("Generate 2FA", "H.TWO_FA", "TwoFA", "unique-source"),
    PaletteAction261("GenRouter", "H.GEN_ROUTER", "GenRouter", "unique-source"),
    PaletteAction261("Get attribute", "H.GET_ATTRIBUTE_VALUE", "GetAttributeValue", "unique-source"),
    PaletteAction261("Get property", "H.GET_PROPERTY", "GetProperty", "unique-source"),
    PaletteAction261("Grok", "H.GROK", "Grok", "unique-source"),
    PaletteAction261("Group Node", "Ht.GROUP_NODE", "GroupNode", "unique-source"),
    PaletteAction261("HTTP", "H.HTTP", "HTTP", "live-flow-anchor"),
    PaletteAction261("If", "H.IF", "If", "unique-source"),
    PaletteAction261("Image search", "H.IMAGE", "Image", "unique-source"),
    PaletteAction261("IMAP (Read mail)", "H.IMAP", "Imap", "unique-source"),
    PaletteAction261("Insert data", "H.INSERT_DATA", "InsertData", "unique-source"),
    PaletteAction261("Install App", "H.INSTALL_APP", "InstallApp", "unique-source"),
    PaletteAction261("Is installed App", "H.IS_INSTALLED_APP", "IsInstalledApp", "unique-source"),
    PaletteAction261("Javascript", "H.JAVASCRIPT", "Javascript", "unique-source"),
    PaletteAction261("Log", "H.LOG", None, "unresolved"),
    PaletteAction261("Loop", "H.LOOP", "Loop", "unique-source"),
    PaletteAction261("Loop V2", "H.LOOPV2", "LoopV2", "unique-source"),
    PaletteAction261("Multi Element exists", "H.MULTI_ELEMENT_EXISTS", "MultiElementExists", "unique-source"),
    PaletteAction261("Open AI", "H.OPEN_AI", "OpenAi", "unique-source"),
    PaletteAction261("Press Back", "H.PRESS_BACK", "PressBack", "unique-source"),
    PaletteAction261("Press Home", "H.PRESS_HOME", "PressHome", "unique-source"),
    PaletteAction261("Press key", "H.PRESS", "Press", "unique-source"),
    PaletteAction261("Press Menu", "H.PRESS_MENU", "PressMenu", "unique-source"),
    PaletteAction261("Random", "H.RANDOM", None, "unresolved"),
    PaletteAction261("Read file / variable", "H.READ_FILE", "ReadFile", "unique-source"),
    PaletteAction261("Reconnect", "H.RECONNECT", "Reconnect", "unique-source"),
    PaletteAction261("RegExp (Data extraction)", "H.RegEx", "RegEx", "unique-source"),
    PaletteAction261("Save assets", "H.SAVE_ASSETS", "SaveAssets", "unique-source"),
    PaletteAction261("Screenshot", "H.SCREENSHOT", "Screenshot", "live-flow-anchor"),
    PaletteAction261("Set variable", "H.SET_VARIABLE", "SetVariable", "unique-source"),
    PaletteAction261("Sleep", "H.PAUSE", "Pause", "unique-source"),
    PaletteAction261("Spreadsheet", "H.SPREADSHEET", "Spreadsheet", "unique-source"),
    PaletteAction261("Start App", "H.START_APP", "StartApp", "unique-source"),
    PaletteAction261("Stop", "H.STOP", None, "unresolved"),
    PaletteAction261("Stop App", "H.STOP_APP", "StopApp", "unique-source"),
    PaletteAction261("Swipe/Scroll", "H.SWIPE", "Swipe", "unique-source"),
    PaletteAction261("Toggle service", "H.TOGGLE_SERVICE", "ToggleService", "unique-source"),
    PaletteAction261("Touch", "H.TOUCH", "Touch", "unique-source"),
    PaletteAction261("Transfer File", "H.TRANSFER_FILE", "TransferFile", "unique-source"),
    PaletteAction261("Type text", "H.TYPE_TEXT", "TypeText", "unique-source"),
    PaletteAction261("Uninstall App", "H.UNINSTALL_APP", "UninstallApp", "unique-source"),
    PaletteAction261("Update field", "H.UPDATE_FIELD", "UpdateField", "unique-source"),
    PaletteAction261("Write file", "H.WRITE_FILE", "WriteFile", "unique-source"),
    PaletteAction261("Xpath", "H.XPATH", "Xpath", "unique-source"),
)

RESOLVED_ACTIONS_261 = frozenset(item.action for item in PALETTE_261 if item.action)
UNRESOLVED_PALETTE_261 = tuple(item for item in PALETTE_261 if item.action is None)

# Special editor nodes already observed in real flows but not part of the 60
# direct label/action/icon action palette rows above.
SPECIAL_LIVE_NODES_261 = ("Start", "Variables", "ContextMenu")


def by_action(action: str) -> PaletteAction261 | None:
    for item in PALETTE_261:
        if item.action == action:
            return item
    return None


def by_label(label: str) -> PaletteAction261 | None:
    for item in PALETTE_261:
        if item.label == label:
            return item
    return None
