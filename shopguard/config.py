"""Central settings. Every value can be overridden with an environment variable."""
import os
from pathlib import Path

try:  # load .env if python-dotenv is installed
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
SCHEMA_PATH = DATA_DIR / "schema.sql"
POLICY_DIR = DATA_DIR / "policy"
STORE_DB = Path(os.environ.get("STORE_DB", DATA_DIR / "store.db"))
POLICY_INDEX = DATA_DIR / "policy_index.json"
TMP_DIR = ROOT / "tmp"
RUNS_DIR = ROOT / "runs"
TASKS_DIR = ROOT / "sim" / "tasks"
RELEASE_DIR = ROOT / "release"

# The store's fixed clock. Rules never read the real date.
STORE_TODAY = "2026-11-01"

# Models. Agent and judge are different on purpose: a model should not grade itself.
AGENT_MODEL = os.environ.get("AGENT_MODEL", "gpt-5-mini")
AGENT_REASONING = os.environ.get("AGENT_REASONING", "low")  # only used for reasoning models
USER_MODEL = os.environ.get("USER_MODEL", "gpt-4.1-mini")
JUDGE_MODEL = os.environ.get("JUDGE_MODEL", "gpt-4.1-mini")
GUARD_MODEL = os.environ.get("GUARD_MODEL", "gpt-4.1-nano")
EMBED_MODEL = os.environ.get("EMBED_MODEL", "text-embedding-3-small")

# Rough prices in USD per 1M tokens, used only for the cost column in reports.
# Check https://openai.com/api/pricing/ and update if you change models.
PRICES = {
    "gpt-5-mini": (0.25, 2.00),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1-nano": (0.10, 0.40),
}

MAX_TURNS = int(os.environ.get("MAX_TURNS", "20"))


def is_reasoning_model(model: str) -> bool:
    return model.startswith(("gpt-5", "o1", "o3", "o4"))


def cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    pin, pout = PRICES.get(model, (0.0, 0.0))
    return (input_tokens * pin + output_tokens * pout) / 1_000_000
