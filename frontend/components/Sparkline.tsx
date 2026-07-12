// Tiny dependency-free inline sparkline (server-renderable). Draws in
// currentColor (default hunter, doc 4 §2b) so dark surfaces like the featured
// pine tile can recolor it to a stroke that stays visible there.
// NOTE: the props interface is imported by the dashboard tiles — keep it
// backward compatible.
export default function Sparkline({
  values,
  width = 120,
  height = 28,
  className = "text-hunter",
  stretch = false,
}: {
  values: number[];
  width?: number;
  height?: number;
  className?: string;
  /** Fill the parent instead of rendering at a fixed pixel size: the svg
   *  scales non-uniformly to 100% width/height (stroke width preserved via
   *  vector-effect). Size it with the className (e.g. `h-full w-full`). */
  stretch?: boolean;
}) {
  if (values.length < 2) {
    return <span className="text-xs text-ink/30">–</span>;
  }
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const coords = values.map((v, i) => {
    const x = (i / (values.length - 1)) * (width - 2) + 1;
    const y = height - 2 - ((v - min) / span) * (height - 4);
    return [x, y] as const;
  });
  const points = coords.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
  const fillPoints = `${coords[0][0].toFixed(1)},${(height - 1).toFixed(1)} ${points} ${coords[
    coords.length - 1
  ][0].toFixed(1)},${(height - 1).toFixed(1)}`;
  return (
    <svg
      {...(stretch
        ? { viewBox: `0 0 ${width} ${height}`, preserveAspectRatio: "none" }
        : { width, height })}
      aria-hidden="true"
      className={className}
    >
      <polygon points={fillPoints} fill="currentColor" fillOpacity={0.12} stroke="none" />
      <polyline
        points={points}
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinejoin="round"
        strokeLinecap="round"
        {...(stretch ? { vectorEffect: "non-scaling-stroke" } : {})}
      />
    </svg>
  );
}
