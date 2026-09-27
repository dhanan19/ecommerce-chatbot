"""
Database initialization helper.

The project ships with a ready-made `ecommerce.db` (users, products, orders,
order_items, payments, returns, tickets, email_logs). This module only adds
what the HITL (human-in-the-loop) flow needs on top of that: a
`pending_actions` table that the admin dashboard reads from, and that the
action tools write to before pausing for approval.

Safe to run multiple times — every statement is idempotent.
"""

import sqlite3

from src.config import DB_PATH

PENDING_ACTIONS_DDL = """
CREATE TABLE IF NOT EXISTS pending_actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    thread_id TEXT NOT NULL,
    user_email TEXT NOT NULL,
    conversation_id TEXT NOT NULL,
    action_type TEXT NOT NULL CHECK (action_type IN ('CANCEL_ORDER', 'CREATE_RETURN')),
    order_id INTEGER NOT NULL,
    order_item_id INTEGER,
    product_name TEXT,
    reason TEXT,
    ticket_id INTEGER,
    return_id INTEGER,
    status TEXT NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'APPROVED', 'REJECTED')),
    admin_email TEXT,
    admin_notes TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (order_id) REFERENCES orders(id)
);
"""

INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_pending_actions_status ON pending_actions(status);",
    "CREATE INDEX IF NOT EXISTS idx_pending_actions_thread ON pending_actions(thread_id);",
]


def init_db() -> None:
    if not DB_PATH.exists():
        raise FileNotFoundError(
            f"ecommerce.db not found at {DB_PATH}. Place it in the project root "
            "or set ECOMMERCE_DB_PATH."
        )
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute(PENDING_ACTIONS_DDL)
        for stmt in INDEXES:
            conn.execute(stmt)
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    init_db()
    print(f"OK — pending_actions table ready in {DB_PATH}")
