from genfarmer_automation.adb_observer import (
    InterruptKind,
    classify_interrupt,
    parse_foreground,
)


def test_parse_current_focus_tiktok():
    package, activity = parse_foreground(
        "mCurrentFocus=Window{123 u0 com.zhiliaoapp.musically/com.ss.android.ugc.aweme.splash.SplashActivity}"
    )
    assert package == "com.zhiliaoapp.musically"
    assert activity == "com.ss.android.ugc.aweme.splash.SplashActivity"


def test_parse_permission_controller_top_resumed():
    package, activity = parse_foreground(
        "topResumedActivity=ActivityRecord{abc u0 com.google.android.permissioncontroller/com.android.permissioncontroller.permission.ui.GrantPermissionsActivity t1}"
    )
    assert package == "com.google.android.permissioncontroller"
    assert "GrantPermissionsActivity" in activity


def test_classify_permission_dialog():
    assert (
        classify_interrupt("device", "com.android.permissioncontroller")
        is InterruptKind.ANDROID_PERMISSION_DIALOG
    )


def test_classify_device_offline_wins():
    assert classify_interrupt("offline", None) is InterruptKind.DEVICE_OFFLINE
