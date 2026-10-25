from flask import Blueprint, render_template, request, redirect, url_for, flash
from db import get_connection
from helpers import login_required

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


# =====================================================================
#  DASHBOARD
# =====================================================================
@admin_bp.route("/dashboard")
@login_required("admin")
def dashboard():
    conn = get_connection()

    def one(sql):
        return conn.execute(sql).fetchone()[0]

    stats = {
        "customers": one("SELECT COUNT(*) FROM users WHERE role = 'customer'"),
        "deactivated": one("SELECT COUNT(*) FROM users WHERE role = 'customer' AND is_active = 0"),
        "sellers": one("SELECT COUNT(*) FROM users WHERE role = 'seller'"),
        "products": one("SELECT COUNT(*) FROM products"),
        "orders": one("SELECT COUNT(*) FROM orders"),
        "revenue": one("SELECT COALESCE(SUM(unit_price * quantity), 0) FROM order_items "
                       "WHERE status != 'cancelled'"),
        "reviews": one("SELECT COUNT(*) FROM reviews"),
        "open_complaints": one("SELECT COUNT(*) FROM complaints WHERE status = 'open'"),
    }
    recent = conn.execute(
        "SELECT order_id, customer_name, total_amount, placed_at "
        "FROM orders ORDER BY order_id DESC LIMIT 5").fetchall()
    conn.close()
    return render_template("admin/dashboard.html", stats=stats, recent=recent)


# =====================================================================
#  USERS (customers can be deactivated / reactivated)
# =====================================================================
@admin_bp.route("/users")
@login_required("admin")
def users():
    q = request.args.get("q", "").strip()
    role = request.args.get("role", "")

    sql = """SELECT u.user_id, u.name, u.email, u.role, u.is_active, u.created_at,
                    (SELECT COUNT(*) FROM orders o WHERE o.user_id = u.user_id) AS order_count
             FROM users u WHERE 1 = 1"""
    params = []
    if q:
        sql += " AND (u.name LIKE ? OR u.email LIKE ?)"
        params += [f"%{q}%"] * 2
    if role in ("customer", "seller", "admin"):
        sql += " AND u.role = ?"
        params.append(role)
    sql += " ORDER BY u.user_id"

    conn = get_connection()
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return render_template("admin/users.html", rows=rows, q=q, role=role)


@admin_bp.route("/users/<int:user_id>/toggle", methods=["POST"])
@login_required("admin")
def toggle_user(user_id):
    conn = get_connection()
    user = conn.execute("SELECT user_id, name, role, is_active FROM users WHERE user_id = ?",
                        (user_id,)).fetchone()
    if user is None:
        flash("User not found.", "warning")
    elif user["role"] != "customer":
        flash("Only customer accounts can be deactivated here. "
              "Sellers are managed on the Sellers page.", "warning")
    else:
        new_state = 0 if user["is_active"] else 1
        conn.execute("UPDATE users SET is_active = ? WHERE user_id = ?", (new_state, user_id))
        conn.commit()
        if new_state:
            flash(f"{user['name']} was reactivated and can log in again.", "success")
        else:
            flash(f"{user['name']} was deactivated. They are logged out and cannot log in. "
                  "Their orders and reviews are kept.", "info")
    conn.close()
    return redirect(request.referrer or url_for("admin.users"))


# =====================================================================
#  SELLERS (view stats, delete with confirmation)
# =====================================================================
@admin_bp.route("/sellers")
@login_required("admin")
def sellers():
    q = request.args.get("q", "").strip()
    sql = """
        SELECT u.user_id, u.name, u.email, u.created_at, sp.store_name,
               (SELECT COUNT(*) FROM products p WHERE p.seller_id = u.user_id) AS product_count,
               (SELECT COALESCE(SUM(oi.quantity), 0) FROM order_items oi
                 WHERE oi.seller_id = u.user_id AND oi.status != 'cancelled') AS units_sold,
               (SELECT COALESCE(SUM(oi.unit_price * oi.quantity), 0) FROM order_items oi
                 WHERE oi.seller_id = u.user_id AND oi.status != 'cancelled') AS revenue,
               (SELECT COUNT(*) FROM order_items oi
                 WHERE oi.seller_id = u.user_id
                   AND oi.status IN ('placed', 'shipped')) AS open_lines
        FROM users u
        JOIN seller_profiles sp ON sp.seller_id = u.user_id
        WHERE u.role = 'seller'
    """
    params = []
    if q:
        sql += " AND (sp.store_name LIKE ? OR u.name LIKE ? OR u.email LIKE ?)"
        params += [f"%{q}%"] * 3
    sql += " ORDER BY sp.store_name"

    conn = get_connection()
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return render_template("admin/sellers.html", rows=rows, q=q)


def seller_impact(conn, seller_id):
    """Counts what deleting this seller will remove, and what will be kept."""
    def one(sql):
        return conn.execute(sql, (seller_id,)).fetchone()[0]

    return {
        "products": one("SELECT COUNT(*) FROM products WHERE seller_id = ?"),
        "cart_rows": one("SELECT COUNT(*) FROM cart_items WHERE product_id IN "
                         "(SELECT product_id FROM products WHERE seller_id = ?)"),
        "cart_customers": one("SELECT COUNT(DISTINCT user_id) FROM cart_items WHERE product_id IN "
                              "(SELECT product_id FROM products WHERE seller_id = ?)"),
        "reviews": one("SELECT COUNT(*) FROM reviews WHERE product_id IN "
                       "(SELECT product_id FROM products WHERE seller_id = ?)"),
        "order_lines": one("SELECT COUNT(*) FROM order_items WHERE seller_id = ?"),
        "open_lines": one("SELECT COUNT(*) FROM order_items WHERE seller_id = ? "
                          "AND status IN ('placed', 'shipped')"),
    }


@admin_bp.route("/sellers/<int:seller_id>/delete", methods=["GET", "POST"])
@login_required("admin")
def delete_seller(seller_id):
    conn = get_connection()
    seller = conn.execute(
        """SELECT u.user_id, u.name, u.email, sp.store_name
           FROM users u JOIN seller_profiles sp ON sp.seller_id = u.user_id
           WHERE u.user_id = ? AND u.role = 'seller'""", (seller_id,)).fetchone()
    if seller is None:
        conn.close()
        flash("Seller not found (it may already be deleted).", "warning")
        return redirect(url_for("admin.sellers"))

    impact = seller_impact(conn, seller_id)

    if request.method == "POST":
        if request.form.get("confirm_name", "").strip() != seller["store_name"]:
            conn.close()
            flash("The store name you typed doesn't match. Nothing was deleted.", "danger")
            return redirect(url_for("admin.delete_seller", seller_id=seller_id))

        # ONE statement does it all. The database cascades:
        #   users -> seller_profiles -> products -> cart_items + reviews
        # and order_items.seller_id / product_id become NULL (history is kept).
        conn.execute("DELETE FROM users WHERE user_id = ? AND role = 'seller'", (seller_id,))
        conn.commit()
        conn.close()
        flash(f"Seller '{seller['store_name']}' was deleted, with {impact['products']} product(s), "
              f"{impact['cart_rows']} cart entr(ies) and {impact['reviews']} review(s). "
              f"{impact['order_lines']} order line(s) were kept in customers' order history.", "info")
        return redirect(url_for("admin.sellers"))

    conn.close()
    return render_template("admin/seller_delete.html", seller=seller, impact=impact)


# =====================================================================
#  PRODUCTS (delete any product)
# =====================================================================
@admin_bp.route("/products")
@login_required("admin")
def products():
    q = request.args.get("q", "").strip()
    sql = """
        SELECT p.product_id, p.name, p.price, p.stock, sp.store_name, c.name AS category,
               (SELECT COUNT(*) FROM cart_items ci WHERE ci.product_id = p.product_id) AS in_carts,
               (SELECT COUNT(*) FROM order_items oi WHERE oi.product_id = p.product_id) AS order_lines
        FROM products p
        JOIN seller_profiles sp ON sp.seller_id = p.seller_id
        LEFT JOIN categories c ON c.category_id = p.category_id
        WHERE 1 = 1
    """
    params = []
    if q:
        sql += " AND (p.name LIKE ? OR sp.store_name LIKE ?)"
        params += [f"%{q}%"] * 2
    sql += " ORDER BY p.product_id DESC"

    conn = get_connection()
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return render_template("admin/products.html", rows=rows, q=q)


@admin_bp.route("/products/<int:product_id>/delete", methods=["POST"])
@login_required("admin")
def delete_product(product_id):
    conn = get_connection()
    product = conn.execute("SELECT name FROM products WHERE product_id = ?",
                           (product_id,)).fetchone()
    if product is None:
        flash("Product not found (it may already be deleted).", "warning")
    else:
        carts = conn.execute("SELECT COUNT(*) FROM cart_items WHERE product_id = ?",
                             (product_id,)).fetchone()[0]
        # Cascades: cart_items and reviews are removed; order_items keeps its snapshot.
        conn.execute("DELETE FROM products WHERE product_id = ?", (product_id,))
        conn.commit()
        flash(f"'{product['name']}' was deleted. It was removed from {carts} cart entr(ies). "
              "Placed orders are unaffected.", "info")
    conn.close()
    return redirect(request.referrer or url_for("admin.products"))


# =====================================================================
#  REVIEWS (moderation)
# =====================================================================
@admin_bp.route("/reviews")
@login_required("admin")
def reviews():
    rating = request.args.get("rating", "")
    sql = """
        SELECT r.review_id, r.rating, r.comment, r.created_at,
               u.name AS reviewer, p.product_id, p.name AS product_name, sp.store_name
        FROM reviews r
        JOIN users u ON u.user_id = r.user_id
        JOIN products p ON p.product_id = r.product_id
        JOIN seller_profiles sp ON sp.seller_id = p.seller_id
        WHERE 1 = 1
    """
    params = []
    if rating in ("1", "2", "3", "4", "5"):
        sql += " AND r.rating = ?"
        params.append(int(rating))
    sql += " ORDER BY r.review_id DESC"

    conn = get_connection()
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return render_template("admin/reviews.html", rows=rows, rating=rating)


@admin_bp.route("/reviews/<int:review_id>/delete", methods=["POST"])
@login_required("admin")
def delete_review(review_id):
    conn = get_connection()
    res = conn.execute("DELETE FROM reviews WHERE review_id = ?", (review_id,))
    conn.commit()
    conn.close()
    flash("Review deleted." if res.rowcount else "Review not found.",
          "info" if res.rowcount else "warning")
    return redirect(request.referrer or url_for("admin.reviews"))


# =====================================================================
#  COMPLAINTS
# =====================================================================
@admin_bp.route("/complaints")
@login_required("admin")
def complaints():
    status = request.args.get("status", "")
    sql = """
        SELECT c.complaint_id, c.subject, c.status, c.created_at, c.order_id,
               u.name AS customer_name
        FROM complaints c JOIN users u ON u.user_id = c.user_id
        WHERE 1 = 1
    """
    params = []
    if status in ("open", "resolved", "rejected"):
        sql += " AND c.status = ?"
        params.append(status)
    sql += " ORDER BY CASE c.status WHEN 'open' THEN 0 ELSE 1 END, c.complaint_id DESC"

    conn = get_connection()
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return render_template("admin/complaints.html", rows=rows, status=status)


@admin_bp.route("/complaints/<int:complaint_id>", methods=["GET", "POST"])
@login_required("admin")
def complaint_detail(complaint_id):
    conn = get_connection()
    complaint = conn.execute(
        """SELECT c.*, u.name AS customer_name, u.email AS customer_email
           FROM complaints c JOIN users u ON u.user_id = c.user_id
           WHERE c.complaint_id = ?""", (complaint_id,)).fetchone()
    if complaint is None:
        conn.close()
        flash("Complaint not found.", "warning")
        return redirect(url_for("admin.complaints"))

    if request.method == "POST":
        new_status = request.form.get("status", "")
        response = request.form.get("admin_response", "").strip()

        errors = []
        if new_status not in ("open", "resolved", "rejected"):
            errors.append("Please choose a valid status.")
        if len(response) > 1000:
            errors.append("The response must be 1000 characters or fewer.")
        if new_status in ("resolved", "rejected") and not response:
            errors.append("Please write a response before resolving or rejecting.")

        if errors:
            for e in errors:
                flash(e, "danger")
        else:
            conn.execute("UPDATE complaints SET status = ?, admin_response = ? "
                         "WHERE complaint_id = ?",
                         (new_status, response or None, complaint_id))
            conn.commit()
            conn.close()
            flash("Complaint updated.", "success")
            return redirect(url_for("admin.complaints"))

    order_items = []
    if complaint["order_id"]:
        order_items = conn.execute(
            "SELECT * FROM order_items WHERE order_id = ? ORDER BY order_item_id",
            (complaint["order_id"],)).fetchall()
    conn.close()
    return render_template("admin/complaint_detail.html", c=complaint, order_items=order_items)

# =====================================================================
#  ADMIN ANALYTICS
# =====================================================================
from analytics import parse_days, admin_report, DAY_OPTIONS


@admin_bp.route("/analytics")
@login_required("admin")
def analytics():
    days = parse_days(request.args.get("days"))
    conn = get_connection()
    report = admin_report(conn, days)
    conn.close()
    return render_template("admin/analytics.html", r=report, days=days, options=DAY_OPTIONS)