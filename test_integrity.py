import sqlite3
from db import get_connection

conn = get_connection()


def check(label, condition):
    print(("PASS  " if condition else "FAIL  ") + label)


def expect_error(label, sql, params=()):
    try:
        conn.execute(sql, params)
        print(f"FAIL  {label} (no error was raised!)")
    except sqlite3.IntegrityError as e:
        print(f"PASS  {label}  -> blocked: {e}")


cust = conn.execute(
    "SELECT user_id, name FROM users WHERE email = 'riya@example.com'").fetchone()
seller = conn.execute(
    "SELECT seller_id, store_name FROM seller_profiles WHERE store_name = 'TechHub'").fetchone()
mine = conn.execute(
    "SELECT * FROM products WHERE seller_id = ? ORDER BY product_id",
    (seller["seller_id"],)).fetchall()
p1, p2 = mine[0], mine[1]
other = conn.execute(
    "SELECT product_id FROM products WHERE seller_id != ? LIMIT 1",
    (seller["seller_id"],)).fetchone()

print("\n--- Constraint tests (bad data must be rejected) ---")
expect_error("Negative stock",
             "UPDATE products SET stock = -5 WHERE product_id = ?", (p1["product_id"],))
expect_error("Price of 0",
             "UPDATE products SET price = 0 WHERE product_id = ?", (p1["product_id"],))
expect_error("Product for a non-existent seller",
             "INSERT INTO products (seller_id, name, price, stock) VALUES (9999, 'Ghost', 10, 1)")
expect_error("Cart quantity of 0",
             "INSERT INTO cart_items VALUES (?, ?, 0)", (cust["user_id"], p1["product_id"]))
expect_error("Rating of 6",
             "INSERT INTO reviews (product_id, user_id, rating) VALUES (?, ?, 6)",
             (other["product_id"], cust["user_id"]))

conn.execute("INSERT INTO reviews (product_id, user_id, rating, comment) VALUES (?, ?, 5, 'Great')",
             (other["product_id"], cust["user_id"]))
expect_error("Second review by same user on same product",
             "INSERT INTO reviews (product_id, user_id, rating) VALUES (?, ?, 4)",
             (other["product_id"], cust["user_id"]))

conn.execute("INSERT INTO cart_items VALUES (?, ?, 2)", (cust["user_id"], p1["product_id"]))
conn.execute("INSERT INTO cart_items VALUES (?, ?, 1)", (cust["user_id"], p2["product_id"]))
expect_error("Same product twice in one cart (should update quantity instead)",
             "INSERT INTO cart_items VALUES (?, ?, 1)", (cust["user_id"], p1["product_id"]))

# Place an order for product 1
cur = conn.execute(
    "INSERT INTO orders (user_id, customer_name, shipping_address, total_amount) "
    "VALUES (?, ?, 'Chennai', ?)",
    (cust["user_id"], cust["name"], p1["price"] * 2))
order_id = cur.lastrowid
conn.execute(
    "INSERT INTO order_items (order_id, product_id, seller_id, product_name, seller_name, "
    "unit_price, quantity) VALUES (?, ?, ?, ?, ?, ?, 2)",
    (order_id, p1["product_id"], seller["seller_id"], p1["name"],
     seller["store_name"], p1["price"]))

print("\n--- Admin deletes a product that is in a cart AND in a placed order ---")
conn.execute("DELETE FROM products WHERE product_id = ?", (p1["product_id"],))
in_cart = conn.execute("SELECT COUNT(*) FROM cart_items WHERE product_id = ?",
                       (p1["product_id"],)).fetchone()[0]
item = conn.execute("SELECT * FROM order_items WHERE order_id = ?", (order_id,)).fetchone()
check("Removed from customer cart", in_cart == 0)
check("Order item still exists", item is not None)
check("Order item keeps product name and price", item["product_name"] == p1["name"]
      and item["unit_price"] == p1["price"])
check("Order item product_id is now NULL", item["product_id"] is None)

print("\n--- Admin deletes the seller ---")
conn.execute("DELETE FROM users WHERE user_id = ?", (seller["seller_id"],))
left = conn.execute("SELECT COUNT(*) FROM products WHERE seller_id = ?",
                    (seller["seller_id"],)).fetchone()[0]
cart_left = conn.execute("SELECT COUNT(*) FROM cart_items WHERE product_id = ?",
                         (p2["product_id"],)).fetchone()[0]
item = conn.execute("SELECT * FROM order_items WHERE order_id = ?", (order_id,)).fetchone()
check("All seller's products deleted", left == 0)
check("Their products removed from carts", cart_left == 0)
check("Order history still exists", item is not None)
check("Order history keeps seller name", item["seller_name"] == "TechHub")

conn.rollback()
conn.close()
print("\nAll test changes rolled back, so your database is unchanged.")