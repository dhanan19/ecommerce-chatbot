"""
Customer chat UI.

Thin Streamlit wrapper: login, start/select a conversation, send messages to
the single agent, render its replies. All business logic lives in
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

st.set_page_config(page_title="ShopBot — Support Chat", page_icon="🛍️")

TAG_RE = re.compile(r"^\[User: [^\]]+\]\s*")


def _display_text(msg) -> str:
    text = getattr(msg, "content", str(msg))
    return TAG_RE.sub("", text)


def render_login():
    st.title("🛍️ ShopBot")
    st.caption("Sign in to chat with support about your orders, returns, and shipping.")
    with st.form("login_form"):
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Log in")
    if submitted:
        user = login(email, password, required_role="customer")
        if user is None:
            st.error("Invalid email or password.")
        else:
            st.session_state.user = user
            st.session_state.conversation_id = str(uuid.uuid4())
            st.rerun()
    st.caption("Demo accounts: alice@example.com / alice123, bob@example.com / bob123")


def render_chat():
    user = st.session_state.user

    with st.sidebar:
        st.subheader(f"👋 {user.full_name}")
        st.caption(user.email)
        if st.button("Start new conversation"):
            st.session_state.conversation_id = str(uuid.uuid4())
            st.rerun()
        st.caption(f"Thread: {user.email}:{st.session_state.conversation_id[:8]}...")
        st.divider()
        st.caption("Try asking:")
        st.markdown(
            "- *Show my last 5 orders*\n"
            "- *What's the status of order #2?*\n"
            "- *How many days do I have to return something?*\n"
            "- *Cancel order #3*"
        )
        if st.button("Log out"):
            for key in ("user", "conversation_id"):
                st.session_state.pop(key, None)
            st.rerun()

    st.title("🛍️ ShopBot Support")

    history = get_conversation_messages(user.email, st.session_state.conversation_id)
    for msg in history:
        if isinstance(msg, HumanMessage):
            with st.chat_message("user"):
                st.markdown(_display_text(msg))
        elif isinstance(msg, AIMessage) and _display_text(msg).strip():
            with st.chat_message("assistant"):
                st.markdown(_display_text(msg))

    user_input = st.chat_input("Ask about a product, order, or return...")
    if user_input:
        with st.chat_message("user"):
            st.markdown(user_input)
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                try:
                    reply, _interrupted = invoke_agent(user.email, st.session_state.conversation_id, user_input)
                except Exception as e:
                    import traceback
                    tb = traceback.format_exc()
                    print(tb)  # also goes to the terminal running `streamlit run`
                    from src.logging_middleware import logger
                    logger.error("CHAT_ERROR user=%s\n%s", user.email, tb)
                    reply = f"Something went wrong: {e}\n\n(Full details logged to logs/app.log and printed in the terminal.)"
            st.markdown(reply)


def main():
    if "user" not in st.session_state:
        render_login()
    else:
        render_chat()


if __name__ == "__main__":
    main()
