from genfarmer_automation.ui_source_bridge import (
    appium_base_candidates,
    extract_session_ids,
    extract_source_xml,
    session_source_paths,
)


def test_extract_session_ids_from_w3c_sessions_list():
    payload = {"value": [{"id": "s1", "capabilities": {}}, {"id": "s2", "capabilities": {}}]}
    assert extract_session_ids(payload) == ("s1", "s2")


def test_extract_session_ids_dedupes_nested_session_id():
    payload = {"value": {"sessionId": "s1", "nested": [{"sessionId": "s1"}]}}
    assert extract_session_ids(payload) == ("s1",)


def test_extract_source_xml_from_w3c_value():
    xml = '<hierarchy rotation="0"><node class="x" /></hierarchy>'
    assert extract_source_xml({"value": xml}) == xml


def test_extract_source_xml_rejects_non_xml_strings():
    assert extract_source_xml({"value": "not xml"}) is None


def test_appium_base_candidates_support_root_and_wd_hub():
    assert appium_base_candidates(12345) == (
        "http://127.0.0.1:12345",
        "http://127.0.0.1:12345/wd/hub",
    )


def test_session_source_paths_reject_path_like_session_ids():
    assert session_source_paths("http://127.0.0.1:1", ["ok", "bad/id"]) == (
        "http://127.0.0.1:1/session/ok/source",
    )
