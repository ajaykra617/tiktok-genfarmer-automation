from pathlib import Path

import pytest

from genfarmer_automation.boost_media import (
    BoostMediaError,
    already_published,
    media_spec,
    parse_content_query,
)


def test_media_spec_uses_hash_based_remote_name(tmp_path: Path):
    path = tmp_path / "clip.mp4"
    path.write_bytes(b"video-bytes")
    spec = media_spec(path)
    assert spec.media_kind == "video"
    assert spec.mime_type == "video/mp4"
    assert spec.remote_name.startswith("gfboost-")
    assert spec.remote_path.endswith(spec.remote_name)


def test_media_spec_rejects_unknown_extension(tmp_path: Path):
    path = tmp_path / "clip.exe"
    path.write_bytes(b"x")
    with pytest.raises(BoostMediaError):
        media_spec(path)


def test_parse_content_query_finds_exact_row():
    text = (
        "Row: 0 _id=41, _display_name=other.mp4\n"
        "Row: 1 _id=52, _display_name=gfboost-abc.mp4\n"
    )
    assert parse_content_query(text, display_name="gfboost-abc.mp4") == "52"


def test_parse_content_query_rejects_duplicate_rows():
    text = (
        "Row: 0 _id=52, _display_name=gfboost-abc.mp4\n"
        "Row: 1 _id=53, _display_name=gfboost-abc.mp4\n"
    )
    with pytest.raises(BoostMediaError):
        parse_content_query(text, display_name="gfboost-abc.mp4")


def test_already_published_is_exact_hash_status():
    history = {"items": {"abc": {"status": "published"}, "def": {"status": "failed"}}}
    assert already_published(history, "abc")
    assert not already_published(history, "def")
    assert not already_published(history, "missing")
