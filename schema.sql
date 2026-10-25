-- E-Mart schema. Running this file RESETS the database.
PRAGMA foreign_keys = ON;

DROP TABLE IF EXISTS complaints;
DROP TABLE IF EXISTS reviews;
DROP TABLE IF EXISTS payments;
DROP TABLE IF EXISTS order_items;
DROP TABLE IF EXISTS orders;
DROP TABLE IF EXISTS cart_items;
DROP TABLE IF EXISTS products;
DROP TABLE IF EXISTS categories;
DROP TABLE IF EXISTS seller_profiles;
DROP TABLE IF EXISTS users;

CREATE TABLE users (
    user_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL,
    email         TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL CHECK (role IN ('customer', 'seller', 'admin')),
    is_active     INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    created_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Extra details only sellers have. Deleting the user deletes this row too.
CREATE TABLE seller_profiles (
    seller_id   INTEGER PRIMARY KEY
                REFERENCES users(user_id) ON DELETE CASCADE,
    store_name  TEXT NOT NULL UNIQUE,
    description TEXT
);

CREATE TABLE categories (
    category_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL UNIQUE
);

CREATE TABLE products (
    product_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    seller_id   INTEGER NOT NULL
                REFERENCES seller_profiles(seller_id) ON DELETE CASCADE,
    category_id INTEGER
                REFERENCES categories(category_id) ON DELETE SET NULL,
    name        TEXT NOT NULL,
    description TEXT,
    price       REAL NOT NULL CHECK (price > 0),
    stock       INTEGER NOT NULL DEFAULT 0 CHECK (stock >= 0),
    created_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- One row per (customer, product). Composite primary key stops duplicates.
CREATE TABLE cart_items (
    user_id    INTEGER NOT NULL
               REFERENCES users(user_id) ON DELETE CASCADE,
    product_id INTEGER NOT NULL
               REFERENCES products(product_id) ON DELETE CASCADE,
    quantity   INTEGER NOT NULL CHECK (quantity > 0),
    PRIMARY KEY (user_id, product_id)
);

CREATE TABLE orders (
    order_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id          INTEGER
                     REFERENCES users(user_id) ON DELETE SET NULL,
    customer_name    TEXT NOT NULL,        -- snapshot
    shipping_address TEXT NOT NULL,
    total_amount     REAL NOT NULL CHECK (total_amount >= 0),
    placed_at        TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Snapshot columns (product_name, seller_name, unit_price) keep order history
-- intact even after the product or seller is deleted.
CREATE TABLE order_items (
    order_item_id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id      INTEGER NOT NULL
                  REFERENCES orders(order_id) ON DELETE CASCADE,
    product_id    INTEGER
                  REFERENCES products(product_id) ON DELETE SET NULL,
    seller_id     INTEGER
                  REFERENCES seller_profiles(seller_id) ON DELETE SET NULL,
    product_name  TEXT NOT NULL,
    seller_name   TEXT NOT NULL,
    unit_price    REAL NOT NULL CHECK (unit_price >= 0),
    quantity      INTEGER NOT NULL CHECK (quantity > 0),
    status        TEXT NOT NULL DEFAULT 'placed'
                  CHECK (status IN ('placed', 'shipped', 'delivered', 'cancelled'))
);

CREATE TABLE payments (
    payment_id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id   INTEGER NOT NULL UNIQUE
               REFERENCES orders(order_id) ON DELETE CASCADE,
    method     TEXT NOT NULL CHECK (method IN ('card', 'upi', 'cod')),
    amount     REAL NOT NULL CHECK (amount >= 0),
    status     TEXT NOT NULL DEFAULT 'pending'
               CHECK (status IN ('pending', 'success', 'failed')),
    paid_at    TEXT
);

CREATE TABLE reviews (
    review_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL
               REFERENCES products(product_id) ON DELETE CASCADE,
    user_id    INTEGER NOT NULL
               REFERENCES users(user_id) ON DELETE CASCADE,
    rating     INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
    comment    TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (product_id, user_id)           -- one review per user per product
);

CREATE TABLE complaints (
    complaint_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id        INTEGER NOT NULL
                   REFERENCES users(user_id) ON DELETE CASCADE,
    order_id       INTEGER
                   REFERENCES orders(order_id) ON DELETE SET NULL,
    subject        TEXT NOT NULL,
    message        TEXT NOT NULL,
    status         TEXT NOT NULL DEFAULT 'open'
                   CHECK (status IN ('open', 'resolved', 'rejected')),
    admin_response TEXT,
    created_at     TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_products_seller   ON products(seller_id);
CREATE INDEX idx_products_category ON products(category_id);
CREATE INDEX idx_orderitems_seller ON order_items(seller_id);
CREATE INDEX idx_orderitems_order  ON order_items(order_id);
CREATE INDEX idx_reviews_product   ON reviews(product_id);