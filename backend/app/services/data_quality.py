"""Deterministic data-quality scoring and rule-based issue detection.

No AI/LLM is used anywhere in this module. Every score is a plain ratio
computed from the dataset's rows, and every finding comes from a fixed,
explicit rule (a comparison, a regex, a date bound, an IQR/z-score
fence) - never a model's judgment call.

Four component scores (0-100, higher is better) plus an overall score:
- Completeness: share of cells that are present (non-null, non-blank)
  across every mapped BusinessField column.
- Validity: share of values, within columns that have an expected shape
  (numbers non-negative, dates parseable and not in the future, UPCs
  well-formed), that actually satisfy it.
- Consistency: share of rows free of internal contradictions (margins
  that make sense, no duplicate keys) - see _CONSISTENCY_CHECKS.
- Uniqueness: share of rows that aren't exact duplicates of another row.
- Overall: unweighted mean of the four component scores.

Each of the 13 detection rules below inspects the dataframe and yields
zero or more DataQualityFinding-shaped records (severity, category,
description, recommendation). A rule that needs a field that isn't
mapped simply yields nothing, mirroring kpi_engine's gating pattern.
"""

import dataclasses
import re
from datetime import UTC, datetime

import pandas as pd

from app.models.dataset import BusinessField, FindingSeverity

ColumnMap = dict[BusinessField, str]

_UPC_RE = re.compile(r"^\d{12}$")


@dataclasses.dataclass(frozen=True)
class QualityFinding:
    severity: FindingSeverity
    category: str
    description: str
    recommendation: str


@dataclasses.dataclass(frozen=True)
class QualityScores:
    completeness_score: float
    validity_score: float
    consistency_score: float
    uniqueness_score: float
    overall_score: float


def _mapped_columns(df: pd.DataFrame, column_map: ColumnMap) -> list[str]:
    return [name for name in column_map.values() if name in df.columns]


def _numeric(df: pd.DataFrame, column_map: ColumnMap, field: BusinessField) -> pd.Series | None:
    column_name = column_map.get(field)
    if column_name is None or column_name not in df.columns:
        return None
    return pd.to_numeric(df[column_name], errors="coerce")


def _iqr_outlier_mask(series: pd.Series, *, multiplier: float) -> pd.Series:
    """Tukey's fences: values outside [Q1 - k*IQR, Q3 + k*IQR]."""
    clean = series.dropna()
    if len(clean) < 4:
        return pd.Series(False, index=series.index)
    q1, q3 = clean.quantile(0.25), clean.quantile(0.75)
    iqr = q3 - q1
    if iqr == 0:
        return pd.Series(False, index=series.index)
    lower, upper = q1 - multiplier * iqr, q3 + multiplier * iqr
    return (series < lower) | (series > upper)


# --- Component scores -----------------------------------------------------


def _completeness_score(df: pd.DataFrame, column_map: ColumnMap) -> float:
    columns = _mapped_columns(df, column_map)
    if not columns or len(df) == 0:
        return 100.0
    subset = df[columns].replace("", pd.NA)
    present = subset.notna().to_numpy().sum()
    total = subset.size
    return float(present / total * 100) if total else 100.0


def _validity_score(df: pd.DataFrame, column_map: ColumnMap) -> float:
    checks: list[pd.Series] = []

    for field in (
        BusinessField.UNIT_COST,
        BusinessField.RETAIL_PRICE,
        BusinessField.SALE_PRICE,
        BusinessField.QUANTITY_AVAILABLE,
        BusinessField.QUANTITY_SOLD,
        BusinessField.QUANTITY_RETURNED,
    ):
        series = _numeric(df, column_map, field)
        if series is not None:
            checks.append(series.notna() & (series >= 0))

    for field in (BusinessField.ORDER_DATE, BusinessField.RETURN_DATE):
        column_name = column_map.get(field)
        if column_name and column_name in df.columns:
            parsed = pd.to_datetime(df[column_name], errors="coerce")
            now = pd.Timestamp(datetime.now(UTC).date())
            checks.append(parsed.notna() & (parsed <= now))

    upc_col = column_map.get(BusinessField.UPC)
    if upc_col and upc_col in df.columns:
        checks.append(df[upc_col].astype(str).str.strip().str.match(_UPC_RE))

    if not checks:
        return 100.0

    valid_counts = sum(c.sum() for c in checks)
    total_counts = sum(len(c) for c in checks)
    return float(valid_counts / total_counts * 100) if total_counts else 100.0


def _consistency_score(df: pd.DataFrame, column_map: ColumnMap) -> float:
    checks: list[pd.Series] = []

    cost = _numeric(df, column_map, BusinessField.UNIT_COST)
    price = _numeric(df, column_map, BusinessField.SALE_PRICE)
    if price is None:
        price = _numeric(df, column_map, BusinessField.RETAIL_PRICE)
    if cost is not None and price is not None:
        both_known = cost.notna() & price.notna()
        margin_ok = ~both_known | (price >= cost)
        checks.append(margin_ok)

    key_field = BusinessField.SKU if BusinessField.SKU in column_map else BusinessField.PRODUCT_ID
    key_col = column_map.get(key_field)
    order_col = column_map.get(BusinessField.ORDER_ID)
    if key_col and key_col in df.columns and order_col and order_col in df.columns:
        combo = df[[key_col, order_col]].astype(str)
        duplicated = combo.duplicated(keep=False)
        checks.append(~duplicated)

    if not checks:
        return 100.0

    valid_counts = sum(c.sum() for c in checks)
    total_counts = sum(len(c) for c in checks)
    return float(valid_counts / total_counts * 100) if total_counts else 100.0


def _uniqueness_score(df: pd.DataFrame, column_map: ColumnMap) -> float:
    if len(df) == 0:
        return 100.0
    columns = _mapped_columns(df, column_map) or list(df.columns)
    duplicated = df[columns].duplicated(keep="first")
    unique_count = len(df) - int(duplicated.sum())
    return float(unique_count / len(df) * 100)


def compute_quality_scores(df: pd.DataFrame, column_map: ColumnMap) -> QualityScores:
    completeness = _completeness_score(df, column_map)
    validity = _validity_score(df, column_map)
    consistency = _consistency_score(df, column_map)
    uniqueness = _uniqueness_score(df, column_map)
    overall = (completeness + validity + consistency + uniqueness) / 4
    return QualityScores(
        completeness_score=completeness,
        validity_score=validity,
        consistency_score=consistency,
        uniqueness_score=uniqueness,
        overall_score=overall,
    )


# --- Detection rules (each yields zero or more QualityFinding) ------------


def _check_missing_values(df: pd.DataFrame, column_map: ColumnMap) -> list[QualityFinding]:
    columns = _mapped_columns(df, column_map)
    if not columns or len(df) == 0:
        return []
    subset = df[columns].replace("", pd.NA)
    missing = subset.isna().sum()
    missing = missing[missing > 0]
    if missing.empty:
        return []
    detail = ", ".join(f"{col} ({int(n)})" for col, n in missing.items())
    return [
        QualityFinding(
            FindingSeverity.WARNING,
            "Missing values",
            f"Missing values found in: {detail}.",
            "Fill in missing values or exclude incomplete rows before analysis.",
        )
    ]


def _check_duplicate_rows(df: pd.DataFrame, column_map: ColumnMap) -> list[QualityFinding]:
    columns = _mapped_columns(df, column_map) or list(df.columns)
    if len(df) == 0:
        return []
    duplicated = df[columns].duplicated(keep="first")
    count = int(duplicated.sum())
    if count == 0:
        return []
    return [
        QualityFinding(
            FindingSeverity.WARNING,
            "Duplicate rows",
            f"{count} row(s) are exact duplicates of another row.",
            "Remove duplicate rows to avoid double-counting sales and inventory.",
        )
    ]


def _check_duplicate_keys(df: pd.DataFrame, column_map: ColumnMap) -> list[QualityFinding]:
    key_field = BusinessField.SKU if BusinessField.SKU in column_map else BusinessField.PRODUCT_ID
    key_col = column_map.get(key_field)
    order_col = column_map.get(BusinessField.ORDER_ID)
    if not key_col or key_col not in df.columns or not order_col or order_col not in df.columns:
        return []
    combo = df[[key_col, order_col]].astype(str)
    duplicated = combo.duplicated(keep="first")
    count = int(duplicated.sum())
    if count == 0:
        return []
    return [
        QualityFinding(
            FindingSeverity.ERROR,
            "Duplicate keys",
            f"{count} row(s) repeat the same product/order combination.",
            "Investigate whether these are re-shipments, refunds, or a data entry error.",
        )
    ]


def _check_negative(
    df: pd.DataFrame, column_map: ColumnMap, field: BusinessField, label: str, category: str
) -> list[QualityFinding]:
    series = _numeric(df, column_map, field)
    if series is None:
        return []
    count = int((series < 0).sum())
    if count == 0:
        return []
    return [
        QualityFinding(
            FindingSeverity.ERROR,
            category,
            f"{count} row(s) have a negative {label}.",
            f"Correct or remove rows with negative {label} before computing KPIs.",
        )
    ]


def _check_negative_inventory(df: pd.DataFrame, column_map: ColumnMap) -> list[QualityFinding]:
    return _check_negative(
        df, column_map, BusinessField.QUANTITY_AVAILABLE, "inventory quantity", "Negative inventory"
    )


def _check_negative_prices(df: pd.DataFrame, column_map: ColumnMap) -> list[QualityFinding]:
    findings: list[QualityFinding] = []
    for field, label in (
        (BusinessField.UNIT_COST, "unit cost"),
        (BusinessField.RETAIL_PRICE, "retail price"),
        (BusinessField.SALE_PRICE, "sale price"),
    ):
        findings.extend(_check_negative(df, column_map, field, label, "Negative prices"))
    return findings


def _check_negative_quantities(df: pd.DataFrame, column_map: ColumnMap) -> list[QualityFinding]:
    findings: list[QualityFinding] = []
    for field, label in (
        (BusinessField.QUANTITY_SOLD, "quantity sold"),
        (BusinessField.QUANTITY_RETURNED, "quantity returned"),
    ):
        findings.extend(_check_negative(df, column_map, field, label, "Negative quantities"))
    return findings


def _check_invalid_dates(df: pd.DataFrame, column_map: ColumnMap) -> list[QualityFinding]:
    findings: list[QualityFinding] = []
    for field, label in (
        (BusinessField.ORDER_DATE, "order date"),
        (BusinessField.RETURN_DATE, "return date"),
    ):
        column_name = column_map.get(field)
        if not column_name or column_name not in df.columns:
            continue
        raw = df[column_name].astype(str).str.strip()
        non_blank = raw != ""
        parsed = pd.to_datetime(df[column_name], errors="coerce")
        invalid = non_blank & parsed.isna()
        count = int(invalid.sum())
        if count == 0:
            continue
        findings.append(
            QualityFinding(
                FindingSeverity.ERROR,
                "Invalid dates",
                f"{count} row(s) have an unparseable {label}.",
                f"Fix the {label} format (expected a standard date/datetime format).",
            )
        )
    return findings


def _check_future_dates(df: pd.DataFrame, column_map: ColumnMap) -> list[QualityFinding]:
    findings: list[QualityFinding] = []
    now = pd.Timestamp(datetime.now(UTC).date())
    for field, label in (
        (BusinessField.ORDER_DATE, "order date"),
        (BusinessField.RETURN_DATE, "return date"),
    ):
        column_name = column_map.get(field)
        if not column_name or column_name not in df.columns:
            continue
        parsed = pd.to_datetime(df[column_name], errors="coerce")
        future = parsed.notna() & (parsed > now)
        count = int(future.sum())
        if count == 0:
            continue
        findings.append(
            QualityFinding(
                FindingSeverity.WARNING,
                "Future dates",
                f"{count} row(s) have a {label} in the future.",
                f"Verify the {label} values; a future date usually indicates a data entry error.",
            )
        )
    return findings


def _check_malformed_upcs(df: pd.DataFrame, column_map: ColumnMap) -> list[QualityFinding]:
    column_name = column_map.get(BusinessField.UPC)
    if not column_name or column_name not in df.columns:
        return []
    raw = df[column_name].astype(str).str.strip()
    non_blank = raw != ""
    malformed = non_blank & ~raw.str.match(_UPC_RE)
    count = int(malformed.sum())
    if count == 0:
        return []
    return [
        QualityFinding(
            FindingSeverity.WARNING,
            "Malformed UPCs",
            f"{count} row(s) have a UPC that isn't a 12-digit code.",
            "Confirm the UPC column and correct any codes with the wrong length or non-digit "
            "characters.",
        )
    ]


def _check_outlier_prices(
    df: pd.DataFrame, column_map: ColumnMap, *, iqr_multiplier: float
) -> list[QualityFinding]:
    findings: list[QualityFinding] = []
    for field, label in (
        (BusinessField.RETAIL_PRICE, "retail price"),
        (BusinessField.SALE_PRICE, "sale price"),
    ):
        series = _numeric(df, column_map, field)
        if series is None:
            continue
        outliers = _iqr_outlier_mask(series, multiplier=iqr_multiplier)
        count = int(outliers.sum())
        if count == 0:
            continue
        findings.append(
            QualityFinding(
                FindingSeverity.INFO,
                "Outlier prices",
                f"{count} row(s) have a {label} far outside the typical range.",
                f"Review these {label} values for pricing errors (e.g. misplaced decimals).",
            )
        )
    return findings


def _check_outlier_quantities(
    df: pd.DataFrame, column_map: ColumnMap, *, iqr_multiplier: float
) -> list[QualityFinding]:
    findings: list[QualityFinding] = []
    for field, label in (
        (BusinessField.QUANTITY_SOLD, "quantity sold"),
        (BusinessField.QUANTITY_AVAILABLE, "inventory quantity"),
    ):
        series = _numeric(df, column_map, field)
        if series is None:
            continue
        outliers = _iqr_outlier_mask(series, multiplier=iqr_multiplier)
        count = int(outliers.sum())
        if count == 0:
            continue
        findings.append(
            QualityFinding(
                FindingSeverity.INFO,
                "Outlier quantities",
                f"{count} row(s) have a {label} far outside the typical range.",
                f"Review these {label} values for entry errors (e.g. an extra zero).",
            )
        )
    return findings


def _check_unknown_categories(df: pd.DataFrame, column_map: ColumnMap) -> list[QualityFinding]:
    column_name = column_map.get(BusinessField.CATEGORY)
    if not column_name or column_name not in df.columns:
        return []
    values = df[column_name].astype(str).str.strip().str.lower()
    unknown = values.isin({"", "unknown", "n/a", "na", "none", "null"})
    count = int(unknown.sum())
    if count == 0:
        return []
    return [
        QualityFinding(
            FindingSeverity.WARNING,
            "Unknown categories",
            f"{count} row(s) have a missing or placeholder category.",
            "Assign a real category so category-level analytics reflect these rows.",
        )
    ]


def _check_unknown_suppliers(df: pd.DataFrame, column_map: ColumnMap) -> list[QualityFinding]:
    column_name = column_map.get(BusinessField.SUPPLIER)
    if not column_name or column_name not in df.columns:
        return []
    values = df[column_name].astype(str).str.strip().str.lower()
    unknown = values.isin({"", "unknown", "n/a", "na", "none", "null"})
    count = int(unknown.sum())
    if count == 0:
        return []
    return [
        QualityFinding(
            FindingSeverity.WARNING,
            "Unknown suppliers",
            f"{count} row(s) have a missing or placeholder supplier.",
            "Assign a real supplier so supplier-performance analytics reflect these rows.",
        )
    ]


def _check_invalid_margins(df: pd.DataFrame, column_map: ColumnMap) -> list[QualityFinding]:
    cost = _numeric(df, column_map, BusinessField.UNIT_COST)
    price = _numeric(df, column_map, BusinessField.SALE_PRICE)
    if price is None:
        price = _numeric(df, column_map, BusinessField.RETAIL_PRICE)
    if cost is None or price is None:
        return []
    both_known = cost.notna() & price.notna()
    invalid = both_known & (price < cost)
    count = int(invalid.sum())
    if count == 0:
        return []
    return [
        QualityFinding(
            FindingSeverity.ERROR,
            "Invalid margins",
            f"{count} row(s) sell below unit cost, producing a negative margin.",
            "Verify these prices/costs; if intentional (clearance), consider flagging separately.",
        )
    ]


_DETECTION_RULES = (
    _check_missing_values,
    _check_duplicate_rows,
    _check_duplicate_keys,
    _check_negative_inventory,
    _check_negative_prices,
    _check_negative_quantities,
    _check_invalid_dates,
    _check_future_dates,
    _check_malformed_upcs,
    _check_unknown_categories,
    _check_unknown_suppliers,
    _check_invalid_margins,
)


def run_detection_rules(
    df: pd.DataFrame, column_map: ColumnMap, *, iqr_multiplier: float
) -> list[QualityFinding]:
    """Run every detection rule and return the combined findings list.
    Order matches the DATA QUALITY spec: Missing, Duplicate rows,
    Duplicate keys, Negative inventory, Negative prices, Negative
    quantities, Invalid dates, Future dates, Malformed UPCs, Outlier
    prices, Outlier quantities, Unknown categories, Unknown suppliers,
    Invalid margins.
    """
    findings: list[QualityFinding] = []
    for rule in _DETECTION_RULES:
        findings.extend(rule(df, column_map))
    findings.extend(_check_outlier_prices(df, column_map, iqr_multiplier=iqr_multiplier))
    findings.extend(_check_outlier_quantities(df, column_map, iqr_multiplier=iqr_multiplier))
    return findings
