'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { useReducer, useSpacetimeDB, useTable } from 'spacetimedb/react';
import { reducers, tables } from '@/src/module_bindings';
import { unwrapOpt } from '@/lib/option';
import { clock, ms, newId, prettyCategory, useRoom } from './demo-data';
import { formatPhone } from './scammer-phone';

/** The judge playing the customer. Scam texts arrive here with Talon's warning. */
export function CustomerPhone({ room }: { room: string }) {
  const { isActive } = useSpacetimeDB();
  const { ready, room: roomRow, customer, messages, sessions, turns } = useRoom(room);
  const [categories] = useTable(tables.scamCategory);
  const [cards] = useTable(tables.impactCard);
  const [alerts] = useTable(tables.customerAlert);
  const takeover = useReducer(reducers.requestTakeover);
  const stop = useReducer(reducers.stopTakeover);
  const dismiss = useReducer(reducers.dismissMessage);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const endRef = useRef<HTMLDivElement>(null);

  const myCards = useMemo(() => cards.filter((c) => c.customerId === customer?.id), [cards, customer]);
  const myAlerts = useMemo(() => alerts.filter((a) => a.customerId === customer?.id), [alerts, customer]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages.length, turns.length, myCards.length]);

  async function act(key: string, fn: () => Promise<void>) {
    setBusy(key);
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  }

  const sender = roomRow ? formatPhone(roomRow.scammerNumber) : '';

  return (
    <div className="phone phone-customer">
      <header className="phone-header">
        <div className="phone-avatar phone-avatar-unknown">?</div>
        <div className="phone-contact">
          <strong>{sender || 'Messages'}</strong>
          <span>{customer ? `${customer.displayName}'s phone` : ready ? `Room ${room} not found` : 'Connecting…'}</span>
        </div>
        <span className={`phone-dot ${isActive ? 'on' : ''}`} />
      </header>

      <div className="phone-thread">
        {messages.length === 0 && (
          <div className="phone-empty">
            <p>You're the customer.</p>
            <p>Wait for a text. Talon checks every message before you read it.</p>
          </div>
        )}

        {messages.map((m) => {
          const session = sessions.find((s) => s.id === unwrapOpt<string>(m.sessionId));
          const category = unwrapOpt<string>(m.category);
          const confidence = unwrapOpt<number>(m.confidence);
          const steps = categories.find((c) => c.id === category)?.nextSteps ?? [];
          const card = session && myCards.find((c) => c.sessionId === session.id);
          const sessionTurns = session ? turns.filter((t) => t.sessionId === session.id) : [];

          if (m.status === 'blocked') {
            return (
              <div key={m.id} className="msg-blocked">
                <span className="talon-mark">T</span>
                <div>
                  <strong>Blocked by Talon</strong>
                  <p>This text came from a scam campaign Talon already shut down. You never had to see it.</p>
                </div>
              </div>
            );
          }
          if (m.status === 'deleted' || m.status === 'reported') {
            return <div key={m.id} className="msg-note">{m.status === 'reported' ? 'Reported as spam' : 'Deleted'}</div>;
          }

          return (
            <div key={m.id}>
              <div className="phone-time">{clock(ms(m.receivedAt))}</div>
              <div className={`bubble bubble-in ${m.status === 'warned' || session ? 'bubble-flagged' : ''}`}>{m.text}</div>

              {m.status === 'warned' && !session && (
                <div className="warn-card">
                  <div className="warn-head">
                    <span className="talon-mark">T</span>
                    <div>
                      <strong>Likely scam: {prettyCategory(category)}</strong>
                      {confidence !== undefined && <span className="warn-conf">{Math.round(confidence * 100)}% sure</span>}
                    </div>
                  </div>
                  {unwrapOpt<string>(m.reason) && <p className="warn-reason">{unwrapOpt<string>(m.reason)}</p>}
                  {steps.length > 0 && (
                    <ul className="warn-steps">{steps.slice(0, 3).map((s) => <li key={s}>{s}</li>)}</ul>
                  )}
                  <div className="warn-actions">
                    <button type="button" disabled={!!busy}
                      onClick={() => act('del' + m.id, () => dismiss({ messageId: m.id, action: 'deleted' }))}>Delete</button>
                    <button type="button" disabled={!!busy}
                      onClick={() => act('rep' + m.id, () => dismiss({ messageId: m.id, action: 'reported' }))}>Report</button>
                    <button type="button" className="primary" disabled={!!busy}
                      onClick={() => act('take' + m.id, () => takeover({ messageId: m.id, sessionId: newId('ses') }))}>
                      {busy === 'take' + m.id ? 'Handing over…' : 'Let Talon handle it'}
                    </button>
                  </div>
                </div>
              )}

              {session && (
                <div className={`takeover-card ${session.status === 'active' ? 'is-live' : ''}`}>
                  <div className="takeover-head">
                    <span className="talon-mark">T</span>
                    <div>
                      <strong>{session.status === 'active' ? 'Talon is handling this' : 'Talon finished'}</strong>
                      <span>
                        {session.status === 'active'
                          ? 'Talking to the scammer as a made-up person. Nothing about you is shared.'
                          : `${sessionTurns.length} messages exchanged`}
                      </span>
                    </div>
                    {session.status === 'active' && (
                      <button type="button" className="stop" disabled={!!busy}
                        onClick={() => act('stop' + session.id, () => stop({ sessionId: session.id }))}>Stop</button>
                    )}
                  </div>
                  {sessionTurns.length > 0 && (
                    <div className="takeover-feed">
                      {sessionTurns.slice(-4).map((t) => (
                        <div key={t.id} className={`feed-line ${t.sender}`}>
                          <span>{t.sender === 'talon' ? 'Talon' : 'Scammer'}</span>
                          <p>{t.text}</p>
                        </div>
                      ))}
                    </div>
                  )}
                  {card && (
                    <div className="impact-card">
                      <div className="impact-num">{card.customersProtected}</div>
                      <div>
                        <strong>{card.customersProtected === 1 ? 'customer protected' : 'customers protected'}</strong>
                        <p>{card.summary}</p>
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}

        {myAlerts.filter((a) => a.kind === 'warned').map((a) => (
          <div key={String(a.id)} className="msg-blocked">
            <span className="talon-mark">T</span>
            <div><strong>Heads up from Talon</strong><p>{a.text}</p></div>
          </div>
        ))}
        <div ref={endRef} />
      </div>
      {error && <div className="phone-error">{error}</div>}
      <div className="phone-compose phone-compose-disabled">
        <input disabled placeholder="Text Message" aria-label="Message (disabled)" />
        <button type="button" disabled>↑</button>
      </div>
    </div>
  );
}
