"""
YourKart customer chat UI (Flipkart-style, with dark mode).

Thin Streamlit wrapper: login, start a conversation, send messages to the
single agent, render its replies. All business logic lives in
src/agent.py and the tool modules.

Run with:  streamlit run src/app_customer.py
"""

import re
import sys
import uuid
from pathlib import Path

# Streamlit runs this file directly, which puts src/ (not the project root)
# on sys.path[0] — so "src.*" imports fail unless we add the root ourselves.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import streamlit as st
from langchain_core.messages import AIMessage, HumanMessage

from src.auth import login
from src.agent import get_conversation_messages, invoke_agent
from src.ui_theme import apply_theme, render_header

st.set_page_config(page_title="YourKart Assistant", page_icon="🛒", layout="centered")
apply_theme()

TAG_RE = re.compile(r"^\[User: [^\]]+\]\s*")

QUICK_REPLIES = [
    ("📦 My orders", "Show my last 5 orders"),
    ("🚚 Track order", "What is the status of my latest order?"),
    ("↩️ Return an item", "I want to return an item from my order"),
    ("❌ Cancel order", "I want to cancel an order"),
    ("📜 Return policy", "What is your return policy?"),
    ("🚀 Shipping info", "How long does shipping take?"),
]


def _display_text(msg) -> str:
    text = getattr(msg, "content", str(msg))
    return TAG_RE.sub("", text)


def render_login():
    render_header("Sign in to continue")
    st.subheader("Login to YourKart")
    with st.form("login_form"):
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Login")
    if submitted:
        user = login(email, password, required_role="customer")
        if user is None:
            st.error("Invalid email or password.")
        else:
            st.session_state.user = user
            st.session_state.conversation_id = str(uuid.uuid4())
            st.rerun()
    st.caption("Demo accounts: alice@example.com / alice123 · bob@example.com / bob123")


def render_chat():
    user = st.session_state.user

    with st.sidebar:
        st.subheader(f"👋 {user.full_name}")
        st.caption(user.email)
        if st.button("➕ New conversation"):
            st.session_state.conversation_id = str(uuid.uuid4())
            st.rerun()
        st.caption(f"Chat ID: {st.session_state.conversation_id[:8]}")
        st.divider()
        if st.button("Log out"):
            for key in ("user", "conversation_id", "pending_prompt"):
                st.session_state.pop(key, None)
            st.rerun()

    render_header("YourKart Assistant · Online")

    history = get_conversation_messages(user.email, st.session_state.conversation_id)
    visible = [
        m for m in history
        if isinstance(m, HumanMessage) or (isinstance(m, AIMessage) and _display_text(m).strip())
    ]

    if not visible:
        with st.chat_message("assistant", avatar="🛒"):
            st.markdown(
                f"Hi **{user.full_name.split()[0]}**! 👋 I'm your YourKart assistant. "
                "I can help with your orders, returns, cancellations and shipping. "
                "What would you like help with?"
            )
        cols = st.columns(3)
        for i, (label, prompt) in enumerate(QUICK_REPLIES):
            with cols[i % 3]:
                if st.button(label, key=f"chip_{i}", width="stretch"):
                    st.session_state.pending_prompt = prompt
                    st.rerun()

    for msg in visible:
        if isinstance(msg, HumanMessage):
            with st.chat_message("user", avatar="🙂"):
                st.markdown(_display_text(msg))
        else:
            with st.chat_message("assistant", avatar="🛒"):
                st.markdown(_display_text(msg))

    user_input = st.chat_input("Type your message...")
    if not user_input:
        user_input = st.session_state.pop("pending_prompt", None)

    if user_input:
        with st.chat_message("user", avatar="🙂"):
            st.markdown(user_input)
        with st.chat_message("assistant", avatar="🛒"):
            with st.spinner("YourKart is typing..."):
                try:
                    reply, _interrupted = invoke_agent(user.email, st.session_state.conversation_id, user_input)
                except Exception as e:
                    import traceback
                    tb = traceback.format_exc()
                    print(tb)  # also goes to the terminal running `streamlit run`
                    from src.logging_middleware import logger
                    logger.error("CHAT_ERROR user=%s\n%s", user.email, tb)
                    reply = f"Something went wrong: {e}\n\n(Full details logged to logs/app.log.)"
            st.markdown(reply)


def main():
    if "user" not in st.session_state:
        render_login()
    else:
        render_chat()


if __name__ == "__main__":
    main()
