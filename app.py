import hmac
import os
import secrets
import sqlite3
from datetime import timedelta
from flask import Flask, render_template, session, g, request, abort
from db import get_connection
from routes.auth import auth_bp
from routes.seller import seller_bp
from routes.admin import admin_bp
from routes.customer import customer_bp

app = Flask(__name__)
# In real deployments the key comes from an environment variable, never from the code.
app.secret_key = os.environ.get("EMART_SECRET_KEY", "emart-change-this-to-any-long-random-text")
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,            # JavaScript can't read the login cookie
    SESSION_COOKIE_SAMESITE="Lax",           # cookie isn't sent on cross-site POSTs
    PERMANENT_SESSION_LIFETIME=timedelta(hours=8),   # auto-logout after 8 idle hours
)

app.register_blueprint(auth_bp)
app.register_blueprint(seller_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(customer_bp)


# ---------------------------------------------------------------- CSRF
def get_csrf_token():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(16)
    return session["csrf_token"]


@app.before_request
def csrf_protect():
    """Every POST must carry the secret token stored in the user's session.
    A malicious site can't read that token, so it can't forge a valid POST."""
    session.permanent = True
    if request.method == "POST":
        sent = request.form.get("csrf_token", "")
        expected = session.get("csrf_token", "")
        if not expected or not hmac.compare_digest(sent, expected):
            abort(400)


@app.context_processor
def inject_csrf():
    return {"csrf_token": get_csrf_token()}


# ------------------------------------------------------- who is logged in
@app.before_request
def load_logged_in_user():
    g.user = None
    user_id = session.get("user_id")
    if user_id is not None:
        conn = get_connection()
        user = conn.execute(
            "SELECT user_id, name, email, role, is_active FROM users WHERE user_id = ?",
            (user_id,)).fetchone()
        conn.close()
        if user is None or not user["is_active"]:
            session.pop("user_id", None)
        else:
            g.user = user


@app.context_processor
def inject_cart_count():
    """Makes `cart_count` available in every template (navbar badge)."""
    count = 0
    try:
        if g.get("user") is not None and g.user["role"] == "customer":
            conn = get_connection()
            count = conn.execute(
                "SELECT COALESCE(SUM(quantity), 0) FROM cart_items WHERE user_id = ?",
                (g.user["user_id"],)).fetchone()[0]
            conn.close()
    except sqlite3.Error:
        count = 0          # an error page must never crash because of the navbar
    return {"cart_count": count}


# ------------------------------------------------------------ error pages
@app.errorhandler(400)
def bad_request(e):
    return render_template(
        "error.html", code=400, title="Request expired",
        message="Your form was invalid or has expired. Go back, refresh the page and try again."), 400


@app.errorhandler(404)
def not_found(e):
    return render_template(
        "error.html", code=404, title="Page not found",
        message="We couldn't find the page you were looking for."), 404


@app.errorhandler(500)
def server_error(e):
    return render_template(
        "error.html", code=500, title="Something went wrong",
        message="An unexpected error occurred. Nothing was lost. Please try again."), 500


# ------------------------------------------------------------------- home
@app.route("/")
def home():
    q = request.args.get("q", "").strip()
    category = request.args.get("category", "")
    sort = request.args.get("sort", "newest")
    in_stock = request.args.get("in_stock")

    sql = """
        SELECT p.product_id, p.name, p.description, p.price, p.stock,
               sp.store_name, c.name AS category,
               (SELECT ROUND(AVG(rating), 1) FROM reviews r
                 WHERE r.product_id = p.product_id) AS avg_rating,
               (SELECT COUNT(*) FROM reviews r
                 WHERE r.product_id = p.product_id) AS review_count
        FROM products p
        JOIN seller_profiles sp ON sp.seller_id = p.seller_id
        LEFT JOIN categories c ON c.category_id = p.category_id
        WHERE 1 = 1
    """
    params = []
    if q:
        sql += " AND (p.name LIKE ? OR p.description LIKE ? OR sp.store_name LIKE ?)"
        params += [f"%{q}%"] * 3
    if category.isdigit():
        sql += " AND p.category_id = ?"
        params.append(int(category))
    if in_stock:
        sql += " AND p.stock > 0"

    # ORDER BY can't use ? placeholders, so we pick from a fixed whitelist.
    order_options = {
        "newest": "p.product_id DESC",
        "price_asc": "p.price ASC",
        "price_desc": "p.price DESC",
        "rating": "avg_rating DESC",
    }
    sql += " ORDER BY " + order_options.get(sort, order_options["newest"])

    conn = get_connection()
    products = conn.execute(sql, params).fetchall()
    categories = conn.execute("SELECT category_id, name FROM categories ORDER BY name").fetchall()
    conn.close()

    return render_template("home.html", products=products, categories=categories,
                           q=q, category=category, sort=sort, in_stock=in_stock)


if __name__ == "__main__":
    app.run(debug=True)