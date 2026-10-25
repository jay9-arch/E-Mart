# E-Mart: tables, keys and relationships

## cart_items

| Column | Type | Key | NOT NULL | Default | References (ON DELETE) |
|---|---|---|---|---|---|
| user_id | INTEGER | PK, FK | yes |  | users.user_id (CASCADE) |
| product_id | INTEGER | PK, FK | yes |  | products.product_id (CASCADE) |
| quantity | INTEGER |  | yes |  |  |

## categories

| Column | Type | Key | NOT NULL | Default | References (ON DELETE) |
|---|---|---|---|---|---|
| category_id | INTEGER | PK |  |  |  |
| name | TEXT |  | yes |  |  |

## complaints

| Column | Type | Key | NOT NULL | Default | References (ON DELETE) |
|---|---|---|---|---|---|
| complaint_id | INTEGER | PK |  |  |  |
| user_id | INTEGER | FK | yes |  | users.user_id (CASCADE) |
| order_id | INTEGER | FK |  |  | orders.order_id (SET NULL) |
| subject | TEXT |  | yes |  |  |
| message | TEXT |  | yes |  |  |
| status | TEXT |  | yes | 'open' |  |
| admin_response | TEXT |  |  |  |  |
| created_at | TEXT |  | yes | CURRENT_TIMESTAMP |  |

## order_items

| Column | Type | Key | NOT NULL | Default | References (ON DELETE) |
|---|---|---|---|---|---|
| order_item_id | INTEGER | PK |  |  |  |
| order_id | INTEGER | FK | yes |  | orders.order_id (CASCADE) |
| product_id | INTEGER | FK |  |  | products.product_id (SET NULL) |
| seller_id | INTEGER | FK |  |  | seller_profiles.seller_id (SET NULL) |
| product_name | TEXT |  | yes |  |  |
| seller_name | TEXT |  | yes |  |  |
| unit_price | REAL |  | yes |  |  |
| quantity | INTEGER |  | yes |  |  |
| status | TEXT |  | yes | 'placed' |  |

## orders

| Column | Type | Key | NOT NULL | Default | References (ON DELETE) |
|---|---|---|---|---|---|
| order_id | INTEGER | PK |  |  |  |
| user_id | INTEGER | FK |  |  | users.user_id (SET NULL) |
| customer_name | TEXT |  | yes |  |  |
| shipping_address | TEXT |  | yes |  |  |
| total_amount | REAL |  | yes |  |  |
| placed_at | TEXT |  | yes | CURRENT_TIMESTAMP |  |

## payments

| Column | Type | Key | NOT NULL | Default | References (ON DELETE) |
|---|---|---|---|---|---|
| payment_id | INTEGER | PK |  |  |  |
| order_id | INTEGER | FK | yes |  | orders.order_id (CASCADE) |
| method | TEXT |  | yes |  |  |
| amount | REAL |  | yes |  |  |
| status | TEXT |  | yes | 'pending' |  |
| paid_at | TEXT |  |  |  |  |

## products

| Column | Type | Key | NOT NULL | Default | References (ON DELETE) |
|---|---|---|---|---|---|
| product_id | INTEGER | PK |  |  |  |
| seller_id | INTEGER | FK | yes |  | seller_profiles.seller_id (CASCADE) |
| category_id | INTEGER | FK |  |  | categories.category_id (SET NULL) |
| name | TEXT |  | yes |  |  |
| description | TEXT |  |  |  |  |
| price | REAL |  | yes |  |  |
| stock | INTEGER |  | yes | 0 |  |
| created_at | TEXT |  | yes | CURRENT_TIMESTAMP |  |

## reviews

| Column | Type | Key | NOT NULL | Default | References (ON DELETE) |
|---|---|---|---|---|---|
| review_id | INTEGER | PK |  |  |  |
| product_id | INTEGER | FK | yes |  | products.product_id (CASCADE) |
| user_id | INTEGER | FK | yes |  | users.user_id (CASCADE) |
| rating | INTEGER |  | yes |  |  |
| comment | TEXT |  |  |  |  |
| created_at | TEXT |  | yes | CURRENT_TIMESTAMP |  |

## seller_profiles

| Column | Type | Key | NOT NULL | Default | References (ON DELETE) |
|---|---|---|---|---|---|
| seller_id | INTEGER | PK, FK |  |  | users.user_id (CASCADE) |
| store_name | TEXT |  | yes |  |  |
| description | TEXT |  |  |  |  |

## users

| Column | Type | Key | NOT NULL | Default | References (ON DELETE) |
|---|---|---|---|---|---|
| user_id | INTEGER | PK |  |  |  |
| name | TEXT |  | yes |  |  |
| email | TEXT |  | yes |  |  |
| password_hash | TEXT |  | yes |  |  |
| role | TEXT |  | yes |  |  |
| is_active | INTEGER |  | yes | 1 |  |
| created_at | TEXT |  | yes | CURRENT_TIMESTAMP |  |
