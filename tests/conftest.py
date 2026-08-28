from __future__ import annotations

import os


"""Keep test collection isolated from the repository's default SQLite file.

``netpilot.main`` constructs its ASGI app during module import, before normal
fixtures run.  Dedicated history tests explicitly enable persistence with a
temporary database path.
"""

os.environ["DIAGNOSIS_HISTORY_ENABLED"] = "false"
