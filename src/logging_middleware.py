"""
Logging and observability middleware.

Implemented as a LangChain `BaseCallbackHandler`, attached to every agent
invocation via the `callbacks` config — not as ad-hoc decorators. Every tool
call (SQL toolkit, rag_policy_search, send_gmail_notification, action tools)
and every agent run passes through this handler automatically, since
LangChain propagates callbacks to all nested runnables and tools.

Logs go to logs/app.log via Python's standard logging module.
"""

import logging
import time
import traceback
from typing import Any, Dict, Optional
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler

from src.config import LOG_FILE

logger = logging.getLogger("ecommerce_agent")
logger.setLevel(logging.INFO)
if not logger.handlers:
    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
    )
    logger.addHandler(file_handler)


def _truncate(value: Any, limit: int = 200) -> str:
    text = str(value)
    return text if len(text) <= limit else text[:limit] + "..."


def _full_traceback(error: BaseException) -> str:
    return "".join(traceback.format_exception(type(error), error, error.__traceback__))


class AgentObservabilityHandler(BaseCallbackHandler):
    """Logs timestamp, user_email, tool/action name, input summary, and
    success/failure for every tool and chain run."""

    def __init__(self, user_email: Optional[str] = None):
        super().__init__()
        self.user_email = user_email or "unknown"
        self._start_times: Dict[UUID, float] = {}

    # --- Tools -----------------------------------------------------------
    def on_tool_start(self, serialized: Dict[str, Any], input_str: str, *, run_id: UUID, **kwargs: Any) -> None:
        self._start_times[run_id] = time.time()
        tool_name = serialized.get("name", "unknown_tool")
        logger.info(
            "TOOL_START user=%s tool=%s input=%s",
            self.user_email, tool_name, _truncate(input_str),
        )

    def on_tool_end(self, output: Any, *, run_id: UUID, **kwargs: Any) -> None:
        elapsed = time.time() - self._start_times.pop(run_id, time.time())
        logger.info(
            "TOOL_END user=%s duration=%.2fs output=%s",
            self.user_email, elapsed, _truncate(output),
        )

    def on_tool_error(self, error: BaseException, *, run_id: UUID, **kwargs: Any) -> None:
        self._start_times.pop(run_id, None)
        logger.error("TOOL_ERROR user=%s error=%s\n%s", self.user_email, _truncate(error), _full_traceback(error))

    # --- Agent / chain runs ------------------------------------------------
    def on_chain_start(self, serialized: Dict[str, Any], inputs: Dict[str, Any], *, run_id: UUID, **kwargs: Any) -> None:
        self._start_times[run_id] = time.time()

    def on_chain_end(self, outputs: Dict[str, Any], *, run_id: UUID, **kwargs: Any) -> None:
        self._start_times.pop(run_id, None)

    def on_chain_error(self, error: BaseException, *, run_id: UUID, **kwargs: Any) -> None:
        self._start_times.pop(run_id, None)
        logger.error("AGENT_ERROR user=%s error=%s\n%s", self.user_email, _truncate(error), _full_traceback(error))

    # --- LLM calls (lightweight, just success/failure) ----------------------
    def on_llm_error(self, error: BaseException, *, run_id: UUID, **kwargs: Any) -> None:
        logger.error("LLM_ERROR user=%s error=%s\n%s", self.user_email, _truncate(error), _full_traceback(error))


def log_event(user_email: str, action: str, summary: str, success: bool = True) -> None:
    """Manual log hook for events outside the callback lifecycle (e.g. a
    business-rule rejection inside a tool, before any interrupt/resume)."""
    level = logger.info if success else logger.warning
    level("EVENT user=%s action=%s summary=%s success=%s", user_email, action, _truncate(summary), success)
