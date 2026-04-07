import os


# API Keys
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")

# Email
EMAIL_ADDRESS = os.environ.get("EMAIL_ADDRESS", "")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD", "")
SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
EMAIL_TO = os.environ.get("EMAIL_TO", EMAIL_ADDRESS)

# Scoring weights
WEIGHT_OPEN = 0.20
WEIGHT_NOVELTY = 0.35
WEIGHT_WOW = 0.25
WEIGHT_BUILD = 0.20

# Scoring threshold for full hackathon idea writeup
SCORE_THRESHOLD = 6.5

# Pipeline settings
LOOKBACK_HOURS = 48
BATCH_SIZE = 8
TOP_N = 15
REQUEST_TIMEOUT = 30

# Dedup
FUZZY_MATCH_THRESHOLD = 85

# arXiv keyword pre-filter
ARXIV_KEYWORDS = [
    "model", "framework", "tool", "dataset", "benchmark",
    "open-source", "demo", "api", "real-time", "interactive", "novel",
]

ARXIV_CATEGORIES = [
    "cs.AI", "cs.CV", "cs.CL", "cs.HC", "cs.NE", "cs.SD",
    "cs.RO", "cs.GR", "cs.MM", "q-bio", "eess.AS", "eess.SP", "stat.ML",
]

# GitHub research orgs to watch
GITHUB_ORGS = [
    "facebookresearch", "google-deepmind", "google-research",
    "microsoft", "apple", "stability-ai", "mistralai",
    "deepseek-ai", "QwenLM", "NVIDIA", "huggingface", "openai",
]

# HuggingFace model filter: minimum downloads in first 48h
HF_MIN_DOWNLOADS = 10
