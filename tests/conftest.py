from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import UUID, uuid4

from fastapi.testclient import TestClient


"""Keep test collection isolated from the repository's default SQLite file.

``netpilot.main`` constructs its ASGI app during module import, before normal
fixtures run.  Dedicated history tests explicitly enable persistence with a
temporary database path.
"""

os.environ["DIAGNOSIS_HISTORY_ENABLED"] = "false"

# Keep Auth API fixtures from modifying a developer's default local database.
_test_database_dir = TemporaryDirectory(prefix="netpilot-pytest-")
os.environ["DIAGNOSIS_DB_PATH"] = str(Path(_test_database_dir.name) / "netpilot.db")


def register_test_user(client: TestClient) -> UUID:
    username = f"test_{uuid4().hex[:20]}"
    response = client.post(
        "/api/auth/register",
        json={"username": username, "password": "test-password-123"},
    )
    assert response.status_code == 201, response.text
    return UUID(response.json()["id"])
