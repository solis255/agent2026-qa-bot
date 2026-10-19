import json
import sqlite3
from uuid import uuid4
from privacy_helpers import response
from netpilot.history import SQLiteDiagnosisRepository


def test_new_history_database_and_index_columns_are_persist_safe(tmp_path):
    repository = SQLiteDiagnosisRepository(tmp_path / "privacy.db")
    owner = uuid4()
    record = repository.upsert_session(owner, "我的 token=history-secret，还是不通", response("password=answer-secret DNS 172.23.0.1"))
    assert "history-secret" not in record.model_dump_json()
    with sqlite3.connect(repository.path) as connection:
        row = connection.execute("SELECT user_message,latest_user_message,answer_preview,snapshot_json FROM diagnosis_records").fetchone()
    assert "history-secret" not in str(row) and "answer-secret" not in str(row)
    assert "172.23.0.1" in str(row)
    assert repository.get(owner, record.record_id) == record


def test_legacy_read_and_list_safety_do_not_rewrite_database(tmp_path):
    repository = SQLiteDiagnosisRepository(tmp_path / "legacy.db")
    owner = uuid4(); record = repository.upsert_session(owner, "问题", response())
    with sqlite3.connect(repository.path) as connection:
        payload = json.loads(connection.execute("SELECT snapshot_json FROM diagnosis_records").fetchone()[0])
        payload["answer"] = "token=legacy-answer-secret"
        raw = json.dumps(payload)
        connection.execute("UPDATE diagnosis_records SET snapshot_json=?,user_message=?,latest_user_message=?,answer_preview=?", (raw, "password=legacy-user-secret", "password=legacy-user-secret", "token=legacy-answer-secret"))
    assert "legacy-user-secret" not in repository.get(owner, record.record_id).model_dump_json()
    assert "legacy-answer-secret" not in repository.list(owner).model_dump_json()
    with sqlite3.connect(repository.path) as connection:
        assert connection.execute("SELECT snapshot_json FROM diagnosis_records").fetchone()[0] == raw
