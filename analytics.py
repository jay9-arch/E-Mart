"""All analytics queries. Each report returns plain dicts and lists,
ready to be shown in a template or turned into chart data."""

from datetime import date, timedelta

DAY_OPTIONS = (7, 30, 90, 0)          # 0 means "all time"

FROM_ITEMS = "FROM order_items oi JOIN orders o ON o.order_id = oi.order_id"
LIVE = "oi.status != 'cancelled'"     # cancelled lines never count as sales

STATUS_ORDER = ["placed", "shipped", "delivered", "cancelled"]


def parse_days(raw):
    try:
        d = int(raw)
    except (TypeError, ValueError):
        return 30
    return d if d in DAY_OPTIONS else 30


def range_clause(days):
    """SQL fragment limiting orders to the last N calendar days (today included)."""
    if days:
        return " AND o.placed_at >= date('now', ?)", [f"-{days - 1} days"]
    return "", []


def _where(scope_sql, scope_params, days):
    clause, extra = range_clause(days)
    return f"WHERE {scope_sql}{clause}", list(scope_params) + extra


def _chart(rows):
    return {"labels": [r["label"] for r in rows],
            "values": [round(r["value"], 2) for r in rows]}


def _daily(conn, where, params, days):
    rows = conn.execute(
        f"""SELECT date(o.placed_at) AS day, SUM(oi.unit_price * oi.quantity) AS revenue
            {FROM_ITEMS} {where} AND {LIVE}
            GROUP BY day ORDER BY day""", params).fetchall()
    data = {r["day"]: round(r["revenue"], 2) for r in rows}

    if days:   # fixed range: show every day, even those with no sales
        today = date.fromisoformat(conn.execute("SELECT date('now')").fetchone()[0])
        labels = [(today - timedelta(days=i)).isoformat() for i in range(days - 1, -1, -1)]
    else:      # all time: only days that had sales
        labels = sorted(data)
    return {"labels": labels, "values": [data.get(d, 0) for d in labels]}


def common_report(conn, scope_sql, scope_params, days):
    """Numbers and charts shared by the seller and admin pages.
    scope_sql limits the rows: 'oi.seller_id = ?' for a seller, '1 = 1' for everyone."""
    where, params = _where(scope_sql, scope_params, days)

    k = conn.execute(
        f"""SELECT COALESCE(SUM(CASE WHEN {LIVE} THEN oi.unit_price * oi.quantity END), 0) AS revenue,
                   COALESCE(SUM(CASE WHEN {LIVE} THEN oi.quantity END), 0)                  AS units,
                   COUNT(DISTINCT CASE WHEN {LIVE} THEN oi.order_id END)                    AS orders,
                   COALESCE(SUM(CASE WHEN oi.status = 'cancelled' THEN 1 END), 0)           AS cancelled
            {FROM_ITEMS} {where}""", params).fetchone()
    revenue = round(k["revenue"], 2)
    kpis = {"revenue": revenue, "units": k["units"], "orders": k["orders"],
            "cancelled": k["cancelled"],
            "avg_order": round(revenue / k["orders"], 2) if k["orders"] else 0}

    top = conn.execute(
        f"""SELECT oi.product_name AS label, SUM(oi.unit_price * oi.quantity) AS value
            {FROM_ITEMS} {where} AND {LIVE}
            GROUP BY oi.product_name ORDER BY value DESC LIMIT 5""", params).fetchall()

    categories = conn.execute(
        f"""SELECT COALESCE(c.name, 'Other / removed') AS label,
                   SUM(oi.unit_price * oi.quantity) AS value
            {FROM_ITEMS}
            LEFT JOIN products p   ON p.product_id = oi.product_id
            LEFT JOIN categories c ON c.category_id = p.category_id
            {where} AND {LIVE}
            GROUP BY label ORDER BY value DESC""", params).fetchall()

    status_rows = conn.execute(
        f"""SELECT oi.status AS label, COUNT(*) AS value
            {FROM_ITEMS} {where} GROUP BY oi.status""", params).fetchall()
    counts = {r["label"]: r["value"] for r in status_rows}
    present = [s for s in STATUS_ORDER if s in counts]

    charts = {
        "daily": _daily(conn, where, params, days),
        "top": _chart(top),
        "categories": _chart(categories),
        "statuses": {"labels": [s.capitalize() for s in present],
                     "values": [counts[s] for s in present]},
    }
    return {"kpis": kpis, "charts": charts}


def seller_report(conn, seller_id, days):
    rep = common_report(conn, "oi.seller_id = ?", [seller_id], days)

    # Per-product table (lifetime numbers): correlated subqueries.
    products = [dict(r) for r in conn.execute(
        """SELECT p.product_id, p.name, p.price, p.stock,
                  COALESCE((SELECT SUM(oi.quantity) FROM order_items oi
                             WHERE oi.product_id = p.product_id
                               AND oi.status != 'cancelled'), 0) AS units,
                  COALESCE((SELECT SUM(oi.unit_price * oi.quantity) FROM order_items oi
                             WHERE oi.product_id = p.product_id
                               AND oi.status != 'cancelled'), 0) AS revenue,
                  (SELECT ROUND(AVG(r.rating), 1) FROM reviews r
                    WHERE r.product_id = p.product_id) AS avg_rating,
                  (SELECT COUNT(*) FROM reviews r
                    WHERE r.product_id = p.product_id) AS review_count
           FROM products p
           WHERE p.seller_id = ?
           ORDER BY revenue DESC, p.name""", (seller_id,))]

    rep["products"] = products
    rep["low_stock"] = sorted((p for p in products if p["stock"] <= 5),
                              key=lambda p: p["stock"])
    return rep


def admin_report(conn, days):
    rep = common_report(conn, "1 = 1", [], days)
    where, params = _where("1 = 1", [], days)

    # Grouped by the SNAPSHOT name, so sales of a deleted seller still show up.
    sellers = conn.execute(
        f"""SELECT CASE WHEN COUNT(oi.seller_id) = 0
                        THEN oi.seller_name || ' (removed)'
                        ELSE oi.seller_name END AS label,
                   SUM(oi.unit_price * oi.quantity) AS value
            {FROM_ITEMS} {where} AND {LIVE}
            GROUP BY oi.seller_name ORDER BY value DESC LIMIT 8""", params).fetchall()

    clause, extra = range_clause(days)
    payments = conn.execute(
        f"""SELECT UPPER(pay.method) AS label, COUNT(*) AS value
            FROM orders o JOIN payments pay ON pay.order_id = o.order_id
            WHERE 1 = 1{clause}
            GROUP BY pay.method ORDER BY value DESC""", extra).fetchall()

    rep["charts"]["sellers"] = _chart(sellers)
    rep["charts"]["payments"] = _chart(payments)

    rep["customers"] = [dict(r) for r in conn.execute(
        f"""SELECT o.customer_name AS name,
                   COUNT(DISTINCT o.order_id) AS orders,
                   SUM(oi.unit_price * oi.quantity) AS spent
            {FROM_ITEMS} {where} AND {LIVE}
            GROUP BY o.user_id, o.customer_name
            ORDER BY spent DESC LIMIT 5""", params)]

    if days:
        new_customers = conn.execute(
            "SELECT COUNT(*) FROM users WHERE role = 'customer' "
            "AND created_at >= date('now', ?)", (f"-{days - 1} days",)).fetchone()[0]
    else:
        new_customers = conn.execute(
            "SELECT COUNT(*) FROM users WHERE role = 'customer'").fetchone()[0]
    rep["kpis"]["new_customers"] = new_customers
    return rep