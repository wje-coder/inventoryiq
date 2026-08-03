#!/usr/bin/env python3
"""Load the synthetic ecommerce CSVs into Postgres using schema.sql.

Requires `psycopg2` (already a backend dependency; `pip install
psycopg2-binary` if running this outside the backend's environment).

Usage:
    python tools/synthetic_data/load_to_postgres.py \\
        --host localhost --port 5432 --dbname inventoryiq \\
        --user inventoryiq --password inventoryiq \\
        --data-dir tools/synthetic_data/output

Rows are loaded with batched INSERTs (not COPY) because a few columns
need light Python-side transformation on the way in: raw date strings
that fail to parse become NULL in the parsed `order_date`/`return_date`
columns (the original text is preserved in `*_raw`), and blank
`product_id` values become SQL NULL rather than the literal empty
string, matching the nullable foreign key in schema.sql.
"""

from __future__ import annotations

import argparse
import csv
import datetime
import os
from pathlib import Path
from typing import Any

import psycopg2
import psycopg2.extras

BATCH_SIZE = 1000


def _parse_date(raw: str) -> datetime.date | None:
    try:
        return datetime.date.fromisoformat(raw)
    except (ValueError, TypeError):
        return None


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _batched_insert(
    cursor: Any, table: str, columns: list[str], rows: list[tuple[Any, ...]]
) -> None:
    if not rows:
        return
    query = f"INSERT INTO {table} ({', '.join(columns)}) VALUES %s"
    for start in range(0, len(rows), BATCH_SIZE):
        psycopg2.extras.execute_values(cursor, query, rows[start : start + BATCH_SIZE])


def load_products(cursor: Any, data_dir: Path) -> int:
    rows = _read_csv(data_dir / "products.csv")
    columns = [
        "product_id", "sku", "upc", "product_name", "category",
        "brand", "supplier", "unit_cost", "retail_price", "status",
    ]
    values = [tuple(r[c] for c in columns) for r in rows]
    _batched_insert(cursor, "products", columns, values)
    return len(rows)


def load_orders(cursor: Any, data_dir: Path) -> int:
    rows = _read_csv(data_dir / "orders.csv")
    columns = [
        "order_id", "order_date_raw", "order_date", "customer_id", "region", "channel", "status",
    ]
    values = [
        (
            r["order_id"],
            r["order_date"],
            _parse_date(r["order_date"]),
            r["customer_id"],
            r["region"],
            r["channel"],
            r["status"],
        )
        for r in rows
    ]
    _batched_insert(cursor, "orders", columns, values)
    return len(rows)


def load_order_items(cursor: Any, data_dir: Path) -> int:
    rows = _read_csv(data_dir / "order_items.csv")
    columns = [
        "order_item_id",
        "order_id",
        "product_id",
        "quantity_sold",
        "unit_sale_price",
        "discount_pct",
    ]
    values = [
        (
            r["order_item_id"],
            r["order_id"],
            r["product_id"] or None,
            int(r["quantity_sold"]),
            r["unit_sale_price"],
            r["discount_pct"] or None,
        )
        for r in rows
    ]
    _batched_insert(cursor, "order_items", columns, values)
    return len(rows)


def load_returns(cursor: Any, data_dir: Path) -> int:
    rows = _read_csv(data_dir / "returns.csv")
    columns = [
        "return_id",
        "order_item_id",
        "return_date_raw",
        "return_date",
        "quantity_returned",
        "reason",
    ]
    values = [
        (
            r["return_id"],
            r["order_item_id"],
            r["return_date"],
            _parse_date(r["return_date"]),
            int(r["quantity_returned"]),
            r["reason"] or None,
        )
        for r in rows
    ]
    _batched_insert(cursor, "returns", columns, values)
    return len(rows)


def load_inventory_snapshots(cursor: Any, data_dir: Path) -> int:
    rows = _read_csv(data_dir / "inventory_snapshots.csv")
    columns = ["snapshot_month", "product_id", "region", "quantity_available"]
    values = [
        (r["snapshot_month"], r["product_id"], r["region"], int(r["quantity_available"]))
        for r in rows
    ]
    _batched_insert(cursor, "inventory_snapshots", columns, values)
    return len(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=os.environ.get("POSTGRES_HOST", "localhost"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("POSTGRES_PORT", "5432")))
    parser.add_argument("--dbname", default=os.environ.get("POSTGRES_DB", "inventoryiq"))
    parser.add_argument("--user", default=os.environ.get("POSTGRES_USER", "inventoryiq"))
    parser.add_argument("--password", default=os.environ.get("POSTGRES_PASSWORD", "inventoryiq"))
    parser.add_argument(
        "--data-dir", type=Path, default=Path(__file__).parent / "output",
        help="Directory containing the generated CSVs (default: tools/synthetic_data/output)",
    )
    args = parser.parse_args()

    schema_sql = (Path(__file__).parent / "schema.sql").read_text()

    conn = psycopg2.connect(
        host=args.host, port=args.port, dbname=args.dbname, user=args.user, password=args.password
    )
    try:
        with conn.cursor() as cursor:
            cursor.execute(schema_sql)
            counts = {
                "products": load_products(cursor, args.data_dir),
                "orders": load_orders(cursor, args.data_dir),
                "order_items": load_order_items(cursor, args.data_dir),
                "returns": load_returns(cursor, args.data_dir),
                "inventory_snapshots": load_inventory_snapshots(cursor, args.data_dir),
            }
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    for table, count in counts.items():
        print(f"Loaded {count} rows into synthetic_ecommerce.{table}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
