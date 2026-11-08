'use client';

import dynamic from 'next/dynamic';
import { useMemo } from 'react';
import { useSpacetimeDB, useTable } from 'spacetimedb/react';
import { tables } from '@/src/module_bindings';
import { unwrapOpt } from '@/lib/option';
import type { HeatPoint } from './heatmap-map';

const HeatmapMap = dynamic(
  () => import('./heatmap-map').then((m) => m.HeatmapMap),
  {
    ssr: false,
    loading: () => <div className="heat-map-canvas heat-map-loading">Loading map…</div>,
  }
);

type OriginRow = {
  originLat: unknown;
  originLng: unknown;
  originCity: unknown;
  originState: unknown;
  originSource: unknown;
  originConfidence: unknown;
};

function coordKey(lat: number, lng: number) {
  return `${lat.toFixed(4)},${lng.toFixed(4)}`;
}

function toPoint(row: OriginRow): HeatPoint | null {
  const lat = unwrapOpt<number>(row.originLat);
  const lng = unwrapOpt<number>(row.originLng);
  if (lat == null || lng == null || Number.isNaN(lat) || Number.isNaN(lng)) {
    return null;
  }
  if (lat < -90 || lat > 90 || lng < -180 || lng > 180) return null;

  const city = unwrapOpt<string>(row.originCity);
  const state = unwrapOpt<string>(row.originState);
  const source = unwrapOpt<string>(row.originSource) ?? 'unknown';
  const confidence = unwrapOpt<number>(row.originConfidence) ?? 0.5;
  const label =
    city && state ? `${city}, ${state}` : city || state || `${lat.toFixed(2)}, ${lng.toFixed(2)}`;

  return {
    lat,
    lng,
    weight: Math.min(1, Math.max(0.15, confidence)),
    label,
    source,
    confidence,
  };
}

function countMap(values: string[]) {
  const map = new Map<string, number>();
  for (const v of values) map.set(v, (map.get(v) ?? 0) + 1);
  return [...map.entries()]
    .map(([name, count]) => ({ name, count }))
    .sort((a, b) => b.count - a.count);
}

export function ScammerHeatmap() {
  const { isActive } = useSpacetimeDB();
  const [messages, messagesReady] = useTable(tables.inboundMessage);
  const [sessions, sessionsReady] = useTable(tables.session);

  const ready = messagesReady && sessionsReady;

  const { points, byPlace, bySource } = useMemo(() => {
    const seen = new Set<string>();
    const collected: HeatPoint[] = [];

    for (const row of messages) {
      const point = toPoint(row);
      if (!point) continue;
      seen.add(coordKey(point.lat, point.lng));
      collected.push(point);
    }

    for (const row of sessions) {
      const point = toPoint(row);
      if (!point) continue;
      const key = coordKey(point.lat, point.lng);
      if (seen.has(key)) continue;
      seen.add(key);
      collected.push(point);
    }

    return {
      points: collected,
      byPlace: countMap(collected.map((p) => p.label)).slice(0, 8),
      bySource: countMap(collected.map((p) => p.source)).slice(0, 8),
    };
  }, [messages, sessions]);

  return (
    <section className="heat-page">
      <div className="heat-map-wrap">
        <HeatmapMap points={points} />
        {!ready ? (
          <div className="heat-overlay">Loading origins from prod…</div>
        ) : points.length === 0 ? (
          <div className="heat-overlay heat-empty">
            <p>No scammer origins with coordinates yet.</p>
            <p className="heat-empty-hint">
              Seed demo rows with{' '}
              <code>python3 scripts/demo/takeover_smoke.py --server maincloud --db talon-prod</code>
            </p>
          </div>
        ) : null}
      </div>

      <aside className="heat-side">
        <header className="heat-side-header">
          <h1>Scammer origins</h1>
          <div className={`dash-status ${isActive ? 'is-live' : 'is-wait'}`}>
            {isActive ? 'Connected' : 'Connecting…'}
          </div>
        </header>

        <div className="heat-stat-row">
          <article className="dash-stat">
            <p className="dash-stat-label">Heat points</p>
            <p className="dash-stat-value">{points.length.toLocaleString()}</p>
            <p className="dash-stat-hint">inbound + unique sessions</p>
          </article>
        </div>

        <article className="dash-panel">
          <h2>Top places</h2>
          {byPlace.length === 0 ? (
            <p className="dash-empty">No origin places yet</p>
          ) : (
            <ul className="dash-bars">
              {byPlace.map((row) => (
                <li key={row.name}>
                  <div className="dash-bar-head">
                    <span>{row.name}</span>
                    <span>{row.count}</span>
                  </div>
                  <div className="dash-bar-track">
                    <div
                      className="dash-bar-fill"
                      style={{
                        width: `${Math.max(6, (row.count / byPlace[0].count) * 100)}%`,
                      }}
                    />
                  </div>
                </li>
              ))}
            </ul>
          )}
        </article>

        <article className="dash-panel">
          <h2>Origin source</h2>
          {bySource.length === 0 ? (
            <p className="dash-empty">No sources yet</p>
          ) : (
            <ul className="dash-bars">
              {bySource.map((row) => (
                <li key={row.name}>
                  <div className="dash-bar-head">
                    <span>{row.name}</span>
                    <span>{row.count}</span>
                  </div>
                  <div className="dash-bar-track">
                    <div
                      className="dash-bar-fill"
                      style={{
                        width: `${Math.max(6, (row.count / bySource[0].count) * 100)}%`,
                      }}
                    />
                  </div>
                </li>
              ))}
            </ul>
          )}
        </article>
      </aside>
    </section>
  );
}
