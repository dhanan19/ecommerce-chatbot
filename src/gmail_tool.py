"""
Gmail notification tool.

Sends a real email via LangChain's GmailToolkit when Gmail OAuth is
configured (GMAIL_ENABLED=true and valid credentials/token on disk).
Otherwise it simulates the send (logs it) so the rest of the app — and the
`email_logs` audit trail — behaves identically without requiring every
student to complete Google Cloud OAuth setup. This simplification is
documented in the README.

Either way, every notification is written to `email_logs` with user_email,
email type, and timestamp, as required by the spec.
"""

import sqlite3
from datetime import datetime, timezone
from typing import Optional

from langchain.tools import tool

from src.config import (
    DB_PATH, GMAIL_ENABLED, GMAIL_CREDENTIALS_PATH, GMAIL_TOKEN_PATH, GMAIL_SENDER,
)
from src.logging_middleware import log_event


def _write_email_log(user_email: str, subject: str, body_preview: str, email_type: str) -> None:
    conn = sqlite3.connect(DB_PATH)
    try:
        user_row = conn.execute("SELECT id FROM users WHERE email = ?", (user_email,)).fetchone()
        user_id = user_row[0] if user_row else None
        conn.execute(
            """INSERT INTO email_logs (user_id, email, subject, body_preview, email_type, sent_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (user_id, user_email, subject, body_preview[:500], email_type, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
    finally:
        conn.close()


def _send_real_gmail(to: str, subject: str, body: str) -> Optional[str]:
    """Attempt a real Gmail send via the Gmail API. Returns an error string
    on failure, or None on success."""
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build
        import base64
        from email.mime.text import MIMEText
        import os

        if not os.path.exists(GMAIL_TOKEN_PATH):
            return f"Gmail token not found at {GMAIL_TOKEN_PATH}"

        creds = Credentials.from_authorized_user_file(GMAIL_TOKEN_PATH)
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())

        service = build("gmail", "v1", credentials=creds)
        message = MIMEText(body)
        message["to"] = to
        message["subject"] = subject
        if GMAIL_SENDER:
            message["from"] = GMAIL_SENDER
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        service.users().messages().send(userId="me", body={"raw": raw}).execute()
        return None
    except Exception as e:  # pragma: no cover - network/OAuth dependent
        return str(e)


def send_notification(user_email: str, subject: str, body: str, email_type: str) -> str:
    """Core notification logic, callable directly by other tools (e.g. the
    action tools after an admin decision) as well as via the agent tool
    below."""
    if GMAIL_ENABLED:
        error = _send_real_gmail(user_email, subject, body)
        if error is None:
            _write_email_log(user_email, subject, body, email_type)
            log_event(user_email, "send_gmail_notification", f"sent: {subject}", success=True)
            return f"Email sent to {user_email}: '{subject}'."
        else:
            log_event(user_email, "send_gmail_notification", f"FAILED ({error}); logged only", success=False)
            _write_email_log(user_email, subject, body, email_type)
            return f"Could not send real email ({error}); notification was logged instead."

    # Simulated send — Gmail not configured.
    _write_email_log(user_email, subject, body, email_type)
    log_event(user_email, "send_gmail_notification", f"simulated: {subject}", success=True)
    return f"(Simulated — Gmail not configured) Notification logged for {user_email}: '{subject}'."


@tool
def send_gmail_notification(user_email: str, subject: str, body: str, email_type: str) -> str:
    """Send an email notification to a customer (e.g. order cancelled,
    return ticket created, return status updated) and record it in
    email_logs. email_type should be a short label such as
    'ORDER_CANCELLED', 'RETURN_CREATED', or 'RETURN_UPDATE'.

    Gmail credentials are read from environment variables only. If Gmail is
    not configured, the notification is simulated and still logged.
    """
    return send_notification(user_email, subject, body, email_type)
