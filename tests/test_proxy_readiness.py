import pytest

from genfarmer_automation.proxy_readiness import (
    ProxyReadinessError,
    extract_external_ip,
    parse_http_proxy,
)


def test_parse_http_proxy_requires_host_and_port():
    endpoint = parse_http_proxy("http://proxy.example:4001")
    assert endpoint.host == "proxy.example"
    assert endpoint.port == 4001


@pytest.mark.parametrize("value", ["socks5://proxy.example:5001", "http://proxy.example", "proxy.example:4001"])
def test_parse_http_proxy_rejects_unsupported_or_incomplete(value):
    with pytest.raises(ProxyReadinessError):
        parse_http_proxy(value)


def test_extract_external_ip_accepts_plain_and_json():
    assert extract_external_ip("203.0.113.7") == "203.0.113.7"
    assert extract_external_ip('{"ip":"2001:db8::7"}') == "2001:db8::7"


def test_extract_external_ip_accepts_first_parseable_origin_member():
    assert extract_external_ip('{"origin":"203.0.113.9, 198.51.100.2"}') == "203.0.113.9"


def test_extract_external_ip_rejects_non_ip_response():
    with pytest.raises(ProxyReadinessError, match="parseable IP"):
        extract_external_ip("CONNECT_INTERNET_ERROR")
