"""Analytics engine, data-quality, anomaly-detector, and API tests.

Three layers, matching the Phase 4 spec's testing requirements:
- Pure unit tests against kpi_engine / data_quality / anomaly_engine
  functions directly on hand-built pandas DataFrames (no DB/HTTP) -
  one assertion per KPI, per data-quality rule, per anomaly detector.
- API integration tests exercising all 10 /analytics/* endpoints
  end-to-end against a real uploaded+mapped dataset.
- Permission/ownership tests: unauthenticated requests, and another
  user's dataset, both must fail without leaking whether the dataset
  exists.
"""

import uuid

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.models.dataset import BusinessField, FindingSeverity
from app.services import anomaly_engine, data_quality, kpi_engine

BF = BusinessField

ANALYTICS_CSV = (
    b"product_id,product_name,category,brand,supplier,unit_cost,retail_price,sale_price,"
    b"quantity_available,quantity_sold,quantity_returned,order_id,order_date,region,channel\n"
    b"P1,Widget,Tools,Acme,SupplyCo,5,12,10,50,3,1,O1,2024-01-01,East,Online\n"
    b"P1,Widget,Tools,Acme,SupplyCo,5,12,10,50,2,0,O2,2024-01-15,West,Retail\n"
    b"P2,Gadget,Electronics,Zenith,PartsInc,10,25,20,2,1,0,O3,2024-02-01,East,Online\n"
    b"P2,Gadget,Electronics,Zenith,PartsInc,10,25,20,2,4,1,O4,2024-02-10,East,Retail\n"
    b"P3,Gizmo,Electronics,Zenith,PartsInc,2,5,4,0,0,0,O5,2024-03-01,West,Online\n"
)

_COLUMN_MAP_FIELDS = {
    "product_id": BF.PRODUCT_ID.value,
    "product_name": BF.PRODUCT_NAME.value,
    "category": BF.CATEGORY.value,
    "brand": BF.BRAND.value,
    "supplier": BF.SUPPLIER.value,
    "unit_cost": BF.UNIT_COST.value,
    "retail_price": BF.RETAIL_PRICE.value,
    "sale_price": BF.SALE_PRICE.value,
    "quantity_available": BF.QUANTITY_AVAILABLE.value,
    "quantity_sold": BF.QUANTITY_SOLD.value,
    "quantity_returned": BF.QUANTITY_RETURNED.value,
    "order_id": BF.ORDER_ID.value,
    "order_date": BF.ORDER_DATE.value,
    "region": BF.REGION.value,
    "channel": BF.CHANNEL.value,
}


def _register(client: TestClient, email: str) -> dict:
    response = client.post(
        "/auth/register",
        json={"email": email, "password": "correct horse battery", "full_name": "Test User"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _upload_and_map(client: TestClient, token: str, content: bytes = ANALYTICS_CSV) -> str:
    upload = client.post(
        "/datasets/upload",
        headers=_auth_headers(token),
        files={"file": ("sales.csv", content, "text/csv")},
    )
    assert upload.status_code == 201, upload.text
    dataset_id = upload.json()["id"]

    columns_resp = client.get(f"/datasets/{dataset_id}/columns", headers=_auth_headers(token))
    assert columns_resp.status_code == 200, columns_resp.text
    columns = columns_resp.json()["columns"]

    mapping_items = []
    for col in columns:
        field = _COLUMN_MAP_FIELDS.get(col["source_name"])
        if field is not None:
            mapping_items.append({"column_id": col["id"], "mapped_business_field": field})

    patch_resp = client.patch(
        f"/datasets/{dataset_id}/columns",
        headers=_auth_headers(token),
        json={"columns": mapping_items},
    )
    assert patch_resp.status_code == 200, patch_resp.text
    return dataset_id


# ===========================================================================
# kpi_engine unit tests - one per scalar KPI, plus grouped/ranking/trends
# ===========================================================================


def _kpi_test_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "prod_id": ["P1", "P1", "P2", "P2", "P3"],
            "prod_name": ["Widget", "Widget", "Gadget", "Gadget", "Gizmo"],
            "cat": ["Tools", "Tools", "Elec", "Elec", "Elec"],
            "region": ["East", "West", "East", "East", "West"],
            "cost": [5, 5, 10, 10, 2],
            "price": [10, 10, 20, 20, 4],
            "qty_sold": [3, 2, 1, 4, 0],
            "qty_returned": [1, 0, 0, 1, 0],
            "qty_avail": [50, 50, 2, 2, 0],
            "order": ["O1", "O2", "O1", "O3", "O4"],
            "order_date": [
                "2024-01-01",
                "2024-01-15",
                "2024-02-01",
                "2024-02-10",
                "2024-03-01",
            ],
        }
    )


def _kpi_test_map() -> kpi_engine.ColumnMap:
    return {
        BF.PRODUCT_ID: "prod_id",
        BF.PRODUCT_NAME: "prod_name",
        BF.CATEGORY: "cat",
        BF.REGION: "region",
        BF.UNIT_COST: "cost",
        BF.SALE_PRICE: "price",
        BF.QUANTITY_SOLD: "qty_sold",
        BF.QUANTITY_RETURNED: "qty_returned",
        BF.QUANTITY_AVAILABLE: "qty_avail",
        BF.ORDER_ID: "order",
        BF.ORDER_DATE: "order_date",
    }


def test_kpi_revenue() -> None:
    result = kpi_engine.compute_revenue(_kpi_test_df(), _kpi_test_map())
    assert result is not None
    assert result.value == pytest.approx(150.0)
    assert result.unit == "USD"


def test_kpi_gross_profit() -> None:
    result = kpi_engine.compute_gross_profit(_kpi_test_df(), _kpi_test_map())
    assert result is not None
    assert result.value == pytest.approx(75.0)


def test_kpi_gross_margin() -> None:
    result = kpi_engine.compute_gross_margin(_kpi_test_df(), _kpi_test_map())
    assert result is not None
    assert result.value == pytest.approx(50.0)
    assert result.unit == "%"


def test_kpi_average_selling_price() -> None:
    result = kpi_engine.compute_average_selling_price(_kpi_test_df(), _kpi_test_map())
    assert result is not None
    assert result.value == pytest.approx(15.0)


def test_kpi_average_order_value() -> None:
    result = kpi_engine.compute_average_order_value(_kpi_test_df(), _kpi_test_map())
    assert result is not None
    assert result.value == pytest.approx(37.5)


def test_kpi_inventory_value() -> None:
    result = kpi_engine.compute_inventory_value(_kpi_test_df(), _kpi_test_map())
    assert result is not None
    assert result.value == pytest.approx(540.0)


def test_kpi_inventory_turnover() -> None:
    result = kpi_engine.compute_inventory_turnover(_kpi_test_df(), _kpi_test_map())
    assert result is not None
    assert result.value == pytest.approx(75.0 / 540.0)


def test_kpi_sell_through_rate() -> None:
    result = kpi_engine.compute_sell_through_rate(_kpi_test_df(), _kpi_test_map())
    assert result is not None
    assert result.value == pytest.approx(10.0 / 114.0 * 100)


def test_kpi_return_rate() -> None:
    result = kpi_engine.compute_return_rate(_kpi_test_df(), _kpi_test_map())
    assert result is not None
    assert result.value == pytest.approx(20.0)


def test_kpi_return_cost() -> None:
    result = kpi_engine.compute_return_cost(_kpi_test_df(), _kpi_test_map())
    assert result is not None
    assert result.value == pytest.approx(30.0)


def test_kpi_units_sold() -> None:
    result = kpi_engine.compute_units_sold(_kpi_test_df(), _kpi_test_map())
    assert result is not None
    assert result.value == pytest.approx(10.0)


def test_kpi_units_returned() -> None:
    result = kpi_engine.compute_units_returned(_kpi_test_df(), _kpi_test_map())
    assert result is not None
    assert result.value == pytest.approx(2.0)


def test_kpi_stockouts() -> None:
    result = kpi_engine.compute_stockouts(_kpi_test_df(), _kpi_test_map())
    assert result is not None
    assert result.value == pytest.approx(1.0)


def test_kpi_overstock_count() -> None:
    result = kpi_engine.compute_overstock_count(_kpi_test_df(), _kpi_test_map(), multiple=3.0)
    assert result is not None
    assert result.value == pytest.approx(2.0)


def test_kpi_low_inventory_count() -> None:
    result = kpi_engine.compute_low_inventory_count(_kpi_test_df(), _kpi_test_map(), threshold=10)
    assert result is not None
    assert result.value == pytest.approx(3.0)


def test_kpi_compute_all_scalar_kpis_gates_on_mapping() -> None:
    full = kpi_engine.compute_all_scalar_kpis(
        _kpi_test_df(), _kpi_test_map(), overstock_multiple=3.0, low_inventory_threshold=10
    )
    assert len(full) == 15

    empty = kpi_engine.compute_all_scalar_kpis(
        _kpi_test_df(), {}, overstock_multiple=3.0, low_inventory_threshold=10
    )
    assert empty == {}


def test_kpi_product_ranking_top_and_worst() -> None:
    top = kpi_engine.product_ranking(_kpi_test_df(), _kpi_test_map(), limit=5)
    worst = kpi_engine.product_ranking(_kpi_test_df(), _kpi_test_map(), limit=5, worst=True)
    assert top[0]["product_id"] in ("P1", "P2")
    assert worst[0]["product_id"] == "P3"


def test_kpi_category_performance() -> None:
    rows = kpi_engine.category_performance(_kpi_test_df(), _kpi_test_map())
    dimensions = {row["dimension"] for row in rows}
    assert dimensions == {"Tools", "Elec"}


def test_kpi_regional_performance() -> None:
    rows = kpi_engine.regional_performance(_kpi_test_df(), _kpi_test_map())
    dimensions = {row["dimension"] for row in rows}
    assert dimensions == {"East", "West"}


def test_kpi_compute_trends_monthly() -> None:
    rows = kpi_engine.compute_trends(_kpi_test_df(), _kpi_test_map(), granularity="monthly")
    assert [row["period"] for row in rows] == ["2024-01-01", "2024-02-01", "2024-03-01"]


def test_kpi_apply_filters_by_category() -> None:
    filtered = kpi_engine.apply_filters(_kpi_test_df(), _kpi_test_map(), category="Elec")
    assert len(filtered) == 3


# ===========================================================================
# data_quality unit tests - one per detection rule, plus the 4+1 scores
# ===========================================================================


def _quality_test_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "prod_id": ["P1", "P2", "P3", "P4", "P5", "P5", "P6", "P7", "P8", "P9"],
            "cat": ["Tools", "", "Tools", "Tools", "Elec", "Elec", "Elec", "Elec", "Elec", "Elec"],
            "cost": [5, 5, -3, 5, 5, 5, 5, 5, 5, 20],
            "price": [10, 10, 10, 10, 10, 10, 10, 10, 10, 10],
            "qty_sold": [3, 2, 1, -4, 1, 1, 1, 1, 1, 1],
            "qty_avail": [50, 50, 2, 2, 10, 10, 10, 10, 10, 10],
            "upc": [
                "123456789012",
                "123456789012",
                "123456789012",
                "123456789012",
                "123456789012",
                "123456789012",
                "123456789012",
                "123456789012",
                "BADUPC",
                "123456789012",
            ],
            "order": ["O1", "O2", "O3", "O4", "O5", "O5", "O7", "O8", "O9", "O10"],
            "order_date": [
                "2024-01-01",
                "2024-01-15",
                "2024-02-01",
                "2024-02-10",
                "2024-03-01",
                "2024-03-01",
                "not-a-date",
                "2099-01-01",
                "2024-04-01",
                "2024-04-05",
            ],
        }
    )


def _quality_test_map() -> data_quality.ColumnMap:
    return {
        BF.PRODUCT_ID: "prod_id",
        BF.CATEGORY: "cat",
        BF.UNIT_COST: "cost",
        BF.SALE_PRICE: "price",
        BF.QUANTITY_SOLD: "qty_sold",
        BF.QUANTITY_AVAILABLE: "qty_avail",
        BF.UPC: "upc",
        BF.ORDER_ID: "order",
        BF.ORDER_DATE: "order_date",
    }


def test_quality_scores_are_bounded_and_sensible() -> None:
    scores = data_quality.compute_quality_scores(_quality_test_df(), _quality_test_map())
    for value in (
        scores.completeness_score,
        scores.validity_score,
        scores.consistency_score,
        scores.uniqueness_score,
        scores.overall_score,
    ):
        assert 0.0 <= value <= 100.0
    assert scores.overall_score == pytest.approx(
        (
            scores.completeness_score
            + scores.validity_score
            + scores.consistency_score
            + scores.uniqueness_score
        )
        / 4
    )


@pytest.mark.parametrize(
    "expected_category",
    [
        "Missing values",
        "Duplicate rows",
        "Duplicate keys",
        "Negative prices",
        "Negative quantities",
        "Invalid dates",
        "Future dates",
        "Malformed UPCs",
        "Unknown categories",
        "Invalid margins",
    ],
)
def test_quality_detection_rule_fires(expected_category: str) -> None:
    findings = data_quality.run_detection_rules(
        _quality_test_df(), _quality_test_map(), iqr_multiplier=1.5
    )
    categories = {f.category for f in findings}
    assert expected_category in categories


def test_quality_negative_inventory_rule() -> None:
    df = _quality_test_df().copy()
    df.loc[0, "qty_avail"] = -5
    findings = data_quality.run_detection_rules(df, _quality_test_map(), iqr_multiplier=1.5)
    categories = {f.category for f in findings}
    assert "Negative inventory" in categories


def test_quality_unknown_suppliers_rule() -> None:
    df = _quality_test_df().copy()
    df["supplier"] = ["Acme", "", "Acme", "Acme", "Acme", "Acme", "Acme", "Acme", "Acme", "Acme"]
    column_map = {**_quality_test_map(), BF.SUPPLIER: "supplier"}
    findings = data_quality.run_detection_rules(df, column_map, iqr_multiplier=1.5)
    categories = {f.category for f in findings}
    assert "Unknown suppliers" in categories


def test_quality_outlier_prices_and_quantities() -> None:
    # Prices/quantities need genuine spread for IQR fences to be
    # meaningful (Tukey's fences degenerate to a single point, and
    # therefore never fire, when most values are identical) - this
    # uses a standalone dataframe with natural spread plus one clear
    # outlier in each of price and quantity_sold.
    prices = [9.0, 9.5, 10.0, 10.2, 9.8, 10.5, 9.6, 10.1, 9.9, 10.3, 100000.0]
    qtys = [3, 4, 2, 5, 3, 4, 2, 3, 4, 3, 100000]
    df = pd.DataFrame(
        {"prod_id": [f"P{i}" for i in range(len(prices))], "price": prices, "qty_sold": qtys}
    )
    column_map = {BF.PRODUCT_ID: "prod_id", BF.SALE_PRICE: "price", BF.QUANTITY_SOLD: "qty_sold"}
    findings = data_quality.run_detection_rules(df, column_map, iqr_multiplier=1.5)
    categories = {f.category for f in findings}
    assert "Outlier prices" in categories
    assert "Outlier quantities" in categories


def test_quality_findings_have_required_shape() -> None:
    findings = data_quality.run_detection_rules(
        _quality_test_df(), _quality_test_map(), iqr_multiplier=1.5
    )
    assert findings
    for finding in findings:
        assert isinstance(finding.severity, FindingSeverity)
        assert finding.category
        assert finding.description
        assert finding.recommendation


def test_quality_no_mapping_yields_perfect_scores_and_no_findings() -> None:
    scores = data_quality.compute_quality_scores(_quality_test_df(), {})
    findings = data_quality.run_detection_rules(_quality_test_df(), {}, iqr_multiplier=1.5)
    assert scores.completeness_score == 100.0
    assert scores.validity_score == 100.0
    assert scores.consistency_score == 100.0
    assert len(findings) <= 1  # duplicate-row check still runs across all columns


# ===========================================================================
# anomaly_engine unit tests - one per detector
# ===========================================================================


def _anomaly_test_df() -> pd.DataFrame:
    rows = []
    months = pd.date_range("2024-01-01", periods=12, freq="MS")
    for i, month in enumerate(months):
        qty_sold = 100
        qty_returned = 5
        if i == 5:
            qty_sold = 500
            qty_returned = 60
        rows.append(
            {
                "prod_id": f"NORM{i}",
                "cost": 5,
                "price": 10,
                "qty_sold": qty_sold,
                "qty_returned": qty_returned,
                "qty_avail": 100,
                "order_date": month.strftime("%Y-%m-%d"),
            }
        )
    rows.append(
        {
            "prod_id": "OVERSTOCK1",
            "cost": 5,
            "price": 10,
            "qty_sold": 100,
            "qty_returned": 0,
            "qty_avail": 5000,
            "order_date": "2024-06-15",
        }
    )
    rows.append(
        {
            "prod_id": "TURNOVER1",
            "cost": 5,
            "price": 10,
            "qty_sold": 1,
            "qty_returned": 0,
            "qty_avail": 400,
            "order_date": "2024-06-15",
        }
    )
    return pd.DataFrame(rows)


def _anomaly_test_map() -> anomaly_engine.ColumnMap:
    return {
        BF.PRODUCT_ID: "prod_id",
        BF.UNIT_COST: "cost",
        BF.SALE_PRICE: "price",
        BF.QUANTITY_SOLD: "qty_sold",
        BF.QUANTITY_RETURNED: "qty_returned",
        BF.QUANTITY_AVAILABLE: "qty_avail",
        BF.ORDER_DATE: "order_date",
    }


def test_anomaly_revenue_spikes() -> None:
    findings = anomaly_engine.detect_revenue_anomalies(
        _anomaly_test_df(), _anomaly_test_map(), zscore_threshold=2.0
    )
    assert any(f.anomaly_type == "Revenue spikes" for f in findings)


def test_anomaly_revenue_drops() -> None:
    # A standalone series (no spike present) - combining a spike and a
    # drop in the same 12-point series can inflate the standard
    # deviation enough to mask a merely-moderate drop, which is a real
    # statistical effect rather than a detector bug (see module
    # docstring); this test isolates the drop to avoid that dilution.
    rows = []
    months = pd.date_range("2024-01-01", periods=12, freq="MS")
    for i, month in enumerate(months):
        qty_sold = 100
        if i == 8:
            qty_sold = 5
        rows.append(
            {
                "prod_id": f"NORM{i}",
                "cost": 5,
                "price": 10,
                "qty_sold": qty_sold,
                "qty_returned": 5,
                "qty_avail": 100,
                "order_date": month.strftime("%Y-%m-%d"),
            }
        )
    df = pd.DataFrame(rows)
    findings = anomaly_engine.detect_revenue_anomalies(
        df, _anomaly_test_map(), zscore_threshold=2.0
    )
    assert any(f.anomaly_type == "Revenue drops" for f in findings)


def test_anomaly_return_spikes() -> None:
    findings = anomaly_engine.detect_return_spikes(
        _anomaly_test_df(), _anomaly_test_map(), zscore_threshold=2.0
    )
    assert any(f.anomaly_type == "Return spikes" for f in findings)


def test_anomaly_sales_anomalies() -> None:
    findings = anomaly_engine.detect_sales_anomalies(
        _anomaly_test_df(), _anomaly_test_map(), zscore_threshold=2.0
    )
    assert any(f.anomaly_type == "Sales anomalies" for f in findings)


def _inventory_level_df(*, extra_avail: float, extra_id: str) -> pd.DataFrame:
    # A spike and a drop that are both extreme relative to the same
    # peer distribution can mask each other (the spike inflates
    # variance enough to hide a moderate drop, and vice versa) - so
    # spikes and drops are each tested against their own isolated
    # peer distribution, matching how they'd realistically be
    # evaluated one product at a time.
    avails = [95, 105, 100, 98, 102, 97, 103, 99, 101, 96, 104, 100, 98, 102, 100]
    rows = [{"prod_id": f"P{i}", "qty_avail": avail} for i, avail in enumerate(avails)]
    rows.append({"prod_id": extra_id, "qty_avail": extra_avail})
    return pd.DataFrame(rows)


def test_anomaly_inventory_spikes() -> None:
    df = _inventory_level_df(extra_avail=5000, extra_id="OVERSTOCK1")
    column_map = {BF.PRODUCT_ID: "prod_id", BF.QUANTITY_AVAILABLE: "qty_avail"}
    findings = anomaly_engine.detect_inventory_anomalies_by_level(
        df, column_map, zscore_threshold=2.0
    )
    assert any(f.anomaly_type == "Inventory spikes" and f.entity == "OVERSTOCK1" for f in findings)


def test_anomaly_inventory_drops() -> None:
    df = _inventory_level_df(extra_avail=1, extra_id="UNDERSTOCK1")
    column_map = {BF.PRODUCT_ID: "prod_id", BF.QUANTITY_AVAILABLE: "qty_avail"}
    findings = anomaly_engine.detect_inventory_anomalies_by_level(
        df, column_map, zscore_threshold=2.0
    )
    assert any(f.anomaly_type == "Inventory drops" and f.entity == "UNDERSTOCK1" for f in findings)


def test_anomaly_inventory_turnover_anomalies() -> None:
    findings = anomaly_engine.detect_inventory_turnover_anomalies(
        _anomaly_test_df(), _anomaly_test_map(), zscore_threshold=2.0
    )
    assert any(f.anomaly_type == "Inventory anomalies" for f in findings)


def test_anomaly_price_anomalies() -> None:
    # Prices need genuine spread across products for IQR fences to be
    # meaningful (Tukey's fences degenerate to a single point, and
    # therefore never fire, when most values are identical) - see
    # data_quality._iqr_outlier_mask's same "iqr == 0" guard.
    prices = [9.0, 9.5, 10.0, 10.2, 9.8, 10.5, 9.6, 10.1, 9.9, 10.3, 9.7, 10.4, 500.0]
    costs = [5.0, 5.2, 4.8, 5.1, 4.9, 5.3, 4.7, 5.0, 5.2, 4.9, 5.1, 4.8, 5.0]
    df = pd.DataFrame(
        {"prod_id": [f"P{i}" for i in range(len(prices))], "price": prices, "cost": costs}
    )
    column_map = {BF.PRODUCT_ID: "prod_id", BF.UNIT_COST: "cost", BF.SALE_PRICE: "price"}
    findings = anomaly_engine.detect_price_anomalies(df, column_map, iqr_multiplier=1.5)
    assert any(f.anomaly_type == "Price anomalies" and f.entity == "P12" for f in findings)


def test_anomaly_margin_anomalies() -> None:
    prices = [10.0, 10.5, 9.8, 10.2, 9.9, 10.3, 9.7, 10.1, 9.9, 10.4, 9.6, 10.0, 6.0]
    costs = [5.0, 5.3, 4.9, 5.1, 5.0, 5.2, 4.8, 5.0, 4.9, 5.1, 4.8, 5.0, 5.9]
    df = pd.DataFrame(
        {"prod_id": [f"P{i}" for i in range(len(prices))], "price": prices, "cost": costs}
    )
    column_map = {BF.PRODUCT_ID: "prod_id", BF.UNIT_COST: "cost", BF.SALE_PRICE: "price"}
    findings = anomaly_engine.detect_margin_anomalies(df, column_map, iqr_multiplier=1.5)
    assert any(f.anomaly_type == "Margin anomalies" and f.entity == "P12" for f in findings)


def test_anomaly_run_all_detectors_no_mapping_yields_nothing() -> None:
    findings = anomaly_engine.run_all_detectors(
        _anomaly_test_df(), {}, zscore_threshold=2.0, iqr_multiplier=1.5
    )
    assert findings == []


# ===========================================================================
# API integration tests: endpoints, permissions, dataset ownership
# ===========================================================================


def test_run_analytics_and_read_summary(client: TestClient) -> None:
    user = _register(client, "analytics-owner@example.com")
    token = user["access_token"]
    dataset_id = _upload_and_map(client, token)

    run_resp = client.post(
        "/analytics/run", params={"dataset_id": dataset_id}, headers=_auth_headers(token)
    )
    assert run_resp.status_code == 200, run_resp.text
    run_body = run_resp.json()
    assert run_body["job"]["status"] == "completed"
    assert run_body["snapshot"]["row_count"] == 5

    summary_resp = client.get(
        "/analytics/summary", params={"dataset_id": dataset_id}, headers=_auth_headers(token)
    )
    assert summary_resp.status_code == 200, summary_resp.text
    summary_body = summary_resp.json()
    assert len(summary_body["kpis"]) == 15
    assert summary_body["data_quality_overall_score"] is not None


def test_get_kpis_before_run_returns_404(client: TestClient) -> None:
    user = _register(client, "no-run-yet@example.com")
    token = user["access_token"]
    dataset_id = _upload_and_map(client, token)

    resp = client.get(
        "/analytics/kpis", params={"dataset_id": dataset_id}, headers=_auth_headers(token)
    )
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "ANALYTICS_NOT_RUN"


def test_get_data_quality_endpoint(client: TestClient) -> None:
    user = _register(client, "quality-endpoint@example.com")
    token = user["access_token"]
    dataset_id = _upload_and_map(client, token)
    client.post("/analytics/run", params={"dataset_id": dataset_id}, headers=_auth_headers(token))

    resp = client.get(
        "/analytics/data-quality", params={"dataset_id": dataset_id}, headers=_auth_headers(token)
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert 0.0 <= body["overall_score"] <= 100.0


def test_get_anomalies_endpoint(client: TestClient) -> None:
    user = _register(client, "anomalies-endpoint@example.com")
    token = user["access_token"]
    dataset_id = _upload_and_map(client, token)

    resp = client.get(
        "/analytics/anomalies", params={"dataset_id": dataset_id}, headers=_auth_headers(token)
    )
    assert resp.status_code == 200, resp.text
    assert "anomalies" in resp.json()


def test_get_trends_endpoint_with_granularity(client: TestClient) -> None:
    user = _register(client, "trends-endpoint@example.com")
    token = user["access_token"]
    dataset_id = _upload_and_map(client, token)

    resp = client.get(
        "/analytics/trends",
        params={"dataset_id": dataset_id, "granularity": "monthly"},
        headers=_auth_headers(token),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["granularity"] == "monthly"
    assert len(body["points"]) >= 1


def test_get_products_endpoint(client: TestClient) -> None:
    user = _register(client, "products-endpoint@example.com")
    token = user["access_token"]
    dataset_id = _upload_and_map(client, token)

    resp = client.get(
        "/analytics/products", params={"dataset_id": dataset_id}, headers=_auth_headers(token)
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["top_products"]) > 0
    assert len(body["worst_products"]) > 0


def test_get_categories_endpoint(client: TestClient) -> None:
    user = _register(client, "categories-endpoint@example.com")
    token = user["access_token"]
    dataset_id = _upload_and_map(client, token)

    resp = client.get(
        "/analytics/categories", params={"dataset_id": dataset_id}, headers=_auth_headers(token)
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    dimensions = {row["dimension"] for row in body["categories"]}
    assert dimensions == {"Tools", "Electronics"}


def test_get_suppliers_endpoint(client: TestClient) -> None:
    user = _register(client, "suppliers-endpoint@example.com")
    token = user["access_token"]
    dataset_id = _upload_and_map(client, token)

    resp = client.get(
        "/analytics/suppliers", params={"dataset_id": dataset_id}, headers=_auth_headers(token)
    )
    assert resp.status_code == 200, resp.text
    dimensions = {row["dimension"] for row in resp.json()["suppliers"]}
    assert dimensions == {"SupplyCo", "PartsInc"}


def test_get_regions_endpoint(client: TestClient) -> None:
    user = _register(client, "regions-endpoint@example.com")
    token = user["access_token"]
    dataset_id = _upload_and_map(client, token)

    resp = client.get(
        "/analytics/regions", params={"dataset_id": dataset_id}, headers=_auth_headers(token)
    )
    assert resp.status_code == 200, resp.text
    dimensions = {row["dimension"] for row in resp.json()["regions"]}
    assert dimensions == {"East", "West"}


def test_analytics_filters_narrow_results(client: TestClient) -> None:
    user = _register(client, "filters-endpoint@example.com")
    token = user["access_token"]
    dataset_id = _upload_and_map(client, token)

    resp = client.get(
        "/analytics/regions",
        params={"dataset_id": dataset_id, "region": "East"},
        headers=_auth_headers(token),
    )
    assert resp.status_code == 200, resp.text
    dimensions = {row["dimension"] for row in resp.json()["regions"]}
    assert dimensions == {"East"}


def test_analytics_endpoints_require_authentication(client: TestClient) -> None:
    dataset_id = str(uuid.uuid4())
    for path in (
        "/analytics/summary",
        "/analytics/kpis",
        "/analytics/data-quality",
        "/analytics/anomalies",
        "/analytics/trends",
        "/analytics/products",
        "/analytics/categories",
        "/analytics/suppliers",
        "/analytics/regions",
    ):
        resp = client.get(path, params={"dataset_id": dataset_id})
        assert resp.status_code == 401, f"{path} did not require auth"

    run_resp = client.post("/analytics/run", params={"dataset_id": dataset_id})
    assert run_resp.status_code == 401


def test_analytics_enforces_dataset_ownership(client: TestClient) -> None:
    owner = _register(client, "owner-of-dataset@example.com")
    other = _register(client, "not-the-owner@example.com")
    dataset_id = _upload_and_map(client, owner["access_token"])

    resp = client.get(
        "/analytics/summary",
        params={"dataset_id": dataset_id},
        headers=_auth_headers(other["access_token"]),
    )
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "DATASET_NOT_FOUND"

    run_resp = client.post(
        "/analytics/run",
        params={"dataset_id": dataset_id},
        headers=_auth_headers(other["access_token"]),
    )
    assert run_resp.status_code == 404
    assert run_resp.json()["detail"]["code"] == "DATASET_NOT_FOUND"


def test_analytics_nonexistent_dataset_returns_404(client: TestClient) -> None:
    user = _register(client, "nonexistent-dataset@example.com")
    resp = client.get(
        "/analytics/summary",
        params={"dataset_id": str(uuid.uuid4())},
        headers=_auth_headers(user["access_token"]),
    )
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "DATASET_NOT_FOUND"
