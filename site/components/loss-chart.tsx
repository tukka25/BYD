/* A validation-loss curve as an inline SVG: the page's own figure, drawn from
   data/loss.json, which tests/loss.test.mts checks against the training
   records. Not a model's chart. One series, so no legend: the caption names
   it. A 2 px line, 8 px markers with a surface ring, only the highest and
   lowest values labelled, a native tooltip per point, and the values again as
   a table for screen readers. */
export function LossChart({
  label,
  points,
  names,
  caption,
}: {
  label: string;
  points: number[];
  names: string[];
  caption: string;
}) {
  const width = 300;
  const height = 160;
  const pad = { left: 46, right: 14, top: 16, bottom: 22 };
  const max = Math.max(...points);
  const min = Math.min(...points);
  const x = (i: number) => pad.left + (i / (points.length - 1)) * (width - pad.left - pad.right);
  const y = (v: number) => pad.top + ((max - v) / (max - min || 1)) * (height - pad.top - pad.bottom);
  const path = points.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)} ${y(v).toFixed(1)}`).join(" ");

  return (
    <figure className="rounded-[var(--r-card)] bg-surface p-4 shadow-[var(--lift-1)]">
      <figcaption className="flex flex-wrap items-baseline justify-between gap-x-3">
        <span className="font-display text-[15px] font-semibold text-ink">{label} · validation loss</span>
        <span className="text-[12px] text-muted">{caption}</span>
      </figcaption>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="mt-3 w-full"
        role="img"
        aria-label={`${label} validation loss, from ${points[0]} to ${points[points.length - 1]}`}
      >
        <line
          x1={pad.left}
          x2={width - pad.right}
          y1={height - pad.bottom}
          y2={height - pad.bottom}
          stroke="var(--hairline)"
          strokeWidth={1}
        />
        <text x={pad.left - 8} y={y(max) + 4} textAnchor="end" fontSize={11} fill="var(--muted)">
          {max}
        </text>
        <text x={pad.left - 8} y={y(min) + 4} textAnchor="end" fontSize={11} fill="var(--muted)">
          {min}
        </text>
        <path d={path} fill="none" stroke="var(--pine)" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" />
        {points.map((v, i) => (
          <g key={names[i]}>
            <circle cx={x(i)} cy={y(v)} r={4} fill="var(--pine)" stroke="var(--surface)" strokeWidth={2} />
            <circle cx={x(i)} cy={y(v)} r={11} fill="transparent">
              <title>{`${names[i]}: ${v}`}</title>
            </circle>
          </g>
        ))}
      </svg>
      <table className="sr-only">
        <caption>{label} validation loss</caption>
        <tbody>
          {points.map((v, i) => (
            <tr key={names[i]}>
              <th scope="row">{names[i]}</th>
              <td>{v}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </figure>
  );
}
