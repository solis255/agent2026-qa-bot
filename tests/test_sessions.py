from __future__ import annotations

import pytest

from netpilot.agent import (
    SessionBusyError,
    SessionCapacityError,
    SessionNotFoundError,
    SessionStore,
)


def test_session_store_creates_isolated_uuid_sessions() -> None:
    store = SessionStore(max_history_messages=20)

    first = store.create()
    second = store.create()

    assert first.session_id != second.session_id
    assert store.history(first.session_id) == []
    assert store.history(second.session_id) == []


def test_session_store_trims_complete_turns_without_orphan_messages() -> None:
    store = SessionStore(max_history_messages=3)
    session = store.create()

    for index in range(3):
        store.begin_turn(session.session_id)
        store.finish_turn(session.session_id, f"问题 {index}", f"回答 {index}")

    history = store.history(session.session_id)
    assert [message.content for message in history] == ["问题 2", "回答 2"]
    assert [message.role.value for message in history] == ["user", "assistant"]


def test_session_store_rejects_a_second_active_turn() -> None:
    store = SessionStore()
    session = store.create()

    store.begin_turn(session.session_id)

    try:
        store.begin_turn(session.session_id)
    except SessionBusyError:
        pass
    else:
        raise AssertionError("second active turn should fail")
    store.abort_turn(session.session_id)
    assert store.get(session.session_id).busy is False


def test_session_store_clear_invalidates_old_sessions() -> None:
    store = SessionStore()
    session = store.create()

    assert store.clear() == 1

    try:
        store.get(session.session_id)
    except SessionNotFoundError:
        pass
    else:
        raise AssertionError("cleared session should not exist")


def test_session_store_evicts_oldest_idle_and_never_evicts_busy() -> None:
    store = SessionStore(max_sessions=2)
    first = store.create()
    second = store.create()
    store.begin_turn(second.session_id)

    third = store.create()

    with pytest.raises(SessionNotFoundError):
        store.get(first.session_id)
    assert store.get(second.session_id).busy is True
    assert store.get(third.session_id).busy is False


def test_session_store_rejects_when_all_slots_are_busy() -> None:
    store = SessionStore(max_sessions=1)
    session = store.create()
    store.begin_turn(session.session_id)

    with pytest.raises(SessionCapacityError):
        store.create()
