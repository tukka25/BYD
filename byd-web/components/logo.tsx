/* The mark.

   A dense field of thin bars is the raw data in your file. The bold
   node-and-line polyline crossing it is what the model found in that data,
   separated from the field by a keyline so it stays readable wherever it sits.
   That is the product in one drawing: your data, and the answer drawn through
   it on this machine.

   Two cuts, not one scaled drawing. The full cut carries eleven bars and six
   nodes and is used wherever the mark is 28px or larger. Below that, eleven
   hairlines average out to grey mush, so the favicon gets a four-bar cut with
   a heavier line instead. A logo that is only legible at one size is a logo
   with one size.

   The keyline colour has to match whatever sits behind the mark, so it is a
   prop rather than a constant: canvas in the sidebar, white on a panel, pine
   on the favicon tile. */

const FULL_FIELD: [number, number][] = [
  [4.8, 20.2],
  [2.6, 20.8],
  [7.0, 19.8],
  [3.4, 21.0],
  [8.4, 20.4],
  [2.2, 20.9],
  [5.6, 19.6],
  [7.6, 20.7],
  [3.9, 20.1],
  [6.4, 20.9],
  [2.9, 20.3],
];

const FULL_LINE: [number, number][] = [
  [3.4, 18.6],
  [6.84, 14.4],
  [10.28, 17.2],
  [13.72, 11.8],
  [17.16, 14.6],
  [20.6, 8.2],
];

const COMPACT_FIELD: [number, number][] = [
  [5.4, 20.6],
  [2.2, 21.2],
  [7.6, 20.2],
  [3.6, 21.0],
];

const COMPACT_LINE: [number, number][] = [
  [4.2, 17.0],
  [12.0, 12.4],
  [19.8, 6.6],
];

function path(points: [number, number][]) {
  return points.map(([x, y], i) => `${i === 0 ? "M" : "L"} ${x} ${y}`).join(" ");
}

type MarkProps = {
  /** What sits behind the mark. The keyline separating line from field is drawn in it. */
  keyline?: string;
  /** Play the draw-on once on mount. Off by default: a logo's resting state is drawn. */
  animate?: boolean;
  className?: string;
  title?: string;
};

/** The full cut. Use at 28px and above. */
export function LogoMark({
  keyline = "var(--canvas)",
  animate = false,
  className,
  title,
}: MarkProps) {
  return (
    <svg
      viewBox="0 0 24 24"
      className={[animate ? "logo-animate" : "", className ?? ""].join(" ").trim()}
      role={title ? "img" : undefined}
      aria-label={title}
      aria-hidden={title ? undefined : true}
    >
      <g fill="var(--pine)">
        {FULL_FIELD.map(([top, bottom], i) => (
          <rect
            key={i}
            className="logo-bar"
            x={0.95 + i * 2.1}
            y={top}
            width={1.15}
            height={bottom - top}
            rx={0.575}
            style={{ animationDelay: `${i * 38}ms`, transformOrigin: `0 ${bottom}px` }}
          />
        ))}
      </g>

      {/* The keyline draws in step with the line it protects. Drawn all at once
          it would cut a canvas-coloured swath through the field before the ink
          line arrived to fill it, which looks like a rendering fault. */}
      <path
        d={path(FULL_LINE)}
        fill="none"
        stroke={keyline}
        strokeWidth={4.1}
        strokeLinecap="round"
        strokeLinejoin="round"
        className="logo-line"
      />
      {FULL_LINE.map(([x, y], i) => (
        <circle
          key={`k${i}`}
          cx={x}
          cy={y}
          r={3.1}
          fill={keyline}
          className="logo-node"
          style={{ animationDelay: `${420 + i * 80}ms`, transformOrigin: `${x}px ${y}px` }}
        />
      ))}

      <path
        d={path(FULL_LINE)}
        fill="none"
        stroke="var(--ink)"
        strokeWidth={1.8}
        strokeLinecap="round"
        strokeLinejoin="round"
        className="logo-line"
      />
      {FULL_LINE.map(([x, y], i) => (
        <circle
          key={`n${i}`}
          cx={x}
          cy={y}
          r={2.25}
          fill="var(--ink)"
          className="logo-node"
          style={{ animationDelay: `${420 + i * 80}ms`, transformOrigin: `${x}px ${y}px` }}
        />
      ))}
    </svg>
  );
}

/** The small cut: four bars, three nodes. For the favicon and anything under 28px. */
export function LogoMarkCompact({
  keyline = "var(--canvas)",
  bar = "var(--pine)",
  line = "var(--ink)",
  className,
  title,
}: MarkProps & { bar?: string; line?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      className={className}
      role={title ? "img" : undefined}
      aria-label={title}
      aria-hidden={title ? undefined : true}
    >
      <g fill={bar}>
        {COMPACT_FIELD.map(([top, bottom], i) => (
          <rect
            key={i}
            x={2.6 + i * 5.9}
            y={top}
            width={2.6}
            height={bottom - top}
            rx={1.3}
          />
        ))}
      </g>
      <path
        d={path(COMPACT_LINE)}
        fill="none"
        stroke={keyline}
        strokeWidth={6.2}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {COMPACT_LINE.map(([x, y], i) => (
        <circle key={`k${i}`} cx={x} cy={y} r={4.3} fill={keyline} />
      ))}
      <path
        d={path(COMPACT_LINE)}
        fill="none"
        stroke={line}
        strokeWidth={2.6}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {COMPACT_LINE.map(([x, y], i) => (
        <circle key={`n${i}`} cx={x} cy={y} r={3.1} fill={line} />
      ))}
    </svg>
  );
}

/* The lockup. The mark sits bare next to the wordmark — no tinted tile behind
   it. A stock icon in a coloured squircle is what this replaced. */
export function Wordmark({
  size = 19,
  mark = 26,
  keyline = "var(--canvas)",
  animate = false,
  className,
}: {
  size?: number;
  mark?: number;
  keyline?: string;
  animate?: boolean;
  className?: string;
}) {
  return (
    <span className={["flex items-center gap-2.5", className ?? ""].join(" ").trim()}>
      <span className="shrink-0" style={{ width: mark, height: mark }}>
        <LogoMark keyline={keyline} animate={animate} />
      </span>
      <span
        className="font-display font-bold tracking-[-0.03em] text-ink"
        style={{ fontSize: size }}
      >
        PromptDash
      </span>
    </span>
  );
}
