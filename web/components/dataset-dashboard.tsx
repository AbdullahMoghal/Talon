'use client';

import { useEffect, useMemo, useState } from 'react';
import { useSpacetimeDB, useTable } from 'spacetimedb/react';
import { tables } from '@/src/module_bindings';
import { unwrapOpt } from '@/lib/option';
import { labelFor } from '@/lib/labels';
import { ScamTypeDonut, type Slice } from '@/components/scam-type-donut';

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

// Messages from Talon's own sessions first (the "live" split), then the rest, so the panel shows what Talon has
// actually been seeing rather than the first rows of the test set.
function latestSamples<T extends { split: string; id: string }>(rows: readonly T[], limit = 6): T[] {
  const live = rows.filter((r) => r.split === 'live');
  const pool = live.length >= limit ? live : [...live, ...rows.filter((r) => r.split !== 'live')];
  return [...pool].sort((a, b) => b.id.localeCompare(a.id)).slice(0, limit);
}

const OTHER = '__other__';

export function DatasetDashboard() {
  const { isActive } = useSpacetimeDB();
  const [messages, messagesReady] = useTable(tables.datasetMessage);
  const [categories, categoriesReady] = useTable(tables.scamCategory);
  const [indicators, indicatorsReady] = useTable(tables.datasetIndicator);
  const [meta, metaReady] = useTable(tables.taxonomyMeta);
  const [tactics, tacticsReady] = useTable(tables.decoyTactic);
  const [subtypes, subtypesReady] = useTable(tables.legitSubtype);

  const [selected, setSelected] = useState<string | null>(null);

  const ready =
    messagesReady &&
    categoriesReady &&
    indicatorsReady &&
    metaReady &&
    tacticsReady &&
    subtypesReady;

  const stats = useMemo(() => {
    const names = new Map<string, string>([
      ...categories.map((c) => [c.id, c.name] as [string, string]),
      ...subtypes.map((s) => [s.id, s.name] as [string, string]),
    ]);
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
      byCategory: byCategory.slice(0, 8).map((r) => ({ ...r, id: r.name, name: labelFor(r.name, names) })),
      categoryIds: byCategory.map((c) => c.name),
      byIndicator: byIndicator.slice(0, 8).map((r) => ({ ...r, name: labelFor(r.name) })),
      categoryCount: categories.length,
      tacticCount: tactics.length,
      subtypeCount: subtypes.length,
      indicatorCount: indicators.length,
      version,
      updated,
      names,
    };
  }, [messages, categories, indicators, meta, tactics, subtypes]);

  // Donut slices: the five biggest scam types, the rest folded into "Other".
  const slices = useMemo<Slice[]>(() => {
    const scams = messages.filter((m) => m.label === 'scam');
    const intelByMessage = new Map<string, string[]>();
    for (const ind of indicators) {
      const list = intelByMessage.get(ind.messageId) ?? [];
      list.push(ind.kind);
      intelByMessage.set(ind.messageId, list);
    }
    const ids = stats.categoryIds;
    const top = ids.slice(0, 5);
    const groups: { key: string; name: string; match: (cat: string) => boolean }[] = top.map((id) => ({
      key: id,
      name: labelFor(id, stats.names),
      match: (cat) => cat === id,
    }));
    if (ids.length > 5) {
      const rest = new Set(ids.slice(5));
      groups.push({ key: OTHER, name: `Other (${rest.size} types)`, match: (cat) => rest.has(cat) });
    }
    return groups
      .map((g) => {
        const rows = scams.filter((m) => g.match(unwrapOpt<string>(m.category) ?? ''));
        const brands = countBy(rows, 'brand').filter((b) => b.name !== '(none)').slice(0, 3);
        const intel = new Map<string, number>();
        for (const m of rows) {
          for (const kind of intelByMessage.get(m.id) ?? []) intel.set(kind, (intel.get(kind) ?? 0) + 1);
        }
        const example = latestSamples(rows, 1)[0];
        return {
          key: g.key,
          name: g.name,
          count: rows.length,
          share: scams.length ? rows.length / scams.length : 0,
          brands: brands.map((b) => b.name),
          intel: [...intel.entries()]
            .sort((a, b) => b[1] - a[1])
            .slice(0, 3)
            .map(([kind, n]) => ({ name: labelFor(kind), count: n })),
          example: example?.text,
        };
      })
      .filter((s) => s.count > 0);
  }, [messages, indicators, stats]);

  // Any click that isn't on a slice, legend row or category bar clears the filter.
  useEffect(() => {
    if (!selected) return;
    const onClick = (e: MouseEvent) => {
      const target = e.target as Element | null;
      if (target?.closest('.donut-slice, .donut-legend-row, .dash-bar-btn')) return;
      setSelected(null);
    };
    document.addEventListener('click', onClick);
    return () => document.removeEventListener('click', onClick);
  }, [selected]);

  const toggle = (key: string) => setSelected((cur) => (cur === key ? null : key));
  const selectedSlice = slices.find((s) => s.key === selected) ?? null;
  const selectedName = selectedSlice?.name ?? (selected ? labelFor(selected, stats.names) : null);
  const sampleRows = useMemo(() => {
    if (!selected) return latestSamples(messages);
    const top = new Set(stats.categoryIds.slice(0, 5));
    return latestSamples(
      messages.filter((m) => {
        const cat = unwrapOpt<string>(m.category);
        if (!cat) return false;
        return selected === OTHER ? !top.has(cat) : cat === selected;
      })
    );
  }, [messages, selected, stats.categoryIds]);


  return (
    <section className="dash">
      <header className="dash-header">
        <div>
          <h1>Overview</h1>
          <p className="dash-sub">Every text Talon has handled across its sessions, updated as they happen.</p>
        </div>
        <div className={`dash-status ${isActive ? 'is-live' : 'is-wait'}`}>
          {isActive ? 'Live' : 'Connecting…'}
        </div>
      </header>

      {!ready ? (
        <p className="dash-loading">Loading…</p>
      ) : (
        <>
          <div className="dash-grid">
            <StatCard label="Messages" value={stats.total} hint="texts Talon has seen" />
            <StatCard label="Scam" value={stats.scam} hint="confirmed scams" />
            <StatCard label="Legit" value={stats.legit} hint="real messages let through" />
            <StatCard
              label="Indicators"
              value={stats.indicatorCount}
              hint="links, numbers and payment details"
            />
            <StatCard
              label="Categories"
              value={stats.categoryCount}
              hint="types of scam tracked"
            />
            <StatCard
              label="Tactics"
              value={stats.tacticCount}
              hint="ways Talon keeps scammers talking"
            />
          </div>

          <Panel title="Scam types">
            <ScamTypeDonut
              slices={slices}
              total={stats.scam}
              selected={selected}
              onSelect={toggle}
              selectedSlice={selectedSlice}
            />
          </Panel>

          <div className="dash-panels">
            <Panel title="Top categories">
              <BarList
                rows={stats.byCategory}
                selected={selected}
                onSelect={toggle}
              />
            </Panel>
            <Panel title="Indicator kinds">
              <BarList rows={stats.byIndicator} />
            </Panel>
          </div>

          <Panel
            title={selectedName ? `Sample messages · ${selectedName}` : 'Sample messages'}
            action={
              selected ? (
                <button type="button" className="dash-clear" onClick={() => setSelected(null)}>
                  Show all
                </button>
              ) : null
            }
          >
            <ul className="dash-samples">
              {sampleRows.map((m) => (
                <li key={m.id}>
                  <span className={`dash-pill ${m.label}`}>{m.label}</span>
                  <span className="dash-sample-cat">
                    {(() => {
                      const id = unwrapOpt<string>(m.category) ?? unwrapOpt<string>(m.legitSubtype);
                      return id ? labelFor(id, stats.names) : '—';
                    })()}
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
  action,
  children,
}: {
  title: string;
  action?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <article className="dash-panel">
      <div className="dash-panel-head">
        <h2>{title}</h2>
        {action}
      </div>
      {children}
    </article>
  );
}

function BarList({
  rows,
  selected,
  onSelect,
}: {
  rows: { id?: string; name: string; count: number }[];
  selected?: string | null;
  onSelect?: (id: string) => void;
}) {
  const max = rows[0]?.count ?? 1;
  if (rows.length === 0) {
    return <p className="dash-empty">No rows yet</p>;
  }
  return (
    <ul className="dash-bars">
      {rows.map((row) => {
        const id = row.id ?? row.name;
        const body = (
          <>
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
          </>
        );
        return (
          <li key={id} className={selected === id ? 'is-selected' : undefined}>
            {onSelect ? (
              <button type="button" className="dash-bar-btn" onClick={() => onSelect(id)} aria-pressed={selected === id}>
                {body}
              </button>
            ) : (
              <div className="dash-bar-row">{body}</div>
            )}
          </li>
        );
      })}
    </ul>
  );
}
