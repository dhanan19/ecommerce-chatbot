"""
Admin dashboard.

Lists pending cancellation/return requests (from `pending_actions`), plus a
read-only view of all tickets. Approving/rejecting a request resumes the
customer's exact paused agent thread via `resume_thread`, so the same agent
run finishes the SQL updates and sends the notification email.

Run with:  streamlit run src/app_admin.py --server.port 8502
"""

import sqlite3
import sys
from pathlib import Path

# Streamlit runs this file directly, which puts src/ (not the project root)
# on sys.path[0] — so "src.*" imports fail unless we add the root ourselves.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import streamlit as st

from src.auth import login
from src.agent import resume_thread
from src.config import DB_PATH
from src.ui_theme import apply_theme, render_header

st.set_page_config(page_title="YourKart — Admin Dashboard", page_icon="🛠️", layout="centered")
apply_theme()


def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def render_login():
    render_header("Admin Console")
    st.subheader("Admin login")
    with st.form("admin_login"):
        email = st.text_input("Admin email")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Log in")
    if submitted:
        user = login(email, password, required_role="admin")
        if user is None:
            st.error("Invalid admin credentials.")
        else:
            st.session_state.admin = user
            st.rerun()
    st.caption("Demo admin account: admin@example.com / admin123")


def render_dashboard():
    admin = st.session_state.admin
    with st.sidebar:
        st.subheader(f"🛠️ {admin.full_name}")
        st.caption(admin.email)
        if st.button("Log out"):
            st.session_state.pop("admin", None)
            st.rerun()

    render_header("Admin Console")
    st.subheader("Return & Cancellation Review Queue")

    col1, col2, col3 = st.columns(3)
    with col1:
        status_filter = st.selectbox("Status", ["PENDING", "APPROVED", "REJECTED", "ALL"], index=0)
    with col2:
        email_filter = st.text_input("Filter by customer email (optional)")
    with col3:
        type_filter = st.selectbox("Type", ["ALL", "CANCEL_ORDER", "CREATE_RETURN"], index=0)

    conn = _conn()
    query = "SELECT * FROM pending_actions WHERE 1=1"
    params = []
    if status_filter != "ALL":
        query += " AND status = ?"
        params.append(status_filter)
    if email_filter:
        query += " AND user_email LIKE ?"
        params.append(f"%{email_filter}%")
    if type_filter != "ALL":
        query += " AND action_type = ?"
        params.append(type_filter)
    query += " ORDER BY created_at DESC"
    rows = conn.execute(query, params).fetchall()
    conn.close()

    if not rows:
        st.info("No requests match these filters.")
    else:
        for row in rows:
            label = (
                f"#{row['id']} · {row['action_type']} · order #{row['order_id']} · "
                f"{row['user_email']} · {row['status']}"
            )
            with st.expander(label, expanded=(row["status"] == "PENDING")):
                c1, c2 = st.columns(2)
                with c1:
                    st.write("**Order ID:**", row["order_id"])
                    if row["product_name"]:
                        st.write("**Product:**", row["product_name"])
                    if row["reason"]:
                        st.write("**Reason:**", row["reason"])
                    st.write("**Requested at:**", row["created_at"])
                with c2:
                    st.write("**Customer:**", row["user_email"])
                    st.write("**Thread:**", row["thread_id"])
                    st.write("**Status:**", row["status"])
                    if row["admin_notes"]:
                        st.write("**Admin notes:**", row["admin_notes"])

                if row["status"] == "PENDING":
                    notes = st.text_input("Notes to customer (optional)", key=f"notes_{row['id']}")
                    b1, b2 = st.columns(2)
                    with b1:
                        if st.button("✅ Approve", key=f"approve_{row['id']}", width="stretch"):
                            with st.spinner("Resuming customer thread..."):
                                reply = resume_thread(row["thread_id"], True, admin.email, notes)
                            st.success(f"Approved. Agent said: {reply}")
                            st.rerun()
                    with b2:
                        if st.button("❌ Reject", key=f"reject_{row['id']}", width="stretch"):
                            with st.spinner("Resuming customer thread..."):
                                reply = resume_thread(row["thread_id"], False, admin.email, notes)
                            st.warning(f"Rejected. Agent said: {reply}")
                            st.rerun()

    st.divider()
    st.subheader("All Tickets (read-only)")
    conn = _conn()
    tickets = conn.execute("SELECT * FROM tickets ORDER BY created_at DESC LIMIT 50").fetchall()
    conn.close()
    if tickets:
        # Rendered manually (not st.dataframe) to avoid a pandas/numpy import —
        # this environment has a broken pandas/numpy ABI outside our control.
        cols = tickets[0].keys()
        header = " | ".join(cols)
        st.markdown(f"**{header}**")
        st.divider()
        for t in tickets:
            row_dict = dict(t)
            st.text(" | ".join(str(row_dict[c]) for c in cols))
    else:
        st.caption("No tickets yet.")


def main():
    if "admin" not in st.session_state:
        render_login()
    else:
        render_dashboard()


if __name__ == "__main__":
    main()
