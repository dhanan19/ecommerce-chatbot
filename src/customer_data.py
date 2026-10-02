"""Read-only helpers for the current customer's orders, tickets, and queue."""

import sqlite3
from typing import Any, Optional

from src.config import DB_PATH


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _rows(sql: str, params: tuple = ()) -> list[dict[str, Any]]:
    conn = _conn()
    try:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


def get_user_id(email: str) -> Optional[int]:
    conn = _conn()
    try:
        row = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        return int(row["id"]) if row else None
    finally:
        conn.close()


def list_orders(email: str) -> list[dict[str, Any]]:
    return _rows(
        """
        SELECT o.id, o.status, o.order_date, o.total_amount
        FROM orders o
        JOIN users u ON u.id = o.user_id
        WHERE u.email = ?
        ORDER BY o.order_date DESC
        """,
        (email,),
    )


def get_order_details(email: str, order_id: int) -> Optional[dict[str, Any]]:
    conn = _conn()
    try:
        order = conn.execute(
            """
            SELECT o.id, o.status, o.order_date, o.total_amount, u.email
            FROM orders o
            JOIN users u ON u.id = o.user_id
            WHERE o.id = ? AND u.email = ?
            """,
            (order_id, email),
        ).fetchone()
        if order is None:
            return None
        items = conn.execute(
            """
            SELECT oi.id AS order_item_id, p.name, oi.quantity, oi.unit_price
            FROM order_items oi
            JOIN products p ON p.id = oi.product_id
            WHERE oi.order_id = ?
            """,
            (order_id,),
        ).fetchall()
        payment = conn.execute(
            """
            SELECT amount, status, payment_method, transaction_reference, paid_at
            FROM payments WHERE order_id = ?
            """,
            (order_id,),
        ).fetchone()
        returns = conn.execute(
            """
            SELECT id, order_item_id, reason, status, requested_at, resolved_at
            FROM returns WHERE order_id = ?
            """,
            (order_id,),
        ).fetchall()
        return {
            "order": dict(order),
            "items": [dict(i) for i in items],
            "payment": dict(payment) if payment else None,
            "returns": [dict(r) for r in returns],
        }
    finally:
        conn.close()


def list_tickets(email: str) -> list[dict[str, Any]]:
    return _rows(
        """
        SELECT t.id, t.subject, t.status, t.return_id, t.created_at, t.updated_at
        FROM tickets t
        JOIN users u ON u.id = t.user_id
        WHERE u.email = ?
        ORDER BY t.created_at DESC
        """,
        (email,),
    )


def list_email_logs(email: str) -> list[dict[str, Any]]:
    return _rows(
        """
        SELECT subject, email_type, sent_at, body_preview
        FROM email_logs
        WHERE email = ?
        ORDER BY sent_at DESC
        LIMIT 20
        """,
        (email,),
    )


def list_pending_actions(email: str) -> list[dict[str, Any]]:
    return _rows(
        """
        SELECT id, action_type, order_id, product_name, reason, status, created_at
        FROM pending_actions
        WHERE user_email = ?
        ORDER BY created_at DESC
        """,
        (email,),
    )


def queue_counts() -> dict[str, int]:
    conn = _conn()
    try:
        rows = conn.execute(
            "SELECT status, COUNT(*) AS n FROM pending_actions GROUP BY status"
        ).fetchall()
        counts = {"PENDING": 0, "APPROVED": 0, "REJECTED": 0}
        for row in rows:
            counts[row["status"]] = row["n"]
        return counts
    finally:
        conn.close()


def search_products(query: str) -> list[dict[str, Any]]:
    like = f"%{query.strip()}%"
    return _rows(
        """
        SELECT id, name, description, price, stock_qty
        FROM products
        WHERE name LIKE ? OR description LIKE ?
        ORDER BY name
        LIMIT 20
        """,
        (like, like),
    )
