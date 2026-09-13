import pytest

from genfarmer_automation.adb_observer import DeviceObservation, InterruptKind
from genfarmer_automation.hierarchy_runtime import HierarchyRuntimeError
from genfarmer_automation import permission_recovery as pr
from genfarmer_automation.permission_recovery import (
    PermissionRecoveryError,
    find_tiktok_permission_deny_node,
    recover_tiktok_permission_dialog,
)


def hierarchy(*nodes: str) -> str:
    return '<hierarchy rotation="0">' + ''.join(nodes) + '</hierarchy>'


def node(**attrs) -> str:
    base = {
        "text": "",
        "content-desc": "",
        "resource-id": "",
        "class": "android.widget.Button",
        "package": "com.android.permissioncontroller",
        "clickable": "true",
        "enabled": "true",
        "bounds": "[0,0][100,100]",
    }
    base.update(attrs)
    encoded = " ".join(f'{key}="{value}"' for key, value in base.items())
    return f"<node {encoded} />"


def observation(*, interrupt: InterruptKind, foreground: bool) -> DeviceObservation:
    return DeviceObservation(
        device="device-1",
        adb_state="device",
        foreground_package=(
            "com.zhiliaoapp.musically" if foreground
            else "com.android.permissioncontroller"
        ),
        foreground_activity="Activity",
        tiktok_foreground=foreground,
        interrupt=interrupt,
    )


class FakeObserver:
    def __init__(self, values):
        self.values = list(values)
        self.index = 0

    def observe(self):
        value = self.values[min(self.index, len(self.values) - 1)]
        self.index += 1
        return value


class FakeActions:
    def __init__(self):
        self.taps = []
        self.keys = []

    def tap(self, x, y):
        self.taps.append((x, y))

    def keyevent(self, keycode):
        self.keys.append(keycode)


def test_selects_exact_deny_control_for_tiktok():
    xml = hierarchy(
        node(text="Allow TikTok to access your contacts?", **{"resource-id": "com.android.permissioncontroller:id/permission_message"}),
        node(text="Allow", **{"resource-id": "com.android.permissioncontroller:id/permission_allow_button", "bounds": "[0,100][100,200]"}),
        node(text="Don't allow", **{"resource-id": "com.android.permissioncontroller:id/permission_deny_button", "bounds": "[0,200][100,300]"}),
    )
    target = find_tiktok_permission_deny_node(xml)
    assert target.resource_id.endswith("permission_deny_button")
    assert target.center == (50, 250)


def test_refuses_permission_dialog_not_identified_as_tiktok():
    xml = hierarchy(
        node(text="Don't allow", **{"resource-id": "com.android.permissioncontroller:id/permission_deny_button"}),
    )
    with pytest.raises(PermissionRecoveryError, match="does not identify TikTok"):
        find_tiktok_permission_deny_node(xml)


def test_never_substitutes_allow_button_for_missing_deny():
    xml = hierarchy(
        node(text="Allow TikTok to access your contacts?", **{"resource-id": "com.android.permissioncontroller:id/permission_message"}),
        node(text="Allow", **{"resource-id": "com.android.permissioncontroller:id/permission_allow_button"}),
    )
    with pytest.raises(PermissionRecoveryError, match="no known Android permission-deny control"):
        find_tiktok_permission_deny_node(xml)


def test_hierarchy_failure_uses_one_safe_back_and_requires_tiktok_recovery(monkeypatch):
    initial = observation(interrupt=InterruptKind.ANDROID_PERMISSION_DIALOG, foreground=False)
    final = observation(interrupt=InterruptKind.NONE, foreground=True)
    observer = FakeObserver([initial, final])
    actions = FakeActions()

    def fail_dump(*args, **kwargs):
        raise HierarchyRuntimeError("uiautomator dump failed")

    monkeypatch.setattr(pr, "capture_uiautomator_once", fail_dump)
    result = recover_tiktok_permission_dialog(
        "device-1",
        observer=observer,
        actions=actions,
        settle_seconds=0,
        poll_seconds=0,
    )

    assert result.success
    assert result.handled
    assert result.deny_resource_id is None
    assert actions.keys == [4]
    assert actions.taps == []
    assert "safe BACK fallback" in result.reason


def test_back_fallback_fails_closed_if_permission_dialog_remains(monkeypatch):
    initial = observation(interrupt=InterruptKind.ANDROID_PERMISSION_DIALOG, foreground=False)
    observer = FakeObserver([initial, initial, initial])
    actions = FakeActions()

    def fail_dump(*args, **kwargs):
        raise HierarchyRuntimeError("uiautomator dump failed")

    monkeypatch.setattr(pr, "capture_uiautomator_once", fail_dump)
    result = recover_tiktok_permission_dialog(
        "device-1",
        observer=observer,
        actions=actions,
        settle_seconds=0,
        poll_seconds=0,
        max_polls=2,
    )

    assert not result.success
    assert result.handled
    assert actions.keys == [4]
    assert actions.taps == []
