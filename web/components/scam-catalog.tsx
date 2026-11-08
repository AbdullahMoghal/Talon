'use client';

import { Fragment, useMemo, useState } from 'react';
import { useTable } from 'spacetimedb/react';
import { tables } from '@/src/module_bindings';
import { ms } from '@/components/demo/demo-data';
import { labelFor } from '@/lib/labels';

const STATUS: Record<string, { label: string; tone: string }> = {
  shut_down: { label: 'Shut down', tone: 'is-down' },
  blocked: { label: 'Blocked', tone: 'is-blocked' },
  reported: { label: 'Reported', tone: 'is-reported' },
  active: { label: 'Seen', tone: 'is-active' },
};

function formatPhone(p: string): string {
  const d = p.replace(/\D/g, '').slice(-10);
  return d.length === 10 ? `(${d.slice(0, 3)}) ${d.slice(3, 6)}-${d.slice(6)}` : p;
}

function when(t: number): string {
  return new Date(t).toLocaleString([], { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });
}

/** Every scammer number Talon has seen, what it tried and what Talon collected. Kept across demo resets. */
// Intel is stored as "kind: value"; show the kind in plain words.
function intelLabel(item: string) {
  const at = item.indexOf(': ');
  if (at < 0) return item;
  return `${labelFor(item.slice(0, at))}: ${item.slice(at + 2)}`;
}

export function ScamCatalog() {
  const [rows, ready] = useTable(tables.scamCatalog);
  const [categories] = useTable(tables.scamCategory);
  const [open, setOpen] = useState<string | null>(null);
  const [query, setQuery] = useState('');

  const names = useMemo(() => new Map(categories.map((c) => [c.id, c.name])), [categories]);
  const list = useMemo(() => {
    const q = query.trim().toLowerCase();
    return [...rows]
      .filter((r) => !q || [r.number, ...r.categories, ...r.brands, ...r.intel].join(' ').toLowerCase().includes(q))
      .sort((a, b) => ms(b.lastSeen) - ms(a.lastSeen));
  }, [rows, query]);

  const totals = useMemo(() => ({
    numbers: rows.length,
    shutDown: rows.filter((r) => r.status === 'shut_down').length,
    attempts: rows.reduce((n, r) => n + r.attempts, 0),
    intel: rows.reduce((n, r) => n + r.intel.length, 0),
  }), [rows]);

  return (
    <section className="catalog">
      <header className="catalog-head">
        <div>
          <h1>Scam catalog</h1>
          <p>Every number Talon caught scamming, what it tried, and what Talon collected. Updates live.</p>
        </div>
        <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search number, brand, link…" />
      </header>

      <div className="catalog-stats">
        <div><strong>{totals.numbers}</strong><span>scammer numbers</span></div>
        <div><strong>{totals.shutDown}</strong><span>shut down</span></div>
        <div><strong>{totals.attempts}</strong><span>scam texts caught</span></div>
        <div><strong>{totals.intel}</strong><span>details collected</span></div>
      </div>

      {!ready && <p className="catalog-empty">Loading…</p>}
      {ready && list.length === 0 && (
        <p className="catalog-empty">No scammer numbers yet. Send a scam from the demo&apos;s sender phone.</p>
      )}

      {list.length > 0 && (
        <table className="catalog-table">
          {/* Fixed column widths, so opening a row's details never reflows the table. */}
          <colgroup>
            <col className="c-number" /><col className="c-status" /><col /><col />
            <col className="c-num" /><col className="c-num" /><col className="c-intel" />
            <col className="c-date" /><col className="c-date" />
          </colgroup>
          <thead>
            <tr>
              <th>Number</th><th>Status</th><th>Pretending to be</th><th>Scam type</th>
              <th>Attempts</th><th>Customers</th><th>Intel</th><th>First seen</th><th>Last seen</th>
            </tr>
          </thead>
          <tbody>
            {list.map((r) => {
              const st = STATUS[r.status] ?? STATUS.active;
              const isOpen = open === r.number;
              return (
                <Fragment key={r.number}>
                  <tr className={isOpen ? 'is-open' : ''} onClick={() => setOpen(isOpen ? null : r.number)}>
                    <td className="mono">{formatPhone(r.number)}</td>
                    <td><span className={`pill ${st.tone}`}>{st.label}</span></td>
                    <td>{r.brands.join(', ') || '—'}</td>
                    <td>{r.categories.map((c) => names.get(c) ?? c.replace(/_/g, ' ')).join(', ') || '—'}</td>
                    <td>{r.attempts}</td>
                    <td>{r.customers.length}</td>
                    <td>{r.intel.length}</td>
                    <td className="nowrap">{when(ms(r.firstSeen))}</td>
                    <td className="nowrap">{when(ms(r.lastSeen))}</td>
                  </tr>
                  {isOpen && (
                    <tr className="catalog-intel">
                      <td colSpan={9}>
                        {r.intel.length === 0 ? <em>No details collected yet.</em> : (
                          <ul>{r.intel.map((i) => <li key={i}><code>{intelLabel(i)}</code></li>)}</ul>
                        )}
                        <small>{r.sessions.length} Talon conversation(s) with this number</small>
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      )}
    </section>
  );
}
