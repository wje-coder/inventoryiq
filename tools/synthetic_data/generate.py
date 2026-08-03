#!/usr/bin/env python3
"""Reproducible synthetic ecommerce dataset generator for InventoryIQ.

Standard library only (no pandas/numpy/faker) so it can run anywhere
Python 3.11+ runs, with no dependency install step. Fixed random seed
(see RANDOM_SEED) makes every run byte-for-byte identical.

Usage:
    python tools/synthetic_data/generate.py [--out-dir DIR] [--seed N]

Generates five CSV files (products, orders, order_items, returns,
inventory_snapshots) containing realistic patterns (seasonality,
regional demand, category margins, discounts, stockouts, excess
inventory, supplier patterns, revenue trends) alongside deliberately
injected data quality problems, documented in DATA_DICTIONARY.md.
"""

from __future__ import annotations

import argparse
import csv
import random
import sys
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any

RANDOM_SEED = 42

# --- Reference data -----------------------------------------------------

CATEGORIES: dict[str, tuple[float, float, float, float]] = {
    # name -> (cost_min, cost_max, margin_multiplier_min, margin_multiplier_max)
    "Electronics": (20.0, 400.0, 1.3, 1.6),
    "Apparel": (5.0, 60.0, 1.8, 3.0),
    "Home & Kitchen": (8.0, 150.0, 1.5, 2.2),
    "Sporting Goods": (10.0, 200.0, 1.4, 2.0),
    "Toys & Games": (3.0, 80.0, 1.6, 2.5),
    "Beauty": (3.0, 50.0, 2.0, 3.5),
    "Grocery": (1.0, 25.0, 1.2, 1.5),
    "Office Supplies": (2.0, 60.0, 1.4, 1.9),
}

# Inconsistent-casing variants injected as a data quality problem; the
# "canonical" name is always the dict key above.
CATEGORY_NAME_VARIANTS: dict[str, list[str]] = {
    name: [name, name.upper(), name.lower(), f" {name} "] for name in CATEGORIES
}

REGIONS: list[tuple[str, float]] = [
    ("Northeast", 0.24),
    ("Southeast", 0.22),
    ("Midwest", 0.19),
    ("West", 0.24),
    ("Southwest", 0.11),
]

CHANNELS: list[tuple[str, float]] = [
    ("online", 0.55),
    ("retail", 0.30),
    ("marketplace", 0.15),
]

SUPPLIERS = [f"Supplier {chr(65 + i // 26)}{chr(65 + i % 26)}" for i in range(24)]

BRAND_PREFIXES = [
    "Aero", "Nova", "Crestline", "Bluewave", "Summit", "Cobalt", "Willow", "Granite",
    "Harbor", "Pioneer", "Vertex", "Orbit", "Lumen", "Cedar", "Meridian", "Falcon",
]
BRAND_SUFFIXES = ["Co", "Goods", "Supply", "Works", "Home", "Labs", "Brands", "Group"]

PRODUCT_ADJECTIVES = ["Classic", "Premium", "Everyday", "Pro", "Essential", "Deluxe", "Compact"]
PRODUCT_NOUNS: dict[str, list[str]] = {
    "Electronics": ["Headphones", "Charger", "Speaker", "Cable", "Monitor", "Router", "Webcam"],
    "Apparel": ["T-Shirt", "Hoodie", "Jacket", "Socks", "Cap", "Jeans", "Sweater"],
    "Home & Kitchen": ["Blender", "Toaster", "Cookware Set", "Storage Bin", "Lamp", "Rug"],
    "Sporting Goods": ["Yoga Mat", "Dumbbell Set", "Water Bottle", "Backpack", "Tent"],
    "Toys & Games": ["Puzzle", "Board Game", "Action Figure", "Building Blocks", "Plush Toy"],
    "Beauty": ["Moisturizer", "Shampoo", "Lip Balm", "Face Mask", "Sunscreen"],
    "Grocery": ["Coffee", "Granola", "Olive Oil", "Pasta", "Tea", "Snack Mix"],
    "Office Supplies": ["Notebook", "Pen Set", "Stapler", "Desk Organizer", "Sticky Notes"],
}

RETURN_REASONS = [
    "defective",
    "wrong_item",
    "no_longer_needed",
    "damaged_in_transit",
    "not_as_described",
    "better_price_found",
]

ORDER_STATUSES: list[tuple[str, float]] = [
    ("completed", 0.90),
    ("cancelled", 0.06),
    ("pending", 0.04),
]

ORDER_START = date(2023, 1, 1)
ORDER_END = date(2024, 6, 30)
INVENTORY_MONTHS = 14  # comfortably exceeds the "at least 12 months" requirement


def _weighted_choice(rng: random.Random, options: list[tuple[str, float]]) -> str:
    names = [name for name, _ in options]
    weights = [w for _, w in options]
    return rng.choices(names, weights=weights, k=1)[0]


def _seasonal_weight(d: date) -> float:
    """Relative order-volume multiplier by month: a holiday peak in
    Nov/Dec, a summer dip, and a modest back-to-school bump in Sept."""
    month_weights = {
        1: 0.8, 2: 0.75, 3: 0.85, 4: 0.9, 5: 0.95, 6: 0.9,
        7: 0.85, 8: 0.9, 9: 1.05, 10: 1.1, 11: 1.55, 12: 1.8,
    }
    return month_weights[d.month]


def daterange_days(start: date, end: date) -> list[date]:
    days = (end - start).days
    return [start + timedelta(days=i) for i in range(days + 1)]


def format_date(d: date) -> str:
    return d.isoformat()


@dataclass
class GenerationContext:
    rng: random.Random
    problem_product_ids: set[str] = field(default_factory=set)


def generate_products(ctx: GenerationContext, count: int) -> list[dict[str, Any]]:
    rng = ctx.rng
    products: list[dict[str, Any]] = []
    category_names = list(CATEGORIES.keys())

    for i in range(1, count + 1):
        product_id = f"P{i:05d}"
        category = rng.choice(category_names)
        cost_min, cost_max, margin_min, margin_max = CATEGORIES[category]
        unit_cost = round(rng.uniform(cost_min, cost_max), 2)
        margin = rng.uniform(margin_min, margin_max)
        retail_price = round(unit_cost * margin, 2)

        # Supplier patterns: each supplier is drawn from a fixed rotation
        # weighted so a handful of suppliers dominate each category,
        # rather than a uniform random assignment. Python's built-in
        # hash() is randomized per-process for strings (by design), so a
        # deterministic index (category's position in CATEGORIES) is used
        # instead - required for the seeded output to be reproducible.
        category_offset = category_names.index(category) % 6
        supplier_pool = SUPPLIERS[category_offset::4]
        supplier = rng.choice(supplier_pool or SUPPLIERS)

        brand = f"{rng.choice(BRAND_PREFIXES)}{rng.choice(BRAND_SUFFIXES)}"
        noun = rng.choice(PRODUCT_NOUNS[category])
        adjective = rng.choice(PRODUCT_ADJECTIVES)
        product_name = f"{brand} {adjective} {noun}"

        sku = f"SKU-{category[:3].upper()}-{i:05d}"
        upc = f"{rng.randint(10**11, 10**12 - 1)}"  # valid 12-digit UPC-A

        display_category = rng.choice(CATEGORY_NAME_VARIANTS[category])

        status = "discontinued" if rng.random() < 0.06 else "active"

        products.append(
            {
                "product_id": product_id,
                "sku": sku,
                "upc": upc,
                "product_name": product_name,
                "category": display_category,
                "brand": brand,
                "supplier": supplier,
                "unit_cost": unit_cost,
                "retail_price": retail_price,
                "status": status,
            }
        )

    _inject_malformed_upcs(ctx, products)
    _select_problem_products(ctx, products)
    return products


def _inject_malformed_upcs(ctx: GenerationContext, products: list[dict[str, Any]]) -> None:
    """Quality issue: malformed UPC values (~3% of products)."""
    rng = ctx.rng
    sample_size = max(1, len(products) * 3 // 100)
    for row in rng.sample(products, sample_size):
        mutation = rng.choice(["too_short", "letters", "empty"])
        if mutation == "too_short":
            row["upc"] = row["upc"][:5]
        elif mutation == "letters":
            row["upc"] = "UPC" + row["upc"][:6]
        else:
            row["upc"] = ""


def _select_problem_products(ctx: GenerationContext, products: list[dict[str, Any]]) -> None:
    """Pick ~4% of active products to exhibit a rising return rate over
    time (both a realistic quality-decline pattern and an intentional
    data-quality signal for downstream anomaly detection)."""
    rng = ctx.rng
    active = [p for p in products if p["status"] == "active"]
    sample_size = max(1, len(active) * 4 // 100)
    ctx.problem_product_ids = {p["product_id"] for p in rng.sample(active, sample_size)}


def generate_customers(ctx: GenerationContext, count: int) -> list[str]:
    return [f"C{i:06d}" for i in range(1, count + 1)]


def generate_orders_and_items(
    ctx: GenerationContext,
    products: list[dict[str, Any]],
    customer_ids: list[str],
    order_count: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rng = ctx.rng
    active_products = [p for p in products if p["status"] == "active"]
    all_days = daterange_days(ORDER_START, ORDER_END)
    day_weights = [_seasonal_weight(d) for d in all_days]
    products_by_id = {p["product_id"]: p for p in products}

    orders: list[dict[str, Any]] = []
    order_items: list[dict[str, Any]] = []
    item_seq = 1

    order_dates = rng.choices(all_days, weights=day_weights, k=order_count)
    order_dates.sort()

    for i, order_date in enumerate(order_dates, start=1):
        order_id = f"O{i:06d}"
        region = _weighted_choice(rng, REGIONS)
        channel = _weighted_choice(rng, CHANNELS)
        customer_id = rng.choice(customer_ids)
        status = _weighted_choice(rng, ORDER_STATUSES)

        raw_order_date = format_date(order_date)
        if rng.random() < 0.005:
            raw_order_date = _corrupt_date(rng, order_date)

        orders.append(
            {
                "order_id": order_id,
                "order_date": raw_order_date,
                "customer_id": customer_id,
                "region": region,
                "channel": channel,
                "status": status,
            }
        )

        item_count = rng.choices([1, 2, 3, 4], weights=[0.45, 0.32, 0.15, 0.08], k=1)[0]
        # Regional demand differences: bias category selection slightly
        # by region using a deterministic offset into the category list.
        for _ in range(item_count):
            product = _pick_regional_product(rng, active_products, region)
            unit_sale_price = _price_for_sale(rng, product, order_date)
            quantity_sold = rng.choices([1, 2, 3, 4, 5], weights=[0.55, 0.2, 0.12, 0.08, 0.05], k=1)[
                0
            ]
            discount_pct = _discount_for(rng, order_date)

            product_id = product["product_id"]
            if rng.random() < 0.015:
                product_id = ""  # quality issue: missing product identifier

            order_items.append(
                {
                    "order_item_id": f"OI{item_seq:07d}",
                    "order_id": order_id,
                    "product_id": product_id,
                    "quantity_sold": quantity_sold,
                    "unit_sale_price": unit_sale_price,
                    "discount_pct": discount_pct,
                }
            )
            item_seq += 1

    _inject_duplicate_rows(ctx, order_items)
    _inject_price_anomalies(ctx, order_items, products_by_id)
    return orders, order_items


def _pick_regional_product(
    rng: random.Random, active_products: list[dict[str, Any]], region: str
) -> dict[str, Any]:
    region_index = [name for name, _ in REGIONS].index(region)
    category_names = list(CATEGORIES.keys())
    preferred_category = category_names[region_index % len(category_names)]
    if rng.random() < 0.35:
        candidates = [p for p in active_products if p["category"].strip().lower() ==
                      preferred_category.lower()]
        if candidates:
            return rng.choice(candidates)
    return rng.choice(active_products)


def _price_for_sale(rng: random.Random, product: dict[str, Any], order_date: date) -> float:
    retail_price = product["retail_price"]
    # Seasonal discounts: deeper markdowns in Nov/Dec.
    if order_date.month in (11, 12) and rng.random() < 0.4:
        markdown = rng.uniform(0.15, 0.35)
    elif rng.random() < 0.12:
        markdown = rng.uniform(0.05, 0.20)
    else:
        markdown = 0.0
    return round(retail_price * (1 - markdown), 2)


def _discount_for(rng: random.Random, order_date: date) -> float:
    base = 0.25 if order_date.month in (11, 12) else 0.08
    return round(max(0.0, rng.gauss(base, 0.07)), 3)


def _inject_duplicate_rows(ctx: GenerationContext, order_items: list[dict[str, Any]]) -> None:
    """Quality issue: exact duplicate rows (~0.5% of rows), appended so
    they are indistinguishable from originals by any column."""
    rng = ctx.rng
    sample_size = max(1, len(order_items) // 200)
    duplicates = [dict(row) for row in rng.sample(order_items, sample_size)]
    order_items.extend(duplicates)


def _inject_price_anomalies(
    ctx: GenerationContext, order_items: list[dict[str, Any]], products_by_id: dict[str, Any]
) -> None:
    """Quality issues: sale prices below cost, and extreme price outliers."""
    rng = ctx.rng
    priced_rows = [row for row in order_items if row["product_id"] in products_by_id]

    below_cost_sample = rng.sample(priced_rows, max(1, len(priced_rows) // 250))
    for row in below_cost_sample:
        cost = products_by_id[row["product_id"]]["unit_cost"]
        row["unit_sale_price"] = round(cost * rng.uniform(0.4, 0.9), 2)

    outlier_sample = rng.sample(priced_rows, max(1, len(priced_rows) // 400))
    for row in outlier_sample:
        row["unit_sale_price"] = round(
            row["unit_sale_price"] * rng.choice([0.01, 0.02, 50.0, 80.0]), 2
        )


def _corrupt_date(rng: random.Random, original: date) -> str:
    mutation = rng.choice(["bad_month", "bad_day", "text", "swapped"])
    if mutation == "bad_month":
        return f"{original.year}-13-{original.day:02d}"
    if mutation == "bad_day":
        return f"{original.year}-{original.month:02d}-45"
    if mutation == "swapped":
        return f"{original.day:02d}/{original.month:02d}/{original.year}"
    return "not_a_date"


def generate_returns(
    ctx: GenerationContext,
    orders: list[dict[str, Any]],
    order_items: list[dict[str, Any]],
    target_count: int,
) -> list[dict[str, Any]]:
    rng = ctx.rng
    orders_by_id = {o["order_id"]: o for o in orders}

    eligible = [
        row
        for row in order_items
        if row["product_id"]
        and row["order_id"] in orders_by_id
        and orders_by_id[row["order_id"]]["status"] == "completed"
    ]

    def base_return_probability(row: dict[str, Any]) -> float:
        if row["product_id"] in ctx.problem_product_ids:
            order = orders_by_id[row["order_id"]]
            try:
                order_date = date.fromisoformat(order["order_date"])
            except ValueError:
                return 0.15
            span_days = (ORDER_END - ORDER_START).days or 1
            progress = max(0.0, min(1.0, (order_date - ORDER_START).days / span_days))
            # Rises from ~5% early in the range to ~45% by the end.
            return 0.05 + progress * 0.40
        return 0.04

    returns: list[dict[str, Any]] = []
    return_seq = 1
    for row in eligible:
        if rng.random() < base_return_probability(row):
            order = orders_by_id[row["order_id"]]
            try:
                order_date = date.fromisoformat(order["order_date"])
            except ValueError:
                order_date = ORDER_START
            delay = rng.randint(1, 30)
            return_date = order_date + timedelta(days=delay)
            raw_return_date = format_date(return_date)

            if rng.random() < 0.01:
                raw_return_date = _corrupt_date(rng, return_date)
            elif rng.random() < 0.01:
                # Quality issue: return_date before order_date.
                raw_return_date = format_date(order_date - timedelta(days=rng.randint(1, 10)))

            returns.append(
                {
                    "return_id": f"R{return_seq:06d}",
                    "order_item_id": row["order_item_id"],
                    "return_date": raw_return_date,
                    "quantity_returned": min(
                        row["quantity_sold"], rng.randint(1, row["quantity_sold"])
                    ),
                    "reason": rng.choice(RETURN_REASONS),
                }
            )
            return_seq += 1
            if len(returns) >= target_count and return_seq > target_count:
                break

    # Top up if the eligible-row sampling came in under target (keeps the
    # generator robust to parameter changes without silently under-shooting
    # the required minimum row count).
    while len(returns) < target_count and eligible:
        row = rng.choice(eligible)
        order = orders_by_id[row["order_id"]]
        try:
            order_date = date.fromisoformat(order["order_date"])
        except ValueError:
            order_date = ORDER_START
        return_date = order_date + timedelta(days=rng.randint(1, 30))
        returns.append(
            {
                "return_id": f"R{return_seq:06d}",
                "order_item_id": row["order_item_id"],
                "return_date": format_date(return_date),
                "quantity_returned": 1,
                "reason": rng.choice(RETURN_REASONS),
            }
        )
        return_seq += 1

    return returns


def generate_inventory_snapshots(
    ctx: GenerationContext, products: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    rng = ctx.rng
    snapshots: list[dict[str, Any]] = []

    months: list[date] = []
    cursor = date(ORDER_START.year, ORDER_START.month, 1)
    for _ in range(INVENTORY_MONTHS):
        months.append(cursor)
        cursor = date(cursor.year + (cursor.month == 12), (cursor.month % 12) + 1, 1)

    # A subset of products run persistently low (stockout-prone) and a
    # subset run persistently high (excess inventory), the rest fluctuate
    # around a normal operating band.
    active_products = [p for p in products if p["status"] == "active"]
    stockout_prone = set(p["product_id"] for p in rng.sample(
        active_products, max(1, len(active_products) // 12)
    ))
    excess_prone = set(p["product_id"] for p in rng.sample(
        [p for p in active_products if p["product_id"] not in stockout_prone],
        max(1, len(active_products) // 12),
    ))

    for product in products:
        for month in months:
            if product["product_id"] in stockout_prone:
                quantity = rng.choices([0, 0, 5, 10, 20], k=1)[0]
            elif product["product_id"] in excess_prone:
                quantity = rng.randint(800, 3000)
            else:
                quantity = rng.randint(20, 400)

            region = _weighted_choice(rng, REGIONS)

            if rng.random() < 0.01:
                quantity = -abs(rng.randint(1, 50))  # quality issue: negative inventory

            snapshots.append(
                {
                    "snapshot_month": f"{month.year:04d}-{month.month:02d}",
                    "product_id": product["product_id"],
                    "region": region,
                    "quantity_available": quantity,
                }
            )

    return snapshots


def generate_all(seed: int = RANDOM_SEED) -> dict[str, list[dict[str, Any]]]:
    ctx = GenerationContext(rng=random.Random(seed))

    products = generate_products(ctx, count=550)
    customer_ids = generate_customers(ctx, count=5000)
    orders, order_items = generate_orders_and_items(
        ctx, products, customer_ids, order_count=17000
    )
    returns = generate_returns(ctx, orders, order_items, target_count=2600)
    inventory_snapshots = generate_inventory_snapshots(ctx, products)

    return {
        "products": products,
        "orders": orders,
        "order_items": order_items,
        "returns": returns,
        "inventory_snapshots": inventory_snapshots,
    }


def write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("")
        return
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path(__file__).parent / "output",
        help="Directory to write CSV files into (default: tools/synthetic_data/output)",
    )
    parser.add_argument("--seed", type=int, default=RANDOM_SEED)
    args = parser.parse_args(argv)

    data = generate_all(seed=args.seed)
    for name, rows in data.items():
        write_csv(rows, args.out_dir / f"{name}.csv")
        print(f"{name}: {len(rows)} rows -> {args.out_dir / f'{name}.csv'}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
