"""
Simple authentication helpers.

Deliberately minimal per the project spec: plain-text password comparison
against the `users` table is acceptable for this lab. Do not reuse this in
production — passwords should be hashed and salted.
"""

import sqlite3
from dataclasses import dataclass
from typing import Optional

from src.config import DB_PATH


@dataclass
class AuthenticatedUser:
    id: int
    email: str
    full_name: str
    role: str


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def login(email: str, password: str, required_role: Optional[str] = None) -> Optional[AuthenticatedUser]:
    """Validate credentials against the users table.

    If required_role is given (e.g. "admin"), the user's role must match.
    Returns None on any failure (unknown email, wrong password, wrong role).
    """
    if not email or not password:
        return None
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT id, email, password, full_name, role FROM users WHERE email = ?",
            (email.strip().lower(),),
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        return None
    if row["password"] != password:
        return None
    if required_role is not None and row["role"] != required_role:
        return None

    return AuthenticatedUser(id=row["id"], email=row["email"], full_name=row["full_name"], role=row["role"])
