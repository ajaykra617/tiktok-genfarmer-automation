import hashlib

import pytest

from genfarmer_automation.boost_fixture import (
    FIXTURE_SHA256,
    FIXTURE_SIZE,
    fixture_bytes,
    write_fixture,
)


def test_embedded_boost_fixture_integrity():
    data = fixture_bytes()
    assert len(data) == FIXTURE_SIZE
    assert hashlib.sha256(data).hexdigest() == FIXTURE_SHA256
    assert data[4:8] == b"ftyp"
    assert b"avc1" in data
    assert b"moov" in data
    assert b"mdat" in data


def test_write_fixture_refuses_overwrite_by_default(tmp_path):
    target = tmp_path / "boost-test.mp4"
    write_fixture(target)
    assert target.read_bytes() == fixture_bytes()
    with pytest.raises(FileExistsError):
        write_fixture(target)
    write_fixture(target, overwrite=True)
