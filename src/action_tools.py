"""
Action tools that require human-in-the-loop approval.

Cancelling an order or requesting a return are never auto-approved by the
agent. Each tool here:
  1. Validates the request against business rules.
  2. Writes a PENDING row to `pending_actions` (and, for returns, a PENDING
     `returns` row + `OPEN` ticket) so the admin dashboard can see it.
  3. Calls LangGraph's `interrupt()`, which pauses this agent run and
     returns control to the caller immediately (non-blocking) with the
     interrupt payload — it does NOT block the Streamlit request.
  4. Later, when an admin approves/rejects from the dashboard, the admin app
     resumes the *same* thread with `Command(resume=decision)`. Execution
     continues right here, `interrupt()` returns the admin's decision, and
     the tool finishes the real database update + notification.

Tools are built per-session via `build_action_tools(user_email,
conversation_id)` so the LLM never has to supply those identifiers itself —
they're captured in a closure instead.
"""

import sqlite3
from datetime import datetime, timezone
from typing import Optional

from langchain.tools import tool
from langgraph.types import interrupt

from src.config import DB_PATH, CANCELLABLE_STATUSES, RETURN_WINDOW_DAYS
from src.gmail_tool import send_notification
from src.logging_middleware import log_event


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def build_action_tools(user_email: str, conversation_id: str):
    thread_id = f"{user_email}:{conversation_id}"

    @tool
    def cancel_order_action(order_id: int) -> str:
        """Request cancellation of one of the current customer's orders.
        Only allowed while the order is still PLACED or SHIPPED (not yet
        DELIVERED). This does NOT cancel immediately — it creates a pending
        request that a human admin must approve, and returns a message you
        should relay to the customer explaining that.
        """
        conn = _conn()
        try:
            order = conn.execute(
                "SELECT o.id, o.status, o.user_id, u.email FROM orders o "
                "JOIN users u ON u.id = o.user_id WHERE o.id = ?",
                (order_id,),
            ).fetchone()
            if order is None:
                return f"Order #{order_id} was not found."
            if order["email"] != user_email:
                log_event(user_email, "cancel_order_action", f"order {order_id} not owned by user", success=False)
                return "That order does not belong to your account."
            if order["status"] not in CANCELLABLE_STATUSES:
                return (
                    f"Order #{order_id} is currently {order['status']} and can no longer be "
                    "cancelled. If it has already arrived, you can request a return instead."
                )

            ticket_id = conn.execute(
                """INSERT INTO tickets (user_id, subject, status, thread_id, user_email, created_at, updated_at)
                   VALUES (?, ?, 'OPEN', ?, ?, ?, ?)""",
                (order["user_id"], f"Order #{order_id} Cancellation", thread_id, user_email, _now(), _now()),
            ).lastrowid

            pending_id = conn.execute(
                """INSERT INTO pending_actions
                   (thread_id, user_email, conversation_id, action_type, order_id, ticket_id, status, created_at, updated_at)
                   VALUES (?, ?, ?, 'CANCEL_ORDER', ?, ?, 'PENDING', ?, ?)""",
                (thread_id, user_email, conversation_id, order_id, ticket_id, _now(), _now()),
            ).lastrowid
            conn.commit()
            log_event(user_email, "cancel_order_action", f"pending_action {pending_id} created for order {order_id}")
        finally:
            conn.close()

        decision = interrupt({
            "action_type": "CANCEL_ORDER",
            "pending_action_id": pending_id,
            "order_id": order_id,
            "user_email": user_email,
            "thread_id": thread_id,
            "message": f"Customer {user_email} requests cancellation of order #{order_id}.",
        })

        return _resolve_cancel(pending_id, order_id, ticket_id, user_email, decision)

    @tool
    def request_return_action(order_id: int, order_item_id: int, reason: str) -> str:
        """Request a return for a specific item within one of the current
        customer's orders. Only allowed within the 30-day return window from
        delivery. This does NOT approve the return immediately — it creates
        a pending request that a human admin must review, and returns a
        message you should relay to the customer explaining that.
        """
        conn = _conn()
        try:
            item = conn.execute(
                """SELECT oi.id as item_id, oi.order_id, o.status, o.order_date, o.user_id, u.email,
                          p.name as product_name
                   FROM order_items oi
                   JOIN orders o ON o.id = oi.order_id
                   JOIN users u ON u.id = o.user_id
                   JOIN products p ON p.id = oi.product_id
                   WHERE oi.id = ? AND oi.order_id = ?""",
                (order_item_id, order_id),
            ).fetchone()
            if item is None:
                return f"Could not find item #{order_item_id} on order #{order_id}."
            if item["email"] != user_email:
                log_event(user_email, "request_return_action", f"item {order_item_id} not owned by user", success=False)
                return "That order item does not belong to your account."

            try:
                order_date = datetime.fromisoformat(item["order_date"])
                if order_date.tzinfo is None:
                    order_date = order_date.replace(tzinfo=timezone.utc)
                days_since = (datetime.now(timezone.utc) - order_date).days
            except ValueError:
                days_since = 0
            if days_since > RETURN_WINDOW_DAYS:
                return (
                    f"Order #{order_id} was placed {days_since} days ago, which is outside the "
                    f"{RETURN_WINDOW_DAYS}-day return window, so it isn't eligible for a standard return."
                )

            return_id = conn.execute(
                """INSERT INTO returns (order_id, order_item_id, user_id, reason, status, requested_at)
                   VALUES (?, ?, ?, ?, 'PENDING', ?)""",
                (order_id, order_item_id, item["user_id"], reason, _now()),
            ).lastrowid

            ticket_id = conn.execute(
                """INSERT INTO tickets (user_id, return_id, subject, status, thread_id, user_email, created_at, updated_at)
                   VALUES (?, ?, ?, 'OPEN', ?, ?, ?, ?)""",
                (item["user_id"], return_id, f"Return: {item['product_name']}", thread_id, user_email, _now(), _now()),
            ).lastrowid

            pending_id = conn.execute(
                """INSERT INTO pending_actions
                   (thread_id, user_email, conversation_id, action_type, order_id, order_item_id,
                    product_name, reason, ticket_id, return_id, status, created_at, updated_at)
                   VALUES (?, ?, ?, 'CREATE_RETURN', ?, ?, ?, ?, ?, ?, 'PENDING', ?, ?)""",
                (thread_id, user_email, conversation_id, order_id, order_item_id,
                 item["product_name"], reason, ticket_id, return_id, _now(), _now()),
            ).lastrowid
            conn.commit()
            log_event(user_email, "request_return_action", f"pending_action {pending_id} created for order {order_id}")
        finally:
            conn.close()

        decision = interrupt({
            "action_type": "CREATE_RETURN",
            "pending_action_id": pending_id,
            "order_id": order_id,
            "order_item_id": order_item_id,
            "product_name": item["product_name"],
            "reason": reason,
            "user_email": user_email,
            "thread_id": thread_id,
            "message": f"Customer {user_email} requests a return for '{item['product_name']}' on order #{order_id}.",
        })

        return _resolve_return(pending_id, return_id, ticket_id, order_id, user_email, decision)

    return [cancel_order_action, request_return_action]


# --- Resolution logic, also reused by the admin app's direct-resume path ----

def _resolve_cancel(pending_id: int, order_id: int, ticket_id: int, user_email: str, decision: dict) -> str:
    approved = bool(decision.get("approved"))
    notes = decision.get("notes", "")
    admin_email = decision.get("admin_email", "admin")
    conn = _conn()
    try:
        if approved:
            conn.execute("UPDATE orders SET status = 'CANCELLED' WHERE id = ?", (order_id,))
            conn.execute("UPDATE tickets SET status = 'RESOLVED', updated_at = ? WHERE id = ?", (_now(), ticket_id))
            conn.execute(
                "UPDATE pending_actions SET status='APPROVED', admin_email=?, admin_notes=?, updated_at=? WHERE id=?",
                (admin_email, notes, _now(), pending_id),
            )
            conn.commit()
        else:
            conn.execute("UPDATE tickets SET status = 'RESOLVED', updated_at = ? WHERE id = ?", (_now(), ticket_id))
            conn.execute(
                "UPDATE pending_actions SET status='REJECTED', admin_email=?, admin_notes=?, updated_at=? WHERE id=?",
                (admin_email, notes, _now(), pending_id),
            )
            conn.commit()
    finally:
        conn.close()

    if approved:
        send_notification(
            user_email, f"Order #{order_id} cancelled",
            f"Your order #{order_id} has been cancelled and refunded per our shipping policy. {notes}".strip(),
            "ORDER_CANCELLED",
        )
        return f"Order #{order_id} has been cancelled and the customer notified by email."
    else:
        send_notification(
            user_email, f"Order #{order_id} cancellation request update",
            f"Your cancellation request for order #{order_id} was not approved. {notes}".strip(),
            "ORDER_CANCEL_REJECTED",
        )
        return f"The cancellation request for order #{order_id} was rejected. Reason: {notes or 'not specified'}."


def _resolve_return(pending_id: int, return_id: int, ticket_id: int, order_id: int, user_email: str, decision: dict) -> str:
    approved = bool(decision.get("approved"))
    notes = decision.get("notes", "")
    admin_email = decision.get("admin_email", "admin")
    conn = _conn()
    try:
        new_status = "APPROVED" if approved else "REJECTED"
        conn.execute(
            "UPDATE returns SET status=?, resolved_at=? WHERE id=?",
            (new_status, _now(), return_id),
        )
        conn.execute("UPDATE tickets SET status = 'RESOLVED', updated_at = ? WHERE id = ?", (_now(), ticket_id))
        conn.execute(
            "UPDATE pending_actions SET status=?, admin_email=?, admin_notes=?, updated_at=? WHERE id=?",
            (new_status, admin_email, notes, _now(), pending_id),
        )
        conn.commit()
    finally:
        conn.close()

    if approved:
        send_notification(
            user_email, f"Return approved for order #{order_id}",
            f"Your return request for order #{order_id} has been approved. {notes}".strip(),
            "RETURN_UPDATE",
        )
        return f"The return for order #{order_id} has been approved and the customer notified by email."
    else:
        send_notification(
            user_email, f"Return request update for order #{order_id}",
            f"Your return request for order #{order_id} was not approved. {notes}".strip(),
            "RETURN_UPDATE",
        )
        return f"The return for order #{order_id} was rejected. Reason: {notes or 'not specified'}."
