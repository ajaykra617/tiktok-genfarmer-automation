from datetime import datetime, timedelta, timezone
import json

from genfarmer_automation.boost_prepare import (
    BoostPrepareError,
    PreparationLeaseStore,
    choose_and_reserve_media,
    discover_approved_media,
    pending_media,
)


def _media(tmp_path, name, data=b"fixture"):
    path = tmp_path / name
    path.write_bytes(data)
    return path


def test_discover_media_expands_directory_and_ignores_unsupported(tmp_path):
    _media(tmp_path, "b.mp4", b"b")
    _media(tmp_path, "a.jpg", b"a")
    _media(tmp_path, "notes.txt", b"x")
    specs = discover_approved_media([tmp_path])
    assert [spec.local_path.name for spec in specs] == ["a.jpg", "b.mp4"]


def test_discover_missing_path_fails_closed(tmp_path):
    try:
        discover_approved_media([tmp_path / "missing"])
    except BoostPrepareError as exc:
        assert "does not exist" in str(exc)
    else:
        raise AssertionError("expected BoostPrepareError")


def test_pending_media_excludes_published_hash(tmp_path):
    specs = discover_approved_media([_media(tmp_path, "one.mp4")])
    history = {"version": 1, "items": {specs[0].sha256: {"status": "published"}}}
    assert pending_media(specs, history) == ()


def test_atomic_reservation_blocks_second_device(tmp_path):
    spec = discover_approved_media([_media(tmp_path, "one.mp4")])[0]
    store = PreparationLeaseStore(tmp_path / "leases")
    first = store.reserve(spec.sha256, device="d1", account_key="a1", ttl_seconds=60)
    second = store.reserve(spec.sha256, device="d2", account_key="a2", ttl_seconds=60)
    assert first is not None
    assert second is None
    assert store.is_active(spec.sha256)


def test_expired_reservation_can_be_reclaimed(tmp_path):
    spec = discover_approved_media([_media(tmp_path, "one.mp4")])[0]
    store = PreparationLeaseStore(tmp_path / "leases")
    now = datetime(2026, 9, 15, tzinfo=timezone.utc)
    first = store.reserve(spec.sha256, device="d1", account_key="a1", ttl_seconds=1, now=now)
    assert first is not None
    second = store.reserve(
        spec.sha256,
        device="d2",
        account_key="a2",
        ttl_seconds=60,
        now=now + timedelta(seconds=2),
    )
    assert second is not None
    payload = json.loads(second.read_text(encoding="utf-8"))
    assert payload["device"] == "d2"


def test_malformed_existing_lease_fails_closed(tmp_path):
    spec = discover_approved_media([_media(tmp_path, "one.mp4")])[0]
    store = PreparationLeaseStore(tmp_path / "leases")
    store.root.mkdir(parents=True)
    store.lease_path(spec.sha256).write_text("not-json", encoding="utf-8")
    assert store.is_active(spec.sha256)
    assert store.reserve(spec.sha256, device="d1", account_key="a1", ttl_seconds=60) is None


def test_choose_and_reserve_skips_busy_hash(tmp_path):
    first_path = _media(tmp_path, "a.mp4", b"a")
    second_path = _media(tmp_path, "b.mp4", b"b")
    specs = discover_approved_media([tmp_path])
    assert specs[0].local_path == first_path.resolve()
    assert specs[1].local_path == second_path.resolve()
    store = PreparationLeaseStore(tmp_path / "leases")
    assert store.reserve(specs[0].sha256, device="busy", account_key="busy", ttl_seconds=60)
    chosen = choose_and_reserve_media(
        specs,
        {"version": 1, "items": {}},
        store,
        device="d2",
        account_key="a2",
        ttl_seconds=60,
    )
    assert chosen.spec.sha256 == specs[1].sha256
    assert chosen.lease_path is not None
