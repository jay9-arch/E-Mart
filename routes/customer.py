import re
import sqlite3
from flask import (Blueprint, render_template, request, redirect, url_for,
                   flash, g, session)
from db import get_connection
from helpers import login_required, redirect_back, order_status, cancel_order_item

customer_bp = Blueprint("customer", __name__)


# =====================================================================
#  PRODUCT PAGE (public)
# =====================================================================

def has_delivered_purchase(conn, user_id, product_id):
    """True only if this customer has a DELIVERED order line for this product."""
    row = conn.execute(
        """SELECT 1 FROM order_items oi
           JOIN orders o ON o.order_id = oi.order_id
           WHERE o.user_id = ? AND oi.product_id = ? AND oi.status = 'delivered'
           LIMIT 1""", (user_id, product_id)).fetchone()
    return row is not None


@customer_bp.route("/product/<int:product_id>")
def product_detail(product_id):
    conn = get_connection()
    product = conn.execute(
        """SELECT p.*, sp.store_name, c.name AS category,
                  (SELECT ROUND(AVG(rating), 1) FROM reviews r
                    WHERE r.product_id = p.product_id) AS avg_rating,
                  (SELECT COUNT(*) FROM reviews r
                    WHERE r.product_id = p.product_id) AS review_count
           FROM products p
           JOIN seller_profiles sp ON sp.seller_id = p.seller_id
           LEFT JOIN categories c ON c.category_id = p.category_id
           WHERE p.product_id = ?""", (product_id,)).fetchone()

    if product is None:
        conn.close()
        flash("That product doesn't exist (it may have been removed).", "warning")
        return redirect(url_for("home"))

    reviews = conn.execute(
        """SELECT r.review_id, r.user_id, r.rating, r.comment, r.created_at, u.name
           FROM reviews r JOIN users u ON u.user_id = r.user_id
           WHERE r.product_id = ? ORDER BY r.created_at DESC""", (product_id,)).fetchall()

    in_cart = 0
    can_review = False
    my_review = None
    if g.user is not None and g.user["role"] == "customer":
        row = conn.execute("SELECT quantity FROM cart_items WHERE user_id = ? AND product_id = ?",
                           (g.user["user_id"], product_id)).fetchone()
        in_cart = row["quantity"] if row else 0
        can_review = has_delivered_purchase(conn, g.user["user_id"], product_id)
        my_review = conn.execute(
            "SELECT * FROM reviews WHERE product_id = ? AND user_id = ?",
            (product_id, g.user["user_id"])).fetchone()
    conn.close()

    return render_template("product.html", product=product, reviews=reviews,
                           in_cart=in_cart, can_review=can_review, my_review=my_review)


# =====================================================================
#  CART
# =====================================================================

@customer_bp.route("/cart")
@login_required("customer")
def cart():
    conn = get_connection()

    # If a seller lowered the stock below what's in this cart, trim the cart to match.
    trimmed = conn.execute(
        """UPDATE cart_items
           SET quantity = (SELECT stock FROM products p WHERE p.product_id = cart_items.product_id)
           WHERE user_id = ?
             AND (SELECT stock FROM products p WHERE p.product_id = cart_items.product_id) > 0
             AND quantity > (SELECT stock FROM products p WHERE p.product_id = cart_items.product_id)""",
        (g.user["user_id"],)).rowcount
    conn.commit()
    if trimmed:
        flash("Some quantities were reduced because stock changed.", "warning")

    items = conn.execute(
        """SELECT c.product_id, c.quantity, p.name, p.price, p.stock, sp.store_name
           FROM cart_items c
           JOIN products p ON p.product_id = c.product_id
           JOIN seller_profiles sp ON sp.seller_id = p.seller_id
           WHERE c.user_id = ?
           ORDER BY p.name""", (g.user["user_id"],)).fetchall()
    conn.close()

    available = [i for i in items if i["stock"] > 0]
    subtotal = sum(i["price"] * i["quantity"] for i in available)
    has_unavailable = len(available) != len(items)
    return render_template("cart.html", items=items, subtotal=subtotal,
                           has_unavailable=has_unavailable)


@customer_bp.route("/cart/add/<int:product_id>", methods=["POST"])
@login_required("customer")
def add_to_cart(product_id):
    try:
        qty = max(1, int(request.form.get("quantity", 1)))
    except ValueError:
        qty = 1

    conn = get_connection()
    product = conn.execute("SELECT name, stock FROM products WHERE product_id = ?",
                           (product_id,)).fetchone()
    if product is None:
        conn.close()
        flash("That product is no longer available.", "warning")
        return redirect(url_for("home"))
    if product["stock"] == 0:
        conn.close()
        flash(f"'{product['name']}' is out of stock.", "warning")
        return redirect_back()

    row = conn.execute("SELECT quantity FROM cart_items WHERE user_id = ? AND product_id = ?",
                       (g.user["user_id"], product_id)).fetchone()
    current = row["quantity"] if row else 0
    new_qty = min(current + qty, product["stock"])

    if new_qty == current:
        flash(f"You already have all {product['stock']} available units in your cart.", "warning")
    else:
        if row:
            conn.execute("UPDATE cart_items SET quantity = ? WHERE user_id = ? AND product_id = ?",
                         (new_qty, g.user["user_id"], product_id))
        else:
            conn.execute("INSERT INTO cart_items (user_id, product_id, quantity) VALUES (?, ?, ?)",
                         (g.user["user_id"], product_id, new_qty))
        conn.commit()
        if current + qty > product["stock"]:
            flash(f"Only {product['stock']} in stock, so your cart has {new_qty}.", "warning")
        else:
            flash(f"Added '{product['name']}' to your cart.", "success")
    conn.close()
    return redirect_back()


@customer_bp.route("/cart/update/<int:product_id>", methods=["POST"])
@login_required("customer")
def update_cart(product_id):
    action = request.form.get("action")
    conn = get_connection()
    row = conn.execute(
        """SELECT c.quantity, p.stock FROM cart_items c
           JOIN products p ON p.product_id = c.product_id
           WHERE c.user_id = ? AND c.product_id = ?""",
        (g.user["user_id"], product_id)).fetchone()

    if row is None:
        flash("That item is no longer in your cart.", "warning")
    elif action == "inc":
        if row["quantity"] < row["stock"]:
            conn.execute("UPDATE cart_items SET quantity = quantity + 1 "
                         "WHERE user_id = ? AND product_id = ?", (g.user["user_id"], product_id))
            conn.commit()
        else:
            flash(f"Only {row['stock']} available.", "warning")
    elif action == "dec":
        if row["quantity"] > 1:
            conn.execute("UPDATE cart_items SET quantity = quantity - 1 "
                         "WHERE user_id = ? AND product_id = ?", (g.user["user_id"], product_id))
            conn.commit()
    conn.close()
    return redirect(url_for("customer.cart"))


@customer_bp.route("/cart/remove/<int:product_id>", methods=["POST"])
@login_required("customer")
def remove_from_cart(product_id):
    conn = get_connection()
    conn.execute("DELETE FROM cart_items WHERE user_id = ? AND product_id = ?",
                 (g.user["user_id"], product_id))
    conn.commit()
    conn.close()
    flash("Item removed from your cart.", "info")
    return redirect(url_for("customer.cart"))


# =====================================================================
#  CHECKOUT, PAYMENT, ORDERS
# =====================================================================

def get_checkout_items(conn):
    return conn.execute(
        """SELECT c.product_id, c.quantity, p.name, p.price, p.stock, sp.store_name
           FROM cart_items c
           JOIN products p ON p.product_id = c.product_id
           JOIN seller_profiles sp ON sp.seller_id = p.seller_id
           WHERE c.user_id = ?
           ORDER BY p.name""", (g.user["user_id"],)).fetchall()


def cart_problem(items):
    """Returns a message if the cart can't be checked out right now, else None."""
    if not items:
        return "Your cart is empty."
    for it in items:
        if it["stock"] == 0:
            return f"'{it['name']}' is out of stock. Please remove it from your cart."
        if it["quantity"] > it["stock"]:
            return f"Only {it['stock']} of '{it['name']}' left. Please update your cart."
    return None


def validate_payment(method, form):
    """Simulated payment. We only check the FORMAT. Card details are never stored."""
    if method == "card":
        number = re.sub(r"[\s-]", "", form.get("card_number", ""))
        if not re.fullmatch(r"\d{16}", number):
            return "Enter a valid 16-digit card number."
        if not re.fullmatch(r"(0[1-9]|1[0-2])/\d{2}", form.get("expiry", "").strip()):
            return "Expiry must be in MM/YY format."
        if not re.fullmatch(r"\d{3}", form.get("cvv", "").strip()):
            return "CVV must be 3 digits."
    elif method == "upi":
        if not re.fullmatch(r"[\w.\-]{2,}@\w{2,}", form.get("upi_id", "").strip()):
            return "Enter a valid UPI ID, like name@bank."
    return None


def place_order(conn, user, address, method):
    """THE TRANSACTION. Everything below commits together or not at all.
    Raises ValueError with a friendly message if something is wrong."""
    conn.execute("BEGIN IMMEDIATE")          # lock the DB so nobody else changes stock mid-checkout
    try:
        items = conn.execute(
            """SELECT c.product_id, c.quantity, p.name, p.price, p.stock,
                      p.seller_id, sp.store_name
               FROM cart_items c
               JOIN products p ON p.product_id = c.product_id
               JOIN seller_profiles sp ON sp.seller_id = p.seller_id
               WHERE c.user_id = ?""", (user["user_id"],)).fetchall()

        if not items:
            raise ValueError("Your cart is empty.")

        total = 0
        for it in items:
            if it["quantity"] > it["stock"]:
                raise ValueError(f"Not enough stock for '{it['name']}' "
                                 f"(only {it['stock']} left). Nothing was charged.")
            total += it["price"] * it["quantity"]   # price comes from the DB, never the browser
        total = round(total, 2)

        cur = conn.execute(
            "INSERT INTO orders (user_id, customer_name, shipping_address, total_amount) "
            "VALUES (?, ?, ?, ?)", (user["user_id"], user["name"], address, total))
        order_id = cur.lastrowid

        for it in items:
            # Atomic stock reduction: only succeeds if enough stock is still there.
            res = conn.execute(
                "UPDATE products SET stock = stock - ? WHERE product_id = ? AND stock >= ?",
                (it["quantity"], it["product_id"], it["quantity"]))
            if res.rowcount != 1:
                raise ValueError(f"'{it['name']}' just sold out. Nothing was charged.")

            # Snapshot name, price and seller name, so history survives deletions.
            conn.execute(
                """INSERT INTO order_items
                   (order_id, product_id, seller_id, product_name, seller_name,
                    unit_price, quantity)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (order_id, it["product_id"], it["seller_id"], it["name"],
                 it["store_name"], it["price"], it["quantity"]))

        if method == "cod":
            conn.execute("INSERT INTO payments (order_id, method, amount, status) "
                         "VALUES (?, 'cod', ?, 'pending')", (order_id, total))
        else:
            conn.execute("INSERT INTO payments (order_id, method, amount, status, paid_at) "
                         "VALUES (?, ?, ?, 'success', CURRENT_TIMESTAMP)",
                         (order_id, method, total))

        conn.execute("DELETE FROM cart_items WHERE user_id = ?", (user["user_id"],))
        conn.commit()
        return order_id
    except Exception:
        conn.rollback()      # undo EVERYTHING: order, items, stock changes, payment
        raise


@customer_bp.route("/checkout", methods=["GET", "POST"])
@login_required("customer")
def checkout():
    conn = get_connection()
    items = get_checkout_items(conn)
    conn.close()

    problem = cart_problem(items)
    if problem:
        flash(problem, "warning")
        return redirect(url_for("customer.cart"))

    total = round(sum(i["price"] * i["quantity"] for i in items), 2)

    if request.method == "POST":
        address = request.form.get("address", "").strip()
        method = request.form.get("method", "")
        errors = []
        if len(address) < 10:
            errors.append("Please enter a full shipping address (at least 10 characters).")
        if method not in ("card", "upi", "cod"):
            errors.append("Please choose a payment method.")
        if errors:
            for e in errors:
                flash(e, "danger")
            return render_template("checkout.html", items=items, total=total,
                                   values=request.form)

        session["checkout"] = {"address": address, "method": method}
        return redirect(url_for("customer.payment"))

    return render_template("checkout.html", items=items, total=total,
                           values=session.get("checkout", {}))


@customer_bp.route("/payment", methods=["GET", "POST"])
@login_required("customer")
def payment():
    info = session.get("checkout")
    if not info:
        flash("Please enter your delivery details first.", "warning")
        return redirect(url_for("customer.checkout"))

    conn = get_connection()
    try:
        items = get_checkout_items(conn)
        problem = cart_problem(items)
        if problem:
            flash(problem, "warning")
            return redirect(url_for("customer.cart"))
        total = round(sum(i["price"] * i["quantity"] for i in items), 2)

        if request.method == "POST":
            if request.form.get("action") == "fail":
                flash("Payment failed (simulated). You were not charged and no order "
                      "was created. Your cart is unchanged.", "danger")
                return redirect(url_for("customer.payment"))

            error = validate_payment(info["method"], request.form)
            if error:
                flash(error, "danger")
                return render_template("payment.html", total=total, method=info["method"])

            try:
                order_id = place_order(conn, g.user, info["address"], info["method"])
            except ValueError as e:
                flash(str(e), "danger")
                return redirect(url_for("customer.cart"))
            except sqlite3.Error:
                flash("Something went wrong while placing your order. "
                      "Nothing was charged. Please try again.", "danger")
                return redirect(url_for("customer.cart"))

            session.pop("checkout", None)
            flash(f"Order #{order_id} placed successfully. Thank you for shopping!", "success")
            return redirect(url_for("customer.order_detail", order_id=order_id))

        return render_template("payment.html", total=total, method=info["method"])
    finally:
        conn.close()


@customer_bp.route("/orders")
@login_required("customer")
def orders():
    conn = get_connection()
    rows = conn.execute(
        """SELECT o.order_id, o.placed_at, o.total_amount,
                  p.method, p.status AS payment_status,
                  (SELECT COUNT(*) FROM order_items oi
                    WHERE oi.order_id = o.order_id) AS item_count,
                  (SELECT GROUP_CONCAT(oi.status) FROM order_items oi
                    WHERE oi.order_id = o.order_id) AS statuses
           FROM orders o
           LEFT JOIN payments p ON p.order_id = o.order_id
           WHERE o.user_id = ?
           ORDER BY o.order_id DESC""", (g.user["user_id"],)).fetchall()
    conn.close()

    orders_list = []
    for r in rows:
        d = dict(r)
        d["status"] = order_status(d["statuses"].split(","))
        orders_list.append(d)
    return render_template("orders.html", orders=orders_list)


@customer_bp.route("/orders/<int:order_id>")
@login_required("customer")
def order_detail(order_id):
    conn = get_connection()
    order = conn.execute(
        """SELECT o.*, p.method, p.status AS payment_status, p.paid_at
           FROM orders o LEFT JOIN payments p ON p.order_id = o.order_id
           WHERE o.order_id = ? AND o.user_id = ?""",     # you can only see YOUR orders
        (order_id, g.user["user_id"])).fetchone()
    if order is None:
        conn.close()
        flash("Order not found.", "danger")
        return redirect(url_for("customer.orders"))

    items = conn.execute("SELECT * FROM order_items WHERE order_id = ? ORDER BY order_item_id",
                         (order_id,)).fetchall()
    conn.close()

    status = order_status([i["status"] for i in items])
    refunded = sum(i["unit_price"] * i["quantity"] for i in items if i["status"] == "cancelled")
    return render_template("order_detail.html", order=order, items=items,
                           status=status, refunded=refunded)


@customer_bp.route("/orders/item/<int:item_id>/cancel", methods=["POST"])
@login_required("customer")
def cancel_item(item_id):
    conn = get_connection()
    try:
        ok = cancel_order_item(conn, item_id, customer_id=g.user["user_id"])
    finally:
        conn.close()
    if ok:
        flash("Item cancelled. The amount will be refunded and the stock restored.", "info")
    else:
        flash("That item can't be cancelled (it may already be shipped).", "warning")
    return redirect_back("customer.orders")


# =====================================================================
#  REVIEWS
# =====================================================================

@customer_bp.route("/product/<int:product_id>/review", methods=["POST"])
@login_required("customer")
def submit_review(product_id):
    try:
        rating = int(request.form.get("rating", ""))
    except ValueError:
        rating = 0
    comment = request.form.get("comment", "").strip()

    errors = []
    if rating < 1 or rating > 5:
        errors.append("Please choose a rating from 1 to 5 stars.")
    if len(comment) > 1000:
        errors.append("Your review must be 1000 characters or fewer.")
    if errors:
        for e in errors:
            flash(e, "danger")
        return redirect(url_for("customer.product_detail", product_id=product_id))

    conn = get_connection()
    try:
        product = conn.execute("SELECT 1 FROM products WHERE product_id = ?",
                               (product_id,)).fetchone()
        if product is None:
            flash("That product no longer exists.", "warning")
            return redirect(url_for("home"))

        # The server enforces this. Hiding the form in the page is only cosmetic.
        if not has_delivered_purchase(conn, g.user["user_id"], product_id):
            flash("You can review a product only after your order for it is delivered.", "warning")
            return redirect(url_for("customer.product_detail", product_id=product_id))

        existing = conn.execute(
            "SELECT 1 FROM reviews WHERE product_id = ? AND user_id = ?",
            (product_id, g.user["user_id"])).fetchone()

        # "Upsert": insert, or update if this customer already reviewed this product
        # (relies on UNIQUE(product_id, user_id) from schema.sql).
        conn.execute(
            """INSERT INTO reviews (product_id, user_id, rating, comment)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(product_id, user_id)
               DO UPDATE SET rating = excluded.rating,
                             comment = excluded.comment,
                             created_at = CURRENT_TIMESTAMP""",
            (product_id, g.user["user_id"], rating, comment))
        conn.commit()
        flash("Your review was updated." if existing else "Thanks for your review!", "success")
    finally:
        conn.close()
    return redirect(url_for("customer.product_detail", product_id=product_id))


@customer_bp.route("/product/<int:product_id>/review/delete", methods=["POST"])
@login_required("customer")
def delete_review(product_id):
    conn = get_connection()
    res = conn.execute("DELETE FROM reviews WHERE product_id = ? AND user_id = ?",
                       (product_id, g.user["user_id"]))     # only YOUR review can match
    conn.commit()
    conn.close()
    flash("Your review was deleted." if res.rowcount else "Review not found.",
          "info" if res.rowcount else "warning")
    return redirect(url_for("customer.product_detail", product_id=product_id))


# =====================================================================
#  COMPLAINTS
# =====================================================================

@customer_bp.route("/complaints")
@login_required("customer")
def complaints():
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM complaints WHERE user_id = ? ORDER BY complaint_id DESC",
        (g.user["user_id"],)).fetchall()
    conn.close()
    return render_template("complaints.html", complaints=rows)


@customer_bp.route("/complaints/new", methods=["GET", "POST"])
@login_required("customer")
def new_complaint():
    conn = get_connection()
    my_orders = conn.execute(
        "SELECT order_id, placed_at, total_amount FROM orders "
        "WHERE user_id = ? ORDER BY order_id DESC", (g.user["user_id"],)).fetchall()

    if request.method == "POST":
        subject = request.form.get("subject", "").strip()
        message = request.form.get("message", "").strip()
        order_raw = request.form.get("order_id", "")

        errors = []
        if not (3 <= len(subject) <= 100):
            errors.append("Subject must be between 3 and 100 characters.")
        if not (10 <= len(message) <= 1000):
            errors.append("Please describe the problem in 10 to 1000 characters.")

        order_id = None
        if order_raw != "":
            # The order must exist AND belong to this customer.
            valid = order_raw.isdigit() and any(o["order_id"] == int(order_raw) for o in my_orders)
            if valid:
                order_id = int(order_raw)
            else:
                errors.append("Please choose one of your own orders (or leave it blank).")

        if errors:
            for e in errors:
                flash(e, "danger")
            conn.close()
            return render_template("complaint_form.html", orders=my_orders,
                                   values=request.form)

        conn.execute(
            "INSERT INTO complaints (user_id, order_id, subject, message) VALUES (?, ?, ?, ?)",
            (g.user["user_id"], order_id, subject, message))
        conn.commit()
        conn.close()
        flash("Your complaint was submitted. We'll look into it.", "success")
        return redirect(url_for("customer.complaints"))

    conn.close()
    return render_template("complaint_form.html", orders=my_orders,
                           values={"order_id": request.args.get("order_id", "")})