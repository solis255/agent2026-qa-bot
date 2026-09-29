from __future__ import annotations

import pytest
from uuid import uuid4

from netpilot.agent import (
    SessionBusyError,
    SessionCapacityError,
    SessionNotFoundError,
    SessionStore,
)


OWNER = uuid4()


def test_session_store_creates_isolated_uuid_sessions() -> None:
    store = SessionStore(max_history_messages=20)

    first = store.create(OWNER)
    second = store.create(OWNER)

    assert first.session_id != second.session_id
    assert store.history(first.session_id, OWNER) == []
    assert store.history(second.session_id, OWNER) == []


def test_session_store_trims_complete_turns_without_orphan_messages() -> None:
    store = SessionStore(max_history_messages=3)
    session = store.create(OWNER)

    for index in range(3):
        store.begin_turn(session.session_id, OWNER)
        store.finish_turn(session.session_id, f"问题 {index}", f"回答 {index}")

    history = store.history(session.session_id, OWNER)
    assert [message.content for message in history] == ["问题 2", "回答 2"]
    assert [message.role.value for message in history] == ["user", "assistant"]


def test_session_store_rejects_a_second_active_turn() -> None:
    store = SessionStore()
    session = store.create(OWNER)

    store.begin_turn(session.session_id, OWNER)

    try:
        store.begin_turn(session.session_id, OWNER)
    except SessionBusyError:
        pass
    else:
        raise AssertionError("second active turn should fail")
    store.abort_turn(session.session_id)
    assert store.get(session.session_id, OWNER).busy is False


def test_session_store_clear_invalidates_old_sessions() -> None:
    store = SessionStore()
    session = store.create(OWNER)

    assert store.clear() == 1

    try:
        store.get(session.session_id, OWNER)
    except SessionNotFoundError:
        pass
    else:
        raise AssertionError("cleared session should not exist")


def test_session_store_evicts_oldest_idle_and_never_evicts_busy() -> None:
    store = SessionStore(max_sessions=2)
    first = store.create(OWNER)
    second = store.create(OWNER)
    store.begin_turn(second.session_id, OWNER)

    third = store.create(OWNER)

    with pytest.raises(SessionNotFoundError):
        store.get(first.session_id, OWNER)
    assert store.get(second.session_id, OWNER).busy is True
    assert store.get(third.session_id, OWNER).busy is False


def test_session_store_rejects_when_all_slots_are_busy() -> None:
    store = SessionStore(max_sessions=1)
    session = store.create(OWNER)
    store.begin_turn(session.session_id, OWNER)

    with pytest.raises(SessionCapacityError):
        store.create(OWNER)


def test_session_store_rejects_other_owner_without_marking_busy() -> None:
    store = SessionStore()
    session = store.create(OWNER)
    other = uuid4()
    with pytest.raises(SessionNotFoundError):
        store.get(session.session_id, other)
    with pytest.raises(SessionNotFoundError):
        store.history(session.session_id, other)
    with pytest.raises(SessionNotFoundError):
        store.begin_turn(session.session_id, other)
    assert store.get(session.session_id, OWNER).busy is False
