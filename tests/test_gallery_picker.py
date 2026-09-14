from genfarmer_automation.gallery_picker import (
    GalleryPickerError,
    duration_label,
    find_unique_duration_tile,
)

PKG = "com.zhiliaoapp.musically"


def _xml(*tiles):
    children = []
    x = 0
    for duration in tiles:
        children.append(
            f'<node package="{PKG}" clickable="true" enabled="true" bounds="[{x},300][{x+300},700]">'
            f'<node package="{PKG}" class="android.widget.TextView" text="{duration}" clickable="false" enabled="true" bounds="[{x+150},620][{x+250},680]" />'
            '</node>'
        )
        x += 300
    return '<hierarchy>' + ''.join(children) + '</hierarchy>'


def test_duration_label():
    assert duration_label(3000) == "00:03"
    assert duration_label(65000) == "01:05"
    assert duration_label(3661000) == "1:01:01"


def test_unique_duration_tile():
    tile = find_unique_duration_tile(_xml("00:03", "00:08"), duration_ms=3000, package=PKG)
    assert tile.center == (150, 500)


def test_duration_tile_ambiguous_fails_closed():
    try:
        find_unique_duration_tile(_xml("00:03", "00:03"), duration_ms=3000, package=PKG)
    except GalleryPickerError as exc:
        assert "ambiguous" in str(exc)
    else:
        raise AssertionError("expected GalleryPickerError")


def test_missing_duration_fails_closed():
    try:
        find_unique_duration_tile(_xml("00:08"), duration_ms=3000, package=PKG)
    except GalleryPickerError as exc:
        assert "not visible" in str(exc)
    else:
        raise AssertionError("expected GalleryPickerError")
