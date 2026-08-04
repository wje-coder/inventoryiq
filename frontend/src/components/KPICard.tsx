interface KPICardProps {
  label: string;
  value: number;
  unit: string;
}

function formatValue(value: number, unit: string): string {
  if (unit === "USD") {
    return value.toLocaleString(undefined, {
      style: "currency",
      currency: "USD",
      maximumFractionDigits: 2,
    });
  }
  if (unit === "%") {
    return `${value.toLocaleString(undefined, { maximumFractionDigits: 2 })}%`;
  }
  if (unit === "x") {
    return `${value.toLocaleString(undefined, { maximumFractionDigits: 2 })}x`;
  }
  return value.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

/** A single executive KPI figure, shown as a labeled card. */
export function KPICard({ label, value, unit }: KPICardProps) {
  return (
    <div className="kpi-card" role="group" aria-label={label}>
      <span className="kpi-card-label">{label}</span>
      <span className="kpi-card-value">{formatValue(value, unit)}</span>
    </div>
  );
}
