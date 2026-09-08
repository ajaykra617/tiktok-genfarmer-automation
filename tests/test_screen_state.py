import struct

import pytest

from genfarmer_automation.screen_state import (
    GridPoint,
    ScreenStateError,
    measure_temporal_stability,
    parse_android_raw_screencap,
)


def raw_frame(width, height, rgba, *, header16=False):
    payload = bytes(rgba) * (width * height)
    header = struct.pack("<III", width, height, 1)
    if header16:
        header += struct.pack("<I", 0)
    return header + payload


def test_parse_12_byte_rgba_frame():
    frame = parse_android_raw_screencap(raw_frame(2, 2, (10, 20, 30, 255)))
    assert frame.width == 2
    assert frame.height == 2
    assert frame.rgb_at(1, 1) == (10, 20, 30)


def test_parse_16_byte_rgba_frame():
    frame = parse_android_raw_screencap(raw_frame(1, 1, (1, 2, 3, 255), header16=True))
    assert frame.rgb_at(0, 0) == (1, 2, 3)


def test_rejects_unknown_layout():
    with pytest.raises(ScreenStateError):
        parse_android_raw_screencap(b"x" * 20)


def test_temporal_stability_all_stable():
    frames = [
        parse_android_raw_screencap(raw_frame(2, 2, (10, 20, 30, 255))),
        parse_android_raw_screencap(raw_frame(2, 2, (12, 21, 31, 255))),
    ]
    report = measure_temporal_stability(
        frames,
        points=[GridPoint(0, 0), GridPoint(1, 1)],
        per_point_range_threshold=4,
    )
    assert report.stable_points == 2
    assert report.stable_ratio == 1.0


def test_temporal_stability_detects_dynamic_point():
    a = bytearray(raw_frame(2, 1, (10, 10, 10, 255)))
    b = bytearray(raw_frame(2, 1, (10, 10, 10, 255)))
    # 12-byte header + second pixel starts at byte 16.
    b[16:20] = bytes((200, 200, 200, 255))
    frames = [parse_android_raw_screencap(bytes(a)), parse_android_raw_screencap(bytes(b))]
    report = measure_temporal_stability(
        frames,
        points=[GridPoint(0, 0), GridPoint(1, 0)],
        per_point_range_threshold=8,
    )
    assert report.stable_points == 1
    assert report.stable_ratio == 0.5
