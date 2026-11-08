'use client';

import { useState } from 'react';

export type Slice = {
  key: string;
  name: string;
  count: number;
  share: number;
  brands: string[];
  intel: { name: string; count: number }[];
  example?: string;
};

// Magenta ramp, darkest for the biggest type; "Other" is neutral gray.
const RAMP = ['#5e0030', '#8a0049', '#b80064', '#e20074', '#ef6aa9'];
const OTHER_COLOR = '#c9cdd3';

const SIZE = 220;
const C = SIZE / 2;
const R_OUT = 96;
const R_IN = 62;
const POP = 6;

function polar(r: number, a: number) {
  return [C + r * Math.cos(a), C + r * Math.sin(a)];
}

function arcPath(a0: number, a1: number, rOut: number, rIn: number) {
  // A full circle can't be drawn as a single arc; nudge the end so one slice still renders.
  if (a1 - a0 >= Math.PI * 2) a1 = a0 + Math.PI * 2 - 0.0001;
  const large = a1 - a0 > Math.PI ? 1 : 0;
  const [x0, y0] = polar(rOut, a0);
  const [x1, y1] = polar(rOut, a1);
  const [x2, y2] = polar(rIn, a1);
  const [x3, y3] = polar(rIn, a0);
  return `M${x0} ${y0}A${rOut} ${rOut} 0 ${large} 1 ${x1} ${y1}L${x2} ${y2}A${rIn} ${rIn} 0 ${large} 0 ${x3} ${y3}Z`;
}

const pct = (n: number) => `${Math.round(n * 100)}%`;

export function ScamTypeDonut({
  slices,
  total,
  selected,
  onSelect,
  selectedSlice,
}: {
  slices: Slice[];
  total: number;
  selected: string | null;
  onSelect: (key: string) => void;
  selectedSlice: Slice | null;
}) {
  const [hovered, setHovered] = useState<string | null>(null);
  if (slices.length === 0) return <p className="dash-empty">No scams yet</p>;

  const colorFor = (i: number, key: string) => (key === '__other__' ? OTHER_COLOR : RAMP[i] ?? OTHER_COLOR);
  const activeKey = hovered ?? selected;
  const active = slices.find((s) => s.key === activeKey) ?? selectedSlice;
  const sum = slices.reduce((n, s) => n + s.count, 0) || 1;

  let angle = -Math.PI / 2;
  const arcs = slices.map((s, i) => {
    const a0 = angle;
    const a1 = angle + (s.count / sum) * Math.PI * 2;
    angle = a1;
    return { s, i, a0, a1 };
  });

  return (
    <div className="donut">
      <div className="donut-chart">
        <svg
          viewBox={`0 0 ${SIZE} ${SIZE}`}
          role="img"
          aria-label="Share of scams by type"
          onMouseLeave={() => setHovered(null)}
        >
          {arcs.map(({ s, i, a0, a1 }) => {
            const isActive = activeKey === s.key;
            const dim = activeKey !== null && !isActive;
            return (
              <path
                key={s.key}
                d={arcPath(a0, a1, isActive ? R_OUT + POP : R_OUT, R_IN)}
                fill={colorFor(i, s.key)}
                stroke="#fff"
                strokeWidth={2}
                className="donut-slice"
                style={{ opacity: dim ? 0.35 : 1 }}
                tabIndex={0}
                role="button"
                aria-pressed={selected === s.key}
                aria-label={`${s.name}: ${s.count} texts, ${pct(s.share)}`}
                onMouseEnter={() => setHovered(s.key)}
                onFocus={() => setHovered(s.key)}
                onBlur={() => setHovered(null)}
                onClick={() => onSelect(s.key)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    onSelect(s.key);
                  }
                }}
              />
            );
          })}
        </svg>
        <div className="donut-center" aria-hidden>
          <span className="donut-center-value">{(active ? active.count : total).toLocaleString()}</span>
          <span className="donut-center-label">{active ? `${pct(active.share)} of scams` : 'scams caught'}</span>
        </div>
      </div>

      <ul className="donut-legend">
        {arcs.map(({ s, i }) => (
          <li key={s.key}>
            <button
              type="button"
              className={`donut-legend-row${activeKey === s.key ? ' is-active' : ''}${selected === s.key ? ' is-selected' : ''}`}
              onMouseEnter={() => setHovered(s.key)}
              onMouseLeave={() => setHovered(null)}
              onClick={() => onSelect(s.key)}
              aria-pressed={selected === s.key}
            >
              <span className="donut-swatch" style={{ background: colorFor(i, s.key) }} />
              <span className="donut-legend-name">{s.name}</span>
              <span className="donut-legend-value">{pct(s.share)}</span>
            </button>
          </li>
        ))}
      </ul>

      <div className={`donut-detail${active ? '' : ' is-empty'}`}>
        {active ? (
          <>
            <p className="donut-detail-title">{active.name}</p>
            <p className="donut-detail-sub">
              {active.count.toLocaleString()} texts · {pct(active.share)} of all scams
            </p>
            {active.brands.length > 0 && (
              <div className="donut-detail-block">
                <span className="donut-detail-label">Brands impersonated</span>
                <div className="donut-chips">
                  {active.brands.map((b) => (
                    <span key={b} className="donut-chip">{b}</span>
                  ))}
                </div>
              </div>
            )}
            {active.intel.length > 0 && (
              <div className="donut-detail-block">
                <span className="donut-detail-label">Intel pulled</span>
                <ul className="donut-intel">
                  {active.intel.map((k) => (
                    <li key={k.name}>
                      <span>{k.name}</span>
                      <span>{k.count}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {active.example && <p className="donut-example">“{active.example}”</p>}
            <p className="donut-hint">
              {selected === active.key ? 'Click again to clear the filter' : 'Click to filter the sample messages'}
            </p>
          </>
        ) : (
          <p className="donut-hint">Hover over a slice to see what Talon learned about that scam type. Click one to filter the messages below.</p>
        )}
      </div>
    </div>
  );
}
