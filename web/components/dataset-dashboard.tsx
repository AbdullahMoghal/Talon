'use client';

import { useMemo } from 'react';
import { useSpacetimeDB, useTable } from 'spacetimedb/react';
import { tables } from '@/src/module_bindings';
import { unwrapOpt } from '@/lib/option';

function countBy(rows: readonly { [k: string]: unknown }[], key: string) {
  const map = new Map<string, number>();
  for (const row of rows) {
    const raw = row[key];
    const label =
      typeof raw === 'string' ? raw : unwrapOpt<string>(raw) ?? '(none)';
    map.set(label, (map.get(label) ?? 0) + 1);
  }
  return [...map.entries()]
    .map(([name, count]) => ({ name, count }))
    .sort((a, b) => b.count - a.count);
}

export function DatasetDashboard() {
  const { isActive, identity } = useSpacetimeDB();
  const [messages, messagesReady] = useTable(tables.datasetMessage);
  const [categories, categoriesReady] = useTable(tables.scamCategory);
  const [indicators, indicatorsReady] = useTable(tables.datasetIndicator);
  const [meta, metaReady] = useTable(tables.taxonomyMeta);
  const [tactics, tacticsReady] = useTable(tables.decoyTactic);
  const [subtypes, subtypesReady] = useTable(tables.legitSubtype);

  const ready =
    messagesReady &&
    categoriesReady &&
    indicatorsReady &&
    metaReady &&
    tacticsReady &&
    subtypesReady;

  const stats = useMemo(() => {
    const byLabel = countBy(messages, 'label');
    const byCategory = countBy(messages, 'category').filter(
      (c) => c.name !== '(none)'
    );
    const byIndicator = countBy(indicators, 'kind');
    const version = meta.find((m) => m.key === 'version')?.value;
    const updated = meta.find((m) => m.key === 'updated')?.value;
    const scam = byLabel.find((l) => l.name === 'scam')?.count ?? 0;
    const legit = byLabel.find((l) => l.name === 'legit')?.count ?? 0;
    return {
      total: messages.length,
      scam,
      legit,
      byCategory: byCategory.slice(0, 8),
      byIndicator: byIndicator.slice(0, 8),
      categoryCount: categories.length,
      tacticCount: tactics.length,
      subtypeCount: subtypes.length,
      indicatorCount: indicators.length,
      version,
      updated,
    };
  }, [messages, categories, indicators, meta, tactics, subtypes]);

  const uri = process.env.NEXT_PUBLIC_SPACETIMEDB_URI ?? '';
  const db = process.env.NEXT_PUBLIC_SPACETIMEDB_DB ?? '';

  return (
    <section className="dash">
      <header className="dash-header">
        <div>
          <h1>Dataset</h1>
          <p className="dash-sub">
            Live from <code>{db}</code> · {uri.replace(/^https?:\/\//, '')}
          </p>
        </div>
        <div className={`dash-status ${isActive ? 'is-live' : 'is-wait'}`}>
          {isActive ? 'Connected' : 'Connecting…'}
          {identity ? (
            <span className="dash-id">
              {identity.toHexString().slice(0, 10)}…
            </span>
          ) : null}
        </div>
      </header>

      {!ready ? (
        <p className="dash-loading">Loading tables from prod…</p>
      ) : (
        <>
          <div className="dash-grid">
            <StatCard label="Messages" value={stats.total} hint="dataset_message" />
            <StatCard label="Scam" value={stats.scam} hint="label = scam" />
            <StatCard label="Legit" value={stats.legit} hint="label = legit" />
            <StatCard
              label="Indicators"
              value={stats.indicatorCount}
              hint="dataset_indicator"
            />
            <StatCard
              label="Categories"
              value={stats.categoryCount}
              hint="scam_category"
            />
            <StatCard
              label="Tactics"
              value={stats.tacticCount}
              hint="decoy_tactic"
            />
          </div>

          <div className="dash-panels">
            <Panel title="Top categories">
              <BarList rows={stats.byCategory} />
            </Panel>
            <Panel title="Indicator kinds">
              <BarList rows={stats.byIndicator} />
            </Panel>
            <Panel title="Taxonomy">
              <dl className="dash-meta">
                <div>
                  <dt>Version</dt>
                  <dd>{stats.version ?? '—'}</dd>
                </div>
                <div>
                  <dt>Updated</dt>
                  <dd>{stats.updated ?? '—'}</dd>
                </div>
                <div>
                  <dt>Legit subtypes</dt>
                  <dd>{stats.subtypeCount}</dd>
                </div>
              </dl>
            </Panel>
          </div>

          <Panel title="Sample messages">
            <ul className="dash-samples">
              {messages.slice(0, 6).map((m) => (
                <li key={m.id}>
                  <span className={`dash-pill ${m.label}`}>{m.label}</span>
                  <span className="dash-sample-cat">
                    {unwrapOpt(m.category) ?? unwrapOpt(m.legitSubtype) ?? '—'}
                  </span>
                  <p>{m.text}</p>
                </li>
              ))}
            </ul>
          </Panel>
        </>
      )}
    </section>
  );
}

function StatCard({
  label,
  value,
  hint,
}: {
  label: string;
  value: number;
  hint: string;
}) {
  return (
    <article className="dash-stat">
      <p className="dash-stat-label">{label}</p>
      <p className="dash-stat-value">{value.toLocaleString()}</p>
      <p className="dash-stat-hint">{hint}</p>
    </article>
  );
}

function Panel({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <article className="dash-panel">
      <h2>{title}</h2>
      {children}
    </article>
  );
}

function BarList({ rows }: { rows: { name: string; count: number }[] }) {
  const max = rows[0]?.count ?? 1;
  if (rows.length === 0) {
    return <p className="dash-empty">No rows yet</p>;
  }
  return (
    <ul className="dash-bars">
      {rows.map((row) => (
        <li key={row.name}>
          <div className="dash-bar-head">
            <span>{row.name}</span>
            <span>{row.count}</span>
          </div>
          <div className="dash-bar-track">
            <div
              className="dash-bar-fill"
              style={{ width: `${Math.max(6, (row.count / max) * 100)}%` }}
            />
          </div>
        </li>
      ))}
    </ul>
  );
}
