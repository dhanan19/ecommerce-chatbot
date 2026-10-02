"""Safe, session-scoped lookup tools. The LLM never supplies the customer email."""

from langchain.tools import tool

from src.customer_data import (
    get_order_details,
    list_email_logs,
    list_orders,
    list_pending_actions,
    list_tickets,
    search_products,
)


def _fmt_rows(rows: list[dict], empty: str) -> str:
    if not rows:
        return empty
    lines = []
    for row in rows:
        parts = [f"{k}={v}" for k, v in row.items() if v is not None]
        lines.append("- " + ", ".join(parts))
    return "\n".join(lines)


def build_lookup_tools(user_email: str):
    @tool
    def get_my_orders() -> str:
        """List this logged-in customer's orders (id, status, date, total)."""
        return _fmt_rows(list_orders(user_email), "You have no orders on file.")

    @tool
    def get_order_details_tool(order_id: int) -> str:
        """Show items, payment, and returns for one of this customer's orders."""
        detail = get_order_details(user_email, order_id)
        if detail is None:
            return f"Order #{order_id} was not found on this account."
        order = detail["order"]
        lines = [
            f"Order #{order['id']} status={order['status']} date={order['order_date']} total={order['total_amount']}",
            "Items:",
        ]
        for item in detail["items"]:
            lines.append(
                f"  - item_id={item['order_item_id']} {item['name']} x{item['quantity']} @ {item['unit_price']}"
            )
        if detail["payment"]:
            p = detail["payment"]
            lines.append(
                f"Payment: {p['status']} {p['amount']} via {p['payment_method']} ref={p['transaction_reference']}"
            )
        if detail["returns"]:
            lines.append("Returns:")
            for r in detail["returns"]:
                lines.append(
                    f"  - return_id={r['id']} item={r['order_item_id']} status={r['status']} reason={r['reason']}"
                )
        return "\n".join(lines)

    @tool
    def get_my_tickets() -> str:
        """List this customer's support tickets."""
        return _fmt_rows(list_tickets(user_email), "You have no support tickets.")

    @tool
    def get_my_notifications() -> str:
        """List recent emails/notifications logged for this customer."""
        return _fmt_rows(list_email_logs(user_email), "No notifications have been logged for you yet.")

    @tool
    def get_my_pending_requests() -> str:
        """List this customer's cancellation/return requests awaiting or already reviewed by admin."""
        return _fmt_rows(list_pending_actions(user_email), "You have no cancellation or return requests.")

    @tool
    def search_catalog(query: str) -> str:
        """Search the product catalog by name or description. Not for order status."""
        return _fmt_rows(search_products(query), f"No products matched '{query}'.")

    return [
        get_my_orders,
        get_order_details_tool,
        get_my_tickets,
        get_my_notifications,
        get_my_pending_requests,
        search_catalog,
    ]
