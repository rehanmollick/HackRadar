"""HackRadar V2 configuration.

All LLM provider knobs are env-driven so tuning doesn't need code changes.
V1 Gemini + email config removed.
"""

import os
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

# ---------------------------------------------------------------------------
# API keys
# ---------------------------------------------------------------------------
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
CEREBRAS_API_KEY = os.environ.get("CEREBRAS_API_KEY", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
HF_TOKEN = os.environ.get("HF_TOKEN", "")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")

REQUIRED_KEYS = {
    "GROQ_API_KEY": GROQ_API_KEY,
    "CEREBRAS_API_KEY": CEREBRAS_API_KEY,
    "ANTHROPIC_API_KEY": ANTHROPIC_API_KEY,
}


def validate_keys() -> list[str]:
    """Return names of any required keys that are missing. Empty list = OK."""
    return [name for name, value in REQUIRED_KEYS.items() if not value]


# ---------------------------------------------------------------------------
# Scoring weights (unchanged from V1)
# ---------------------------------------------------------------------------
WEIGHT_OPEN = 0.20
WEIGHT_NOVELTY = 0.35
WEIGHT_WOW = 0.25
WEIGHT_BUILD = 0.20
SCORE_THRESHOLD = 6.5

# ---------------------------------------------------------------------------
# Pipeline settings
# ---------------------------------------------------------------------------
LOOKBACK_HOURS = int(os.environ.get("LOOKBACK_HOURS", "48"))
TOP_N = int(os.environ.get("TOP_N", "20"))
REQUEST_TIMEOUT = int(os.environ.get("REQUEST_TIMEOUT", "30"))
FUZZY_MATCH_THRESHOLD = 85

# ---------------------------------------------------------------------------
# V2 multi-pass scoring
# ---------------------------------------------------------------------------
# Pass 1 = cheap triage filter. Primary provider is Cerebras llama3.1-8b
# (60K TPM, vs Groq's 6K TPM on the same base model). Groq kept as soft
# fallback, OpenRouter as outer ring.
PASS1_PROVIDER = os.environ.get("PASS1_PROVIDER", "cerebras")
PASS1_MODEL = os.environ.get("PASS1_MODEL", "llama-3.1-8b-instant")  # Groq id
PASS1_CEREBRAS_MODEL = os.environ.get("PASS1_CEREBRAS_MODEL", "llama3.1-8b")
PASS1_OPENROUTER_MODEL = os.environ.get(
    "PASS1_OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct:free"
)
PASS1_BATCH_SIZE = int(os.environ.get("PASS1_BATCH_SIZE", "10"))
PASS1_TRIAGE_THRESHOLD = float(os.environ.get("PASS1_TRIAGE_THRESHOLD", "5.0"))
# Cerebras llama3.1-8b is 60K TPM + 30 RPM. 8s per batch of 10 = ~7 RPM
# and ~40K TPM — comfortably under both limits with headroom for variance.
PASS1_INTER_BATCH_SLEEP_S = float(os.environ.get("PASS1_INTER_BATCH_SLEEP_S", "8.0"))

# Pass 2 = full 4-criterion scoring. Cerebras qwen-3-235b primary.
PASS2_PROVIDER = os.environ.get("PASS2_PROVIDER", "cerebras")
PASS2_MODEL = os.environ.get("PASS2_MODEL", "qwen-3-235b-a22b-instruct-2507")
PASS2_OPENROUTER_MODEL = os.environ.get(
    "PASS2_OPENROUTER_MODEL", "openai/gpt-oss-120b:free"
)
# Cerebras qwen-3-235b free tier is 30K TPM + 30 RPM. With ~3K tok/item,
# a batch of 4 is ~12K tokens; pacing 25s/batch keeps avg under ~30K TPM
# AND under 30 RPM. If a batch still 429s, the coordinator falls through
# to OpenRouter automatically for that batch.
PASS2_BATCH_SIZE = int(os.environ.get("PASS2_BATCH_SIZE", "4"))
PASS2_INTER_BATCH_SLEEP_S = float(os.environ.get("PASS2_INTER_BATCH_SLEEP_S", "25.0"))

PASS3_PROVIDER = os.environ.get("PASS3_PROVIDER", "anthropic")
PASS3_MODEL = os.environ.get("PASS3_MODEL", "claude-opus-4-6")
PASS3_RATE_LIMIT_PER_HOUR = int(os.environ.get("PASS3_RATE_LIMIT_PER_HOUR", "20"))

# Items from these sources bypass the Pass 1 triage filter entirely.
# Protects TRIBE-v2-type drops from being dropped by an 8B triage model.
HIGH_TRUST_SOURCES = set(
    os.environ.get(
        "HIGH_TRUST_SOURCES",
        "meta_ai_blog,deepmind_blog,google_research_blog,microsoft_research_blog,"
        "apple_ml_blog,stability_ai_blog,mistral_blog,nvidia_blog,"
        "anthropic_research,openai_research,github_research_orgs,huggingface_papers",
    ).split(",")
)

# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------
DB_PATH = Path(os.environ.get("HACKRADAR_DB", "~/.hackradar/hackradar.db")).expanduser()

# ---------------------------------------------------------------------------
# arXiv pre-filter (unchanged)
# ---------------------------------------------------------------------------
ARXIV_KEYWORDS = [
    "model", "framework", "tool", "dataset", "benchmark",
    "open-source", "demo", "api", "real-time", "interactive", "novel",
]

ARXIV_CATEGORIES = [
    "cs.AI", "cs.CV", "cs.CL", "cs.HC", "cs.NE", "cs.SD",
    "cs.RO", "cs.GR", "cs.MM", "q-bio", "eess.AS", "eess.SP", "stat.ML",
]

GITHUB_ORGS = [
    "facebookresearch", "google-deepmind", "google-research",
    "microsoft", "apple", "stability-ai", "mistralai",
    "deepseek-ai", "QwenLM", "NVIDIA", "huggingface", "openai",
]

HF_MIN_DOWNLOADS = 10
