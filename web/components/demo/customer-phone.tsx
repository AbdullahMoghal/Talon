'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { useReducer, useSpacetimeDB, useTable } from 'spacetimedb/react';
import { reducers, tables } from '@/src/module_bindings';
import { unwrapOpt } from '@/lib/option';
import { clock, ms, newId, prettyCategory, redactScam, useRoom } from './demo-data';
import { formatPhone } from './scammer-phone';
import { TalonMark } from '@/components/talon-logo';

type Item =
  | { kind: 'in'; at: number; id: string }
  | { kind: 'out'; at: number; id: string; text: string };

/** The judge playing the customer: their own texting app, with Talon built in. */
export function CustomerPhone({ room }: { room: string }) {
  const { isActive } = useSpacetimeDB();
  const { ready, room: roomRow, customer, messages, sessions, turns } = useRoom(room);
  const [categories] = useTable(tables.scamCategory);
  const [cards] = useTable(tables.impactCard);
  const [alerts] = useTable(tables.customerAlert);
  const [replies] = useTable(tables.customerMessage);
  const takeover = useReducer(reducers.requestTakeover);
  const dismiss = useReducer(reducers.dismissMessage);
  const reply = useReducer(reducers.customerSend);
  const opened = useReducer(reducers.phoneOpened);
  const [busy, setBusy] = useState<string | null>(null);

  // Tell the engine someone is looking at this phone (one row per connection; dropped on disconnect).
  // The second customer's follow-up scam waits for this, so its block happens on screen.
  const roomOpen = Boolean(roomRow);
  useEffect(() => {
    if (!isActive || !roomOpen) return;
    opened({ roomCode: room }).catch((e) => console.warn('[phone] phone_opened', e));
  }, [isActive, roomOpen, room, opened]);
  const [error, setError] = useState<string | null>(null);
  const [draft, setDraft] = useState('');
  const endRef = useRef<HTMLDivElement>(null);

  const myCards = useMemo(() => cards.filter((c) => c.customerId === customer?.id), [cards, customer]);
  // Why each blocked text was blocked ("this text uses the payment handle ... from a scam Talon shut down 40 seconds ago").
  const blockedWhy = useMemo(() => new Map(alerts
    .filter((a) => a.customerId === customer?.id && a.kind === 'blocked' && unwrapOpt<string>(a.inboundMessageId))
    .map((a) => [unwrapOpt<string>(a.inboundMessageId)!, redactScam(a.text.replace(/^Blocked: /, '').replace(/^./, (c) => c.toUpperCase()))])), [alerts, customer]);
  const myAlerts = useMemo(() => alerts.filter((a) => a.customerId === customer?.id && a.kind === 'warned'), [alerts, customer]);
  const byId = useMemo(() => new Map(messages.map((m) => [m.id, m])), [messages]);

  const items: Item[] = useMemo(() => {
    const out: Item[] = messages.map((m) => ({ kind: 'in', at: ms(m.receivedAt), id: m.id }));
    for (const r of replies) {
      if (r.roomCode === room) out.push({ kind: 'out', at: ms(r.sentAt), id: `r${r.id}`, text: r.text });
    }
    return out.sort((a, b) => a.at - b.at);
  }, [messages, replies, room]);

  const talonActive = sessions.some((s) => s.status === 'active');

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [items.length, turns.length, myCards.length]);

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

  async function send() {
    const text = draft.trim();
    if (!text) return;
    await act('send', async () => {
      await reply({ roomCode: room, text });
      setDraft('');
    });
  }

  const sender = roomRow ? formatPhone(roomRow.scammerNumber) : '';
  // The second customer (room CODE-2) is the one the campaign reaches next: they never hand anything to Talon.
  // Each scam shows as the text with links and numbers removed, then Talon's "scam blocked" notice. No buttons.
  const secondCustomer = room.endsWith('-2');

  return (
    <div className="phone phone-customer">
      <header className="phone-header">
        <div className="phone-avatar">?</div>
        <div className="phone-contact">
          <strong>{sender || 'Messages'}</strong>
          <span>{customer ? `${customer.displayName}'s phone` : ready ? `Room ${room} not found` : 'Connecting…'}</span>
        </div>
        <span className={`phone-dot ${isActive ? 'on' : ''}`} />
      </header>

      <div className="phone-thread">
        {items.length === 0 && (
          <div className="phone-empty">
            <p>You're the customer.</p>
            <p>You are the T-Mobile customer. Text normally; Talon watches for scams.</p>
          </div>
        )}

        {items.map((it, i) => {
          const showTime = i === 0 || it.at - items[i - 1].at > 5 * 60_000;
          const time = showTime ? <div className="phone-time">{clock(it.at)}</div> : null;
          if (it.kind === 'out') {
            return (
              <div key={it.id}>
                {time}
                <div className="bubble bubble-out">{it.text}</div>
              </div>
            );
          }
          const m = byId.get(it.id)!;
          const session = sessions.find((s) => s.id === unwrapOpt<string>(m.sessionId));
          const category = unwrapOpt<string>(m.category);
          const confidence = unwrapOpt<number>(m.confidence);
          const reason = unwrapOpt<string>(m.reason);
          const steps = categories.find((c) => c.id === category)?.nextSteps ?? [];
          const card = session && myCards.find((c) => c.sessionId === session.id);

          if (m.status === 'blocked' || (secondCustomer && m.status === 'warned' && !session)) {
            const blocked = m.status === 'blocked';
            return (
              <div key={m.id}>
                {time}
                {secondCustomer && <div className="bubble bubble-in bubble-flagged">{redactScam(m.text)}</div>}
                <div className="talon-alert talon-alert-blocked">
                  <div className="talon-alert-from"><TalonMark size={22} />T-Mobile Talon</div>
                  {blocked ? (
                    <p><strong>Scam blocked.</strong> {blockedWhy.get(m.id) ?? `A text from ${sender} was part of a scam campaign Talon already shut down.`} You never had to see it.</p>
                  ) : (
                    <p><strong>Scam blocked.</strong> Talon flagged this text as a {prettyCategory(category)} scam and removed its links and numbers. You don't need to do anything.</p>
                  )}
                </div>
              </div>
            );
          }
          if (m.status === 'deleted' || m.status === 'reported') {
            return <div key={m.id} className="msg-note">{m.status === 'reported' ? 'Reported as spam and deleted' : 'Message deleted'}</div>;
          }

          return (
            <div key={m.id}>
              {time}
              <div className={`bubble bubble-in ${m.status === 'warned' || session ? 'bubble-flagged' : ''}`}>
                {m.status === 'warned' || session ? redactScam(m.text) : m.text}
              </div>
              {(m.status === 'warned' || session) && redactScam(m.text) !== m.text && (
                <div className="talon-checked">Talon removed the links and numbers from this text</div>
              )}
              {m.status === 'delivered' && unwrapOpt<string>(m.triageLabel) && (
                <div className="talon-checked">✓ Checked by Talon</div>
              )}

              {m.status === 'warned' && !session && (
                <div className="talon-alert">
                  <div className="talon-alert-from"><TalonMark size={22} />T-Mobile Talon Alert</div>
                  <p>
                    <strong>SCAM DETECTED.</strong> This looks like a {prettyCategory(category)} scam
                    {confidence !== undefined ? ` (${Math.round(confidence * 100)}% sure)` : ''}.{reason ? ` ${reason}` : ''}
                  </p>
                  {steps.length > 0 && <ul>{steps.slice(0, 2).map((s) => <li key={s}>{s}</li>)}</ul>}
                  <p className="talon-alert-ask">Let Talon handle it? Talon replies as a made-up person to waste the scammer's time and shut the scam down. Nothing about you is shared.</p>
                  <div className="talon-alert-actions">
                    <button type="button" className="primary" disabled={!!busy}
                      onClick={() => act('take' + m.id, () => takeover({ messageId: m.id, sessionId: newId('ses') }))}>
                      {busy === 'take' + m.id ? 'Handing over…' : 'Let Talon handle it'}
                    </button>
                    <button type="button" disabled={!!busy}
                      onClick={() => act('rep' + m.id, () => dismiss({ messageId: m.id, action: 'reported' }))}>Report</button>
                    <button type="button" disabled={!!busy}
                      onClick={() => act('del' + m.id, () => dismiss({ messageId: m.id, action: 'deleted' }))}>Delete</button>
                  </div>
                </div>
              )}

              {session && (
                <div className={`talon-alert talon-takeover ${session.status === 'active' ? 'is-live' : ''}`}>
                  <div className="talon-alert-from">
                    <TalonMark size={22} />
                    {session.status === 'active' ? 'Talon is handling this' : 'Scam stopped'}
                  </div>
                  <p className="talon-alert-sub">
                    {session.status === 'active'
                      ? "You don't need to do anything. Talon is dealing with this sender for you, and you'll get a summary here when it's done. You can keep using your phone as normal."
                      : 'Talon dealt with this sender and blocked their number. Nothing about you was shared.'}
                  </p>
                  {session.status === 'active' && (
                    <div className="talon-working"><span /><span /><span /> Talon is working on it</div>
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
                  {card && steps.length > 0 && (
                    <div className="learn-card">
                      <strong>How to spot this scam next time</strong>
                      <ul>{steps.slice(0, 3).map((s) => <li key={s}>{s}</li>)}</ul>
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}

        {myAlerts.map((a) => (
          <div key={String(a.id)} className="talon-alert talon-alert-blocked">
            <div className="talon-alert-from"><TalonMark size={22} />T-Mobile Talon</div>
            <p>{redactScam(a.text)}</p>
          </div>
        ))}
        <div ref={endRef} />
      </div>

      {error && <div className="phone-error">{error}</div>}
      <form className={`phone-compose ${talonActive ? 'phone-compose-disabled' : ''}`}
        onSubmit={(e) => { e.preventDefault(); void send(); }}>
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder={talonActive ? 'Talon is handling this conversation' : 'Text Message'}
          maxLength={480}
          disabled={!roomRow || talonActive}
          aria-label="Message"
        />
        <button type="submit" disabled={!draft.trim() || !roomRow || talonActive} aria-label="Send">↑</button>
      </form>
    </div>
  );
}
