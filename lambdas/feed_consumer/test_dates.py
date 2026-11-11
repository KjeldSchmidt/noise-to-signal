from datetime import UTC, datetime
from time import struct_time
from types import SimpleNamespace

from main import _entry_published_at


def _st(*parts: int) -> struct_time:
    # year, month, day, hour, min, sec, wday, yday, dst
    y, m, d, hh, mm, ss = parts
    return struct_time((y, m, d, hh, mm, ss, 0, 0, -1))


def test_prefers_published_parsed() -> None:
    entry = SimpleNamespace(
        published_parsed=_st(2024, 1, 2, 3, 4, 5),
        updated_parsed=_st(2025, 6, 7, 8, 9, 10),
    )
    assert _entry_published_at(entry) == datetime(2024, 1, 2, 3, 4, 5, tzinfo=UTC)


def test_falls_back_to_updated_parsed() -> None:
    entry = SimpleNamespace(
        published_parsed=None,
        updated_parsed=_st(2025, 6, 7, 8, 9, 10),
    )
    assert _entry_published_at(entry) == datetime(2025, 6, 7, 8, 9, 10, tzinfo=UTC)


def test_falls_back_to_created_parsed() -> None:
    entry = SimpleNamespace(
        published_parsed=None,
        updated_parsed=None,
        created_parsed=_st(2023, 3, 4, 5, 6, 7),
    )
    assert _entry_published_at(entry) == datetime(2023, 3, 4, 5, 6, 7, tzinfo=UTC)


def test_last_resort_is_now() -> None:
    entry = SimpleNamespace(
        published_parsed=None,
        updated_parsed=None,
        created_parsed=None,
    )
    before = datetime.now(UTC)
    result = _entry_published_at(entry)
    after = datetime.now(UTC)
    assert before <= result <= after
