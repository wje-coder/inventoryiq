"""Validation tests for the synthetic data generator.

Run from the repo root with:
    python -m pytest tools/synthetic_data/test_generate.py -v

Requires only pytest (already a backend dev dependency); the generator
itself has zero third-party dependencies.
"""

import datetime

import generate


def _is_valid_iso_date(value: str) -> bool:
    try:
        datetime.date.fromisoformat(value)
        return True
    except (ValueError, TypeError):
        return False


class TestReproducibility:
    def test_same_seed_produces_identical_output(self) -> None:
        first = generate.generate_all(seed=42)
        second = generate.generate_all(seed=42)
        assert first == second

    def test_different_seed_produces_different_output(self) -> None:
        first = generate.generate_all(seed=42)
        other = generate.generate_all(seed=7)
        assert first["orders"] != other["orders"]


class TestMinimumRowCounts:
    def setup_method(self) -> None:
        self.data = generate.generate_all(seed=42)

    def test_at_least_500_products(self) -> None:
        assert len(self.data["products"]) >= 500

    def test_at_least_15000_orders(self) -> None:
        assert len(self.data["orders"]) >= 15000

    def test_at_least_30000_order_items(self) -> None:
        assert len(self.data["order_items"]) >= 30000

    def test_at_least_2500_returns(self) -> None:
        assert len(self.data["returns"]) >= 2500

    def test_at_least_12_months_of_inventory_snapshots(self) -> None:
        months = {row["snapshot_month"] for row in self.data["inventory_snapshots"]}
        assert len(months) >= 12


class TestIntentionalDataQualityProblems:
    def setup_method(self) -> None:
        self.data = generate.generate_all(seed=42)

    def test_missing_product_identifiers_present(self) -> None:
        missing = [r for r in self.data["order_items"] if r["product_id"] == ""]
        assert len(missing) > 0

    def test_duplicate_rows_present(self) -> None:
        rows = self.data["order_items"]
        seen: dict[tuple, int] = {}
        for row in rows:
            key = tuple(row.items())
            seen[key] = seen.get(key, 0) + 1
        assert any(count > 1 for count in seen.values())

    def test_malformed_upc_values_present(self) -> None:
        malformed = [
            p for p in self.data["products"] if not (p["upc"].isdigit() and len(p["upc"]) == 12)
        ]
        assert len(malformed) > 0

    def test_negative_inventory_values_present(self) -> None:
        negative = [r for r in self.data["inventory_snapshots"] if r["quantity_available"] < 0]
        assert len(negative) > 0

    def test_invalid_dates_present(self) -> None:
        bad_orders = [o for o in self.data["orders"] if not _is_valid_iso_date(o["order_date"])]
        bad_returns = [r for r in self.data["returns"] if not _is_valid_iso_date(r["return_date"])]
        assert len(bad_orders) > 0
        assert len(bad_returns) > 0

    def test_inconsistent_category_names_present(self) -> None:
        distinct_strings = {p["category"] for p in self.data["products"]}
        # 8 canonical categories but more than 8 distinct raw strings due
        # to injected casing/whitespace variants.
        assert len(distinct_strings) > len(generate.CATEGORIES)

    def test_sale_prices_below_cost_present(self) -> None:
        cost_by_id = {p["product_id"]: p["unit_cost"] for p in self.data["products"]}
        below_cost = [
            r
            for r in self.data["order_items"]
            if r["product_id"] in cost_by_id and r["unit_sale_price"] < cost_by_id[r["product_id"]]
        ]
        assert len(below_cost) > 0

    def test_price_outliers_present(self) -> None:
        prices = sorted(r["unit_sale_price"] for r in self.data["order_items"])
        median = prices[len(prices) // 2]
        extreme_low = [p for p in prices if p < median * 0.1]
        extreme_high = [p for p in prices if p > median * 10]
        assert extreme_low or extreme_high

    def test_products_with_rising_return_rates_present(self) -> None:
        data = self.data
        orders_by_id = {o["order_id"]: o for o in data["orders"]}
        returned_item_ids = {r["order_item_id"] for r in data["returns"]}

        start = generate.ORDER_START
        end = generate.ORDER_END
        midpoint = start + (end - start) // 2

        totals: dict[str, list[int]] = {}
        for item in data["order_items"]:
            pid = item["product_id"]
            if not pid:
                continue
            order = orders_by_id.get(item["order_id"])
            if order is None or not _is_valid_iso_date(order["order_date"]):
                continue
            order_date = datetime.date.fromisoformat(order["order_date"])
            bucket = 1 if order_date >= midpoint else 0
            # [early_total, early_returned, late_total, late_returned]
            counts = totals.setdefault(pid, [0, 0, 0, 0])
            if bucket == 0:
                counts[0] += 1
                if item["order_item_id"] in returned_item_ids:
                    counts[1] += 1
            else:
                counts[2] += 1
                if item["order_item_id"] in returned_item_ids:
                    counts[3] += 1

        rising = 0
        for early_total, early_ret, late_total, late_ret in totals.values():
            if early_total >= 5 and late_total >= 5:
                early_rate = early_ret / early_total
                late_rate = late_ret / late_total
                if late_rate - early_rate > 0.15:
                    rising += 1

        assert rising > 0


class TestReferentialConsistency:
    def setup_method(self) -> None:
        self.data = generate.generate_all(seed=42)

    def test_order_items_reference_valid_orders(self) -> None:
        order_ids = {o["order_id"] for o in self.data["orders"]}
        assert all(item["order_id"] in order_ids for item in self.data["order_items"])

    def test_returns_reference_valid_order_items(self) -> None:
        item_ids = {i["order_item_id"] for i in self.data["order_items"]}
        assert all(r["order_item_id"] in item_ids for r in self.data["returns"])

    def test_quantity_returned_never_exceeds_quantity_sold(self) -> None:
        items_by_id = {i["order_item_id"]: i for i in self.data["order_items"]}
        for ret in self.data["returns"]:
            item = items_by_id[ret["order_item_id"]]
            assert ret["quantity_returned"] <= item["quantity_sold"]
