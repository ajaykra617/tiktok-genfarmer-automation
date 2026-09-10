import pytest

from genfarmer_automation.atx_bridge import (
    AtxBridgeError,
    atx_base_url,
    extract_atx_hierarchy_xml,
    extract_atx_version,
)


def test_atx_base_url_validates_port():
    assert atx_base_url(12345) == "http://127.0.0.1:12345"
    with pytest.raises(AtxBridgeError):
        atx_base_url(0)
    with pytest.raises(AtxBridgeError):
        atx_base_url(True)


def test_extract_atx_version_from_plain_text_and_envelope():
    assert extract_atx_version("0.10.0") == "0.10.0"
    assert extract_atx_version({"version": "0.9.5"}) == "0.9.5"
    assert extract_atx_version({"value": "v1"}) == "v1"


def test_extract_atx_hierarchy_from_jsonrpc_result():
    xml = '<hierarchy rotation="0"><node class="x" /></hierarchy>'
    assert extract_atx_hierarchy_xml({"jsonrpc": "2.0", "id": 1, "result": xml}) == xml


def test_extract_atx_hierarchy_from_raw_xml():
    xml = '<hierarchy rotation="0"><node class="x" /></hierarchy>'
    assert extract_atx_hierarchy_xml(xml) == xml


def test_extract_atx_hierarchy_rejects_non_xml_payload():
    assert extract_atx_hierarchy_xml({"result": "not xml"}) is None
