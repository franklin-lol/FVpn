"""Test-only environment: never load a real installation or start its services."""

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("JWT_SECRET", "fixture-only-secret-at-least-thirty-two-bytes")
os.environ.setdefault("MASTER_PASSWORD", "fixture-only-password")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:////tmp/fvpn-tests.db")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

# Settings resolves .env relative to cwd. A synthetic directory prevents even
# probing a developer's environment file when tests import the application.
_TEST_CWD = tempfile.TemporaryDirectory(prefix="fvpn-tests-")
os.chdir(_TEST_CWD.name)

