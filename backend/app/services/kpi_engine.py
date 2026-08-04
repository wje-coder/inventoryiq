"""Deterministic KPI calculations over a dataset's normalized rows.

No AI/LLM is used anywhere in this module - every figure is a plain
arithmetic aggregate over columns the user has explicitly mapped to a
BusinessField (see app/models/dataset.py). A function returns None
(or an empty list, for the grouped/ranking ones) whenever the fields it
needs weren't mapped, mirroring dataset_service.available_analyses's
gating pattern - a KPI that can't be computed from what was mapped is
simply omitted, never guessed at or defaulted to zero.

Two shapes of result:
- The 15 scalar KPIs (compute_revenue, compute_gross_profit, ...) return
  a KPIValue and are what gets persisted as KPIResult rows by
  app/services/analytics_service.py on `POST /analytics/run`.
- The 10 grouped/ranking/trend functions (product_ranking,
  category_performance, ..., compute_trends) return a list of one of
  the TypedDict record shapes below (ProductRankingRecord,
  DimensionPerformanceRecord, TrendPointRecord) and are always computed
  live (they support filters a frozen snapshot can't answer), never
  persisted.

Typing note: pandas' own stubs type `DataFrame.to_dict(orient="records")`
as `list[dict[Hashable, Any]]`, which is too loose to hand back to
callers (and to app/api/analytics.py's Pydantic response models)
directly. Each grouped/ranking/trend function therefore makes exactly
one `cast` at that boundary - from pandas' loose stub type to the
concrete `list[dict[str, object]]` it's actually known to produce here
- and then converts each row into a precisely-typed record via
_as_float/_as_str, with no further Any or `# type: ignore` needed. The
cast changes nothing at runtime; the float()/str() conversions are
value-preserving (a numpy.float64 and the equivalent Python float
serialize identically to JSON, which is the only place these records
end up).
"""

import dataclasses
from datetime import date
from typing import TypedDict, cast

import pandas as pd

from app.models.dataset import BusinessField

ColumnMap = dict[BusinessField, str]


class ProductRankingRecord(TypedDict):
    product_id: str
    product_name: str | None
    units_sold: float | None
    revenue: float | None


class DimensionPerformanceRecord(TypedDict):
    dimension: str
    units_sold: float | None
    revenue: float | None
    gross_profit: float | None
    units_returned: float | None
    return_rate: float | None


class TrendPointRecord(TypedDict):
    period: str
    units_sold: float | None
    revenue: float | None


def _as_float(value: object) -> float | None:
    """Coerce a pandas cell value (numpy scalar, Python number, or
    missing) to a plain float, or None if it isn't numeric. `bool` is
    excluded even though it's an `int` subclass - none of these columns
    are ever boolean, and accepting one silently would be a bug."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    return None


def _as_str(value: object) -> str | None:
    return None if value is None else str(value)


@dataclasses.dataclass(frozen=True)
class KPIValue:
    value: float
    unit: str


def _numeric(df: pd.DataFrame, column_map: ColumnMap, field: BusinessField) -> pd.Series | None:
    """The mapped column for `field` coerced to numeric (unparseable
    values become NaN), or None if `field` isn't mapped at all."""
    column_name = column_map.get(field)
    if column_name is None or column_name not in df.columns:
        return None
    return pd.to_numeric(df[column_name], errors="coerce")


def _sale_price(df: pd.DataFrame, column_map: ColumnMap) -> pd.Series | None:
    """Prefer SALE_PRICE; fall back to RETAIL_PRICE if no sale price was
    mapped, since many catalogs only have a single "the" price."""
    series = _numeric(df, column_map, BusinessField.SALE_PRICE)
    if series is None:
        series = _numeric(df, column_map, BusinessField.RETAIL_PRICE)
    return series


def _dimension(df: pd.DataFrame, column_map: ColumnMap, field: BusinessField) -> pd.Series | None:
    column_name = column_map.get(field)
    if column_name is None or column_name not in df.columns:
        return None
    return df[column_name].astype(str).str.strip()


# --- Scalar KPIs (persisted as KPIResult rows) ---------------------------


def compute_revenue(df: pd.DataFrame, column_map: ColumnMap) -> KPIValue | None:
    qty = _numeric(df, column_map, BusinessField.QUANTITY_SOLD)
    price = _sale_price(df, column_map)
    if qty is None or price is None:
        return None
    return KPIValue(float((qty.fillna(0) * price.fillna(0)).sum()), "USD")


def compute_gross_profit(df: pd.DataFrame, column_map: ColumnMap) -> KPIValue | None:
    qty = _numeric(df, column_map, BusinessField.QUANTITY_SOLD)
    price = _sale_price(df, column_map)
    cost = _numeric(df, column_map, BusinessField.UNIT_COST)
    if qty is None or price is None or cost is None:
        return None
    profit = (qty.fillna(0) * (price.fillna(0) - cost.fillna(0))).sum()
    return KPIValue(float(profit), "USD")


def compute_gross_margin(df: pd.DataFrame, column_map: ColumnMap) -> KPIValue | None:
    revenue = compute_revenue(df, column_map)
    profit = compute_gross_profit(df, column_map)
    if revenue is None or profit is None or revenue.value == 0:
        return None
    return KPIValue(profit.value / revenue.value * 100, "%")


def compute_average_selling_price(df: pd.DataFrame, column_map: ColumnMap) -> KPIValue | None:
    qty = _numeric(df, column_map, BusinessField.QUANTITY_SOLD)
    price = _sale_price(df, column_map)
    if qty is None or price is None:
        return None
    total_qty = float(qty.fillna(0).sum())
    if total_qty <= 0:
        return None
    total_revenue = float((qty.fillna(0) * price.fillna(0)).sum())
    return KPIValue(total_revenue / total_qty, "USD")


def compute_average_order_value(df: pd.DataFrame, column_map: ColumnMap) -> KPIValue | None:
    order_ids = _dimension(df, column_map, BusinessField.ORDER_ID)
    qty = _numeric(df, column_map, BusinessField.QUANTITY_SOLD)
    price = _sale_price(df, column_map)
    if order_ids is None or qty is None or price is None:
        return None
    distinct_orders = order_ids[order_ids != ""].nunique()
    if distinct_orders <= 0:
        return None
    total_revenue = float((qty.fillna(0) * price.fillna(0)).sum())
    return KPIValue(total_revenue / distinct_orders, "USD")


def compute_inventory_value(df: pd.DataFrame, column_map: ColumnMap) -> KPIValue | None:
    qty_avail = _numeric(df, column_map, BusinessField.QUANTITY_AVAILABLE)
    cost = _numeric(df, column_map, BusinessField.UNIT_COST)
    if qty_avail is None or cost is None:
        return None
    value = (qty_avail.clip(lower=0).fillna(0) * cost.fillna(0)).sum()
    return KPIValue(float(value), "USD")


def compute_inventory_turnover(df: pd.DataFrame, column_map: ColumnMap) -> KPIValue | None:
    qty_sold = _numeric(df, column_map, BusinessField.QUANTITY_SOLD)
    cost = _numeric(df, column_map, BusinessField.UNIT_COST)
    qty_avail = _numeric(df, column_map, BusinessField.QUANTITY_AVAILABLE)
    if qty_sold is None or cost is None or qty_avail is None:
        return None
    cogs = float((qty_sold.fillna(0) * cost.fillna(0)).sum())
    inventory_value = float((qty_avail.clip(lower=0).fillna(0) * cost.fillna(0)).sum())
    if inventory_value <= 0:
        return None
    return KPIValue(cogs / inventory_value, "x")


def compute_sell_through_rate(df: pd.DataFrame, column_map: ColumnMap) -> KPIValue | None:
    qty_sold = _numeric(df, column_map, BusinessField.QUANTITY_SOLD)
    qty_avail = _numeric(df, column_map, BusinessField.QUANTITY_AVAILABLE)
    if qty_sold is None or qty_avail is None:
        return None
    total_sold = float(qty_sold.fillna(0).sum())
    total_avail = float(qty_avail.clip(lower=0).fillna(0).sum())
    denominator = total_sold + total_avail
    if denominator <= 0:
        return None
    return KPIValue(total_sold / denominator * 100, "%")


def compute_return_rate(df: pd.DataFrame, column_map: ColumnMap) -> KPIValue | None:
    qty_sold = _numeric(df, column_map, BusinessField.QUANTITY_SOLD)
    qty_returned = _numeric(df, column_map, BusinessField.QUANTITY_RETURNED)
    if qty_sold is None or qty_returned is None:
        return None
    total_sold = float(qty_sold.fillna(0).sum())
    if total_sold <= 0:
        return None
    total_returned = float(qty_returned.fillna(0).sum())
    return KPIValue(total_returned / total_sold * 100, "%")


def compute_return_cost(df: pd.DataFrame, column_map: ColumnMap) -> KPIValue | None:
    qty_returned = _numeric(df, column_map, BusinessField.QUANTITY_RETURNED)
    price = _sale_price(df, column_map)
    if qty_returned is None or price is None:
        return None
    return KPIValue(float((qty_returned.fillna(0) * price.fillna(0)).sum()), "USD")


def compute_units_sold(df: pd.DataFrame, column_map: ColumnMap) -> KPIValue | None:
    qty = _numeric(df, column_map, BusinessField.QUANTITY_SOLD)
    if qty is None:
        return None
    return KPIValue(float(qty.fillna(0).sum()), "units")


def compute_units_returned(df: pd.DataFrame, column_map: ColumnMap) -> KPIValue | None:
    qty = _numeric(df, column_map, BusinessField.QUANTITY_RETURNED)
    if qty is None:
        return None
    return KPIValue(float(qty.fillna(0).sum()), "units")


def compute_stockouts(df: pd.DataFrame, column_map: ColumnMap) -> KPIValue | None:
    qty_avail = _numeric(df, column_map, BusinessField.QUANTITY_AVAILABLE)
    if qty_avail is None:
        return None
    return KPIValue(float((qty_avail.fillna(0) <= 0).sum()), "count")


def compute_overstock_count(
    df: pd.DataFrame, column_map: ColumnMap, *, multiple: float
) -> KPIValue | None:
    qty_avail = _numeric(df, column_map, BusinessField.QUANTITY_AVAILABLE)
    qty_sold = _numeric(df, column_map, BusinessField.QUANTITY_SOLD)
    if qty_avail is None or qty_sold is None:
        return None
    avail = qty_avail.fillna(0)
    sold = qty_sold.fillna(0)
    overstocked = (avail > 0) & (avail > sold * multiple)
    return KPIValue(float(overstocked.sum()), "count")


def compute_low_inventory_count(
    df: pd.DataFrame, column_map: ColumnMap, *, threshold: int
) -> KPIValue | None:
    qty_avail = _numeric(df, column_map, BusinessField.QUANTITY_AVAILABLE)
    if qty_avail is None:
        return None
    low = qty_avail.fillna(0).between(0, threshold)
    return KPIValue(float(low.sum()), "count")


def compute_all_scalar_kpis(
    df: pd.DataFrame,
    column_map: ColumnMap,
    *,
    overstock_multiple: float,
    low_inventory_threshold: int,
) -> dict[str, KPIValue]:
    """Every scalar KPI whose required fields are mapped, keyed by the
    matching app.models.analytics.KPIName value. Callers persist one
    KPIResult row per entry."""
    candidates: dict[str, KPIValue | None] = {
        "revenue": compute_revenue(df, column_map),
        "gross_profit": compute_gross_profit(df, column_map),
        "gross_margin": compute_gross_margin(df, column_map),
        "average_selling_price": compute_average_selling_price(df, column_map),
        "average_order_value": compute_average_order_value(df, column_map),
        "inventory_value": compute_inventory_value(df, column_map),
        "inventory_turnover": compute_inventory_turnover(df, column_map),
        "sell_through_rate": compute_sell_through_rate(df, column_map),
        "return_rate": compute_return_rate(df, column_map),
        "return_cost": compute_return_cost(df, column_map),
        "units_sold": compute_units_sold(df, column_map),
        "units_returned": compute_units_returned(df, column_map),
        "stockouts": compute_stockouts(df, column_map),
        "overstock_count": compute_overstock_count(df, column_map, multiple=overstock_multiple),
        "low_inventory_count": compute_low_inventory_count(
            df, column_map, threshold=low_inventory_threshold
        ),
    }
    return {name: value for name, value in candidates.items() if value is not None}


# --- Filtering (shared by every grouped/ranking/trend function) ---------


def apply_filters(
    df: pd.DataFrame,
    column_map: ColumnMap,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    category: str | None = None,
    supplier: str | None = None,
    region: str | None = None,
    channel: str | None = None,
) -> pd.DataFrame:
    """Row-level filter applied before any grouped/ranking/trend
    computation. Silently ignores a filter dimension that isn't mapped
    (rather than erroring), since not every dataset maps every field."""
    filtered = df

    if date_from is not None or date_to is not None:
        date_col = column_map.get(BusinessField.ORDER_DATE)
        if date_col and date_col in filtered.columns:
            parsed = pd.to_datetime(filtered[date_col], errors="coerce")
            mask = parsed.notna()
            if date_from is not None:
                mask &= parsed >= pd.Timestamp(date_from)
            if date_to is not None:
                mask &= parsed <= pd.Timestamp(date_to)
            filtered = filtered[mask]

    for field, value in (
        (BusinessField.CATEGORY, category),
        (BusinessField.SUPPLIER, supplier),
        (BusinessField.REGION, region),
        (BusinessField.CHANNEL, channel),
    ):
        if value is None:
            continue
        column_name = column_map.get(field)
        if column_name and column_name in filtered.columns:
            normalized = filtered[column_name].astype(str).str.strip().str.lower()
            filtered = filtered[normalized == value.strip().lower()]

    return filtered


# --- Grouped / ranking / trend results (always computed live) ----------


def _to_product_ranking_records(rows: list[dict[str, object]]) -> list[ProductRankingRecord]:
    records: list[ProductRankingRecord] = []
    for row in rows:
        # "product_id" is always a populated string column by the time rows
        # reach here (product_ranking returns [] earlier if it's unmapped),
        # so - unlike the optional columns below - it's converted directly
        # rather than through _as_str's Optional-returning fallback.
        records.append(
            ProductRankingRecord(
                product_id=str(row["product_id"]),
                product_name=_as_str(row.get("product_name")),
                units_sold=_as_float(row.get("units_sold")),
                revenue=_as_float(row.get("revenue")),
            )
        )
    return records


def product_ranking(
    df: pd.DataFrame, column_map: ColumnMap, *, limit: int, worst: bool = False
) -> list[ProductRankingRecord]:
    """Top (or, if worst=True, bottom) products by units sold, with
    revenue alongside when a price field is also mapped."""
    product_ids = _dimension(df, column_map, BusinessField.PRODUCT_ID)
    qty_sold = _numeric(df, column_map, BusinessField.QUANTITY_SOLD)
    if product_ids is None or qty_sold is None:
        return []

    mask = product_ids != ""
    if not mask.any():
        return []

    working = pd.DataFrame(
        {"product_id": product_ids[mask], "units_sold": qty_sold[mask].fillna(0)}
    )

    name_col = column_map.get(BusinessField.PRODUCT_NAME)
    if name_col and name_col in df.columns:
        working["product_name"] = df[name_col][mask]

    price = _sale_price(df, column_map)
    if price is not None:
        working["revenue"] = qty_sold[mask].fillna(0) * price[mask].fillna(0)

    agg_columns = [c for c in ("units_sold", "revenue") if c in working.columns]
    grouped = working.groupby("product_id", as_index=False)[agg_columns].sum()

    if "product_name" in working.columns:
        first_names = working.groupby("product_id")["product_name"].first()
        grouped = grouped.merge(first_names, on="product_id", how="left")

    grouped = grouped.sort_values("units_sold", ascending=worst).head(limit)
    raw_rows = cast(list[dict[str, object]], grouped.to_dict(orient="records"))
    return _to_product_ranking_records(raw_rows)


def _to_dimension_performance_records(
    rows: list[dict[str, object]],
) -> list[DimensionPerformanceRecord]:
    records: list[DimensionPerformanceRecord] = []
    for row in rows:
        records.append(
            DimensionPerformanceRecord(
                # "dimension" is always a populated string column by the
                # time rows reach here, same as "product_id" above.
                dimension=str(row["dimension"]),
                units_sold=_as_float(row.get("units_sold")),
                revenue=_as_float(row.get("revenue")),
                gross_profit=_as_float(row.get("gross_profit")),
                units_returned=_as_float(row.get("units_returned")),
                return_rate=_as_float(row.get("return_rate")),
            )
        )
    return records


def _performance_by_dimension(
    df: pd.DataFrame, column_map: ColumnMap, dimension_field: BusinessField, *, limit: int | None
) -> list[DimensionPerformanceRecord]:
    """Revenue / units sold / gross profit / return rate grouped by a
    single dimension column (category, brand, supplier, region, or
    channel) - whichever of those figures are computable given what's
    mapped."""
    dimension = _dimension(df, column_map, dimension_field)
    if dimension is None:
        return []

    mask = dimension != ""
    if not mask.any():
        return []

    qty_sold = _numeric(df, column_map, BusinessField.QUANTITY_SOLD)
    price = _sale_price(df, column_map)
    cost = _numeric(df, column_map, BusinessField.UNIT_COST)
    qty_returned = _numeric(df, column_map, BusinessField.QUANTITY_RETURNED)

    working = pd.DataFrame({"dimension": dimension[mask]})
    if qty_sold is not None:
        working["units_sold"] = qty_sold[mask].fillna(0)
    if qty_sold is not None and price is not None:
        working["revenue"] = qty_sold[mask].fillna(0) * price[mask].fillna(0)
    if qty_sold is not None and price is not None and cost is not None:
        working["gross_profit"] = qty_sold[mask].fillna(0) * (
            price[mask].fillna(0) - cost[mask].fillna(0)
        )
    if qty_returned is not None:
        working["units_returned"] = qty_returned[mask].fillna(0)

    numeric_columns = [c for c in working.columns if c != "dimension"]
    if not numeric_columns:
        return []

    grouped = working.groupby("dimension", as_index=False)[numeric_columns].sum()

    if {"units_sold", "units_returned"}.issubset(grouped.columns):
        grouped["return_rate"] = grouped.apply(
            lambda row: (
                (row["units_returned"] / row["units_sold"] * 100) if row["units_sold"] else 0.0
            ),
            axis=1,
        )

    sort_column = next(
        (c for c in ("revenue", "units_sold") if c in grouped.columns), numeric_columns[0]
    )
    grouped = grouped.sort_values(sort_column, ascending=False).reset_index(drop=True)
    if limit is not None:
        grouped = grouped.head(limit)
    raw_rows = cast(list[dict[str, object]], grouped.to_dict(orient="records"))
    return _to_dimension_performance_records(raw_rows)


def category_performance(
    df: pd.DataFrame, column_map: ColumnMap, *, limit: int | None = None
) -> list[DimensionPerformanceRecord]:
    return _performance_by_dimension(df, column_map, BusinessField.CATEGORY, limit=limit)


def brand_performance(
    df: pd.DataFrame, column_map: ColumnMap, *, limit: int | None = None
) -> list[DimensionPerformanceRecord]:
    return _performance_by_dimension(df, column_map, BusinessField.BRAND, limit=limit)


def supplier_performance(
    df: pd.DataFrame, column_map: ColumnMap, *, limit: int | None = None
) -> list[DimensionPerformanceRecord]:
    return _performance_by_dimension(df, column_map, BusinessField.SUPPLIER, limit=limit)


def regional_performance(
    df: pd.DataFrame, column_map: ColumnMap, *, limit: int | None = None
) -> list[DimensionPerformanceRecord]:
    return _performance_by_dimension(df, column_map, BusinessField.REGION, limit=limit)


def channel_performance(
    df: pd.DataFrame, column_map: ColumnMap, *, limit: int | None = None
) -> list[DimensionPerformanceRecord]:
    return _performance_by_dimension(df, column_map, BusinessField.CHANNEL, limit=limit)


_TREND_FREQUENCIES = {"daily": "D", "weekly": "W", "monthly": "MS"}


def _to_trend_point_records(rows: list[dict[str, object]]) -> list[TrendPointRecord]:
    records: list[TrendPointRecord] = []
    for row in rows:
        records.append(
            TrendPointRecord(
                # "period" is always populated (added unconditionally
                # below), unlike the optional units_sold/revenue columns.
                period=str(row["period"]),
                units_sold=_as_float(row.get("units_sold")),
                revenue=_as_float(row.get("revenue")),
            )
        )
    return records


def compute_trends(
    df: pd.DataFrame,
    column_map: ColumnMap,
    *,
    granularity: str = "monthly",
) -> list[TrendPointRecord]:
    """Revenue and units sold grouped into calendar buckets. `granularity`
    is one of "daily", "weekly", "monthly" (Monthly/Weekly/Daily Trends).
    Apply date-range/dimension filters via apply_filters() before calling
    this, not after - trends are meaningless once already aggregated.
    """
    date_col = column_map.get(BusinessField.ORDER_DATE)
    if date_col is None or date_col not in df.columns:
        return []

    qty_sold = _numeric(df, column_map, BusinessField.QUANTITY_SOLD)
    price = _sale_price(df, column_map)

    parsed_dates = pd.to_datetime(df[date_col], errors="coerce")
    mask = parsed_dates.notna()
    if not mask.any():
        return []

    working = pd.DataFrame({"date": parsed_dates[mask]})
    if qty_sold is not None:
        working["units_sold"] = qty_sold[mask].fillna(0)
    if qty_sold is not None and price is not None:
        working["revenue"] = qty_sold[mask].fillna(0) * price[mask].fillna(0)

    numeric_columns = [c for c in working.columns if c != "date"]
    if not numeric_columns:
        return []

    freq = _TREND_FREQUENCIES.get(granularity, "MS")
    resampled = working.set_index("date").resample(freq)[numeric_columns].sum().reset_index()
    resampled["period"] = resampled["date"].dt.strftime("%Y-%m-%d")
    resampled = resampled.drop(columns=["date"])
    raw_rows = cast(list[dict[str, object]], resampled.to_dict(orient="records"))
    return _to_trend_point_records(raw_rows)
