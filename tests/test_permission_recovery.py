import pytest

from genfarmer_automation.permission_recovery import (
    PermissionRecoveryError,
    find_tiktok_permission_deny_node,
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
