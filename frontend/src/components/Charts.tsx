import type { ReactNode } from 'react';

/** Tiny dependency-free SVG charts (bars, stacked bars, line) for the Logs page. */

const W = 720;
const H = 300;
const PAD = { top: 10, right: 12, bottom: 24, left: 40 };
const innerW = W - PAD.left - PAD.right;
const innerH = H - PAD.top - PAD.bottom;

export interface BarSeries {
  name: string;
  values: number[];
  color: string;
}

function niceMax(v: number): number {
  if (v <= 0) return 1;
  const exp = Math.pow(10, Math.floor(Math.log10(v)));
  const n = v / exp;
  return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 5 ? 5 : 10) * exp;
}

const shortDay = (iso: string) => `${iso.slice(8, 10)}/${iso.slice(5, 7)}`;

function Frame(props: { title: string; max: number; labels: string[]; fmt: (n: number) => string; legend: BarSeries[]; children: ReactNode }) {
  const { title, max, labels, fmt, legend, children } = props;
  const ticks = [0, 0.5, 1].map((f) => max * f);
  const step = Math.max(1, Math.ceil(labels.length / 7));
  const x = (i: number) => PAD.left + (innerW / labels.length) * (i + 0.5);
  return (
    <figure className="chart">
      <figcaption>
        <span>{title}</span>
        <span className="chart-legend">
          {legend.map((s) => (
            <span key={s.name}>
              <i style={{ background: s.color }} />
              {s.name}
            </span>
          ))}
        </span>
      </figcaption>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={title} preserveAspectRatio="xMidYMid meet">
        {ticks.map((t) => {
          const y = PAD.top + innerH - (t / max) * innerH;
          return (
            <g key={t}>
              <line x1={PAD.left} x2={W - PAD.right} y1={y} y2={y} className="chart-grid" />
              <text x={PAD.left - 6} y={y + 4} textAnchor="end" className="chart-axis">
                {fmt(t)}
              </text>
            </g>
          );
        })}
        {labels.map((l, i) =>
          i % step === 0 ? (
            <text key={l} x={x(i)} y={H - 6} textAnchor="middle" className="chart-axis">
              {shortDay(l)}
            </text>
          ) : null,
        )}
        {children}
      </svg>
    </figure>
  );
}

export function BarChart(props: {
  title: string;
  labels: string[];
  series: BarSeries[];
  fmt?: (n: number) => string;
}) {
  const { title, labels, series, fmt = (n) => String(Math.round(n * 100) / 100) } = props;
  const totals = labels.map((_, i) => series.reduce((a, s) => a + (s.values[i] || 0), 0));
  const max = niceMax(Math.max(0, ...totals));
  const slot = innerW / labels.length;
  const bw = Math.max(3, slot * 0.62);
  return (
    <Frame title={title} max={max} labels={labels} fmt={fmt} legend={series}>
      {labels.map((l, i) => {
        let acc = 0;
        return (
          <g key={l}>
            {series.map((s) => {
              const v = s.values[i] || 0;
              const h = (v / max) * innerH;
              const y = PAD.top + innerH - ((acc + v) / max) * innerH;
              acc += v;
              return v > 0 ? (
                <rect key={s.name} x={PAD.left + slot * i + (slot - bw) / 2} y={y} width={bw} height={h} rx={2} fill={s.color}>
                  <title>{`${shortDay(l)} · ${s.name}: ${fmt(v)}`}</title>
                </rect>
              ) : null;
            })}
          </g>
        );
      })}
    </Frame>
  );
}

export function LineChart(props: {
  title: string;
  labels: string[];
  series: BarSeries[];
  fmt?: (n: number) => string;
}) {
  const { title, labels, series, fmt = (n) => String(Math.round(n * 100) / 100) } = props;
  const max = niceMax(Math.max(0, ...series.flatMap((s) => s.values)));
  const x = (i: number) => PAD.left + (innerW / labels.length) * (i + 0.5);
  const y = (v: number) => PAD.top + innerH - (v / max) * innerH;
  return (
    <Frame title={title} max={max} labels={labels} fmt={fmt} legend={series}>
      {series.map((s) => (
        <g key={s.name}>
          <polyline
            fill="none"
            stroke={s.color}
            strokeWidth="2"
            strokeLinejoin="round"
            points={s.values.map((v, i) => `${x(i)},${y(v)}`).join(' ')}
          />
          {s.values.map((v, i) => (
            <circle key={i} cx={x(i)} cy={y(v)} r="3" fill={s.color}>
              <title>{`${shortDay(labels[i])} · ${s.name}: ${fmt(v)}`}</title>
            </circle>
          ))}
        </g>
      ))}
    </Frame>
  );
}
