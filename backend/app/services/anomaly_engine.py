"""Deterministic anomaly detection over a dataset's normalized rows.

No AI/LLM is used anywhere in this module. Every anomaly is flagged by a
plain statistical rule - a z-score against a distribution, or an IQR
(Tukey's fence) - never a model's judgment call. As with kpi_engine and
data_quality, a detector that needs a field that isn't mapped simply
yields nothing.

Two families of detector, both driven by the same underlying idea
(compare a value to the spread of its peers) but applied along
different axes:

- Time-series detectors (Revenue spikes/drops, Return spikes, Sales
  anomalies) bucket rows into calendar periods and z-score each
  period's total against the mean/stdev of all periods.
- Cross-sectional detectors (Inventory spikes/drops, Inventory
  anomalies, Price anomalies, Margin anomalies) compare each row (or
  each product, where a product id is mapped) against the distribution
  of its peers at a single point in time - no dates required.

"Inventory spikes"/"Inventory drops" flag raw on-hand quantity that is
statistically high/low relative to peers; "Inventory anomalies" is a
distinct check on the *ratio* of stock to sales velocity (a product can
have an unremarkable stock level yet still be a turnover outlier).
"""

import dataclasses

import numpy as np
import pandas as pd

from app.models.dataset import BusinessField

ColumnMap = dict[BusinessField, str]

_TREND_FREQUENCIES = {"daily": "D", "weekly": "W", "monthly": "MS"}


@dataclasses.dataclass(frozen=True)
class AnomalyFinding:
    anomaly_type: str
    severity: str  # "warning" | "error" - kept as plain str, not tied to FindingSeverity
    entity: str
    metric: str
    value: float
    z_score: float
    description: str


def _numeric(df: pd.DataFrame, column_map: ColumnMap, field: BusinessField) -> pd.Series | None:
    column_name = column_map.get(field)
    if column_name is None or column_name not in df.columns:
        return None
    return pd.to_numeric(df[column_name], errors="coerce")


def _sale_price(df: pd.DataFrame, column_map: ColumnMap) -> pd.Series | None:
    series = _numeric(df, column_map, BusinessField.SALE_PRICE)
    if series is None:
        series = _numeric(df, column_map, BusinessField.RETAIL_PRICE)
    return series


def _zscores(series: pd.Series) -> pd.Series | None:
    clean = series.dropna()
    if len(clean) < 3:
        return None
    std = clean.std()
    if not std or std == 0:
        return None
    mean = clean.mean()
    return (series - mean) / std


def _severity_for(z: float, threshold: float) -> str:
    return "error" if abs(z) >= threshold * 1.5 else "warning"


# --- Time-series detectors -------------------------------------------------


def _period_series(
    df: pd.DataFrame, column_map: ColumnMap, value_field: BusinessField, *, granularity: str
) -> pd.Series | None:
    """Sum of `value_field` per calendar period, indexed by period label."""
    date_col = column_map.get(BusinessField.ORDER_DATE)
    if date_col is None or date_col not in df.columns:
        return None
    values = _numeric(df, column_map, value_field)
    if values is None:
        return None
    parsed = pd.to_datetime(df[date_col], errors="coerce")
    mask = parsed.notna()
    if not mask.any():
        return None
    working = pd.DataFrame({"date": parsed[mask], "value": values[mask].fillna(0)})
    freq = _TREND_FREQUENCIES.get(granularity, "MS")
    resampled = working.set_index("date").resample(freq)["value"].sum()
    if len(resampled) < 3:
        return None
    resampled.index = resampled.index.strftime("%Y-%m-%d")
    return resampled


def _revenue_period_series(
    df: pd.DataFrame, column_map: ColumnMap, *, granularity: str
) -> pd.Series | None:
    date_col = column_map.get(BusinessField.ORDER_DATE)
    qty = _numeric(df, column_map, BusinessField.QUANTITY_SOLD)
    price = _sale_price(df, column_map)
    if date_col is None or date_col not in df.columns or qty is None or price is None:
        return None
    parsed = pd.to_datetime(df[date_col], errors="coerce")
    mask = parsed.notna()
    if not mask.any():
        return None
    revenue = (qty.fillna(0) * price.fillna(0))[mask]
    working = pd.DataFrame({"date": parsed[mask], "value": revenue})
    freq = _TREND_FREQUENCIES.get(granularity, "MS")
    resampled = working.set_index("date").resample(freq)["value"].sum()
    if len(resampled) < 3:
        return None
    resampled.index = resampled.index.strftime("%Y-%m-%d")
    return resampled


def detect_revenue_anomalies(
    df: pd.DataFrame,
    column_map: ColumnMap,
    *,
    zscore_threshold: float,
    granularity: str = "monthly",
) -> list[AnomalyFinding]:
    """Revenue spikes and Revenue drops: one detector, two anomaly_type
    labels depending on the sign of the period's z-score."""
    series = _revenue_period_series(df, column_map, granularity=granularity)
    if series is None:
        return []
    z = _zscores(series)
    if z is None:
        return []
    findings: list[AnomalyFinding] = []
    for period, z_value in z.items():
        if abs(z_value) < zscore_threshold:
            continue
        anomaly_type = "Revenue spikes" if z_value > 0 else "Revenue drops"
        direction = "spiked" if z_value > 0 else "dropped"
        findings.append(
            AnomalyFinding(
                anomaly_type=anomaly_type,
                severity=_severity_for(z_value, zscore_threshold),
                entity=str(period),
                metric="revenue",
                value=float(series[period]),
                z_score=float(z_value),
                description=f"Revenue {direction} in {period} (z-score {z_value:.2f}).",
            )
        )
    return findings


def detect_return_spikes(
    df: pd.DataFrame,
    column_map: ColumnMap,
    *,
    zscore_threshold: float,
    granularity: str = "monthly",
) -> list[AnomalyFinding]:
    series = _period_series(
        df, column_map, BusinessField.QUANTITY_RETURNED, granularity=granularity
    )
    if series is None:
        return []
    z = _zscores(series)
    if z is None:
        return []
    findings: list[AnomalyFinding] = []
    for period, z_value in z.items():
        if z_value < zscore_threshold:
            continue
        findings.append(
            AnomalyFinding(
                anomaly_type="Return spikes",
                severity=_severity_for(z_value, zscore_threshold),
                entity=str(period),
                metric="units_returned",
                value=float(series[period]),
                z_score=float(z_value),
                description=f"Returns spiked in {period} (z-score {z_value:.2f}).",
            )
        )
    return findings


def detect_sales_anomalies(
    df: pd.DataFrame,
    column_map: ColumnMap,
    *,
    zscore_threshold: float,
    granularity: str = "monthly",
) -> list[AnomalyFinding]:
    series = _period_series(df, column_map, BusinessField.QUANTITY_SOLD, granularity=granularity)
    if series is None:
        return []
    z = _zscores(series)
    if z is None:
        return []
    findings: list[AnomalyFinding] = []
    for period, z_value in z.items():
        if abs(z_value) < zscore_threshold:
            continue
        direction = "spiked" if z_value > 0 else "dropped"
        findings.append(
            AnomalyFinding(
                anomaly_type="Sales anomalies",
                severity=_severity_for(z_value, zscore_threshold),
                entity=str(period),
                metric="units_sold",
                value=float(series[period]),
                z_score=float(z_value),
                description=f"Units sold {direction} in {period} (z-score {z_value:.2f}).",
            )
        )
    return findings


# --- Cross-sectional detectors ---------------------------------------------


def _entity_series(
    df: pd.DataFrame, column_map: ColumnMap, value_field: BusinessField
) -> tuple[pd.Series, pd.Series] | None:
    """(entity_id, value) pairs grouped by PRODUCT_ID (or SKU if no
    product id is mapped), summed per entity. None if neither the
    entity dimension nor the value field is mapped."""
    entity_field = (
        BusinessField.PRODUCT_ID if BusinessField.PRODUCT_ID in column_map else BusinessField.SKU
    )
    entity_col = column_map.get(entity_field)
    if entity_col is None or entity_col not in df.columns:
        return None
    values = _numeric(df, column_map, value_field)
    if values is None:
        return None
    entities = df[entity_col].astype(str).str.strip()
    mask = entities != ""
    if not mask.any():
        return None
    grouped = values[mask].fillna(0).groupby(entities[mask]).sum()
    if len(grouped) < 3:
        return None
    return grouped.index, grouped


def detect_inventory_anomalies_by_level(
    df: pd.DataFrame, column_map: ColumnMap, *, zscore_threshold: float
) -> list[AnomalyFinding]:
    """Inventory spikes / Inventory drops: raw on-hand quantity per
    product compared against the peer distribution."""
    result = _entity_series(df, column_map, BusinessField.QUANTITY_AVAILABLE)
    if result is None:
        return []
    _, grouped = result
    z = _zscores(grouped)
    if z is None:
        return []
    findings: list[AnomalyFinding] = []
    for entity, z_value in z.items():
        if abs(z_value) < zscore_threshold:
            continue
        anomaly_type = "Inventory spikes" if z_value > 0 else "Inventory drops"
        direction = "far above" if z_value > 0 else "far below"
        findings.append(
            AnomalyFinding(
                anomaly_type=anomaly_type,
                severity=_severity_for(z_value, zscore_threshold),
                entity=str(entity),
                metric="quantity_available",
                value=float(grouped[entity]),
                z_score=float(z_value),
                description=(
                    f"Product {entity} has on-hand inventory {direction} its peers "
                    f"(z-score {z_value:.2f})."
                ),
            )
        )
    return findings


def detect_inventory_turnover_anomalies(
    df: pd.DataFrame, column_map: ColumnMap, *, zscore_threshold: float
) -> list[AnomalyFinding]:
    """Inventory anomalies: stock-to-sales ratio outliers - a product
    can have an unremarkable stock level yet still be a turnover
    outlier once its sales velocity is accounted for."""
    entity_field = (
        BusinessField.PRODUCT_ID if BusinessField.PRODUCT_ID in column_map else BusinessField.SKU
    )
    entity_col = column_map.get(entity_field)
    avail = _numeric(df, column_map, BusinessField.QUANTITY_AVAILABLE)
    sold = _numeric(df, column_map, BusinessField.QUANTITY_SOLD)
    if entity_col is None or entity_col not in df.columns or avail is None or sold is None:
        return []
    entities = df[entity_col].astype(str).str.strip()
    mask = entities != ""
    if not mask.any():
        return []
    working = pd.DataFrame(
        {
            "entity": entities[mask],
            "avail": avail[mask].fillna(0),
            "sold": sold[mask].fillna(0),
        }
    )
    grouped = working.groupby("entity")[["avail", "sold"]].sum()
    if len(grouped) < 3:
        return []
    grouped = grouped[grouped["sold"] > 0]
    if len(grouped) < 3:
        return []
    ratio = grouped["avail"] / grouped["sold"]
    z = _zscores(ratio)
    if z is None:
        return []
    findings: list[AnomalyFinding] = []
    for entity, z_value in z.items():
        if abs(z_value) < zscore_threshold:
            continue
        direction = "far higher" if z_value > 0 else "far lower"
        findings.append(
            AnomalyFinding(
                anomaly_type="Inventory anomalies",
                severity=_severity_for(z_value, zscore_threshold),
                entity=str(entity),
                metric="inventory_to_sales_ratio",
                value=float(ratio[entity]),
                z_score=float(z_value),
                description=(
                    f"Product {entity} carries stock-to-sales ratio {direction} than "
                    f"peers (z-score {z_value:.2f})."
                ),
            )
        )
    return findings


def _iqr_bounds(series: pd.Series, *, multiplier: float) -> tuple[float, float] | None:
    clean = series.dropna()
    if len(clean) < 4:
        return None
    q1, q3 = clean.quantile(0.25), clean.quantile(0.75)
    iqr = q3 - q1
    if iqr == 0:
        return None
    return q1 - multiplier * iqr, q3 + multiplier * iqr


def detect_price_anomalies(
    df: pd.DataFrame, column_map: ColumnMap, *, iqr_multiplier: float
) -> list[AnomalyFinding]:
    price = _sale_price(df, column_map)
    if price is None:
        return []
    bounds = _iqr_bounds(price, multiplier=iqr_multiplier)
    if bounds is None:
        return []
    lower, upper = bounds
    entity_field = (
        BusinessField.PRODUCT_ID if BusinessField.PRODUCT_ID in column_map else BusinessField.SKU
    )
    entity_col = column_map.get(entity_field)
    entities = df[entity_col].astype(str).str.strip() if entity_col in df.columns else None

    findings: list[AnomalyFinding] = []
    outlier_mask = price.notna() & ((price < lower) | (price > upper))
    for idx in price[outlier_mask].index:
        value = float(price[idx])
        entity = str(entities[idx]) if entities is not None else f"row {idx}"
        direction = "above" if value > upper else "below"
        findings.append(
            AnomalyFinding(
                anomaly_type="Price anomalies",
                severity="warning",
                entity=entity,
                metric="price",
                value=value,
                z_score=0.0,
                description=f"{entity} has a price {direction} the typical range ({value:.2f}).",
            )
        )
    return findings


def detect_margin_anomalies(
    df: pd.DataFrame, column_map: ColumnMap, *, iqr_multiplier: float
) -> list[AnomalyFinding]:
    price = _sale_price(df, column_map)
    cost = _numeric(df, column_map, BusinessField.UNIT_COST)
    if price is None or cost is None:
        return []
    both_known = price.notna() & cost.notna()
    margin = pd.Series(np.nan, index=df.index, dtype="float64")
    valid_price = price[both_known]
    valid_price_safe = valid_price.where(valid_price != 0, np.nan)
    margin.loc[both_known] = (valid_price - cost[both_known]) / valid_price_safe * 100
    bounds = _iqr_bounds(margin, multiplier=iqr_multiplier)
    if bounds is None:
        return []
    lower, upper = bounds
    entity_field = (
        BusinessField.PRODUCT_ID if BusinessField.PRODUCT_ID in column_map else BusinessField.SKU
    )
    entity_col = column_map.get(entity_field)
    entities = df[entity_col].astype(str).str.strip() if entity_col in df.columns else None

    findings: list[AnomalyFinding] = []
    outlier_mask = margin.notna() & ((margin < lower) | (margin > upper))
    for idx in margin[outlier_mask].index:
        value = float(margin[idx])
        entity = str(entities[idx]) if entities is not None else f"row {idx}"
        direction = "above" if value > upper else "below"
        findings.append(
            AnomalyFinding(
                anomaly_type="Margin anomalies",
                severity="warning",
                entity=entity,
                metric="gross_margin_pct",
                value=value,
                z_score=0.0,
                description=(
                    f"{entity} has a gross margin {direction} the typical range ({value:.2f}%)."
                ),
            )
        )
    return findings


def run_all_detectors(
    df: pd.DataFrame,
    column_map: ColumnMap,
    *,
    zscore_threshold: float,
    iqr_multiplier: float,
    granularity: str = "monthly",
) -> list[AnomalyFinding]:
    """Run all 9 anomaly detectors and return the combined findings
    list: Revenue spikes, Revenue drops, Inventory spikes, Inventory
    drops, Return spikes, Price anomalies, Margin anomalies, Inventory
    anomalies, Sales anomalies."""
    findings: list[AnomalyFinding] = []
    findings.extend(
        detect_revenue_anomalies(
            df, column_map, zscore_threshold=zscore_threshold, granularity=granularity
        )
    )
    findings.extend(
        detect_inventory_anomalies_by_level(df, column_map, zscore_threshold=zscore_threshold)
    )
    findings.extend(
        detect_return_spikes(
            df, column_map, zscore_threshold=zscore_threshold, granularity=granularity
        )
    )
    findings.extend(detect_price_anomalies(df, column_map, iqr_multiplier=iqr_multiplier))
    findings.extend(detect_margin_anomalies(df, column_map, iqr_multiplier=iqr_multiplier))
    findings.extend(
        detect_inventory_turnover_anomalies(df, column_map, zscore_threshold=zscore_threshold)
    )
    findings.extend(
        detect_sales_anomalies(
            df, column_map, zscore_threshold=zscore_threshold, granularity=granularity
        )
    )
    return findings
