'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { useReducer, useSpacetimeDB, useTable } from 'spacetimedb/react';
import { reducers, tables } from '@/src/module_bindings';
import { NORMAL_STARTERS, SCAM_STARTERS, clock, ms, useRoom } from './demo-data';

type Bubble = { key: string; mine: boolean; text: string; at: number; status?: string };

/** The judge playing the scammer. They text "the customer"; Talon answers once it takes over. */
export function ScammerPhone({ room }: { room: string }) {
  const { isActive } = useSpacetimeDB();
  const { ready, room: roomRow, customer, sessions, turns } = useRoom(room);
  const [sent] = useTable(tables.scammerMessage);
  const [replies] = useTable(tables.customerMessage);
  const send = useReducer(reducers.scammerSend);
  const [draft, setDraft] = useState('');
  const [error, setError] = useState<string | null>(null);
  const endRef = useRef<HTMLDivElement>(null);

  const mine = useMemo(
    () => sent.filter((m) => m.roomCode === room).sort((a, b) => Number(a.id - b.id)),
    [sent, room]
  );

  const bubbles: Bubble[] = useMemo(() => {
    const out: Bubble[] = mine.map((m) => ({
      key: `s${m.id}`, mine: true, text: m.text, at: ms(m.sentAt), status: m.status,
    }));
    for (const t of turns) if (t.sender === 'talon') out.push({ key: t.id, mine: false, text: t.text, at: ms(t.ts) });
    // The real customer's own replies (before Talon takes over, or after they tap Stop).
    for (const r of replies) {
      if (r.roomCode === room) out.push({ key: `c${r.id}`, mine: false, text: r.text, at: ms(r.sentAt) });
    }
    return out.sort((a, b) => a.at - b.at);
  }, [mine, turns, replies, room]);

  const activeSession = sessions.find((s) => s.status === 'active');

  // Scripted demo: the opener picks a script; after each reply the next follow-up is suggested.
  const script = useMemo(
    () => [...NORMAL_STARTERS, ...SCAM_STARTERS].find((st) => mine[0]?.text === st.text),
    [mine]
  );
  const lastMineAt = mine.length ? ms(mine[mine.length - 1].sentAt) : 0;
  const replied = bubbles.some((b) => !b.mine && b.at > lastMineAt);
  const finished = sessions.some((x) => x.status !== 'active');
  const nextIndex = mine.length - 1; // follow-up index: the opener was message 0
  const scriptDone = Boolean(script) && (finished || nextIndex >= (script?.followups.length ?? 0));
  const suggestion = script && replied && !scriptDone ? script.followups[nextIndex] : null;
  const total = script ? script.followups.length + 1 : 0;
  const last = mine[mine.length - 1];
  // "Typing" only once Talon has taken over; before that the customer is just reading.
  const typing = Boolean(activeSession && last && (last.status === 'queued' || last.status === 'processing'));

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [bubbles.length, typing]);

  async function submit(text: string) {
    const body = text.trim();
    if (!body) return;
    setError(null);
    try {
      await send({ roomCode: room, text: body });
      setDraft('');
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  const contact = customer?.phone ? formatPhone(customer.phone) : 'Target';

  return (
    <div className="phone phone-scammer">
      <header className="phone-header">
        <div className="phone-avatar">{(customer?.displayName ?? '?').slice(0, 1)}</div>
        <div className="phone-contact">
          <strong>{contact}</strong>
          <span>{roomRow ? 'iMessage' : ready ? `Room ${room} not found` : 'Connecting…'}</span>
        </div>
        <span className={`phone-dot ${isActive ? 'on' : ''}`} title={isActive ? 'connected' : 'connecting'} />
      </header>

      <div className="phone-thread">
        {bubbles.length === 0 && (
          <div className="phone-empty">
            <p>Text the other phone.</p>
            <p>Chat normally and Talon stays out of the way. Or play a scammer and try to get paid.</p>
          </div>
        )}
        {bubbles.map((b, i) => {
          const showTime = i === 0 || b.at - bubbles[i - 1].at > 5 * 60_000;
          const lastMine = b.mine && !bubbles.slice(i + 1).some((x) => x.mine);
          return (
            <div key={b.key}>
              {showTime && <div className="phone-time">{clock(b.at)}</div>}
              <div className={`bubble ${b.mine ? 'bubble-out' : 'bubble-in'}`}>{b.text}</div>
              {lastMine && <div className="bubble-receipt">{b.status === 'error' ? 'Not delivered' : 'Delivered'}</div>}
            </div>
          );
        })}
        {typing && (
          <div className="bubble bubble-in bubble-typing" aria-label="typing">
            <span /><span /><span />
          </div>
        )}
        <div ref={endRef} />
      </div>

      {mine.length === 0 && (
        <div className="phone-starters">
          {NORMAL_STARTERS.map((s) => (
            <button key={s.label} type="button" className="starter-normal" onClick={() => setDraft(s.text)}>{s.label}</button>
          ))}
          {SCAM_STARTERS.map((s) => (
            <button key={s.label} type="button" onClick={() => setDraft(s.text)}>{s.label} scam</button>
          ))}
        </div>
      )}
      {suggestion && draft !== suggestion && (
        <button type="button" className="phone-suggest" onClick={() => setDraft(suggestion)}>
          <span>Suggested next message · {mine.length + 1} of {total}</span>
          <p>{suggestion}</p>
          <em>Tap to use it</em>
        </button>
      )}
      {script && !replied && !scriptDone && mine.length > 0 && (
        <div className="phone-hint">Waiting for a reply… the next message will be suggested here.</div>
      )}
      {scriptDone && (
        <div className="phone-hint">
          {finished ? 'The other side has stopped replying. ' : "That's the end of this script. "}
          Reset the session on the dashboard to try another scenario.
        </div>
      )}
      {error && <div className="phone-error">{error}</div>}
      <form className="phone-compose" onSubmit={(e) => { e.preventDefault(); void submit(draft); }}>
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Text Message"
          maxLength={480}
          disabled={!roomRow}
          aria-label="Message"
        />
        <button type="submit" disabled={!draft.trim() || !roomRow} aria-label="Send">↑</button>
      </form>
    </div>
  );
}

export function formatPhone(p: string): string {
  const d = p.replace(/\D/g, '').slice(-10);
  return d.length === 10 ? `(${d.slice(0, 3)}) ${d.slice(3, 6)}-${d.slice(6)}` : p;
}
