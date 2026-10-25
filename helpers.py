from functools import wraps
from flask import g, redirect, url_for, flash, request


def login_required(role=None):
    """@login_required()          -> any logged-in user
       @login_required("seller")  -> sellers only"""
    def decorator(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            if g.user is None:
                flash("Please log in first.", "warning")
                return redirect(url_for("auth.login"))
            if role and g.user["role"] != role:
                flash("You don't have access to that page.", "danger")
                return redirect(url_for("home"))
            return view(*args, **kwargs)
        return wrapper
    return decorator


def redirect_back(default_endpoint="home"):
    """Go back to the page the form was submitted from (hidden 'next' field).
    Only local paths are allowed."""
    nxt = request.form.get("next", "")
    if nxt.startswith("/") and not nxt.startswith("//"):
        return redirect(nxt)
    return redirect(url_for(default_endpoint))


def order_status(item_statuses):
    """An order has no status column of its own. It is derived from its items,
    because in a multi-vendor order each seller ships their part separately."""
    s = set(item_statuses)
    if s == {"cancelled"}:
        return "Cancelled"
    active = s - {"cancelled"}
    if active == {"delivered"}:
        return "Delivered"
    if active == {"placed"}:
        return "Placed"
    if "placed" in active:
        return "Partially shipped"
    return "Shipped"


def sync_cod_payment(conn, order_id):
    """Cash-on-delivery stays 'pending' until everything still active is delivered.
    Does NOT commit. The caller's transaction does that."""
    row = conn.execute(
        """SELECT SUM(status = 'delivered') AS delivered,
                  SUM(status NOT IN ('delivered', 'cancelled')) AS open_items
           FROM order_items WHERE order_id = ?""", (order_id,)).fetchone()
    if row["delivered"] and not row["open_items"]:
        conn.execute(
            """UPDATE payments SET status = 'success', paid_at = CURRENT_TIMESTAMP
               WHERE order_id = ? AND method = 'cod' AND status = 'pending'""", (order_id,))


def cancel_order_item(conn, item_id, customer_id=None, seller_id=None):
    """Cancels one order line (only while it is still 'placed') and puts the stock back.
    Pass customer_id or seller_id so people can only cancel their own lines.
    Returns True if cancelled, False if not allowed."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        sql = """SELECT oi.order_item_id, oi.order_id, oi.product_id, oi.quantity, oi.status
                 FROM order_items oi JOIN orders o ON o.order_id = oi.order_id
                 WHERE oi.order_item_id = ?"""
        params = [item_id]
        if customer_id is not None:
            sql += " AND o.user_id = ?"
            params.append(customer_id)
        if seller_id is not None:
            sql += " AND oi.seller_id = ?"
            params.append(seller_id)
        item = conn.execute(sql, params).fetchone()

        if item is None or item["status"] != "placed":
            conn.rollback()
            return False

        conn.execute("UPDATE order_items SET status = 'cancelled' WHERE order_item_id = ?",
                     (item_id,))
        if item["product_id"] is not None:      # NULL if the product was deleted since
            conn.execute("UPDATE products SET stock = stock + ? WHERE product_id = ?",
                         (item["quantity"], item["product_id"]))
        sync_cod_payment(conn, item["order_id"])
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        raise