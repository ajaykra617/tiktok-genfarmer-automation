from genfarmer_automation.android_listener_discovery import (
    extract_ports_from_cmdline,
    parse_proc_net_tcp,
    parse_ss_listeners,
    prioritized_candidate_ports,
)


def test_parse_proc_net_tcp_extracts_listen_ports_only():
    text = """\
  sl  local_address rem_address   st tx_queue rx_queue tr tm->when retrnsmt   uid  timeout inode
   0: 0100007F:1EE8 00000000:0000 0A 00000000:00000000 00:00000000 00000000  2000        0 1
   1: 0100007F:1A86 0100007F:1234 01 00000000:00000000 00:00000000 00000000  2000        0 2
   2: 00000000:2320 00000000:0000 0A 00000000:00000000 00:00000000 00000000  2000        0 3
"""
    assert parse_proc_net_tcp(text) == (7912, 8992)


def test_parse_ss_listeners_handles_ipv4_and_ipv6():
    text = """\
State  Recv-Q Send-Q Local Address:Port Peer Address:Port
LISTEN 0      128    127.0.0.1:7913    0.0.0.0:*
LISTEN 0      50     [::]:9008          [::]:*
"""
    assert parse_ss_listeners(text) == (7913, 9008)


def test_extract_ports_from_helper_cmdline():
    text = "atx-agent server --addr 127.0.0.1:9100 --port=9200"
    assert extract_ports_from_cmdline(text) == (9200, 9100)


def test_prioritized_candidates_prefer_runtime_evidence_and_dedupe():
    assert prioritized_candidate_ports(
        observed=[9008, 7912],
        cmdline_hints=[9100, 9008],
        common_hints=[7912, 6790],
    ) == (9100, 9008, 7912, 6790)
