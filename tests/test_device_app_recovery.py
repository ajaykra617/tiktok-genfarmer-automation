from types import SimpleNamespace

from genfarmer_automation.adb_observer import TIKTOK_PACKAGE
from genfarmer_automation.device_app_recovery import recover_tiktok_without_reboot
from genfarmer_automation.tiktok_runtime import TIKTOK_COMPONENT


class Transport:
    def __init__(self):
        self.ready_calls = 0

    def ensure_ready(self):
        self.ready_calls += 1
        return SimpleNamespace(ready=True)


class Actions:
    def __init__(self):
        self.stops = []
        self.launches = []

    def stop_package(self, package):
        self.stops.append(package)

    def launch_component(self, component):
        self.launches.append(component)


class Supervisor:
    def __init__(self, fail=False):
        self.calls = []
        self.fail = fail

    def ensure_stable(self, **kwargs):
        self.calls.append(kwargs)
        if self.fail:
            raise RuntimeError("still ANR")


def summary(*, alive, foreground=None, anr=False):
    return SimpleNamespace(
        process_alive=alive,
        foreground_package=foreground,
        anr_detected=anr,
    )


def test_app_only_recovery_force_stops_then_relaunches_and_proves_stable(tmp_path):
    transport = Transport()
    actions = Actions()
    supervisor = Supervisor()
    values = [
        summary(alive=True, foreground=TIKTOK_PACKAGE, anr=True),
        summary(alive=False),
        summary(alive=True, foreground=TIKTOK_PACKAGE, anr=False),
    ]

    def diagnostics(_device, _out, _label):
        return values.pop(0)

    result = recover_tiktok_without_reboot(
        "device:5555",
        tmp_path,
        transport=transport,
        actions=actions,
        observer=object(),
        supervisor=supervisor,
        diagnostics=diagnostics,
        sleeper=lambda _seconds: None,
    )

    assert result.success is True
    assert result.force_stop_attempts == 1
    assert result.process_gone is True
    assert result.stable_foreground is True
    assert actions.stops == [TIKTOK_PACKAGE]
    assert actions.launches == [TIKTOK_COMPONENT]
    assert transport.ready_calls == 2
    assert len(supervisor.calls) == 1
    assert "no reboot/data clear/global ADB restart" in result.reason


def test_app_only_recovery_retries_force_stop_only_after_process_is_proven_alive(tmp_path):
    transport = Transport()
    actions = Actions()
    supervisor = Supervisor()
    values = [
        summary(alive=True, foreground=TIKTOK_PACKAGE, anr=True),
        summary(alive=True, foreground=TIKTOK_PACKAGE, anr=True),
        summary(alive=False),
        summary(alive=True, foreground=TIKTOK_PACKAGE, anr=False),
    ]

    result = recover_tiktok_without_reboot(
        "device:5555",
        tmp_path,
        transport=transport,
        actions=actions,
        observer=object(),
        supervisor=supervisor,
        diagnostics=lambda _device, _out, _label: values.pop(0),
        sleeper=lambda _seconds: None,
    )

    assert result.success is True
    assert result.force_stop_attempts == 2
    assert actions.stops == [TIKTOK_PACKAGE, TIKTOK_PACKAGE]
    assert actions.launches == [TIKTOK_COMPONENT]


def test_app_only_recovery_never_launches_when_process_will_not_die(tmp_path):
    transport = Transport()
    actions = Actions()
    supervisor = Supervisor()
    values = [
        summary(alive=True, foreground=TIKTOK_PACKAGE, anr=True),
        summary(alive=True, foreground=TIKTOK_PACKAGE, anr=True),
        summary(alive=True, foreground=TIKTOK_PACKAGE, anr=True),
    ]

    result = recover_tiktok_without_reboot(
        "device:5555",
        tmp_path,
        transport=transport,
        actions=actions,
        observer=object(),
        supervisor=supervisor,
        diagnostics=lambda _device, _out, _label: values.pop(0),
        sleeper=lambda _seconds: None,
    )

    assert result.success is False
    assert result.process_gone is False
    assert actions.launches == []
    assert "reboot not attempted" in result.reason


def test_app_only_recovery_returns_failure_when_relaunch_is_not_stable(tmp_path):
    transport = Transport()
    actions = Actions()
    supervisor = Supervisor(fail=True)
    values = [
        summary(alive=True, foreground=TIKTOK_PACKAGE, anr=True),
        summary(alive=False),
        summary(alive=True, foreground=TIKTOK_PACKAGE, anr=True),
    ]

    result = recover_tiktok_without_reboot(
        "device:5555",
        tmp_path,
        transport=transport,
        actions=actions,
        observer=object(),
        supervisor=supervisor,
        diagnostics=lambda _device, _out, _label: values.pop(0),
        sleeper=lambda _seconds: None,
    )

    assert result.success is False
    assert result.process_gone is True
    assert result.stable_foreground is False
    assert "stable foreground was not proven" in result.reason
