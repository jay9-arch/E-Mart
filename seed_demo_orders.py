"""Adds ~40 fake orders over the last 60 days so the analytics charts have data.
Run AFTER seed.py. Running seed.py again wipes everything, including this."""
import random
from datetime import datetime, timedelta, timezone
from db import get_connection

random.seed(7)
conn = get_connection()

customers = conn.execute("SELECT user_id, name FROM users WHERE role = 'customer'").fetchall()
products = conn.execute(
    """SELECT p.product_id, p.name, p.price, p.seller_id, sp.store_name
       FROM products p JOIN seller_profiles sp ON sp.seller_id = p.seller_id""").fetchall()
if not customers or not products:
    raise SystemExit("Run seed.py first.")

COMMENTS = ["Works great.", "Good value for money.", "Arrived quickly, as described.",
            "Decent, but could be better.", "Would buy again."]


def pick_status(age_days):
    if random.random() < 0.08:
        return "cancelled"
    if age_days > 10:
        return "delivered"
    if age_days > 4:
        return random.choice(["shipped", "delivered"])
    return random.choice(["placed", "shipped"])


now = datetime.now(timezone.utc)
for _ in range(40):
    cust = random.choice(customers)
    placed = now - timedelta(days=random.randint(0, 59),
                             hours=random.randint(0, 23), minutes=random.randint(0, 59))
    stamp = placed.strftime("%Y-%m-%d %H:%M:%S")
    age = (now - placed).days
    lines = [(p, random.randint(1, 3)) for p in random.sample(products, random.randint(1, 3))]
    total = round(sum(p["price"] * q for p, q in lines), 2)
    method = random.choice(["card", "upi", "cod"])

    order_id = conn.execute(
        "INSERT INTO orders (user_id, customer_name, shipping_address, total_amount, placed_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (cust["user_id"], cust["name"], "12 Demo Street, Chennai 600001", total, stamp)).lastrowid

    statuses = []
    for p, qty in lines:
        status = pick_status(age)
        statuses.append(status)
        conn.execute(
            """INSERT INTO order_items (order_id, product_id, seller_id, product_name,
                                        seller_name, unit_price, quantity, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (order_id, p["product_id"], p["seller_id"], p["name"], p["store_name"],
             p["price"], qty, status))
        if status == "delivered" and random.random() < 0.5:
            conn.execute(
                "INSERT OR IGNORE INTO reviews (product_id, user_id, rating, comment, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (p["product_id"], cust["user_id"], random.choice([3, 4, 4, 5, 5, 5]),
                 random.choice(COMMENTS), stamp))

    active = [s for s in statuses if s != "cancelled"]
    paid = method != "cod" or (active and all(s == "delivered" for s in active))
    conn.execute(
        "INSERT INTO payments (order_id, method, amount, status, paid_at) VALUES (?, ?, ?, ?, ?)",
        (order_id, method, total, "success" if paid else "pending", stamp if paid else None))

conn.commit()
conn.close()
print("Added 40 demo orders. (Stock levels were not changed.)")