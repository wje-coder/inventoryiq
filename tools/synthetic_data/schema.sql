-- Warehouse schema for the synthetic ecommerce dataset.
-- This is a standalone analytics schema, separate from the application's
-- own `datasets`/`dataset_columns`/... tables (see backend/alembic). It
-- exists so the generated CSVs can be loaded into Postgres directly for
-- exploration, demos, or future agent/analytics workflows, independent
-- of the dataset-upload feature.
--
-- Columns intentionally allow the data quality problems described in
-- DATA_DICTIONARY.md (e.g. no CHECK constraint forbidding negative
-- quantity_available) so the raw, imperfect data can be loaded as-is;
-- cleaning/validation is expected to happen downstream.

CREATE SCHEMA IF NOT EXISTS synthetic_ecommerce;
SET search_path TO synthetic_ecommerce;

DROP TABLE IF EXISTS returns CASCADE;
DROP TABLE IF EXISTS order_items CASCADE;
DROP TABLE IF EXISTS inventory_snapshots CASCADE;
DROP TABLE IF EXISTS orders CASCADE;
DROP TABLE IF EXISTS products CASCADE;

CREATE TABLE products (
    product_id      TEXT PRIMARY KEY,
    sku             TEXT NOT NULL,
    upc             TEXT,                 -- intentionally not validated; see data dictionary
    product_name    TEXT NOT NULL,
    category        TEXT NOT NULL,        -- intentionally inconsistent casing; normalize on read
    brand           TEXT,
    supplier        TEXT,
    unit_cost       NUMERIC(10, 2) NOT NULL,
    retail_price    NUMERIC(10, 2) NOT NULL,
    status          TEXT NOT NULL
);

CREATE TABLE orders (
    order_id        TEXT PRIMARY KEY,
    order_date_raw  TEXT NOT NULL,        -- raw text; may be malformed, see data dictionary
    order_date      DATE,                 -- NULL when order_date_raw could not be parsed
    customer_id     TEXT NOT NULL,
    region          TEXT NOT NULL,
    channel         TEXT NOT NULL,
    status          TEXT NOT NULL
);

CREATE TABLE order_items (
    order_item_id   TEXT PRIMARY KEY,
    order_id        TEXT NOT NULL REFERENCES orders (order_id),
    product_id      TEXT REFERENCES products (product_id),  -- nullable: some rows have it missing
    quantity_sold   INTEGER NOT NULL,
    unit_sale_price NUMERIC(10, 2) NOT NULL,
    discount_pct    NUMERIC(5, 3)
);

CREATE TABLE returns (
    return_id           TEXT PRIMARY KEY,
    order_item_id       TEXT NOT NULL REFERENCES order_items (order_item_id),
    return_date_raw      TEXT NOT NULL,
    return_date          DATE,
    quantity_returned    INTEGER NOT NULL,
    reason                TEXT
);

CREATE TABLE inventory_snapshots (
    snapshot_month      TEXT NOT NULL,
    product_id          TEXT NOT NULL REFERENCES products (product_id),
    region               TEXT NOT NULL,
    quantity_available   INTEGER NOT NULL,  -- intentionally allows negatives; see data dictionary
    PRIMARY KEY (snapshot_month, product_id, region)
);

CREATE INDEX ix_orders_order_date ON orders (order_date);
CREATE INDEX ix_order_items_order_id ON order_items (order_id);
CREATE INDEX ix_order_items_product_id ON order_items (product_id);
CREATE INDEX ix_returns_order_item_id ON returns (order_item_id);
CREATE INDEX ix_inventory_snapshots_product_id ON inventory_snapshots (product_id);
