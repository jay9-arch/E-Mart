from db import get_connection

conn = get_connection()

# Demo orders all share this fake address. order_items and payments are removed by CASCADE.
orders = conn.execute(
    "DELETE FROM orders WHERE shipping_address = '12 Demo Street, Chennai 600001'").rowcount

# Demo reviews used these five comments.
reviews = conn.execute(
    """DELETE FROM reviews WHERE comment IN
       ('Works great.', 'Good value for money.', 'Arrived quickly, as described.',
        'Decent, but could be better.', 'Would buy again.')""").rowcount

conn.commit()
conn.close()
print(f"Removed {orders} demo orders and {reviews} demo reviews.")