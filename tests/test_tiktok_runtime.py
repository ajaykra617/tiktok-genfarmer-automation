from genfarmer_automation.adb_observer import DeviceObservation, InterruptKind
from genfarmer_automation.tiktok_runtime import (
    ForegroundDecision,
    TIKTOK_COMPONENT,
    TikTokRuntime,
    plan_foreground,
)


def obs(*, package="com.google.android.apps.nexuslauncher", interrupt=InterruptKind.NONE, state="device"):
    return DeviceObservation(
        device="device:5555",
        adb_state=state,
        foreground_package=package,
        foreground_activity="Activity",
        tiktok_foreground=package == "com.zhiliaoapp.musically",
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
        self.components = []

    def launch_component(self, component):
        self.components.append(component)
        return {"ok": True}


def test_plan_launcher_requires_launch():
    assert plan_foreground(obs()).decision is ForegroundDecision.NEEDS_LAUNCH


def test_plan_tiktok_is_ready():
    assert plan_foreground(obs(package="com.zhiliaoapp.musically")).decision is ForegroundDecision.READY


def test_plan_permission_dialog_fails_closed():
    value = obs(
        package="com.google.android.permissioncontroller",
        interrupt=InterruptKind.ANDROID_PERMISSION_DIALOG,
    )
    assert plan_foreground(value).decision is ForegroundDecision.BLOCKED_INTERRUPT


def test_ensure_foreground_launches_once_and_proves_state():
    observer = FakeObserver([obs(), obs(package="com.zhiliaoapp.musically")])
    actions = FakeActions()
    result = TikTokRuntime(
        "device:5555",
        observer=observer,
        actions=actions,
        settle_seconds=0,
        poll_seconds=0,
        max_polls=2,
    ).ensure_foreground()
    assert result.success is True
    assert result.attempts == 1
    assert actions.components == [TIKTOK_COMPONENT]


def test_ensure_foreground_never_launches_through_interrupt():
    blocked = obs(
        package="com.google.android.permissioncontroller",
        interrupt=InterruptKind.ANDROID_PERMISSION_DIALOG,
    )
    actions = FakeActions()
    result = TikTokRuntime(
        "device:5555",
        observer=FakeObserver([blocked]),
        actions=actions,
        settle_seconds=0,
        poll_seconds=0,
    ).ensure_foreground()
    assert result.success is False
    assert result.attempts == 0
    assert actions.components == []
