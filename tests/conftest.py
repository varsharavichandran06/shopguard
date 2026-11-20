import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["GUARDRAIL_LLM"] = "off"          # no model calls in tests
os.environ["OPENAI_AGENTS_DISABLE_TRACING"] = "1"
os.environ.setdefault("OPENAI_API_KEY", "test-key-not-used")


@pytest.fixture(scope="session", autouse=True)
def seeded_store():
    from agents import set_tracing_disabled

    set_tracing_disabled(True)
    from data.seed import seed

    return seed()


@pytest.fixture
def db(tmp_path, seeded_store):
    from shopguard.db import fresh_copy, open_db

    conn = open_db(fresh_copy(seeded_store, tmp_path / "store.db"))
    yield conn
    conn.close()
