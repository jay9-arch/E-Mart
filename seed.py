from werkzeug.security import generate_password_hash
from db import get_connection, init_db

init_db()
conn = get_connection()


def add_user(name, email, password, role):
    cur = conn.execute(
        "INSERT INTO users (name, email, password_hash, role) VALUES (?, ?, ?, ?)",
        (name, email, generate_password_hash(password), role),
    )
    return cur.lastrowid


# Admin
add_user("Admin", "admin@emart.com", "admin123", "admin")

# Customers
add_user("Riya Sharma", "riya@example.com", "riya123", "customer")
add_user("Arjun Mehta", "arjun@example.com", "arjun123", "customer")

# Sellers (user row + seller profile row)
s1 = add_user("Tech Seller", "tech@example.com", "tech123", "seller")
conn.execute("INSERT INTO seller_profiles VALUES (?, ?, ?)",
             (s1, "TechHub", "Gadgets and accessories"))
s2 = add_user("Book Seller", "books@example.com", "books123", "seller")
conn.execute("INSERT INTO seller_profiles VALUES (?, ?, ?)",
             (s2, "BookNook", "Books and stationery"))

# Categories
for c in ["Electronics", "Books", "Home & Kitchen", "Fashion"]:
    conn.execute("INSERT INTO categories (name) VALUES (?)", (c,))

cat = {r["name"]: r["category_id"]
       for r in conn.execute("SELECT * FROM categories")}

# Products: (seller, category, name, description, price, stock)
products = [
    (s1, cat["Electronics"], "Wireless Mouse", "2.4GHz silent-click mouse", 499, 50),
    (s1, cat["Electronics"], "Bluetooth Headphones", "20-hour battery life", 1499, 30),
    (s1, cat["Electronics"], "USB-C Cable", "1 metre fast-charge cable", 199, 100),
    (s2, cat["Books"], "Python Crash Course", "Beginner-friendly Python book", 699, 25),
    (s2, cat["Books"], "Database System Concepts", "Classic DBMS textbook", 899, 15),
    (s2, cat["Books"], "Notebook Pack (5)", "Ruled A5 notebooks", 249, 80),
]
conn.executemany(
    "INSERT INTO products (seller_id, category_id, name, description, price, stock) "
    "VALUES (?, ?, ?, ?, ?, ?)", products)

conn.commit()
conn.close()

print("Database created and seeded.")
print("  admin    : admin@emart.com / admin123")
print("  customer : riya@example.com / riya123")
print("  seller   : tech@example.com / tech123  (TechHub)")
print("  seller   : books@example.com / books123 (BookNook)")