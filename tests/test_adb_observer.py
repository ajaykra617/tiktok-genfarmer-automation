from genfarmer_automation.adb_observer import (
    InterruptKind,
    classify_interrupt,
    has_app_not_responding,
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


def test_detects_framework_app_not_responding_dialog_marker():
    window = (
        "mCurrentFocus=Window{abc u0 Application Not Responding: "
        "com.zhiliaoapp.musically} AppNotRespondingDialog"
    )
    assert has_app_not_responding(window) is True
    assert (
        classify_interrupt("device", "com.zhiliaoapp.musically", window)
        is InterruptKind.APP_NOT_RESPONDING
    )


def test_anr_detection_does_not_depend_on_localized_visible_text():
    # The user-facing dialog may be French/other languages; framework marker is
    # what the observer relies on.
    activity = "AppNotRespondingDialog package=com.zhiliaoapp.musically"
    assert (
        classify_interrupt("device", "com.zhiliaoapp.musically", activity)
        is InterruptKind.APP_NOT_RESPONDING
    )


def test_normal_tiktok_foreground_is_not_anr():
    text = (
        "mCurrentFocus=Window{123 u0 "
        "com.zhiliaoapp.musically/com.ss.android.ugc.aweme.splash.SplashActivity}"
    )
    assert has_app_not_responding(text) is False
    assert (
        classify_interrupt("device", "com.zhiliaoapp.musically", text)
        is InterruptKind.NONE
    )
