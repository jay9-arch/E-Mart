from flask import Blueprint, render_template, request, redirect, url_for, flash, g
from db import get_connection
from helpers import login_required, cancel_order_item, sync_cod_payment

seller_bp = Blueprint("seller", __name__, url_prefix="/seller")


def get_categories(conn):
    return conn.execute("SELECT category_id, name FROM categories ORDER BY name").fetchall()


def validate_product_form(form, conn):
    """Checks the form. Returns (clean_values, list_of_errors)."""
    errors = []
    name = form.get("name", "").strip()
    description = form.get("description", "").strip()
    category_raw = form.get("category_id", "")

    if not name:
        errors.append("Product name is required.")
    elif len(name) > 100:
        errors.append("Product name must be 100 characters or fewer.")

    try:
        price = round(float(form.get("price", "")), 2)
        if price <= 0:
            errors.append("Price must be greater than 0.")
        elif price > 10_000_000:
            errors.append("Price is too large.")
    except ValueError:
        price = None
        errors.append("Price must be a number.")

    try:
        stock = int(form.get("stock", ""))
        if stock < 0:
            errors.append("Stock cannot be negative.")
        elif stock > 1_000_000:
            errors.append("Stock is too large.")
    except ValueError:
        stock = None
        errors.append("Stock must be a whole number.")

    category_id = None
    if category_raw != "":
        try:
            category_id = int(category_raw)
            exists = conn.execute("SELECT 1 FROM categories WHERE category_id = ?",
                                  (category_id,)).fetchone()
            if not exists:
                errors.append("Please choose a valid category.")
        except ValueError:
            errors.append("Please choose a valid category.")

    values = {"name": name, "description": description, "price": price,
              "stock": stock, "category_id": category_id}
    return values, errors


def get_own_product(conn, product_id):
    """Returns the product ONLY if it belongs to the logged-in seller."""
    return conn.execute(
        "SELECT * FROM products WHERE product_id = ? AND seller_id = ?",
        (product_id, g.user["user_id"])).fetchone()


@seller_bp.route("/dashboard")
@login_required("seller")
def dashboard():
    conn = get_connection()
    products = conn.execute(
        """SELECT p.*, c.name AS category
           FROM products p
           LEFT JOIN categories c ON c.category_id = p.category_id
           WHERE p.seller_id = ?
           ORDER BY p.product_id DESC""", (g.user["user_id"],)).fetchall()
    store = conn.execute("SELECT store_name FROM seller_profiles WHERE seller_id = ?",
                         (g.user["user_id"],)).fetchone()
    conn.close()

    stats = {
        "total": len(products),
        "units": sum(p["stock"] for p in products),
        "out_of_stock": sum(1 for p in products if p["stock"] == 0),
    }
    return render_template("seller/dashboard.html", products=products,
                           store=store, stats=stats)


@seller_bp.route("/products/add", methods=["GET", "POST"])
@login_required("seller")
def add_product():
    conn = get_connection()
    categories = get_categories(conn)

    if request.method == "POST":
        values, errors = validate_product_form(request.form, conn)
        if errors:
            for e in errors:
                flash(e, "danger")
            conn.close()
            return render_template("seller/product_form.html", categories=categories,
                                   values=request.form, mode="add")

        conn.execute(
            "INSERT INTO products (seller_id, category_id, name, description, price, stock) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (g.user["user_id"], values["category_id"], values["name"],
             values["description"], values["price"], values["stock"]))
        conn.commit()
        conn.close()
        flash(f"'{values['name']}' has been listed for sale.", "success")
        return redirect(url_for("seller.dashboard"))

    conn.close()
    return render_template("seller/product_form.html", categories=categories,
                           values={}, mode="add")


@seller_bp.route("/products/<int:product_id>/edit", methods=["GET", "POST"])
@login_required("seller")
def edit_product(product_id):
    conn = get_connection()
    product = get_own_product(conn, product_id)
    if product is None:
        conn.close()
        flash("Product not found.", "danger")
        return redirect(url_for("seller.dashboard"))

    categories = get_categories(conn)

    if request.method == "POST":
        values, errors = validate_product_form(request.form, conn)
        if errors:
            for e in errors:
                flash(e, "danger")
            conn.close()
            return render_template("seller/product_form.html", categories=categories,
                                   values=request.form, mode="edit", product_id=product_id)

        conn.execute(
            """UPDATE products
               SET name = ?, description = ?, price = ?, stock = ?, category_id = ?
               WHERE product_id = ? AND seller_id = ?""",
            (values["name"], values["description"], values["price"], values["stock"],
             values["category_id"], product_id, g.user["user_id"]))
        conn.commit()
        conn.close()
        flash("Product updated.", "success")
        return redirect(url_for("seller.dashboard"))

    conn.close()
    return render_template("seller/product_form.html", categories=categories,
                           values=dict(product), mode="edit", product_id=product_id)


@seller_bp.route("/products/<int:product_id>/delete", methods=["POST"])
@login_required("seller")
def delete_product(product_id):
    conn = get_connection()
    product = get_own_product(conn, product_id)
    if product is None:
        conn.close()
        flash("Product not found.", "danger")
        return redirect(url_for("seller.dashboard"))

    in_carts = conn.execute("SELECT COUNT(*) FROM cart_items WHERE product_id = ?",
                            (product_id,)).fetchone()[0]

    # The database does the rest: cart_items rows CASCADE away,
    # order_items.product_id becomes NULL (order history is kept).
    conn.execute("DELETE FROM products WHERE product_id = ? AND seller_id = ?",
                 (product_id, g.user["user_id"]))
    conn.commit()
    conn.close()

    msg = f"'{product['name']}' was deleted."
    if in_carts:
        msg += f" It was also removed from {in_carts} customer cart(s)."
    flash(msg + " Past orders are unaffected.", "info")
    return redirect(url_for("seller.dashboard"))

# =====================================================================
#  SELLER ORDERS
# =====================================================================

@seller_bp.route("/orders")
@login_required("seller")
def orders():
    status = request.args.get("status", "")
    sql = """
        SELECT oi.order_item_id, oi.order_id, oi.product_name, oi.unit_price,
               oi.quantity, oi.status,
               o.customer_name, o.shipping_address, o.placed_at,
               pay.method, pay.status AS payment_status
        FROM order_items oi
        JOIN orders o ON o.order_id = oi.order_id
        LEFT JOIN payments pay ON pay.order_id = o.order_id
        WHERE oi.seller_id = ?
    """
    params = [g.user["user_id"]]
    if status in ("placed", "shipped", "delivered", "cancelled"):
        sql += " AND oi.status = ?"
        params.append(status)
    sql += """ ORDER BY CASE oi.status WHEN 'placed' THEN 0 WHEN 'shipped' THEN 1 ELSE 2 END,
                        oi.order_item_id DESC"""

    conn = get_connection()
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return render_template("seller/orders.html", rows=rows, status=status)


@seller_bp.route("/orders/item/<int:item_id>/status", methods=["POST"])
@login_required("seller")
def update_order_item(item_id):
    new_status = request.form.get("status")
    conn = get_connection()
    try:
        if new_status == "cancelled":
            ok = cancel_order_item(conn, item_id, seller_id=g.user["user_id"])
            flash("Item cancelled and stock restored." if ok
                  else "That item can't be cancelled anymore.",
                  "info" if ok else "warning")
        elif new_status in ("shipped", "delivered"):
            required = {"shipped": "placed", "delivered": "shipped"}[new_status]  # allowed order
            row = conn.execute(
                "SELECT order_id FROM order_items WHERE order_item_id = ? AND seller_id = ?",
                (item_id, g.user["user_id"])).fetchone()
            res = conn.execute(
                "UPDATE order_items SET status = ? "
                "WHERE order_item_id = ? AND seller_id = ? AND status = ?",
                (new_status, item_id, g.user["user_id"], required))
            if res.rowcount == 1:
                sync_cod_payment(conn, row["order_id"])
                conn.commit()
                flash(f"Marked as {new_status}.", "success")
            else:
                conn.rollback()
                flash("That status change isn't allowed.", "warning")
        else:
            flash("Invalid status.", "danger")
    finally:
        conn.close()
    return redirect(request.referrer or url_for("seller.orders"))

# =====================================================================
#  SELLER ANALYTICS
# =====================================================================
from analytics import parse_days, seller_report, DAY_OPTIONS


@seller_bp.route("/analytics")
@login_required("seller")
def analytics():
    days = parse_days(request.args.get("days"))
    conn = get_connection()
    report = seller_report(conn, g.user["user_id"], days)
    conn.close()
    return render_template("seller/analytics.html", r=report, days=days, options=DAY_OPTIONS)