"""Conservative screen-state sampling for false-success diagnostics.

This module does not decide that a TikTok action succeeded. It only measures
how much of the current screen is visually stable across a short time window so
we can determine whether screenshot-derived evidence is strong enough to be a
useful *secondary* postcondition signal.

The implementation uses raw ``adb exec-out screencap`` frames and only the
Python standard library. It deliberately fails closed on unsupported frame
formats instead of guessing channel layouts.
"""

from __future__ import annotations

from dataclasses import dataclass
import struct
from typing import Iterable, Sequence


class ScreenStateError(RuntimeError):
    pass


@dataclass(frozen=True)
class RawScreenFrame:
    width: int
    height: int
    pixel_format: int
    pixels: bytes
    bytes_per_pixel: int = 4

    def rgb_at(self, x: int, y: int) -> tuple[int, int, int]:
        if not (0 <= x < self.width and 0 <= y < self.height):
            raise IndexError((x, y))
        offset = (y * self.width + x) * self.bytes_per_pixel
        # Android PIXEL_FORMAT_RGBA_8888 == 1 for the qualified lab device.
        if self.pixel_format != 1:
            raise ScreenStateError(f"unsupported Android pixel format {self.pixel_format}")
        r, g, b = self.pixels[offset : offset + 3]
        return int(r), int(g), int(b)


def parse_android_raw_screencap(raw: bytes) -> RawScreenFrame:
    """Parse common Android raw screencap output.

    AOSP variants in the field use either a 12-byte header
    ``width,height,pixel_format`` or a 16-byte header that additionally contains
    dataspace. We accept either only when the remaining payload size exactly
    matches an RGBA_8888 frame.
    """
    if len(raw) < 12:
        raise ScreenStateError("raw screencap is too short")
    width, height, pixel_format = struct.unpack_from("<III", raw, 0)
    if width <= 0 or height <= 0 or width > 10000 or height > 10000:
        raise ScreenStateError(f"invalid raw screencap dimensions {width}x{height}")
    if pixel_format != 1:
        raise ScreenStateError(f"unsupported Android pixel format {pixel_format}")

    payload_size = width * height * 4
    header_size = len(raw) - payload_size
    if header_size not in {12, 16}:
        raise ScreenStateError(
            f"unsupported raw screencap layout: total={len(raw)} expected payload={payload_size} header={header_size}"
        )
    pixels = raw[header_size:]
    if len(pixels) != payload_size:
        raise ScreenStateError("raw screencap payload length mismatch")
    return RawScreenFrame(width, height, pixel_format, pixels)


@dataclass(frozen=True)
class GridPoint:
    x: int
    y: int


@dataclass(frozen=True)
class StabilityReport:
    total_points: int
    stable_points: int
    stable_ratio: float
    per_point_range_threshold: int


def sampling_grid(
    width: int,
    height: int,
    *,
    columns: int = 24,
    rows: int = 36,
    left_fraction: float = 0.05,
    right_fraction: float = 0.90,
    top_fraction: float = 0.08,
    bottom_fraction: float = 0.90,
) -> list[GridPoint]:
    """Return a deterministic interior grid.

    We avoid the extreme screen edges/status/navigation bars and the far-right
    TikTok action rail. These bounds are generic screen fractions, not tap
    coordinates, and are used only for passive image sampling.
    """
    if width <= 0 or height <= 0 or columns < 2 or rows < 2:
        raise ValueError("invalid sampling grid dimensions")
    if not (0 <= left_fraction < right_fraction <= 1):
        raise ValueError("invalid horizontal fractions")
    if not (0 <= top_fraction < bottom_fraction <= 1):
        raise ValueError("invalid vertical fractions")

    x0 = int(width * left_fraction)
    x1 = max(x0 + 1, int(width * right_fraction) - 1)
    y0 = int(height * top_fraction)
    y1 = max(y0 + 1, int(height * bottom_fraction) - 1)

    points: list[GridPoint] = []
    for row in range(rows):
        y = round(y0 + (y1 - y0) * row / (rows - 1))
        for col in range(columns):
            x = round(x0 + (x1 - x0) * col / (columns - 1))
            points.append(GridPoint(x, y))
    return points


def _channel_range(values: Sequence[tuple[int, int, int]]) -> int:
    ranges = [max(v[i] for v in values) - min(v[i] for v in values) for i in range(3)]
    return max(ranges)


def measure_temporal_stability(
    frames: Sequence[RawScreenFrame],
    *,
    points: Iterable[GridPoint] | None = None,
    per_point_range_threshold: int = 16,
) -> StabilityReport:
    if len(frames) < 2:
        raise ValueError("at least two frames are required")
    first = frames[0]
    if any((f.width, f.height, f.pixel_format) != (first.width, first.height, first.pixel_format) for f in frames):
        raise ScreenStateError("screen geometry/pixel format changed during sampling")
    if not (0 <= per_point_range_threshold <= 255):
        raise ValueError("per_point_range_threshold must be 0..255")

    sample_points = list(points or sampling_grid(first.width, first.height))
    stable = 0
    for point in sample_points:
        colors = [frame.rgb_at(point.x, point.y) for frame in frames]
        if _channel_range(colors) <= per_point_range_threshold:
            stable += 1
    total = len(sample_points)
    return StabilityReport(
        total_points=total,
        stable_points=stable,
        stable_ratio=(stable / total) if total else 0.0,
        per_point_range_threshold=per_point_range_threshold,
    )
