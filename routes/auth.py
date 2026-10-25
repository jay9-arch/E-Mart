import sqlite3
from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from werkzeug.security import generate_password_hash, check_password_hash
from db import get_connection

auth_bp = Blueprint("auth", __name__)


def redirect_by_role(role):
    if role == "seller":
        return redirect(url_for("seller.dashboard"))
    if role == "admin":
        return redirect(url_for("admin.dashboard"))
    return redirect(url_for("home"))


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        role = request.form.get("role", "customer")
        store_name = request.form.get("store_name", "").strip()
        store_desc = request.form.get("store_description", "").strip()

        if role not in ("customer", "seller"):   # nobody can self-register as admin
            role = "customer"

        errors = []
        if not name:
            errors.append("Name is required.")
        if "@" not in email:
            errors.append("Enter a valid email.")
        if len(password) < 6:
            errors.append("Password must be at least 6 characters.")
        if role == "seller" and not store_name:
            errors.append("Store name is required for sellers.")

        if errors:
            for e in errors:
                flash(e, "danger")
            return render_template("register.html", form=request.form)

        conn = get_connection()
        try:
            # Both inserts form ONE transaction: either both succeed or neither does.
            cur = conn.execute(
                "INSERT INTO users (name, email, password_hash, role) VALUES (?, ?, ?, ?)",
                (name, email, generate_password_hash(password), role))
            if role == "seller":
                conn.execute(
                    "INSERT INTO seller_profiles (seller_id, store_name, description) "
                    "VALUES (?, ?, ?)", (cur.lastrowid, store_name, store_desc))
            conn.commit()
        except sqlite3.IntegrityError as err:
            conn.rollback()
            if "users.email" in str(err):
                flash("That email is already registered.", "danger")
            elif "store_name" in str(err):
                flash("That store name is already taken.", "danger")
            else:
                flash("Could not register. Please check your details.", "danger")
            return render_template("register.html", form=request.form)
        finally:
            conn.close()

        flash("Account created! Please log in.", "success")
        return redirect(url_for("auth.login"))

    return render_template("register.html", form={})


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        conn = get_connection()
        user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        conn.close()

        if user is None or not check_password_hash(user["password_hash"], password):
            flash("Invalid email or password.", "danger")
        elif not user["is_active"]:
            flash("This account has been deactivated. Contact admin.", "danger")
        else:
            session.clear()
            session["user_id"] = user["user_id"]
            flash(f"Welcome back, {user['name']}!", "success")
            return redirect_by_role(user["role"])

    return render_template("login.html")


@auth_bp.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("home"))