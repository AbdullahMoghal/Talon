'use client';

import { useEffect, useMemo, useState } from 'react';
import type { Feed } from '@/lib/feed/types';

// Phase 1 polls /api/feed. Phase 2 swaps this for SpacetimeDB subscriptions.
const POLL_MS = 2000;

export function LiveFeed() {
  const [feed, setFeed] = useState<Feed | null>(null);
  const [selected, setSelected] = useState<number | null>(null);

  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const res = await fetch('/api/feed', { cache: 'no-store' });
        if (alive && res.ok) setFeed(await res.json());
      } catch {
        /* keep the last good feed */
      }
    };
    load();
    const t = setInterval(load, POLL_MS);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, []);

  const conversations = useMemo(
    () => [...(feed?.conversations ?? [])].sort((a, b) => b.id - a.id),
    [feed],
  );
  const active = selected ?? conversations[0]?.id ?? null;
  const turns = (feed?.turns ?? [])
    .filter((t) => t.conversation_id === active)
    .sort((a, b) => a.id - b.id);
  const indicators = (feed?.indicators ?? []).filter((i) => i.conversation_id === active);

  return (
    <section className="feed">
      <div className="feed-status">
        <span className={`feed-badge ${feed?.source === 'live' ? 'is-live' : 'is-mock'}`}>
          {feed ? (feed.source === 'live' ? 'Live: SpacetimeDB' : 'Mock data') : 'Loading'}
        </span>
        {feed?.error && <span className="feed-error">SpacetimeDB unreachable: {feed.error}</span>}
      </div>

      <div className="feed-grid">
        <div className="feed-panel">
          <h2>Canary conversations</h2>
          {conversations.length === 0 && <p className="feed-muted">No conversations yet.</p>}
          <ul className="feed-list">
            {conversations.map((c) => (
              <li key={c.id}>
                <button
                  type="button"
                  className={c.id === active ? 'feed-row is-on' : 'feed-row'}
                  onClick={() => setSelected(c.id)}
                >
                  <span>Canary #{c.canary_id}</span>
                  <span className="feed-muted">
                    {c.channel} · {c.turn_count} turns{c.is_bot_suspected ? ' · bot?' : ''}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </div>

        <div className="feed-panel">
          <h2>Conversation</h2>
          {turns.length === 0 && <p className="feed-muted">Select a conversation.</p>}
          <ol className="feed-turns">
            {turns.map((t) => (
              <li key={t.id} className={`feed-turn is-${t.sender}`}>
                <div className="feed-who">
                  {t.sender === 'scammer' ? 'Scammer' : 'Canary (decoy)'}
                  {t.triage_label && (
                    <span className="feed-tag">
                      {t.triage_label} · {Math.round(t.confidence * 100)}%
                    </span>
                  )}
                </div>
                <p>{t.text}</p>
              </li>
            ))}
          </ol>
        </div>

        <div className="feed-panel">
          <h2>Indicators</h2>
          {indicators.length === 0 && <p className="feed-muted">None extracted yet.</p>}
          <table className="feed-table">
            <thead>
              <tr>
                <th>Type</th>
                <th>Value</th>
                <th>Conf.</th>
              </tr>
            </thead>
            <tbody>
              {indicators.map((i) => (
                <tr key={i.id}>
                  <td>{i.kind}</td>
                  <td className="feed-mono">{i.value}</td>
                  <td>{Math.round(i.confidence * 100)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
}
