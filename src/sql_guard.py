"""Wrap SQL toolkit tools so the agent can only run scoped, read-only queries."""

import re
from typing import Any, Callable

from langchain.tools import tool

_WRITE = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|ATTACH|DETACH|PRAGMA|REPLACE|CREATE|GRANT|VACUUM)\b",
    re.IGNORECASE,
)
_PASSWORD = re.compile(r"\bpassword\b", re.IGNORECASE)
_CUSTOMER_TABLE = re.compile(
    r"\b(orders|order_items|payments|returns|tickets|email_logs|users|customer_profiles)\b",
    re.IGNORECASE,
)
_FROM_PRODUCTS_ONLY = re.compile(
    r"^\s*SELECT\b(?!.+\bFROM\b.+\b(orders|order_items|payments|returns|tickets|email_logs|users|customer_profiles)\b).+\bFROM\s+products\b",
    re.IGNORECASE | re.DOTALL,
)


def _is_read_only_select(query: str) -> bool:
    stripped = query.strip().rstrip(";")
    if not stripped.lower().startswith("select"):
        return False
    if _WRITE.search(stripped):
        return False
    if _PASSWORD.search(stripped):
        return False
    return True


def _is_scoped_to_customer(query: str, user_email: str) -> bool:
    if _FROM_PRODUCTS_ONLY.search(query):
        return True
    if not _CUSTOMER_TABLE.search(query):
        return True
    return user_email.lower() in query.lower()


def wrap_sql_tools(sql_tools: list, user_email: str) -> list:
    """Keep schema/list tools, replace sql_db_query with a guarded version."""
    wrapped = []
    original_query = None
    for t in sql_tools:
        if getattr(t, "name", "") == "sql_db_query":
            original_query = t
        else:
            wrapped.append(t)

    if original_query is None:
        return sql_tools

    invoke: Callable[[str], Any] = original_query.invoke

    @tool
    def sql_db_query(query: str) -> str:
        """Run a read-only SELECT against the store database.

        Customer tables (orders, payments, returns, tickets, email_logs) MUST
        filter by this customer's email. Product catalog queries do not need
        that filter. Writes and password columns are never allowed.
        """
        if not _is_read_only_select(query):
            return (
                "Query rejected: only SELECT statements are allowed, and they "
                "must not touch password columns or modify data."
            )
        if not _is_scoped_to_customer(query, user_email):
            return (
                f"Query rejected: customer data queries must include this "
                f"customer's email ({user_email}) in the SQL (join users.email "
                f"or filter email_logs.email). Prefer get_my_orders / "
                f"get_order_details instead."
            )
        return invoke({"query": query})

    wrapped.insert(0, sql_db_query)
    return wrapped
