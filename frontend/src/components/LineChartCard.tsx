export interface LineChartDatum {
  label: string;
  value: number;
}

interface LineChartCardProps {
  title: string;
  data: LineChartDatum[];
  color?: string;
  emptyMessage?: string;
}

const CHART_WIDTH = 100;
const CHART_HEIGHT = 100;

/**
 * A dependency-free, hand-rolled SVG line chart for time-series trends
 * (see BarChartCard.tsx for why no charting library is used).
 */
export function LineChartCard({
  title,
  data,
  color = "#16a34a",
  emptyMessage,
}: LineChartCardProps) {
  const values = data.map((d) => d.value);
  const maxValue = Math.max(1, ...values);
  const minValue = Math.min(0, ...values);
  const range = maxValue - minValue || 1;

  const points = data
    .map((datum, index) => {
      const x = data.length > 1 ? (index / (data.length - 1)) * CHART_WIDTH : CHART_WIDTH / 2;
      const y = CHART_HEIGHT - ((datum.value - minValue) / range) * CHART_HEIGHT;
      return `${x},${y}`;
    })
    .join(" ");

  return (
    <div className="chart-card panel">
      <h3>{title}</h3>
      {data.length === 0 ? (
        <p className="text-muted">{emptyMessage ?? "No data available."}</p>
      ) : (
        <svg
          role="img"
          aria-label={title}
          viewBox={`0 0 ${CHART_WIDTH} ${CHART_HEIGHT}`}
          preserveAspectRatio="none"
          className="line-chart"
        >
          <polyline points={points} fill="none" stroke={color} strokeWidth={1.5} />
          {data.map((datum, index) => {
            const x = data.length > 1 ? (index / (data.length - 1)) * CHART_WIDTH : CHART_WIDTH / 2;
            const y = CHART_HEIGHT - ((datum.value - minValue) / range) * CHART_HEIGHT;
            return (
              <circle key={`${datum.label}-${index}`} cx={x} cy={y} r={1.5} fill={color}>
                <title>{`${datum.label}: ${datum.value.toLocaleString()}`}</title>
              </circle>
            );
          })}
        </svg>
      )}
      {data.length > 0 && (
        <ul className="chart-legend">
          {data.map((datum, index) => (
            <li key={`${datum.label}-${index}`}>
              <span>{datum.label}</span>
              <span>{datum.value.toLocaleString()}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
