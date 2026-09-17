from genfarmer_automation.runtime_diagnostics import summarize_runtime_evidence


def test_runtime_diagnostics_detects_live_process_and_foreground_activity():
    summary = summarize_runtime_evidence(
        pid_text="26936\n",
        window_text=(
            "mCurrentFocus=Window{123 u0 "
            "com.zhiliaoapp.musically/com.ss.android.ugc.aweme.splash.SplashActivity}"
        ),
    )
    assert summary.process_alive
    assert summary.pid == "26936"
    assert summary.foreground_package == "com.zhiliaoapp.musically"
    assert summary.foreground_activity == "com.ss.android.ugc.aweme.splash.SplashActivity"
    assert not summary.anr_detected


def test_runtime_diagnostics_detects_process_record_anr():
    summary = summarize_runtime_evidence(
        pid_text="26936",
        process_text=(
            "ProcessRecord{3da4d0d 26936:com.zhiliaoapp.musically/u0a662}\n"
            "  notResponding=true\n"
        ),
    )
    assert summary.anr_detected


def test_runtime_diagnostics_treats_crash_and_low_memory_as_hints():
    summary = summarize_runtime_evidence(
        logcat_text=(
            "FATAL EXCEPTION in com.zhiliaoapp.musically\n"
            "lmkd lowmemory kill candidate com.zhiliaoapp.musically\n"
        ),
    )
    assert summary.crash_marker_detected
    assert summary.low_memory_marker_detected


def test_runtime_diagnostics_preserves_collection_errors():
    summary = summarize_runtime_evidence(collection_errors=["window:timeout", "", "logcat:adb-exit-1"])
    assert summary.collection_errors == ("window:timeout", "logcat:adb-exit-1")
