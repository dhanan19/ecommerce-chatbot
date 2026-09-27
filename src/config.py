"""
Configuration and environment loading for the e-commerce support agent.

Every credential (OpenAI key, Gmail settings) is read from the environment /
.env file — nothing is hard-coded, per the project's non-functional
requirements.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from the project root regardless of current working directory.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")

# --- Core paths -------------------------------------------------------
DB_PATH = Path(os.environ.get("ECOMMERCE_DB_PATH", PROJECT_ROOT / "ecommerce.db"))
CHECKPOINTS_DB_PATH = Path(
    os.environ.get("CHECKPOINTS_DB_PATH", PROJECT_ROOT / "checkpoints.sqlite")
)
CHROMA_DIR = Path(os.environ.get("CHROMA_DIR", PROJECT_ROOT / "chroma_db"))
POLICY_DIR = Path(os.environ.get("POLICY_DIR", PROJECT_ROOT / "policies"))
LOG_DIR = Path(os.environ.get("LOG_DIR", PROJECT_ROOT / "logs"))
LOG_FILE = LOG_DIR / "app.log"

# --- LLM ---------------------------------------------------------------
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
CHAT_MODEL = os.environ.get("CHAT_MODEL", "gpt-4o-mini")
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "text-embedding-3-small")

# --- Gmail ---------------------------------------------------------------
# Gmail sending is entirely optional. If GMAIL_ENABLED is not "true", or the
# OAuth token/credentials are missing, the notification tool falls back to a
# simulated send: it still writes a row to email_logs (so the rest of the
# app behaves identically) but does not call the real Gmail API. This keeps
# the project runnable end-to-end without requiring every student to set up
# Google Cloud OAuth.
GMAIL_ENABLED = os.environ.get("GMAIL_ENABLED", "false").lower() == "true"
GMAIL_CREDENTIALS_PATH = os.environ.get("GMAIL_CREDENTIALS_PATH", str(PROJECT_ROOT / "credentials.json"))
GMAIL_TOKEN_PATH = os.environ.get("GMAIL_TOKEN_PATH", str(PROJECT_ROOT / "token.json"))
GMAIL_SENDER = os.environ.get("GMAIL_SENDER", "")

# --- Business rules ------------------------------------------------------
CANCELLABLE_STATUSES = {"PLACED", "SHIPPED"}
RETURN_WINDOW_DAYS = 30

LOG_DIR.mkdir(parents=True, exist_ok=True)
