/** Pure-SVG radar chart for 4 dimensions. */
export default function HealthRadar({
  values, labels, size = 240, color = '#4f46e5',
}: {
  values: number[];      // 0-100 each
  labels: string[];
  size?: number;
  color?: string;
}) {
  const n = values.length;
  const cx = size / 2;
  const cy = size / 2;
  const radius = (size / 2) * 0.72;

  const angleFor = (i: number) => (-Math.PI / 2) + (2 * Math.PI * i) / n;

  const point = (i: number, v: number) => {
    const r = (v / 100) * radius;
    const a = angleFor(i);
    return [cx + r * Math.cos(a), cy + r * Math.sin(a)];
  };

  const labelPoint = (i: number) => {
    const r = radius * 1.18;
    const a = angleFor(i);
    return [cx + r * Math.cos(a), cy + r * Math.sin(a)];
  };

  const polyPoints = values.map((v, i) => point(i, v).join(',')).join(' ');

  const grid = [20, 40, 60, 80, 100].map((g) => {
    const pts = values.map((_, i) => {
      const a = angleFor(i);
      const r = (g / 100) * radius;
      return `${cx + r * Math.cos(a)},${cy + r * Math.sin(a)}`;
    }).join(' ');
    return pts;
  });

  return (
    <svg width={size} height={size} style={{ display: 'block' }}>
      {grid.map((g, i) => (
        <polygon key={i} points={g} fill="none" stroke="#e5e7eb" strokeWidth="1" />
      ))}
      {values.map((_, i) => {
        const [x, y] = point(i, 100);
        return <line key={i} x1={cx} y1={cy} x2={x} y2={y} stroke="#e5e7eb" strokeWidth="1" />;
      })}
      <polygon points={polyPoints} fill={color} fillOpacity="0.2" stroke={color} strokeWidth="2" />
      {values.map((v, i) => {
        const [x, y] = point(i, v);
        return <circle key={i} cx={x} cy={y} r="3.5" fill={color} />;
      })}
      {labels.map((l, i) => {
        const [x, y] = labelPoint(i);
        return (
          <text key={i} x={x} y={y} textAnchor="middle" dominantBaseline="middle" fontSize="11" fill="#6b7280">
            {l} · <tspan fontWeight="600" fill={color}>{values[i]}</tspan>
          </text>
        );
      })}
    </svg>
  );
}
