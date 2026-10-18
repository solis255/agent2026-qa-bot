"""Synthetic fixtures, isolated Local stand-ins; no real network fault injection."""
from datetime import datetime, timezone
import json
from pathlib import Path

from netpilot.client_snapshot.validation import parse_snapshot

FIXTURES = Path(__file__).parent / "fixtures"


def payload(name="valid"):
    value = json.loads((FIXTURES / f"client_snapshot_{name}.json").read_text(encoding="utf-8"))
    value["generated_at"] = datetime.now(timezone.utc).isoformat()
    return value


def encoded(value):
    return json.dumps(value, ensure_ascii=False).encode("utf-8")


def upload(client, sid, value, *, filename="snapshot.json", mime="application/json", **kwargs):
    raw = encoded(value) if isinstance(value, dict) else value
    return client.post("/api/session/client-snapshot", data={"session_id":str(sid)}, files={"file":(filename,raw,mime)}, **kwargs)


def import_snapshot(store, sid, owner, value=None, **kwargs):
    snapshot, digest = parse_snapshot(encoded(value or payload()))
    return store.import_client_snapshot(sid, owner, snapshot, digest, **kwargs)
