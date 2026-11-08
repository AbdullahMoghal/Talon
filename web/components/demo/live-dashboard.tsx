'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { useReducer, useSpacetimeDB, useTable } from 'spacetimedb/react';
import { reducers, tables } from '@/src/module_bindings';
import { unwrapOpt } from '@/lib/option';
import { TalonLogo } from '@/components/talon-logo';
import {
  AGENT_INFO, INDICATOR_LABEL, KIND_LABEL, clock, ms, parseContent, prettyCategory, summarize, useRoom,
} from './demo-data';

const PIPELINE = ['triage', 'extractor', 'handler', 'persona', 'safety', 'analyst'] as const;
const ACTIVE_WINDOW_MS = 4000;

// What a scammer can't easily change after rotating numbers: where the victim pays or clicks. Checked in this order.
const BLOCK_PRIORITY = ['wallet', 'payment_handle', 'account', 'url', 'email', 'phone'] as const;

/** The same scammer's next text: new number, new wording, same cash-out. Talon should block it on arrival. */
function rotatedScam(kind: string, value: string): string {
  switch (kind) {
    case 'wallet': return `Final notice: your funds are on hold. Send the release fee to ${value} today to unlock them`;
    case 'payment_handle': return `Final notice: your balance is overdue. Send the payment to ${value} today to avoid a late fee`;
    case 'account': return `Final notice: your balance is overdue. Transfer the payment to account ${value} today to avoid a late fee`;
    case 'url': return `Final notice: your account is on hold. Verify today at ${value} to avoid suspension`;
    case 'email': return `Final notice: your account is on hold. Email ${value} today to avoid suspension`;
    default: return `Final notice: your account is on hold. Text ${value} today to avoid suspension`;
  }
}

/** The laptop screen: every agent step, live, for the room's current conversation. */
// showLogo is off when the dashboard sits inside the app shell, which already shows the logo.
export function LiveDashboard({ room, showLogo = true }: { room: string; showLogo?: boolean }) {
  const { isActive } = useSpacetimeDB();
  const { room: roomRow, customer, messages, sessions, turns } = useRoom(room);
  const second = useRoom(`${room}-2`);
  const [steps] = useTable(tables.agentStep);
  const [plans] = useTable(tables.handlerPlan);
  const [indicators] = useTable(tables.indicator);
  const [campaigns] = useTable(tables.campaign);
  const [cards] = useTable(tables.impactCard);
  const [personas] = useTable(tables.persona);
  const [insights] = useTable(tables.insight);
  const [outbox] = useTable(tables.scammerMessage);
  const [replies] = useTable(tables.customerMessage);
  const [alerts] = useTable(tables.customerAlert);
  const send = useReducer(reducers.scammerSend);
  const resetRoom = useReducer(reducers.resetRoom);
  const [resetting, setResetting] = useState(false);
  const [now, setNow] = useState(() => Date.now());
  const [open, setOpen] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const feedRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 500);
    return () => clearInterval(t);
  }, []);

  // Focus on the newest conversation: its first message (triage happens before a session exists) and session.
  const focusMsg = [...messages].reverse().find((m) => unwrapOpt<string>(m.sessionId)) ?? messages[messages.length - 1];
  const session = sessions.find((s) => s.id === unwrapOpt<string>(focusMsg?.sessionId));
  // Trace every message in the room (warm-up texts get triaged too) plus the takeover session.
  const keys = useMemo(
    () => new Set([...messages.map((m) => m.id), ...sessions.map((s) => s.id)]),
    [messages, sessions]
  );

  const feed = useMemo(
    () => steps.filter((s) => keys.has(s.sessionId)).sort((a, b) => Number(a.id - b.id)),
    [steps, keys]
  );
  const lastStep = feed[feed.length - 1];
  const working = outbox.some((m) => m.roomCode === room && (m.status === 'processing' || m.status === 'queued'));
  const activeAgent = lastStep && (working || now - ms(lastStep.createdAt) < ACTIVE_WINDOW_MS) ? lastStep.agent : null;

  useEffect(() => {
    const el = feedRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [feed.length]);

  const plan = useMemo(
    () => plans.filter((p) => p.sessionId === session?.id).sort((a, b) => Number(b.id - a.id))[0],
    [plans, session]
  );
  const myIndicators = useMemo(
    () => indicators.filter((i) => i.sessionId === session?.id).sort((a, b) => Number(a.id - b.id)),
    [indicators, session]
  );
  const campaign = campaigns.find((c) => c.id === unwrapOpt<string>(session?.campaignId));
  const card = cards.find((c) => c.sessionId === session?.id);
  const speakingAs = personas.find((p) => p.id === unwrapOpt<string>(session?.personaId));
  const insight = insights
    .filter((i) => i.campaignId === campaign?.id)
    .sort((a, b) => ms(b.createdAt) - ms(a.createdAt))[0];
  // One thread: scammer texts (each triaged), the customer's replies, then Talon's takeover turns.
  const thread = useMemo(() => {
    type Line = { key: string; at: number; who: 'scammer' | 'customer' | 'talon'; text: string; triage?: Record<string, unknown>; retrieved?: boolean };
    const out: Line[] = [];
    const openers = new Set(messages.map((m) => m.text));
    for (const m of messages) {
      const out_ = steps.find((s) => s.sessionId === m.id && s.agent === 'triage' && s.kind === 'output');
      out.push({
        key: m.id, at: ms(m.receivedAt), who: 'scammer', text: m.text,
        triage: out_ ? parseContent(out_.contentJson) : undefined,
        retrieved: steps.some((s) => s.sessionId === m.id && s.agent === 'triage' && s.kind === 'tool_call'),
      });
    }
    for (const r of replies) if (r.roomCode === room) out.push({ key: `c${r.id}`, at: ms(r.sentAt), who: 'customer', text: r.text });
    for (const t of turns) {
      if (t.sender === 'scammer' && openers.has(t.text) && !out.some((l) => l.key === t.id)) continue; // opener shown above
      out.push({ key: t.id, at: ms(t.ts), who: t.sender === 'talon' ? 'talon' : 'scammer', text: t.text });
    }
    return out.sort((a, b) => a.at - b.at);
  }, [messages, replies, turns, steps, room]);
  const secondLast = second.messages[second.messages.length - 1];
  const secondAlert = secondLast && alerts.find((a) => unwrapOpt<string>(a.inboundMessageId) === secondLast.id);

  const stats = useMemo(() => {
    const by: Record<string, { n: number; ms: number }> = {};
    for (const s of feed) {
      by[s.agent] ??= { n: 0, ms: 0 };
      by[s.agent].n += 1;
      by[s.agent].ms += s.latencyMs;
    }
    return by;
  }, [feed]);

  async function resetSession() {
    if (!window.confirm(`Reset room ${room}? This clears both phones, the agent trace and the campaign so you can try a new scenario.`)) return;
    setResetting(true);
    setNote(null);
    try {
      await resetRoom({ code: room });
    } catch (e) {
      setNote(e instanceof Error ? e.message : String(e));
    } finally {
      setResetting(false);
    }
  }

  // Once the campaign is shut down, the second customer gets the scammer's next move: a new number and new
  // wording that still reuses what Talon extracted. Before that, the same text (so triage has to warn on it).
  const burned = campaign?.status === 'burned';
  const reused = burned
    ? BLOCK_PRIORITY.map((k) => myIndicators.find((i) => i.kind === k)).find(Boolean)
    : undefined;

  async function sendSecond() {
    if (!focusMsg) return;
    setNote(null);
    try {
      if (reused) {
        await send({ roomCode: `${room}-2`, text: rotatedScam(reused.kind, reused.value) });
        setNote(`Sent from a new number with new wording, reusing the ${(INDICATOR_LABEL[reused.kind] ?? reused.kind).toLowerCase()} ${reused.value}`);
      } else {
        await send({ roomCode: `${room}-2`, text: focusMsg.text });
        setNote('Sent the same scam to a second customer');
      }
    } catch (e) {
      setNote(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div className="live">
      <header className="live-header">
        <div className="live-brand">
          {showLogo && <TalonLogo height={34} />}
          <div>
            <h1>Talon live</h1>
            <p>Six Nemotron agents, one conversation, every step as it happens</p>
          </div>
        </div>
        <div className="live-meta">
          <span className="live-room">Room <strong>{room}</strong></span>
          <span className={`live-conn ${isActive ? 'on' : ''}`}>{isActive ? 'Live' : 'Connecting…'}</span>
          <button type="button" className="live-reset" onClick={() => void resetSession()} disabled={!roomRow || resetting}>
            {resetting ? 'Resetting…' : 'Reset session'}
          </button>
        </div>
      </header>

      {!roomRow && <div className="live-banner">Waiting for room {room}. Start the engine: <code>python -m talon_agents.live --room {room}</code></div>}

      <section className="pipeline" aria-label="Agent pipeline">
        {PIPELINE.map((a, i) => (
          <div key={a} className="pipe-wrap">
            <div className={`pipe-node agent-${a} ${activeAgent === a ? 'is-active' : ''} ${stats[a] ? 'has-run' : ''}`}>
              <strong>{AGENT_INFO[a].label}</strong>
              <span>{AGENT_INFO[a].role}</span>
              {stats[a] && <em>{stats[a].n} steps · {(stats[a].ms / 1000).toFixed(1)}s</em>}
            </div>
            {i < PIPELINE.length - 1 && <div className={`pipe-edge ${i === 4 ? 'dashed' : ''}`} />}
          </div>
        ))}
      </section>

      <div className="live-grid">
        <section className="panel panel-convo">
          <h2>Conversation</h2>
          {speakingAs && (
            <div className="speaking-as">
              <span>Talon is texting as</span>
              <strong>{speakingAs.name}, {speakingAs.age} · {speakingAs.city}, {speakingAs.state}</strong>
              <em>{speakingAs.backstory}</em>
              {speakingAs.source === 'nemotron-personas-usa' && <small>Synthetic person from NVIDIA Nemotron-Personas-USA</small>}
            </div>
          )}
          {!focusMsg && <p className="muted">No messages yet. Text the customer from the scammer phone.</p>}
          {thread.length > 0 && (
            <div className="convo">
              {thread.map((l) => (
                <div key={l.key}>
                  <div className={`convo-line ${l.who}`}>
                    <span>
                      {l.who === 'talon' ? 'Talon (as the persona)' : l.who === 'customer' ? `${customer?.displayName ?? 'Customer'} (real customer)` : 'Scammer'}
                      {' · '}{clock(l.at)}
                    </span>
                    <p>{l.text}</p>
                  </div>
                  {l.triage && (
                    <div className={`convo-triage ${l.triage.is_scam ? 'scam' : ''}`}>
                      Triage: {l.triage.is_scam ? `scam · ${prettyCategory(String(l.triage.category))}` : 'not flagged'} ·{' '}
                      {Math.round(Number(l.triage.confidence) * 100)}%{l.retrieved ? ' · searched similar scams' : ''}
                    </div>
                  )}
                  {session && l.key === session.inboundMessageId && (
                    <div className="convo-sys">Customer tapped “Let Talon handle it”</div>
                  )}
                </div>
              ))}
              {focusMsg?.status === 'warned' && !session && <div className="convo-sys">Alert shown. Waiting for the customer…</div>}
              {focusMsg?.status === 'reported' && !session && (
                <div className="convo-sys reported">Reported by customer. The text was reported as spam and deleted from their phone.</div>
              )}
              {focusMsg?.status === 'deleted' && !session && <div className="convo-sys">Deleted by the customer</div>}
              {session && session.status !== 'active' && (
                <div className="convo-sys">Session {session.status === 'stopped' ? 'stopped by the customer' : 'completed'}</div>
              )}
            </div>
          )}
        </section>

        <section className="panel panel-trace">
          <h2>Agent trace <span className="muted">{feed.length} steps</span></h2>
          <div className="trace" ref={feedRef}>
            {feed.map((s) => {
              const c = parseContent(s.contentJson);
              const id = String(s.id);
              return (
                <button type="button" key={id} className={`step agent-${s.agent} kind-${s.kind}`}
                  onClick={() => setOpen(open === id ? null : id)}>
                  <div className="step-head">
                    <span className="step-agent">{AGENT_INFO[s.agent]?.label ?? s.agent}</span>
                    <span className="step-kind">{KIND_LABEL[s.kind] ?? s.kind}</span>
                    {s.latencyMs > 0 && <span className="step-ms">{(s.latencyMs / 1000).toFixed(1)}s</span>}
                  </div>
                  <p>{summarize(s.agent, s.kind, c)}</p>
                  {open === id && <pre>{JSON.stringify(c, null, 2)}</pre>}
                </button>
              );
            })}
            {working && <div className="step step-pending">Agents working…</div>}
          </div>
        </section>

        <aside className="panel panel-side">
          <div className="side-block">
            <h3>Handler plan</h3>
            {plan ? (
              <dl className="plan">
                <dt>Have</dt><dd>{plan.have.length ? plan.have.join(', ') : 'nothing yet'}</dd>
                <dt>Need</dt><dd>{plan.need || '—'}</dd>
                <dt>Tactic</dt><dd><code>{plan.tactic}</code></dd>
                {plan.note && (<><dt>Why</dt><dd>{plan.note}</dd></>)}
              </dl>
            ) : <p className="muted">Planned each turn once Talon takes over.</p>}
          </div>

          <div className="side-block">
            <h3>Scammer intel <span className="muted">{myIndicators.length}</span></h3>
            {myIndicators.length === 0 && <p className="muted">Links, numbers and payment details land here.</p>}
            <ul className="intel">
              {myIndicators.map((i) => (
                <li key={String(i.id)}><span>{INDICATOR_LABEL[i.kind] ?? i.kind}</span><code>{i.value}</code></li>
              ))}
            </ul>
          </div>

          <div className="side-block">
            <h3>Campaign</h3>
            {campaign ? (
              <div className={`campaign ${campaign.status}`}>
                <strong>{campaign.status === 'burned' ? 'Shut down' : 'Tracking'}</strong>
                <span>{campaign.label}</span>
                {campaign.status === 'burned' && unwrapOpt<number>(campaign.timeToBurnS) !== undefined && (
                  <em>burned in {Math.round(unwrapOpt<number>(campaign.timeToBurnS) ?? 0)}s</em>
                )}
              </div>
            ) : <p className="muted">Sessions sharing links or payment details become one campaign.</p>}
            {insight && (
              <div className="insight">
                <span>Analyst summary</span>
                <p>{insight.text}</p>
              </div>
            )}
            <button type="button" className="ghost" onClick={() => void sendSecond()} disabled={!focusMsg}>
              {reused ? 'Same scammer, new number: text a second customer' : 'Send this scam to a second customer'}
            </button>
            {campaign && !burned && (
              <p className="muted">Not shut down yet. Talon burns the campaign once the scammer asks for payment, or a second customer is hit.</p>
            )}
            {secondLast && (
              <p className={`second ${secondLast.status}`}>
                Second customer: <strong>{secondLast.status === 'blocked' ? 'blocked before they saw it' : secondLast.status === 'reported' ? 'reported by customer' : secondLast.status}</strong>
                {secondLast.status === 'blocked' && secondAlert && <><br /><small>{secondAlert.text}</small></>}
              </p>
            )}
            {note && <p className="muted">{note}</p>}
          </div>

          {card && (
            <div className="side-block impact">
              <h3>Impact card</h3>
              <p>{card.summary}</p>
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}
