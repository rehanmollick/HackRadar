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
# Scoring weights (rev 3.1 — tech discovery, not product ideation)
# ---------------------------------------------------------------------------
# The old 4-criterion rubric (Open/Novelty/Wow/Build) was reframed in rev 3.1
# because it was surfacing product pitches instead of impressive tech. The
# user wins hackathons by finding the TECH first; product ideation is his
# own contribution. See memory/feedback_hackradar_is_tech_discovery.md.
#
# Rev 3.1 rubric:
#   Usability 30% — can I actually build with this TODAY? Strict artifact
#                   calibration: code+weights+demo > code+weights > paper+weights
#                   > paper only > closed API. Pushes pure research papers
#                   below the fold without hard-dropping them.
#   Innovation 35% — is the underlying tech genuinely new/interesting?
#                    Dominant single ranker; Innovation is what matters most
#                    when in doubt on ordering.
#   Underexploited 25% — has nobody built products on this yet? Niche is good.
#   Wow 10% — does the tech itself provoke "wait, what?" (not demo sizzle).
#
# total = U*0.30 + I*0.35 + Un*0.25 + W*0.10
#
# Canonical test cases (see memory):
#   TRIBE v2 (U9 I10 Un10 W10)      = 9.70
#   code+weights no demo            = 9.10
#   paper+weights no code           = 8.20
#   pure research paper             = 7.60
#   closed API                      = 7.30
WEIGHT_USABILITY = 0.30
WEIGHT_INNOVATION = 0.35
WEIGHT_UNDEREXPLOITED = 0.25
WEIGHT_WOW = 0.10
SCORE_THRESHOLD = 6.5

# High-conviction threshold: Usability ≥ 7 AND Innovation ≥ 9 AND
# Underexploited ≥ 8 AND Wow ≥ 7. Pure research papers CANNOT be
# high-conviction regardless of how impressive the idea sounds.
HIGH_CONVICTION_MIN_USABILITY = 7.0
HIGH_CONVICTION_MIN_INNOVATION = 9.0
HIGH_CONVICTION_MIN_UNDEREXPLOITED = 8.0
HIGH_CONVICTION_MIN_WOW = 7.0

# ---------------------------------------------------------------------------
# Prompt versioning for score cache keying
# ---------------------------------------------------------------------------
# Bump this MANUALLY whenever prompts.py is edited in a way that changes
# scoring behavior (rubric wording, calibration, schema). See memory
# feedback_prompt_version_bump.md. The score cache is keyed on
# (content_hash, prompt_version) so stale cached scores don't mask broken
# prompt changes.
PROMPT_VERSION = "v2"

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
PASS1_TRIAGE_THRESHOLD = float(os.environ.get("PASS1_TRIAGE_THRESHOLD", "6.5"))
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
#
# IMPORTANT: These strings must exactly match the `_SOURCE` constants
# emitted by each scraper in hackradar/sources/*.py. The scrapers use
# human-readable labels ("Meta AI Blog"), NOT slugs ("meta_ai_blog").
# A bug from earlier used slugs here and the bypass silently never fired.
HIGH_TRUST_SOURCES = set(
    s.strip()
    for s in os.environ.get(
        "HIGH_TRUST_SOURCES",
        "Meta AI Blog,Google DeepMind Blog,Google Research Blog,"
        "Microsoft Research Blog,Apple ML Research,Stability AI Blog,"
        "Mistral Blog,NVIDIA Developer Blog,Anthropic Research,"
        "OpenAI Research,GitHub Research Orgs,HuggingFace Papers",
    ).split(",")
)

# Map high-trust source labels to their parent research org. Used to feed
# `owner_org` into Pass 2 so the LLM has something to ground Innovation
# and Underexploited scoring on ("is this from a known lab?").
SOURCE_TO_ORG: dict[str, str] = {
    "Meta AI Blog": "Meta FAIR",
    "Google DeepMind Blog": "Google DeepMind",
    "Google Research Blog": "Google Research",
    "Microsoft Research Blog": "Microsoft Research",
    "Apple ML Research": "Apple ML Research",
    "Stability AI Blog": "Stability AI",
    "Mistral Blog": "Mistral AI",
    "NVIDIA Developer Blog": "NVIDIA",
    "Anthropic Research": "Anthropic",
    "OpenAI Research": "OpenAI",
    "GitHub Research Orgs": "research lab GitHub org",
    "HuggingFace Papers": "HF Daily Papers (curated)",
}

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
