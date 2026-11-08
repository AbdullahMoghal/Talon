'use client';

import { useMemo } from 'react';
import { useTable } from 'spacetimedb/react';
import { tables } from '@/src/module_bindings';
import { unwrapOpt } from '@/lib/option';

/** Milliseconds since epoch from a SpacetimeDB Timestamp. */
export function ms(ts: { microsSinceUnixEpoch: bigint } | undefined | null): number {
  return ts ? Number(ts.microsSinceUnixEpoch / 1000n) : 0;
}

export function clock(t: number): string {
  return new Date(t).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
}

export function newId(prefix: string): string {
  const rand = Math.random().toString(36).slice(2, 10);
  return `${prefix}_${Date.now().toString(36)}${rand}`;
}

export function prettyCategory(id: string | undefined): string {
  return (id ?? 'unknown').replace(/_/g, ' ');
}

export function cleanRoom(raw: string | null): string {
  return (raw ?? '').toUpperCase().replace(/[^A-Z0-9-]/g, '').slice(0, 10);
}

/**
 * Everything a room's screens need: the room, its customer, that customer's messages,
 * Talon's sessions for them and the turns in those sessions. Demo data is small, so
 * the hook subscribes to whole tables and filters on the client.
 */
export function useRoom(code: string) {
  const [rooms, roomsReady] = useTable(tables.demoRoom);
  const [customers] = useTable(tables.customer);
  const [messages, messagesReady] = useTable(tables.inboundMessage);
  const [sessions] = useTable(tables.session);
  const [turns] = useTable(tables.turn);

  return useMemo(() => {
    const room = rooms.find((r) => r.code === code);
    const customerId = room?.customerId;
    const customer = customers.find((c) => c.id === customerId);
    const roomMessages = messages
      .filter((m) => m.customerId === customerId)
      .sort((a, b) => ms(a.receivedAt) - ms(b.receivedAt));
    const roomSessions = sessions
      .filter((s) => unwrapOpt<string>(s.customerId) === customerId)
      .sort((a, b) => ms(a.startedAt) - ms(b.startedAt));
    const sessionIds = new Set(roomSessions.map((s) => s.id));
    const roomTurns = turns
      .filter((t) => sessionIds.has(t.sessionId))
      .sort((a, b) => ms(a.ts) - ms(b.ts));
    return {
      ready: roomsReady && messagesReady,
      room,
      customer,
      messages: roomMessages,
      sessions: roomSessions,
      turns: roomTurns,
    };
  }, [rooms, customers, messages, sessions, turns, code, roomsReady, messagesReady]);
}

// ---------------------------------------------------------------------------
// Agent steps, in plain language for the live trace
// ---------------------------------------------------------------------------

export const AGENTS = ['triage', 'extractor', 'handler', 'persona', 'safety', 'analyst'] as const;
export type AgentName = (typeof AGENTS)[number] | 'engine';

export const AGENT_INFO: Record<string, { label: string; role: string }> = {
  triage: { label: 'Triage', role: 'Scam or not, with honest confidence' },
  extractor: { label: 'Extractor', role: 'Pulls links, numbers and payment asks' },
  handler: { label: 'Handler', role: 'Plans each reply with tools' },
  persona: { label: 'Persona', role: 'Writes the reply in character' },
  safety: { label: 'Safety', role: 'Blocks anything risky before it goes out' },
  analyst: { label: 'Campaign analyst', role: 'Links, burns and warns' },
  engine: { label: 'Engine', role: 'Session control' },
};

export const KIND_LABEL: Record<string, string> = {
  thought: 'Thinking',
  tool_call: 'Tool call',
  tool_result: 'Tool result',
  output: 'Output',
  rejection: 'Rejected',
  retrieval_skipped: 'Decided not to retrieve',
};

type Json = Record<string, unknown>;

function short(value: unknown, max = 160): string {
  // JSON.stringify(undefined) is undefined, and a step can arrive with a field missing.
  const s = typeof value === 'string' ? value : value == null ? '' : (JSON.stringify(value) ?? String(value));
  return s.length > max ? `${s.slice(0, max - 1)}…` : s;
}

export function parseContent(json: string): Json {
  try {
    const v = JSON.parse(json);
    return v && typeof v === 'object' ? (v as Json) : { value: v };
  } catch {
    return { value: json };
  }
}

/** One readable line for a step. Never throws: a malformed step shows as raw JSON instead. */
export function summarize(agent: string, kind: string, c: Json): string {
  try {
    return summarizeStep(agent, kind, c) || short(c, 200);
  } catch {
    return short(c, 200);
  }
}

function summarizeStep(agent: string, kind: string, c: Json): string {
  if (kind === 'thought') return short(c.text, 260);
  if (kind === 'tool_call') {
    const args = c.args && Object.keys(c.args as Json).length ? short(c.args, 120) : '';
    return `${c.tool}(${args})`;
  }
  if (kind === 'tool_result') return `${c.tool} → ${short(c.result, 180)}`;
  if (kind === 'retrieval_skipped') return `Confident enough (${c.confidence}) to answer without searching similar scams`;
  if (kind === 'rejection') {
    if (Array.isArray(c.violations)) return `Draft rejected: ${(c.violations as string[]).join('; ')}`;
    if (Array.isArray(c.dropped))
      return `Dropped ${(c.dropped as Json[]).map((d) => `${d.kind} "${d.value}" (${d.why})`).join(', ')}`;
    return short(c.why ?? c, 200);
  }
  // outputs
  switch (agent) {
    case 'triage':
      return c.is_scam
        ? `Scam · ${prettyCategory(c.category as string)} · ${Math.round(Number(c.confidence) * 100)}% — ${c.reason}`
        : `Not flagged (${Math.round(Number(c.confidence) * 100)}%) — ${c.reason}`;
    case 'extractor': {
      const found = (c.new_indicators as Json[] | undefined) ?? [];
      return found.length ? `Found ${found.map((i) => `${i.kind}: ${i.value}`).join(' · ')}` : 'Nothing new this turn';
    }
    case 'handler':
      if (c.ended) return `Ending takeover: ${c.ended}`;
      return `Tactic ${c.tactic} — ${short(c.instructions_for_persona, 200)}`;
    case 'persona':
      return `${c.retry ? 'Retry: ' : ''}“${c.draft}”`;
    case 'safety':
      if (c.fallback) return `Out of retries, sending a safe line: “${c.fallback}”`;
      return c.passed ? 'Passed rules and model review' : `Failed: ${short(c.violations)}`;
    case 'analyst':
      if (c.impact_card) return `Impact card: ${short(c.impact_card, 220)}`;
      return `${c.decision ?? ''} ${c.summary ? `— ${c.summary}` : ''}`.trim();
    case 'engine':
      return c.session_ended ? `Session ended: ${c.session_ended}` : short(c);
    default:
      return short(c);
  }
}

/**
 * What a customer sees of a scam text: links, phone numbers, emails and payment handles removed, so
 * there's nothing to tap or copy. The full text stays on the dashboard for analysts.
 */
export function redactScam(text: string): string {
  return text
    .replace(/\b[\w.+-]+@[\w-]+\.[\w.-]+\b/g, '[email removed]')
    .replace(/https?:\/\/\S+|www\.\S+|\b[a-z0-9-]+(?:\.[a-z0-9-]+)*\.(?:com|net|org|info|biz|co|us|io|app|site|online|xyz|top|example|test|invalid|ly|me)(?:\/\S*)?/gi, '[link removed]')
    .replace(/(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}\b/g, '[number removed]')
    .replace(/\$[A-Za-z][\w-]{2,}/g, '[payment handle removed]')
    .replace(/\b0x[a-fA-F0-9]{20,}\b|\b(?:bc1|[13])[a-zA-HJ-NP-Z0-9]{25,}\b/g, '[wallet removed]');
}

export const INDICATOR_LABEL: Record<string, string> = {
  sender_number: 'Texting from',
  url: 'Link',
  phone: 'Phone',
  email: 'Email',
  wallet: 'Crypto wallet',
  payment_handle: 'Payment handle',
  account: 'Account',
  giftcard_ask: 'Gift card ask',
  remote_access_id: 'Remote access',
  brand: 'Impersonating',
};

/**
 * Demo scripts for the sender phone. Each starts with an opener and has follow-ups the phone suggests
 * one at a time after each reply, so a judge can play a whole scam without making one up. Five
 * follow-ups keeps a scenario to six messages a side; the live engine caps takeovers at six too.
 * All links, numbers and handles are fictional (.example/.test domains, 555-01xx numbers).
 */
export type DemoScript = { label: string; text: string; followups: string[] };

/** Everyday texts: Talon should let these straight through. */
export const NORMAL_STARTERS: DemoScript[] = [
  {
    label: 'Normal text',
    text: 'hey! are we still on for dinner sunday?',
    followups: [
      'awesome, should I bring dessert?',
      "ok I'll grab a pie from that bakery you like",
      'what time works, 6 or 7?',
      'perfect, see you sunday!',
    ],
  },
];

/** Fictional scams, each escalating the way real ones do: link, another link, app or email, phone, gift cards. */
export const SCAM_STARTERS: DemoScript[] = [
  {
    label: 'Toll',
    text: 'E-ZPass: You have an unpaid toll balance of $6.85. Pay today to avoid a $50 late fee: ezpass-tollpay.example/pay',
    followups: [
      'Just open the link and enter your card details to pay the balance today.',
      "If the link isn't loading try ezpass-billing.test/secure instead",
      'You can also pay with Cash App $TollDeskPay or Zelle to tolls-dept@payhelp.example',
      'Or call our billing office at (469) 555-0182 to pay by phone',
      'Fine, buy a $100 Apple gift card and text me the code on the back',
    ],
  },
  {
    label: 'Package',
    text: 'USPS: Your package is on hold due to an incomplete address. Update within 24 hours: usps-redelivery.example/track',
    followups: [
      'Your package will go back to the sender unless you update the address and pay the $1.99 redelivery fee.',
      'Use usps-redelivery.example/track and enter your card to pay the fee',
      "If that page won't load, send the fee by Venmo to @USPS-Redeliver",
      'Our support line is (213) 555-0147 if you need help',
      'You can also buy a $50 Google Play card and send me the code',
    ],
  },
  {
    label: 'Bank',
    text: 'Chase Fraud Alert: Did you attempt a $1,249.00 purchase at BestBuy? Reply YES or NO. If NO call 1-888-555-0142 now.',
    followups: [
      "This is the Chase fraud team. To block the charge we need to verify you. What's your online banking username?",
      "We just texted you a code. Read it back to us so we can cancel the purchase.",
      'To protect your money, Zelle your balance to our secure account at secure-desk@chase-protect.example',
      'If you prefer, call our fraud line at (888) 555-0142 right away',
      "If Zelle isn't working, buy $500 in Target gift cards and send us the codes",
    ],
  },
  {
    label: 'Carrier',
    text: 'T-Mobile: Your account is eligible for a $200 loyalty credit. Claim before midnight: tmo-rewards.example/claim',
    followups: [
      'Congrats! To claim the credit just confirm the account PIN on file.',
      'Log in at tmo-rewards.example/claim with your T-Mobile password to finish',
      'There is a $4.99 processing fee. Pay it with Cash App $TmoRewardsDesk',
      'Questions? Text our rewards desk at (972) 555-0119',
      'The offer ends tonight. A $25 gift card works for the fee too',
    ],
  },
];
