"""
The single main conversational agent.

Everything funnels through one LangGraph ReAct agent:
  - SQLDatabaseToolkit tools for orders/order_items/payments/returns/tickets/
    email_logs (dynamic SQL, no manual per-query helper functions).
  - rag_policy_search for policy/FAQ questions.
  - send_gmail_notification for agent-initiated notifications.
  - cancel_order_action / request_return_action for HITL-gated actions.

Conversation state is persisted by a SqliteSaver checkpointer, keyed by
`user_email:conversation_id` — never in the business SQL database.

Streamlit code (app_customer.py / app_admin.py) is a thin wrapper: it builds
a session-scoped agent, invokes it with the user's message, and renders the
response. All business logic lives here and in the tools.
"""

import sqlite3
import threading
from typing import Optional

from langchain_community.agent_toolkits import SQLDatabaseToolkit
from langchain_community.utilities import SQLDatabase
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.prebuilt import create_react_agent
from langgraph.types import Command

from src.action_tools import build_action_tools
from src.config import CHAT_MODEL, CHECKPOINTS_DB_PATH, DB_PATH, OPENAI_API_KEY
from src.gmail_tool import send_gmail_notification
from src.logging_middleware import AgentObservabilityHandler
from src.rag_tool import rag_policy_search

SYSTEM_PROMPT = """You are the YourKart virtual assistant, the customer support assistant for the YourKart online store.

You have three kinds of tools:
1. SQL tools (sql_db_query, sql_db_schema, etc.) — for anything specific to
   THIS customer: their orders, order items, payments, returns, tickets, or
   email history. The current customer's email is included in every message
   as "[User: <email>]" — always filter SQL queries by that email (joining
   through orders.user_id / users.email as needed). Never show another
   customer's data.
2. rag_policy_search — for general POLICY or FAQ questions (return window,
   refund timelines, shipping estimates, who pays return shipping). Do not
   use this for a specific order's status.
3. cancel_order_action / request_return_action — for when the customer wants
   to cancel an order or return an item. These do NOT execute immediately:
   they create a pending request for human admin review. Always tell the
   customer clearly that their request has been submitted and is pending
   human review, not confirmed yet.

Rules:
- Only ever read/write data belonging to the current customer.
- Never auto-approve a cancellation or return — that is the admin's job.
- Be concise, friendly, and specific (mention order IDs, amounts, dates).
- If you don't have enough information (e.g. which order), ask a short
  clarifying question rather than guessing.
- Use send_gmail_notification yourself only for informational confirmations
  you decide are appropriate; the cancel/return action tools already send
  their own notification once an admin decides.
"""

_checkpointer_lock = threading.Lock()
_checkpointer: Optional[SqliteSaver] = None
_sql_toolkit_tools = None


def get_checkpointer() -> SqliteSaver:
    global _checkpointer
    with _checkpointer_lock:
        if _checkpointer is None:
            conn = sqlite3.connect(str(CHECKPOINTS_DB_PATH), check_same_thread=False)
            _checkpointer = SqliteSaver(conn)
        return _checkpointer


def _get_sql_tools():
    global _sql_toolkit_tools
    if _sql_toolkit_tools is None:
        llm = ChatOpenAI(model=CHAT_MODEL, temperature=0, api_key=OPENAI_API_KEY)
        db = SQLDatabase.from_uri(
            f"sqlite:///{DB_PATH}",
            include_tables=[
                "users", "products", "orders", "order_items",
                "payments", "returns", "tickets", "email_logs",
            ],
        )
        toolkit = SQLDatabaseToolkit(db=db, llm=llm)
        _sql_toolkit_tools = toolkit.get_tools()
    return _sql_toolkit_tools


def build_thread_id(user_email: str, conversation_id: str) -> str:
    return f"{user_email}:{conversation_id}"


def build_agent(user_email: str, conversation_id: str):
    """Build the single agent for one customer session. Tools are rebuilt
    per session so the HITL action tools can close over this user's
    identity without the LLM needing to supply it."""
    llm = ChatOpenAI(model=CHAT_MODEL, temperature=0, api_key=OPENAI_API_KEY)
    tools = [
        *_get_sql_tools(),
        rag_policy_search,
        send_gmail_notification,
        *build_action_tools(user_email, conversation_id),
    ]
    agent = create_react_agent(
        llm,
        tools,
        prompt=SYSTEM_PROMPT,
        checkpointer=get_checkpointer(),
    )
    return agent


def invoke_agent(user_email: str, conversation_id: str, user_message: str):
    """Send one customer message to the agent and return (reply_text,
    interrupted: bool)."""
    agent = build_agent(user_email, conversation_id)
    thread_id = build_thread_id(user_email, conversation_id)
    config = {
        "configurable": {"thread_id": thread_id},
        "callbacks": [AgentObservabilityHandler(user_email=user_email)],
    }
    tagged_message = f"[User: {user_email}] {user_message}"
    result = agent.invoke({"messages": [("user", tagged_message)]}, config=config)

    if "__interrupt__" in result:
        # Paused for admin approval — nothing more to say right now beyond
        # what the tool already returned isn't available yet since it hasn't
        # resumed. Give the customer a clear holding message.
        return (
            "Thanks — I've submitted that request for review by our support "
            "team. You'll see an update here once it's been reviewed.",
            True,
        )

    messages = result["messages"]
    last = messages[-1]
    return (getattr(last, "content", str(last)), False)


def get_conversation_messages(user_email: str, conversation_id: str):
    """Read the full persisted message history for a thread, so newly
    arrived messages (e.g. from an admin resuming a paused request) show up
    even if the customer didn't just send a message."""
    agent = build_agent(user_email, conversation_id)
    thread_id = build_thread_id(user_email, conversation_id)
    config = {"configurable": {"thread_id": thread_id}}
    state = agent.get_state(config)
    if not state or not state.values:
        return []
    return state.values.get("messages", [])


def resume_thread(thread_id: str, approved: bool, admin_email: str, notes: str = ""):
    """Resume a paused thread with the admin's decision. Used by the admin
    dashboard after approve/reject."""
    user_email, conversation_id = thread_id.split(":", 1)
    agent = build_agent(user_email, conversation_id)
    config = {
        "configurable": {"thread_id": thread_id},
        "callbacks": [AgentObservabilityHandler(user_email=user_email)],
    }
    decision = {"approved": approved, "admin_email": admin_email, "notes": notes}
    result = agent.invoke(Command(resume=decision), config=config)
    messages = result.get("messages", [])
    if messages:
        return getattr(messages[-1], "content", str(messages[-1]))
    return "Decision recorded."
