'use client';

import dynamic from 'next/dynamic';
import { useMemo, useState } from 'react';
import { useSpacetimeDB, useTable } from 'spacetimedb/react';
import { tables } from '@/src/module_bindings';
import { unwrapOpt } from '@/lib/option';
import { jitter, metroForNumber } from '@/lib/area-codes';
import { labelFor, originSourceLabel } from '@/lib/labels';
import type {
  CustomerPoint,
  HeatPoint,
  OriginCluster,
} from './heatmap-map';

const HeatmapMap = dynamic(
  () => import('./heatmap-map').then((m) => m.HeatmapMap),
  {
    ssr: false,
    loading: () => (
      <div className="heat-map-canvas heat-map-loading">Loading map…</div>
    ),
  }
);

type CampaignStatusFilter = 'all' | 'active' | 'burned' | 'none';

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
  const [campaigns, campaignsReady] = useTable(tables.campaign);
  const [customers, customersReady] = useTable(tables.customer);
  const [indicators, indicatorsReady] = useTable(tables.indicator);
  const [history, historyReady] = useTable(tables.datasetMessage);
  const [historyIndicators] = useTable(tables.datasetIndicator);
  const [scamCategories] = useTable(tables.scamCategory);
  const categoryNames = useMemo(
    () => new Map(scamCategories.map((c) => [c.id, c.name] as [string, string])),
    [scamCategories]
  );
  const catLabel = (id?: string) => (id ? labelFor(id, categoryNames) : '');

  const [categoryFilter, setCategoryFilter] = useState('all');
  const [sourceFilter, setSourceFilter] = useState('all');
  const [campaignStatusFilter, setCampaignStatusFilter] =
    useState<CampaignStatusFilter>('all');
  const [showCustomers, setShowCustomers] = useState(false);
  const [selected, setSelected] = useState<OriginCluster | null>(null);

  const ready =
    messagesReady &&
    sessionsReady &&
    campaignsReady &&
    customersReady &&
    indicatorsReady &&
    historyReady;

  const campaignById = useMemo(() => {
    const map = new Map<string, (typeof campaigns)[number]>();
    for (const c of campaigns) map.set(c.id, c);
    return map;
  }, [campaigns]);

  const allOriginPoints = useMemo(() => {
    const seen = new Set<string>();
    const collected: HeatPoint[] = [];

    for (const row of messages) {
      const lat = unwrapOpt<number>(row.originLat);
      const lng = unwrapOpt<number>(row.originLng);
      if (lat == null || lng == null) continue;
      if (lat < -90 || lat > 90 || lng < -180 || lng > 180) continue;

      const city = unwrapOpt<string>(row.originCity);
      const state = unwrapOpt<string>(row.originState);
      const source = unwrapOpt<string>(row.originSource) ?? 'unknown';
      const confidence = unwrapOpt<number>(row.originConfidence) ?? 0.5;
      const category = unwrapOpt<string>(row.category);
      const campaignId = unwrapOpt<string>(row.campaignId);
      const sessionId = unwrapOpt<string>(row.sessionId);
      const label =
        city && state
          ? `${city}, ${state}`
          : city || state || `${lat.toFixed(2)}, ${lng.toFixed(2)}`;

      const point: HeatPoint = {
        id: `msg:${row.id}`,
        kind: 'message',
        lat,
        lng,
        weight: Math.min(1, Math.max(0.15, confidence)),
        label,
        source,
        confidence,
        category,
        campaignId,
        status: row.status,
        text: row.text,
        sessionId,
      };
      seen.add(`${lat.toFixed(4)},${lng.toFixed(4)}`);
      collected.push(point);
    }

    for (const row of sessions) {
      const lat = unwrapOpt<number>(row.originLat);
      const lng = unwrapOpt<number>(row.originLng);
      if (lat == null || lng == null) continue;
      if (lat < -90 || lat > 90 || lng < -180 || lng > 180) continue;
      const key = `${lat.toFixed(4)},${lng.toFixed(4)}`;
      if (seen.has(key)) continue;

      const city = unwrapOpt<string>(row.originCity);
      const state = unwrapOpt<string>(row.originState);
      const source = unwrapOpt<string>(row.originSource) ?? 'unknown';
      const confidence = unwrapOpt<number>(row.originConfidence) ?? 0.5;
      const category = unwrapOpt<string>(row.category);
      const campaignId = unwrapOpt<string>(row.campaignId);
      const label =
        city && state
          ? `${city}, ${state}`
          : city || state || `${lat.toFixed(2)}, ${lng.toFixed(2)}`;

      collected.push({
        id: `sess:${row.id}`,
        kind: 'session',
        lat,
        lng,
        weight: Math.min(1, Math.max(0.15, confidence)),
        label,
        source,
        confidence,
        category,
        campaignId,
        status: row.status,
        sessionId: row.id,
      });
      seen.add(key);
    }

    // Scam texts from earlier sessions, placed by the sender's area code. Skip any that are
    // already on the map as a live inbound message.
    // Only inbound texts that already have an origin count as "on the map".
    const inboundIds = new Set(
      messages.filter((m) => unwrapOpt<number>(m.originLat) != null).map((m) => m.id)
    );
    for (const row of history) {
      if (row.label !== 'scam' || inboundIds.has(row.id)) continue;
      // Very short texts are test pings, not scams worth mapping.
      if (row.text.trim().length < 20) continue;
      const metro = metroForNumber(row.sender);
      if (!metro) continue;
      const [dLat, dLng] = jitter(row.id);
      collected.push({
        id: `hist:${row.id}`,
        kind: 'message',
        lat: metro.lat,
        lng: metro.lng,
        heatLat: metro.lat + dLat,
        heatLng: metro.lng + dLng,
        weight: 0.5,
        label: `${metro.city}, ${metro.state}`,
        source: 'area_code',
        confidence: 0.35,
        category: unwrapOpt<string>(row.category),
        campaignId: unwrapOpt<string>(row.campaignId),
        text: row.text,
      });
    }

    return collected;
  }, [messages, sessions, history]);

  const categoryOptions = useMemo(
    () =>
      countMap(
        allOriginPoints
          .map((p) => p.category)
          .filter((c): c is string => Boolean(c))
      ).map((c) => c.name),
    [allOriginPoints]
  );

  const sourceOptions = useMemo(
    () => countMap(allOriginPoints.map((p) => p.source)).map((s) => s.name),
    [allOriginPoints]
  );

  const filteredPoints = useMemo(() => {
    return allOriginPoints.filter((point) => {
      if (categoryFilter !== 'all' && point.category !== categoryFilter) {
        return false;
      }
      if (sourceFilter !== 'all' && point.source !== sourceFilter) {
        return false;
      }
      if (campaignStatusFilter === 'none') {
        if (point.campaignId) return false;
      } else if (campaignStatusFilter !== 'all') {
        if (!point.campaignId) return false;
        const campaign = campaignById.get(point.campaignId);
        if (!campaign || campaign.status !== campaignStatusFilter) return false;
      }
      return true;
    });
  }, [
    allOriginPoints,
    categoryFilter,
    sourceFilter,
    campaignStatusFilter,
    campaignById,
  ]);

  const customerPoints = useMemo(() => {
    const list: CustomerPoint[] = [];
    for (const row of customers) {
      const lat = unwrapOpt<number>(row.lat);
      const lng = unwrapOpt<number>(row.lng);
      if (lat == null || lng == null) continue;
      list.push({
        id: row.id,
        lat,
        lng,
        name: row.displayName,
        city: row.city,
        state: row.state,
      });
    }
    return list;
  }, [customers]);

  const { byPlace, bySource } = useMemo(
    () => ({
      byPlace: countMap(filteredPoints.map((p) => p.label)).slice(0, 8),
      bySource: countMap(filteredPoints.map((p) => p.source)).slice(0, 8),
    }),
    [filteredPoints]
  );

  const drawer = useMemo(() => {
    if (!selected) return null;
    const points = selected.points;
    const campaignIds = [
      ...new Set(
        points
          .map((p) => p.campaignId)
          .filter((id): id is string => Boolean(id))
      ),
    ];
    const linkedCampaigns = campaignIds
      .map((id) => campaignById.get(id))
      .filter((c): c is (typeof campaigns)[number] => Boolean(c));

    const sessionIds = new Set(
      points
        .map((p) => p.sessionId)
        .filter((id): id is string => Boolean(id))
    );
    const historyIds = new Set(
      points.filter((p) => p.id.startsWith('hist:')).map((p) => p.id.slice(5))
    );
    const seenInd = new Set<string>();
    const linkedIndicators = [
      ...indicators
        .filter((ind) => sessionIds.has(ind.sessionId))
        .map((ind) => ({ id: `s${ind.id}`, kind: ind.kind, value: ind.value })),
      ...historyIndicators
        .filter((ind) => historyIds.has(ind.messageId))
        .map((ind) => ({ id: `h${ind.id}`, kind: ind.kind, value: ind.value })),
    ]
      .filter((ind) => {
        const k = `${ind.kind}:${ind.value}`;
        if (seenInd.has(k)) return false;
        seenInd.add(k);
        return true;
      })
      .slice(0, 12);

    const samples = points
      .filter((p) => p.text)
      .slice(0, 4)
      .map((p) => ({
        id: p.id,
        text: p.text!,
        category: p.category,
        status: p.status,
      }));

    const categories = countMap(
      points.map((p) => p.category ?? '(none)')
    );

    return {
      linkedCampaigns,
      linkedIndicators,
      samples,
      categories,
      activeSessions: points.filter((p) => p.status === 'active').length,
      takenOver: points.filter((p) => p.status === 'taken_over').length,
    };
  }, [selected, campaignById, campaigns, indicators, historyIndicators]);

  const filtersActive =
    categoryFilter !== 'all' ||
    sourceFilter !== 'all' ||
    campaignStatusFilter !== 'all';

  return (
    <section className={`heat-page${selected ? ' has-drawer' : ''}`}>
      <div className="heat-map-wrap">
        <HeatmapMap
          points={filteredPoints}
          customers={customerPoints}
          showCustomers={showCustomers}
          selectedKey={selected?.key ?? null}
          onSelectCluster={setSelected}
        />
        {!ready ? (
          <div className="heat-overlay">Loading origins from prod…</div>
        ) : filteredPoints.length === 0 ? (
          <div className="heat-overlay heat-empty">
            <p>
              {allOriginPoints.length === 0
                ? 'No scammer origins with coordinates yet.'
                : 'No origins match these filters.'}
            </p>
            {allOriginPoints.length === 0 ? (
              <p className="heat-empty-hint">
                Seed demo rows with{' '}
                <code>
                  python3 scripts/demo/takeover_smoke.py --server maincloud
                  --db talon-prod
                </code>
              </p>
            ) : (
              <button
                type="button"
                className="heat-reset"
                onClick={() => {
                  setCategoryFilter('all');
                  setSourceFilter('all');
                  setCampaignStatusFilter('all');
                }}
              >
                Reset filters
              </button>
            )}
          </div>
        ) : null}

        {selected && drawer ? (
          <div className="heat-drawer" role="dialog" aria-label="Origin detail">
            <header className="heat-drawer-header">
              <div>
                <p className="heat-drawer-kicker">Origin cluster</p>
                <h2>{selected.label}</h2>
                <p className="heat-drawer-meta">
                  {selected.points.length} point
                  {selected.points.length === 1 ? '' : 's'} ·{' '}
                  {selected.lat.toFixed(3)}, {selected.lng.toFixed(3)}
                </p>
              </div>
              <button
                type="button"
                className="heat-drawer-close"
                onClick={() => setSelected(null)}
              >
                Close
              </button>
            </header>

            <div className="heat-drawer-body">
              <section>
                <h3>Campaigns</h3>
                {drawer.linkedCampaigns.length === 0 ? (
                  <p className="dash-empty">No linked campaigns yet</p>
                ) : (
                  <ul className="heat-campaign-list">
                    {drawer.linkedCampaigns.map((c) => (
                      <li key={c.id}>
                        <div className="heat-campaign-top">
                          <strong>{c.label}</strong>
                          <span
                            className={`dash-pill ${c.status === 'burned' ? 'legit' : 'scam'}`}
                          >
                            {c.status}
                          </span>
                        </div>
                        <p>
                          {catLabel(c.category)}
                          {unwrapOpt<string>(c.brand)
                            ? ` · ${unwrapOpt<string>(c.brand)}`
                            : ''}{' '}
                          · {Number(c.customersHit)} customers hit
                          {unwrapOpt<number>(c.timeToBurnS) != null
                            ? ` · burned in ${Math.round(unwrapOpt<number>(c.timeToBurnS)!)}s`
                            : ''}
                        </p>
                      </li>
                    ))}
                  </ul>
                )}
              </section>

              <section>
                <h3>Sample messages</h3>
                {drawer.samples.length === 0 ? (
                  <p className="dash-empty">No message text in this cluster</p>
                ) : (
                  <ul className="dash-samples">
                    {drawer.samples.map((s) => (
                      <li key={s.id}>
                        {s.category ? (
                          <span className="dash-sample-cat">{catLabel(s.category)}</span>
                        ) : null}
                        {s.status ? (
                          <span className="dash-pill scam">{s.status}</span>
                        ) : null}
                        <p>{s.text}</p>
                      </li>
                    ))}
                  </ul>
                )}
              </section>

              <section>
                <h3>Indicators</h3>
                {drawer.linkedIndicators.length === 0 ? (
                  <p className="dash-empty">No extracted indicators yet</p>
                ) : (
                  <ul className="heat-indicator-list">
                    {drawer.linkedIndicators.map((ind) => (
                      <li key={ind.id}>
                        <span className="dash-pill scam">{labelFor(ind.kind)}</span>
                        <code>{ind.value}</code>
                      </li>
                    ))}
                  </ul>
                )}
              </section>

              <section>
                <h3>Quick actions</h3>
                <div className="heat-actions">
                  <button type="button" className="heat-action" disabled>
                    Warn metro (mock)
                  </button>
                  <button type="button" className="heat-action" disabled>
                    Export indicators (mock)
                  </button>
                  <button type="button" className="heat-action" disabled>
                    Create opportunity (mock)
                  </button>
                </div>
                <p className="heat-action-note">
                  Demo stubs — wire to campaign / shield reducers next.
                </p>
              </section>
            </div>
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
            <p className="dash-stat-value">
              {filteredPoints.length.toLocaleString()}
            </p>
            <p className="dash-stat-hint">
              {filtersActive
                ? `${allOriginPoints.length} total before filters`
                : 'scam texts Talon has handled'}
            </p>
          </article>
        </div>

        <article className="dash-panel heat-filters">
          <h2>Filters</h2>
          <label className="heat-field">
            <span>Category</span>
            <select
              value={categoryFilter}
              onChange={(e) => {
                setCategoryFilter(e.target.value);
                setSelected(null);
              }}
            >
              <option value="all">All categories</option>
              {categoryOptions.map((c) => (
                <option key={c} value={c}>
                  {catLabel(c)}
                </option>
              ))}
            </select>
          </label>
          <label className="heat-field">
            <span>Origin source</span>
            <select
              value={sourceFilter}
              onChange={(e) => {
                setSourceFilter(e.target.value);
                setSelected(null);
              }}
            >
              <option value="all">All sources</option>
              {sourceOptions.map((s) => (
                <option key={s} value={s}>
                  {originSourceLabel(s)}
                </option>
              ))}
            </select>
          </label>
          <label className="heat-field">
            <span>Campaign status</span>
            <select
              value={campaignStatusFilter}
              onChange={(e) => {
                setCampaignStatusFilter(e.target.value as CampaignStatusFilter);
                setSelected(null);
              }}
            >
              <option value="all">Any / all</option>
              <option value="active">Active campaigns</option>
              <option value="burned">Burned campaigns</option>
              <option value="none">No campaign linked</option>
            </select>
          </label>
          <label className="heat-toggle">
            <input
              type="checkbox"
              checked={showCustomers}
              onChange={(e) => setShowCustomers(e.target.checked)}
            />
            <span>Show customer landings ({customerPoints.length})</span>
          </label>
          <p className="heat-click-hint">Click a magenta ring to inspect a hotspot.</p>
        </article>

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
                    <span>{originSourceLabel(row.name)}</span>
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
