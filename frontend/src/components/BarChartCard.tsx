export interface BarChartDatum {
  label: string;
  value: number;
}

interface BarChartCardProps {
  title: string;
  data: BarChartDatum[];
  color?: string;
  emptyMessage?: string;
}

const CHART_HEIGHT = 180;
const BAR_GAP = 8;

/**
 * A dependency-free, hand-rolled SVG bar chart. Kept deliberately small
 * (no charting library) so the frontend build/typecheck/test suite can
 * be fully verified with only the packages already installed, rather
 * than depending on a new library that can't be installed or verified
 * in this environment.
 */
export function BarChartCard({ title, data, color = "#2563eb", emptyMessage }: BarChartCardProps) {
  const maxValue = Math.max(1, ...data.map((d) => Math.abs(d.value)));
  const barWidth = data.length > 0 ? 100 / data.length : 100;

  return (
    <div className="chart-card panel">
      <h3>{title}</h3>
      {data.length === 0 ? (
        <p className="text-muted">{emptyMessage ?? "No data available."}</p>
      ) : (
        <svg
          role="img"
          aria-label={title}
          viewBox={`0 0 100 ${CHART_HEIGHT + 20}`}
          preserveAspectRatio="none"
          className="bar-chart"
        >
          {data.map((datum, index) => {
            const height = (Math.abs(datum.value) / maxValue) * CHART_HEIGHT;
            const x = index * barWidth + BAR_GAP / 4;
            const width = Math.max(1, barWidth - BAR_GAP / 2);
            return (
              <g key={`${datum.label}-${index}`}>
                <rect
                  x={x}
                  y={CHART_HEIGHT - height}
                  width={width}
                  height={height}
                  fill={color}
                  data-testid={`bar-${datum.label}`}
                >
                  <title>{`${datum.label}: ${datum.value.toLocaleString()}`}</title>
                </rect>
              </g>
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
