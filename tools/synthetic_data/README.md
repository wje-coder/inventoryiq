# Synthetic Ecommerce Data Generator

Reproducible (fixed seed `42`), standard-library-only Python generator for a realistic
ecommerce dataset: products, orders, order line items, returns, and monthly inventory
snapshots — including intentional data quality problems for testing dataset ingestion,
validation, and analytics. Full column-by-column documentation is in
[`DATA_DICTIONARY.md`](./DATA_DICTIONARY.md).

## Generate the full dataset

```bash
python tools/synthetic_data/generate.py
```

Writes CSVs to `tools/synthetic_data/output/` (gitignored — regenerate rather than expect it
in git). Runs in under a second, no dependencies beyond Python 3.11+.

```
products: 550 rows
orders: 17000 rows
order_items: ~31,800-32,000 rows
returns: 2600 rows
inventory_snapshots: 7700 rows
```

Use `--seed N` to generate a different (still fully reproducible for that seed) dataset, and
`--out-dir DIR` to write elsewhere.

## Committed sample

[`sample/`](./sample) contains a small (~40 products, ~113 orders, 120 order items),
referentially-consistent slice of the same seeded output, committed to git for quick
inspection and as ready-made upload fixtures — no need to run the generator first.

## Load into Postgres

```bash
pip install psycopg2-binary  # only needed if running outside the backend's own environment
python tools/synthetic_data/load_to_postgres.py \
    --host localhost --port 5432 --dbname inventoryiq \
    --user inventoryiq --password inventoryiq
```

Creates a `synthetic_ecommerce` schema (see [`schema.sql`](./schema.sql)) separate from the
application's own dataset-ingestion tables, and loads the CSVs from `output/` into it.

## Validate

```bash
python -m pytest tools/synthetic_data/test_generate.py -v
```

Covers reproducibility, minimum row counts, presence of every intentional data quality
problem, and referential consistency between the generated tables.
