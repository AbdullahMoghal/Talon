import { schema, table, t, SenderError, type InferSchema, type ReducerCtx } from 'spacetimedb/server';

// ---------------------------------------------------------------------------
// Tables
//
// Reference data (scam taxonomy) and the labeled message dataset described in
// docs/TAXONOMY.md and docs/DATA_SPEC.md. Runtime tables from
// docs/ARCHITECTURE.md (canary, conversation, turn, campaign, ...) come next.
// ---------------------------------------------------------------------------

// Identities allowed to import data. The publisher is added in `init`.
const admin = table(
  { name: 'admin' },
  {
    identity: t.identity().primaryKey(),
  }
);

const taxonomyMeta = table(
  { name: 'taxonomy_meta', public: true },
  {
    key: t.string().primaryKey(),
    value: t.string(),
  }
);

const scamCategory = table(
  { name: 'scam_category', public: true },
  {
    id: t.string().primaryKey(),
    name: t.string(),
    description: t.string(),
    weight: t.f64(),
    harm: t.array(t.string()),
    brands: t.array(t.string()),
    hooks: t.array(t.string()),
    asks: t.array(t.string()),
    indicatorTypes: t.array(t.string()),
    targets: t.string(),
    seasonality: t.array(t.string()),
    decoyTactics: t.array(t.string()),
    nextSteps: t.array(t.string()),
  }
);

const legitSubtype = table(
  { name: 'legit_subtype', public: true },
  {
    id: t.string().primaryKey(),
    name: t.string(),
    hardNegativeFor: t.array(t.string()),
  }
);

const decoyTactic = table(
  { name: 'decoy_tactic', public: true },
  {
    id: t.string().primaryKey(),
    description: t.string(),
  }
);

const datasetMessage = table(
  { name: 'dataset_message', public: true },
  {
    id: t.string().primaryKey(),
    text: t.string(),
    label: t.string().index('btree'),
    category: t.option(t.string()),
    legitSubtype: t.option(t.string()),
    campaignId: t.option(t.string()),
    sender: t.string(),
    senderType: t.string(),
    brand: t.option(t.string()),
    hook: t.option(t.string()),
    tactics: t.array(t.string()),
    difficulty: t.string(),
    ageBand: t.string(),
    state: t.string(),
    season: t.option(t.string()),
    generator: t.string(),
    split: t.string().index('btree'),
  }
);

const datasetIndicator = table(
  { name: 'dataset_indicator', public: true },
  {
    id: t.u64().primaryKey().autoInc(),
    messageId: t.string().index('btree'),
    kind: t.string(),
    value: t.string(),
  }
);

// ---------------------------------------------------------------------------
// Runtime tables ("Let Talon handle it", docs/PIVOT.md)
//
// A customer receives a scam, taps "Let Talon handle it", and a takeover
// session starts. Canary numbers are a second source of sessions. Ids that
// other rows point at are strings chosen by the caller (reducers can't return
// values over HTTP); append-only logs use auto-increment ids.
// ---------------------------------------------------------------------------

// Synthetic identities Talon speaks as. Never a real customer's details.
const persona = table(
  { name: 'persona', public: true },
  {
    id: t.string().primaryKey(),
    name: t.string(),
    age: t.u32(),
    city: t.string(),
    state: t.string(),
    backstory: t.string(),
    quirks: t.array(t.string()),
    source: t.string(),
  }
);

// Demo customers (fictional). Production would hold a hashed reference only.
const customer = table(
  { name: 'customer', public: true },
  {
    id: t.string().primaryKey(),
    displayName: t.string(),
    phone: t.string(),
    city: t.string(),
    state: t.string(),
    // Where the customer is, for mapping where scams land. Appended columns
    // need defaults so existing rows migrate.
    lat: t.option(t.f64()).default(undefined),
    lng: t.option(t.f64()).default(undefined),
  }
);

// Decoy numbers: the second source of sessions.
const canary = table(
  { name: 'canary', public: true },
  {
    id: t.string().primaryKey(),
    number: t.string(),
    personaId: t.string(),
    plantingSource: t.string(),
    status: t.string(),
    createdAt: t.timestamp(),
  }
);

// A message arriving on a customer's phone. status:
// delivered -> warned (triaged as scam) -> taken_over | blocked | dismissed
const inboundMessage = table(
  { name: 'inbound_message', public: true },
  {
    id: t.string().primaryKey(),
    customerId: t.string().index('btree'),
    sender: t.string(),
    channel: t.string(),
    text: t.string(),
    receivedAt: t.timestamp(),
    status: t.string(),
    triageLabel: t.option(t.string()),
    category: t.option(t.string()),
    confidence: t.option(t.f64()),
    reason: t.option(t.string()),
    campaignId: t.option(t.string()),
    sessionId: t.option(t.string()),
    // Estimated origin of the scam text, for the map. origin_source says how it
    // was estimated: area_code (spoofable, so low confidence), network (carrier
    // signals such as STIR/SHAKEN origin), text (places named in the message)
    // or reported. Set with set_message_origin.
    originCity: t.option(t.string()).default(undefined),
    originState: t.option(t.string()).default(undefined),
    originCountry: t.option(t.string()).default(undefined),
    originLat: t.option(t.f64()).default(undefined),
    originLng: t.option(t.f64()).default(undefined),
    originSource: t.option(t.string()).default(undefined),
    originConfidence: t.option(t.f64()).default(undefined),
  }
);

// One conversation Talon runs with a scammer. source: takeover | canary.
// status: active -> stopped (customer tapped stop) | completed
const session = table(
  { name: 'session', public: true },
  {
    id: t.string().primaryKey(),
    source: t.string(),
    customerId: t.option(t.string()),
    canaryId: t.option(t.string()),
    inboundMessageId: t.option(t.string()),
    personaId: t.option(t.string()),
    scammerNumber: t.string(),
    channel: t.string(),
    status: t.string(),
    category: t.option(t.string()),
    campaignId: t.option(t.string()),
    startedAt: t.timestamp(),
    endedAt: t.option(t.timestamp()),
    turnCount: t.u32(),
    isBotSuspected: t.bool(),
    runId: t.option(t.string()),
    // Estimated scammer origin (same meaning as on inbound_message). Copied from
    // the message on takeover; set with set_session_origin for canary sessions.
    originCity: t.option(t.string()).default(undefined),
    originState: t.option(t.string()).default(undefined),
    originCountry: t.option(t.string()).default(undefined),
    originLat: t.option(t.f64()).default(undefined),
    originLng: t.option(t.f64()).default(undefined),
    originSource: t.option(t.string()).default(undefined),
    originConfidence: t.option(t.f64()).default(undefined),
  }
);

const turn = table(
  { name: 'turn', public: true },
  {
    id: t.string().primaryKey(),
    sessionId: t.string().index('btree'),
    sender: t.string(), // scammer | talon
    text: t.string(),
    triageLabel: t.option(t.string()),
    confidence: t.option(t.f64()),
    safetyPassed: t.bool(),
    ts: t.timestamp(),
  }
);

// The handler's reasoning before each reply, shown live on the dashboard.
const handlerPlan = table(
  { name: 'handler_plan', public: true },
  {
    id: t.u64().primaryKey().autoInc(),
    sessionId: t.string().index('btree'),
    turnId: t.option(t.string()),
    have: t.array(t.string()),
    need: t.string(),
    tactic: t.string(),
    note: t.string(),
    ts: t.timestamp(),
  }
);

const indicator = table(
  { name: 'indicator', public: true },
  {
    id: t.u64().primaryKey().autoInc(),
    sessionId: t.string().index('btree'),
    sourceTurnId: t.string(),
    kind: t.string(),
    value: t.string(),
    confidence: t.f64(),
    createdAt: t.timestamp(),
  }
);

// status: active -> burned
const campaign = table(
  { name: 'campaign', public: true },
  {
    id: t.string().primaryKey(),
    category: t.string(),
    label: t.string(),
    brand: t.option(t.string()),
    firstSeen: t.timestamp(),
    burnedAt: t.option(t.timestamp()),
    timeToBurnS: t.option(t.f64()),
    status: t.string(),
    customersHit: t.u32(),
  }
);

const insight = table(
  { name: 'insight', public: true },
  {
    id: t.string().primaryKey(),
    campaignId: t.string().index('btree'),
    kind: t.string(), // summary | new_pattern | customer_warning
    text: t.string(),
    citedIndicatorIds: t.array(t.u64()),
    confidence: t.f64(),
    createdAt: t.timestamp(),
  }
);

const tripwire = table(
  { name: 'tripwire', public: true },
  {
    id: t.string().primaryKey(),
    campaignId: t.string(),
    sessionId: t.string(),
    kind: t.string(), // giftcard | wallet | account
    token: t.string().unique(),
    issuedAt: t.timestamp(),
    hitAt: t.option(t.timestamp()),
    hitDetails: t.option(t.string()),
  }
);

const probeResult = table(
  { name: 'probe_result', public: true },
  {
    id: t.u64().primaryKey().autoInc(),
    sessionId: t.string(),
    revealedPrompt: t.option(t.string()),
    revealedPayment: t.option(t.string()),
    success: t.bool(),
    createdAt: t.timestamp(),
  }
);

// A warning or block shown to a customer because of a campaign.
const customerAlert = table(
  { name: 'customer_alert', public: true },
  {
    id: t.u64().primaryKey().autoInc(),
    campaignId: t.string(),
    customerId: t.string().index('btree'),
    inboundMessageId: t.option(t.string()),
    kind: t.string(), // warned | blocked
    text: t.string(),
    shownAt: t.timestamp(),
  }
);

// "You helped shut down a campaign that hit N customers."
const impactCard = table(
  { name: 'impact_card', public: true },
  {
    id: t.u64().primaryKey().autoInc(),
    sessionId: t.string(),
    customerId: t.string().index('btree'),
    campaignId: t.option(t.string()),
    customersProtected: t.u32(),
    summary: t.string(),
    createdAt: t.timestamp(),
  }
);

// Every write during a recorded run, for replaying the demo.
const recordedEvent = table(
  { name: 'recorded_event', public: true },
  {
    id: t.u64().primaryKey().autoInc(),
    runId: t.string().index('btree'),
    offsetMs: t.u64(),
    reducer: t.string(),
    argsJson: t.string(),
  }
);

// ---------------------------------------------------------------------------
// Live demo (docs/PLAN.md, "Live demo: three screens")
//
// A judge texts as the scammer from one phone, another judge is the customer on
// a second phone, and the laptop shows every agent step. Phones never talk to
// the engine directly: the scammer phone writes to scammer_message through the
// open scammer_send reducer, the engine (admin) picks it up and writes
// everything else.
// ---------------------------------------------------------------------------

// Pairs a scammer phone with a fictional customer. status: open | closed
const demoRoom = table(
  { name: 'demo_room', public: true },
  {
    code: t.string().primaryKey(),
    customerId: t.string(),
    scammerNumber: t.string(),
    status: t.string(),
    createdAt: t.timestamp(),
  }
);

// How many times each room was reset. reset_room bumps it and the engine starts fresh when it changes.
// Its own table rather than a demo_room column, so pages built before it existed keep working.
const roomReset = table(
  { name: 'room_reset', public: true },
  {
    code: t.string().primaryKey(),
    count: t.u32(),
  }
);

// Who has a demo phone open right now: one row per live connection, written by phone_opened and deleted
// when the connection drops (onDisconnect). The engine waits for a viewer on the second customer's phone
// before sending the scammer's follow-up, so the block happens while someone is watching.
const roomViewer = table(
  { name: 'room_viewer', public: true },
  {
    id: t.u64().primaryKey().autoInc(),
    roomCode: t.string().index('btree'),
    connection: t.connectionId(),
    joinedAt: t.timestamp(),
  }
);

// Texts typed on the scammer phone, waiting for the engine.
// status: queued -> processing -> done | error
const scammerMessage = table(
  { name: 'scammer_message', public: true },
  {
    id: t.u64().primaryKey().autoInc(),
    roomCode: t.string().index('btree'),
    text: t.string(),
    status: t.string(),
    error: t.option(t.string()),
    sentAt: t.timestamp(),
  }
);

// Texts the customer types back to the scammer (before or after a takeover).
const customerMessage = table(
  { name: 'customer_message', public: true },
  {
    id: t.u64().primaryKey().autoInc(),
    roomCode: t.string().index('btree'),
    text: t.string(),
    sentAt: t.timestamp(),
  }
);

// One step of an agent's work, for the live trace. sessionId is the takeover
// session, or the inbound message id for triage before a session exists.
// kind: thought | tool_call | tool_result | output | rejection | retrieval_skipped
// The catalog of scammer numbers and what each one tried. One row per number, kept across room resets:
// this is the long-lived record Talon builds as it detects and shuts down scams.
// status: active (seen, warned) | blocked (Talon blocked it for a customer) | shut_down (campaign burned)
const scamCatalog = table(
  { name: 'scam_catalog', public: true },
  {
    number: t.string().primaryKey(),
    firstSeen: t.timestamp(),
    lastSeen: t.timestamp(),
    attempts: t.u32(),
    categories: t.array(t.string()),
    brands: t.array(t.string()),
    customers: t.array(t.string()),
    sessions: t.array(t.string()),
    intel: t.array(t.string()), // "kind: value", e.g. "url: ezpass-tollpay.example/pay"
    status: t.string(),
    lastMessageId: t.option(t.string()),
  }
);

const agentStep = table(
  { name: 'agent_step', public: true },
  {
    id: t.u64().primaryKey().autoInc(),
    sessionId: t.string().index('btree'),
    turnId: t.option(t.string()),
    agent: t.string(),
    kind: t.string(),
    contentJson: t.string(),
    latencyMs: t.u32(),
    createdAt: t.timestamp(),
  }
);

// Permanent transcript of every conversation: scammer texts, Talon's replies, the customer's own texts,
// triage results and events (takeover, Stop, Delete/Report, blocks, impact cards). Append-only: neither
// reset_room (Reset session) nor reset_runtime deletes it, so past demo runs survive. Written by the
// reducers below, never by clients directly. round is the room's reset count when the row was written,
// so repeated runs in the same room can be told apart. sender: scammer | talon | customer | system.
// kind: message | triage | event.
const chatLog = table(
  { name: 'chat_log', public: true },
  {
    id: t.u64().primaryKey().autoInc(),
    roomCode: t.string().index('btree'),
    customerId: t.string().index('btree'),
    sessionId: t.option(t.string()),
    round: t.u32(),
    sender: t.string(),
    kind: t.string(),
    text: t.string(),
    detailJson: t.option(t.string()),
    createdAt: t.timestamp(),
  }
);

// Everything the live dashboard shows for one customer's conversation, saved just before Reset session
// (reset_room) or reset_runtime deletes it: messages with triage, sessions, turns, the agent trace,
// handler plans, scammer intel, campaigns with insights, tripwires, probe results, alerts, impact cards
// and both phones' texts. One row per room (or customer) per reset. Never deleted except by
// clear_session_archive (admin). snapshot_json holds the rows as JSON; u64 ids and timestamps are strings.
const sessionArchive = table(
  { name: 'session_archive', public: true },
  {
    id: t.u64().primaryKey().autoInc(),
    roomCode: t.string().index('btree'),
    customerId: t.string().index('btree'),
    round: t.u32(),
    reason: t.string(), // reset_room | reset_runtime
    sessionIds: t.array(t.string()),
    campaignIds: t.array(t.string()),
    messageCount: t.u32(),
    turnCount: t.u32(),
    agentStepCount: t.u32(),
    indicatorCount: t.u32(),
    snapshotJson: t.string(),
    archivedAt: t.timestamp(),
  }
);

const spacetimedb = schema({
  admin,
  taxonomyMeta,
  scamCategory,
  legitSubtype,
  decoyTactic,
  datasetMessage,
  datasetIndicator,
  persona,
  customer,
  canary,
  inboundMessage,
  session,
  turn,
  handlerPlan,
  indicator,
  campaign,
  insight,
  tripwire,
  probeResult,
  customerAlert,
  impactCard,
  recordedEvent,
  demoRoom,
  roomReset,
  roomViewer,
  scammerMessage,
  customerMessage,
  agentStep,
  scamCatalog,
  chatLog,
  sessionArchive,
});
export default spacetimedb;

type Ctx = ReducerCtx<InferSchema<typeof spacetimedb>>;

function requireAdmin(ctx: Ctx) {
  if (!ctx.db.admin.identity.find(ctx.sender)) {
    throw new SenderError('only an admin can do this');
  }
}

// ---- Chat log helpers -------------------------------------------------------

function roomForCustomer(ctx: Ctx, customerId: string | undefined): string {
  if (!customerId) return '';
  for (const r of ctx.db.demoRoom.iter()) if (r.customerId === customerId) return r.code;
  return '';
}

function logChat(
  ctx: Ctx,
  entry: {
    customerId?: string;
    roomCode?: string;
    sessionId?: string;
    sender: 'scammer' | 'talon' | 'customer' | 'system';
    kind: 'message' | 'triage' | 'event';
    text: string;
    detail?: Record<string, unknown>;
  }
) {
  const roomCode = entry.roomCode ?? roomForCustomer(ctx, entry.customerId);
  const round = roomCode ? (ctx.db.roomReset.code.find(roomCode)?.count ?? 0) : 0;
  ctx.db.chatLog.insert({
    id: 0n,
    roomCode,
    customerId: entry.customerId ?? '',
    sessionId: entry.sessionId,
    round,
    sender: entry.sender,
    kind: entry.kind,
    text: entry.text,
    detailJson: entry.detail ? JSON.stringify(entry.detail) : undefined,
    createdAt: ctx.timestamp,
  });
}

// ---- Dataset from live sessions ---------------------------------------------
// Every message Talon handles in a session joins the labeled dataset (split "live"), so the Overview page
// and future training data grow with each session. Like chat_log, resets never delete these rows.

function senderTypeOf(sender: string): string {
  if (sender.includes('@')) return 'email_gateway';
  const digits = sender.replace(/\D/g, '');
  if (digits.length <= 6) return 'short_code';
  if (/^1?8(00|33|44|55|66|77|88)/.test(digits)) return 'toll_free';
  return 'long_code';
}

function addToDataset(
  ctx: Ctx,
  m: { id: string; text: string; label: string; category?: string; campaignId?: string; sender: string; customerId?: string }
) {
  const label = m.label === 'scam' ? 'scam' : 'legit';
  const existing = ctx.db.datasetMessage.id.find(m.id);
  if (existing) {
    ctx.db.datasetMessage.id.update({ ...existing, label, category: label === 'scam' ? m.category : undefined,
      campaignId: m.campaignId ?? existing.campaignId });
    return;
  }
  const customer = m.customerId ? ctx.db.customer.id.find(m.customerId) : undefined;
  ctx.db.datasetMessage.insert({
    id: m.id,
    text: m.text,
    label,
    category: label === 'scam' ? m.category : undefined,
    legitSubtype: undefined,
    campaignId: m.campaignId,
    sender: m.sender,
    senderType: senderTypeOf(m.sender),
    brand: undefined,
    hook: undefined,
    tactics: [],
    difficulty: 'medium',
    ageBand: '',
    state: customer?.state ?? '',
    season: undefined,
    generator: 'talon-live',
    split: 'live',
  });
}

// ---- Session archive helpers ------------------------------------------------

// JSON.stringify can't handle bigint (u64 ids, timestamp micros); store those as strings.
function toJson(value: unknown): string {
  return JSON.stringify(value, (_key, v) => (typeof v === 'bigint' ? v.toString() : v));
}

// Save everything the dashboard shows for one customer (and their room's phone texts) before a reset
// deletes it. Writes nothing if there's nothing to save.
function archiveCustomer(ctx: Ctx, customerId: string, roomCode: string, reason: string) {
  const messages = [...ctx.db.inboundMessage.customerId.filter(customerId)];
  const sessions = [...ctx.db.session.iter()].filter(s => s.customerId === customerId);
  const sessionIds = new Set(sessions.map(s => s.id));
  const campaignIds = new Set<string>();
  for (const s of sessions) if (s.campaignId) campaignIds.add(s.campaignId);
  for (const m of messages) if (m.campaignId) campaignIds.add(m.campaignId);

  const turns = sessions.flatMap(s => [...ctx.db.turn.sessionId.filter(s.id)]);
  // Agent steps are keyed by session, or by message id for triage before a session exists.
  const agentSteps = [
    ...messages.flatMap(m => [...ctx.db.agentStep.sessionId.filter(m.id)]),
    ...sessions.flatMap(s => [...ctx.db.agentStep.sessionId.filter(s.id)]),
  ];
  const handlerPlans = sessions.flatMap(s => [...ctx.db.handlerPlan.sessionId.filter(s.id)]);
  const indicators = sessions.flatMap(s => [...ctx.db.indicator.sessionId.filter(s.id)]);
  const campaigns = [...campaignIds].map(id => ctx.db.campaign.id.find(id)).filter(c => c != null);
  const insights = [...campaignIds].flatMap(id => [...ctx.db.insight.campaignId.filter(id)]);
  const tripwires = [...ctx.db.tripwire.iter()].filter(r => sessionIds.has(r.sessionId));
  const probeResults = [...ctx.db.probeResult.iter()].filter(r => sessionIds.has(r.sessionId));
  const customerAlerts = [...ctx.db.customerAlert.customerId.filter(customerId)];
  const impactCards = [...ctx.db.impactCard.customerId.filter(customerId)];
  const scammerTexts = roomCode ? [...ctx.db.scammerMessage.roomCode.filter(roomCode)] : [];
  const customerTexts = roomCode ? [...ctx.db.customerMessage.roomCode.filter(roomCode)] : [];

  if (!messages.length && !sessions.length && !scammerTexts.length && !customerTexts.length) return;

  const round = roomCode ? (ctx.db.roomReset.code.find(roomCode)?.count ?? 0) : 0;
  ctx.db.sessionArchive.insert({
    id: 0n,
    roomCode,
    customerId,
    round,
    reason,
    sessionIds: [...sessionIds],
    campaignIds: [...campaignIds],
    messageCount: messages.length,
    turnCount: turns.length,
    agentStepCount: agentSteps.length,
    indicatorCount: indicators.length,
    snapshotJson: toJson({
      customer: ctx.db.customer.id.find(customerId) ?? null,
      inbound_messages: messages,
      sessions,
      turns,
      agent_steps: agentSteps,
      handler_plans: handlerPlans,
      indicators,
      campaigns,
      insights,
      tripwires,
      probe_results: probeResults,
      customer_alerts: customerAlerts,
      impact_cards: impactCards,
      scammer_texts: scammerTexts,
      customer_texts: customerTexts,
    }),
    archivedAt: ctx.timestamp,
  });
}

// ---------------------------------------------------------------------------
// Reducer argument types
// ---------------------------------------------------------------------------

const CategoryInput = t.object('CategoryInput', {
  id: t.string(),
  name: t.string(),
  description: t.string(),
  weight: t.f64(),
  harm: t.array(t.string()),
  brands: t.array(t.string()),
  hooks: t.array(t.string()),
  asks: t.array(t.string()),
  indicatorTypes: t.array(t.string()),
  targets: t.string(),
  seasonality: t.array(t.string()),
  decoyTactics: t.array(t.string()),
  nextSteps: t.array(t.string()),
});

const SubtypeInput = t.object('SubtypeInput', {
  id: t.string(),
  name: t.string(),
  hardNegativeFor: t.array(t.string()),
});

const TacticInput = t.object('TacticInput', {
  id: t.string(),
  description: t.string(),
});

const IndicatorInput = t.object('IndicatorInput', {
  kind: t.string(),
  value: t.string(),
});

const MessageInput = t.object('MessageInput', {
  id: t.string(),
  text: t.string(),
  label: t.string(),
  category: t.option(t.string()),
  legitSubtype: t.option(t.string()),
  campaignId: t.option(t.string()),
  sender: t.string(),
  senderType: t.string(),
  brand: t.option(t.string()),
  hook: t.option(t.string()),
  tactics: t.array(t.string()),
  difficulty: t.string(),
  ageBand: t.string(),
  state: t.string(),
  season: t.option(t.string()),
  generator: t.string(),
  split: t.string(),
  indicators: t.array(IndicatorInput),
});

// ---------------------------------------------------------------------------
// Lifecycle
// ---------------------------------------------------------------------------

export const init = spacetimedb.init(ctx => {
  // The identity that publishes the module may import data.
  ctx.db.admin.insert({ identity: ctx.sender });
});

// `init` only runs when a database is first created. When the module is
// published over an existing database, the first caller claims admin.
export const claimAdmin = spacetimedb.reducer(ctx => {
  if ([...ctx.db.admin.iter()].length > 0) {
    throw new SenderError('admin already set');
  }
  ctx.db.admin.insert({ identity: ctx.sender });
});

export const addAdmin = spacetimedb.reducer(
  { identity: t.identity() },
  (ctx, { identity }) => {
    if (!ctx.db.admin.identity.find(ctx.sender)) {
      throw new SenderError('only an admin can add admins');
    }
    if (!ctx.db.admin.identity.find(identity)) ctx.db.admin.insert({ identity });
  }
);

export const onConnect = spacetimedb.clientConnected(_ctx => {});

export const onDisconnect = spacetimedb.clientDisconnected(ctx => {
  // A closed phone is no longer watching its room.
  const conn = ctx.connectionId;
  if (!conn) return;
  for (const v of [...ctx.db.roomViewer.iter()]) {
    if (v.connection.isEqual(conn)) ctx.db.roomViewer.id.delete(v.id);
  }
});

// ---------------------------------------------------------------------------
// Import reducers (admin only, idempotent)
// ---------------------------------------------------------------------------

export const importTaxonomy = spacetimedb.reducer(
  {
    version: t.string(),
    updated: t.string(),
    sharedNextSteps: t.array(t.string()),
    categories: t.array(CategoryInput),
    subtypes: t.array(SubtypeInput),
    tactics: t.array(TacticInput),
  },
  (ctx, { version, updated, sharedNextSteps, categories, subtypes, tactics }) => {
    if (!ctx.db.admin.identity.find(ctx.sender)) {
      throw new SenderError('only an admin can import data');
    }

    for (const row of [...ctx.db.scamCategory.iter()]) ctx.db.scamCategory.id.delete(row.id);
    for (const row of [...ctx.db.legitSubtype.iter()]) ctx.db.legitSubtype.id.delete(row.id);
    for (const row of [...ctx.db.decoyTactic.iter()]) ctx.db.decoyTactic.id.delete(row.id);
    for (const row of [...ctx.db.taxonomyMeta.iter()]) ctx.db.taxonomyMeta.key.delete(row.key);

    for (const c of categories) ctx.db.scamCategory.insert(c);
    for (const s of subtypes) ctx.db.legitSubtype.insert(s);
    for (const tac of tactics) ctx.db.decoyTactic.insert(tac);

    ctx.db.taxonomyMeta.insert({ key: 'version', value: version });
    ctx.db.taxonomyMeta.insert({ key: 'updated', value: updated });
    ctx.db.taxonomyMeta.insert({ key: 'shared_next_steps', value: JSON.stringify(sharedNextSteps) });
  }
);

export const importMessages = spacetimedb.reducer(
  { messages: t.array(MessageInput) },
  (ctx, { messages }) => {
    if (!ctx.db.admin.identity.find(ctx.sender)) {
      throw new SenderError('only an admin can import data');
    }

    for (const m of messages) {
      // Replace any earlier copy of this message and its indicators.
      if (ctx.db.datasetMessage.id.find(m.id)) ctx.db.datasetMessage.id.delete(m.id);
      for (const old of [...ctx.db.datasetIndicator.messageId.filter(m.id)]) {
        ctx.db.datasetIndicator.id.delete(old.id);
      }

      const { indicators, ...row } = m;
      ctx.db.datasetMessage.insert(row);
      for (const ind of indicators) {
        ctx.db.datasetIndicator.insert({ id: 0n, messageId: m.id, kind: ind.kind, value: ind.value });
      }
    }
  }
);

export const clearDataset = spacetimedb.reducer(
  { split: t.string() },
  (ctx, { split }) => {
    if (!ctx.db.admin.identity.find(ctx.sender)) {
      throw new SenderError('only an admin can clear data');
    }
    for (const m of [...ctx.db.datasetMessage.split.filter(split)]) {
      for (const ind of [...ctx.db.datasetIndicator.messageId.filter(m.id)]) {
        ctx.db.datasetIndicator.id.delete(ind.id);
      }
      ctx.db.datasetMessage.id.delete(m.id);
    }
  }
);

// ---------------------------------------------------------------------------
// Runtime reducers
//
// Pipeline writes are admin-only (the pipeline runs with an admin identity).
// The customer's two taps, request_takeover and stop_takeover, are open so the
// phone app can call them.
// ---------------------------------------------------------------------------

const PersonaInput = t.object('PersonaInput', {
  id: t.string(),
  name: t.string(),
  age: t.u32(),
  city: t.string(),
  state: t.string(),
  backstory: t.string(),
  quirks: t.array(t.string()),
  source: t.string(),
});

const CustomerInput = t.object('CustomerInput', {
  id: t.string(),
  displayName: t.string(),
  phone: t.string(),
  city: t.string(),
  state: t.string(),
  lat: t.option(t.f64()),
  lng: t.option(t.f64()),
});

// Estimated origin of a scam text or scammer. Approximate on purpose (city or
// region), never a precise address.
const OriginInput = t.object('OriginInput', {
  city: t.option(t.string()),
  state: t.option(t.string()),
  country: t.option(t.string()),
  lat: t.f64(),
  lng: t.f64(),
  source: t.string(), // area_code | network | text | reported
  confidence: t.f64(),
});

export const upsertPersona = spacetimedb.reducer({ persona: PersonaInput }, (ctx, { persona: p }) => {
  requireAdmin(ctx);
  if (ctx.db.persona.id.find(p.id)) ctx.db.persona.id.update(p);
  else ctx.db.persona.insert(p);
});

export const upsertCustomer = spacetimedb.reducer({ customer: CustomerInput }, (ctx, { customer: c }) => {
  requireAdmin(ctx);
  if (ctx.db.customer.id.find(c.id)) ctx.db.customer.id.update(c);
  else ctx.db.customer.insert(c);
});

export const registerCanary = spacetimedb.reducer(
  { id: t.string(), number: t.string(), personaId: t.string(), plantingSource: t.string() },
  (ctx, { id, number, personaId, plantingSource }) => {
    requireAdmin(ctx);
    if (!ctx.db.persona.id.find(personaId)) throw new SenderError(`unknown persona ${personaId}`);
    ctx.db.canary.insert({ id, number, personaId, plantingSource, status: 'active', createdAt: ctx.timestamp });
  }
);

// A scam (or legit) message lands on a customer's phone.
export const receiveMessage = spacetimedb.reducer(
  { id: t.string(), customerId: t.string(), sender: t.string(), channel: t.string(), text: t.string() },
  (ctx, { id, customerId, sender, channel, text }) => {
    requireAdmin(ctx);
    if (!ctx.db.customer.id.find(customerId)) throw new SenderError(`unknown customer ${customerId}`);
    ctx.db.inboundMessage.insert({
      id, customerId, sender, channel, text,
      receivedAt: ctx.timestamp,
      status: 'delivered',
      triageLabel: undefined, category: undefined, confidence: undefined, reason: undefined,
      campaignId: undefined, sessionId: undefined,
      originCity: undefined, originState: undefined, originCountry: undefined, originLat: undefined, originLng: undefined, originSource: undefined, originConfidence: undefined,
    });
    logChat(ctx, { customerId, sender: 'scammer', kind: 'message', text, detail: { message_id: id, from: sender, channel } });
  }
);

// Triage result for an inbound message. A scam shows the warning and buttons.
export const setTriage = spacetimedb.reducer(
  { messageId: t.string(), label: t.string(), category: t.option(t.string()), confidence: t.f64(), reason: t.string() },
  (ctx, { messageId, label, category, confidence, reason }) => {
    requireAdmin(ctx);
    const msg = ctx.db.inboundMessage.id.find(messageId);
    if (!msg) throw new SenderError(`unknown message ${messageId}`);
    const status = label === 'scam' && msg.status === 'delivered' ? 'warned' : msg.status;
    ctx.db.inboundMessage.id.update({ ...msg, triageLabel: label, category, confidence, reason, status });
    addToDataset(ctx, { id: messageId, text: msg.text, label, category, campaignId: msg.campaignId, sender: msg.sender,
      customerId: msg.customerId });
    logChat(ctx, {
      customerId: msg.customerId, sender: 'system', kind: 'triage',
      text: `${label}${category ? ` · ${category}` : ''} · ${Math.round(confidence * 100)}%: ${reason}`,
      detail: { message_id: messageId, label, category: category ?? null, confidence, reason },
    });
  }
);

// Customer taps "Let Talon handle it".
export const requestTakeover = spacetimedb.reducer(
  { messageId: t.string(), sessionId: t.string() },
  (ctx, { messageId, sessionId }) => {
    const msg = ctx.db.inboundMessage.id.find(messageId);
    if (!msg) throw new SenderError(`unknown message ${messageId}`);
    if (msg.sessionId) throw new SenderError('Talon is already handling this message');
    if (msg.status === 'blocked') throw new SenderError('message was already blocked');
    ctx.db.session.insert({
      id: sessionId,
      source: 'takeover',
      customerId: msg.customerId,
      canaryId: undefined,
      inboundMessageId: msg.id,
      personaId: undefined,
      scammerNumber: msg.sender,
      channel: msg.channel,
      status: 'active',
      category: msg.category,
      campaignId: msg.campaignId,
      startedAt: ctx.timestamp,
      endedAt: undefined,
      turnCount: 0,
      isBotSuspected: false,
      runId: undefined,
      originCity: msg.originCity,
      originState: msg.originState,
      originCountry: msg.originCountry,
      originLat: msg.originLat,
      originLng: msg.originLng,
      originSource: msg.originSource,
      originConfidence: msg.originConfidence,
    });
    ctx.db.inboundMessage.id.update({ ...msg, status: 'taken_over', sessionId });
    logChat(ctx, { customerId: msg.customerId, sessionId, sender: 'system', kind: 'event',
      text: 'Customer tapped Let Talon handle it', detail: { message_id: messageId } });
  }
);

function originFields(o: { city?: string; state?: string; country?: string; lat: number; lng: number; source: string; confidence: number }) {
  if (o.lat < -90 || o.lat > 90 || o.lng < -180 || o.lng > 180) throw new SenderError('lat/lng out of range');
  if (o.confidence < 0 || o.confidence > 1) throw new SenderError('confidence must be between 0 and 1');
  return {
    originCity: o.city, originState: o.state, originCountry: o.country,
    originLat: o.lat, originLng: o.lng, originSource: o.source, originConfidence: o.confidence,
  };
}

// Set the estimated origin of a scam text, for the map. Also updates the
// takeover session that came from it, if any.
export const setMessageOrigin = spacetimedb.reducer(
  { messageId: t.string(), origin: OriginInput },
  (ctx, { messageId, origin }) => {
    requireAdmin(ctx);
    const msg = ctx.db.inboundMessage.id.find(messageId);
    if (!msg) throw new SenderError(`unknown message ${messageId}`);
    const fields = originFields(origin);
    ctx.db.inboundMessage.id.update({ ...msg, ...fields });
    if (msg.sessionId) {
      const s = ctx.db.session.id.find(msg.sessionId);
      if (s) ctx.db.session.id.update({ ...s, ...fields });
    }
  }
);

// Set the estimated scammer origin on a session (canary sessions have no message).
export const setSessionOrigin = spacetimedb.reducer(
  { sessionId: t.string(), origin: OriginInput },
  (ctx, { sessionId, origin }) => {
    requireAdmin(ctx);
    const s = ctx.db.session.id.find(sessionId);
    if (!s) throw new SenderError(`unknown session ${sessionId}`);
    ctx.db.session.id.update({ ...s, ...originFields(origin) });
  }
);

// Customer taps stop. Talon sends nothing more in this session.
export const stopTakeover = spacetimedb.reducer({ sessionId: t.string() }, (ctx, { sessionId }) => {
  const s = ctx.db.session.id.find(sessionId);
  if (!s) throw new SenderError(`unknown session ${sessionId}`);
  if (s.status === 'active') {
    ctx.db.session.id.update({ ...s, status: 'stopped', endedAt: ctx.timestamp });
    logChat(ctx, { customerId: s.customerId, sessionId, sender: 'system', kind: 'event', text: 'Talon stopped (customer tapped Stop or the takeover ended)' });
  }
});

export const startCanarySession = spacetimedb.reducer(
  { sessionId: t.string(), canaryId: t.string(), scammerNumber: t.string(), channel: t.string() },
  (ctx, { sessionId, canaryId, scammerNumber, channel }) => {
    requireAdmin(ctx);
    const c = ctx.db.canary.id.find(canaryId);
    if (!c) throw new SenderError(`unknown canary ${canaryId}`);
    ctx.db.session.insert({
      id: sessionId, source: 'canary', customerId: undefined, canaryId, inboundMessageId: undefined,
      personaId: c.personaId, scammerNumber, channel, status: 'active', category: undefined,
      campaignId: undefined, startedAt: ctx.timestamp, endedAt: undefined, turnCount: 0,
      isBotSuspected: false, runId: undefined,
      originCity: undefined, originState: undefined, originCountry: undefined, originLat: undefined, originLng: undefined, originSource: undefined, originConfidence: undefined,
    });
  }
);

export const assignPersona = spacetimedb.reducer(
  { sessionId: t.string(), personaId: t.string() },
  (ctx, { sessionId, personaId }) => {
    requireAdmin(ctx);
    const s = ctx.db.session.id.find(sessionId);
    if (!s) throw new SenderError(`unknown session ${sessionId}`);
    if (!ctx.db.persona.id.find(personaId)) throw new SenderError(`unknown persona ${personaId}`);
    ctx.db.session.id.update({ ...s, personaId });
  }
);

export const addTurn = spacetimedb.reducer(
  {
    id: t.string(), sessionId: t.string(), sender: t.string(), text: t.string(),
    triageLabel: t.option(t.string()), confidence: t.option(t.f64()), safetyPassed: t.bool(),
  },
  (ctx, { id, sessionId, sender, text, triageLabel, confidence, safetyPassed }) => {
    requireAdmin(ctx);
    const s = ctx.db.session.id.find(sessionId);
    if (!s) throw new SenderError(`unknown session ${sessionId}`);
    if (sender === 'talon') {
      if (s.status !== 'active') throw new SenderError(`session is ${s.status}; Talon can't reply`);
      if (!safetyPassed) throw new SenderError('reply did not pass the safety guard');
    }
    ctx.db.turn.insert({ id, sessionId, sender, text, triageLabel, confidence, safetyPassed, ts: ctx.timestamp });
    ctx.db.session.id.update({ ...s, turnCount: s.turnCount + 1 });
    // The engine replays the handed-over scam text as the session's first scammer turn; it's already logged.
    const inbound = s.inboundMessageId ? ctx.db.inboundMessage.id.find(s.inboundMessageId) : undefined;
    const isReplay = sender === 'scammer' && s.turnCount === 0 && inbound?.text === text;
    if (!isReplay) {
      logChat(ctx, { customerId: s.customerId, sessionId, sender: sender === 'talon' ? 'talon' : 'scammer',
        kind: 'message', text, detail: { turn_id: id } });
      if (sender === 'scammer') {
        addToDataset(ctx, { id, text, label: 'scam', category: s.category, campaignId: s.campaignId,
          sender: s.scammerNumber, customerId: s.customerId });
      }
    }
  }
);

export const addHandlerPlan = spacetimedb.reducer(
  { sessionId: t.string(), turnId: t.option(t.string()), have: t.array(t.string()), need: t.string(), tactic: t.string(), note: t.string() },
  (ctx, { sessionId, turnId, have, need, tactic, note }) => {
    requireAdmin(ctx);
    ctx.db.handlerPlan.insert({ id: 0n, sessionId, turnId, have, need, tactic, note, ts: ctx.timestamp });
  }
);

export const addIndicator = spacetimedb.reducer(
  { sessionId: t.string(), sourceTurnId: t.string(), kind: t.string(), value: t.string(), confidence: t.f64() },
  (ctx, { sessionId, sourceTurnId, kind, value, confidence }) => {
    requireAdmin(ctx);
    const srcTurn = ctx.db.turn.id.find(sourceTurnId);
    if (!srcTurn) throw new SenderError(`unknown turn ${sourceTurnId}`);
    ctx.db.indicator.insert({ id: 0n, sessionId, sourceTurnId, kind, value, confidence, createdAt: ctx.timestamp });
    // Label the dataset row this came from: the turn itself, or the handed-over message the turn replays.
    let messageId: string | undefined = ctx.db.datasetMessage.id.find(sourceTurnId) ? sourceTurnId : undefined;
    if (!messageId) {
      const sess = ctx.db.session.id.find(sessionId);
      const inbound = sess?.inboundMessageId ? ctx.db.inboundMessage.id.find(sess.inboundMessageId) : undefined;
      if (inbound && inbound.text === srcTurn.text && ctx.db.datasetMessage.id.find(inbound.id)) messageId = inbound.id;
    }
    if (messageId && ![...ctx.db.datasetIndicator.messageId.filter(messageId)].some(d => d.kind === kind && d.value === value)) {
      ctx.db.datasetIndicator.insert({ id: 0n, messageId, kind, value });
    }
  }
);

export const flagBotSuspected = spacetimedb.reducer({ sessionId: t.string() }, (ctx, { sessionId }) => {
  requireAdmin(ctx);
  const s = ctx.db.session.id.find(sessionId);
  if (!s) throw new SenderError(`unknown session ${sessionId}`);
  ctx.db.session.id.update({ ...s, isBotSuspected: true });
});

export const addProbeResult = spacetimedb.reducer(
  { sessionId: t.string(), revealedPrompt: t.option(t.string()), revealedPayment: t.option(t.string()), success: t.bool() },
  (ctx, { sessionId, revealedPrompt, revealedPayment, success }) => {
    requireAdmin(ctx);
    ctx.db.probeResult.insert({ id: 0n, sessionId, revealedPrompt, revealedPayment, success, createdAt: ctx.timestamp });
  }
);

export const upsertCampaign = spacetimedb.reducer(
  { id: t.string(), category: t.string(), label: t.string(), brand: t.option(t.string()), customersHit: t.u32() },
  (ctx, { id, category, label, brand, customersHit }) => {
    requireAdmin(ctx);
    const existing = ctx.db.campaign.id.find(id);
    if (existing) ctx.db.campaign.id.update({ ...existing, category, label, brand, customersHit });
    else ctx.db.campaign.insert({
      id, category, label, brand, customersHit,
      firstSeen: ctx.timestamp, burnedAt: undefined, timeToBurnS: undefined, status: 'active',
    });
  }
);

// Attach a session, and the message it came from, to a campaign.
export const linkSession = spacetimedb.reducer(
  { sessionId: t.string(), campaignId: t.string() },
  (ctx, { sessionId, campaignId }) => {
    requireAdmin(ctx);
    const s = ctx.db.session.id.find(sessionId);
    if (!s) throw new SenderError(`unknown session ${sessionId}`);
    if (!ctx.db.campaign.id.find(campaignId)) throw new SenderError(`unknown campaign ${campaignId}`);
    ctx.db.session.id.update({ ...s, campaignId });
    if (s.inboundMessageId) {
      const msg = ctx.db.inboundMessage.id.find(s.inboundMessageId);
      if (msg) ctx.db.inboundMessage.id.update({ ...msg, campaignId });
    }
  }
);

export const burnCampaign = spacetimedb.reducer({ campaignId: t.string() }, (ctx, { campaignId }) => {
  requireAdmin(ctx);
  const c = ctx.db.campaign.id.find(campaignId);
  if (!c) throw new SenderError(`unknown campaign ${campaignId}`);
  if (c.status === 'burned') return;
  const micros = ctx.timestamp.microsSinceUnixEpoch - c.firstSeen.microsSinceUnixEpoch;
  ctx.db.campaign.id.update({ ...c, status: 'burned', burnedAt: ctx.timestamp, timeToBurnS: Number(micros) / 1e6 });
});

export const issueTripwire = spacetimedb.reducer(
  { id: t.string(), campaignId: t.string(), sessionId: t.string(), kind: t.string(), token: t.string() },
  (ctx, { id, campaignId, sessionId, kind, token }) => {
    requireAdmin(ctx);
    ctx.db.tripwire.insert({ id, campaignId, sessionId, kind, token, issuedAt: ctx.timestamp, hitAt: undefined, hitDetails: undefined });
  }
);

export const hitTripwire = spacetimedb.reducer(
  { token: t.string(), hitDetails: t.string() },
  (ctx, { token, hitDetails }) => {
    requireAdmin(ctx);
    const tw = ctx.db.tripwire.token.find(token);
    if (!tw) throw new SenderError('unknown tripwire token');
    ctx.db.tripwire.id.update({ ...tw, hitAt: ctx.timestamp, hitDetails });
  }
);

// Warn or block a customer's message because of a campaign.
export const addCustomerAlert = spacetimedb.reducer(
  { campaignId: t.string(), customerId: t.string(), inboundMessageId: t.option(t.string()), kind: t.string(), text: t.string() },
  (ctx, { campaignId, customerId, inboundMessageId, kind, text }) => {
    requireAdmin(ctx);
    ctx.db.customerAlert.insert({ id: 0n, campaignId, customerId, inboundMessageId, kind, text, shownAt: ctx.timestamp });
    logChat(ctx, { customerId, sender: 'system', kind: 'event', text,
      detail: { alert: kind, campaign_id: campaignId, message_id: inboundMessageId ?? null } });
    if (inboundMessageId) {
      const msg = ctx.db.inboundMessage.id.find(inboundMessageId);
      if (msg && !msg.sessionId) {
        ctx.db.inboundMessage.id.update({ ...msg, campaignId, status: kind === 'blocked' ? 'blocked' : 'warned' });
      }
      // A message blocked by a burned campaign is a confirmed scam even though it never went through triage.
      if (msg && kind === 'blocked') {
        addToDataset(ctx, { id: msg.id, text: msg.text, label: 'scam', category: ctx.db.campaign.id.find(campaignId)?.category,
          campaignId, sender: msg.sender, customerId: msg.customerId });
      }
    }
  }
);

// End a takeover with the customer's impact card.
export const addImpactCard = spacetimedb.reducer(
  { sessionId: t.string(), campaignId: t.option(t.string()), customersProtected: t.u32(), summary: t.string() },
  (ctx, { sessionId, campaignId, customersProtected, summary }) => {
    requireAdmin(ctx);
    const s = ctx.db.session.id.find(sessionId);
    if (!s) throw new SenderError(`unknown session ${sessionId}`);
    if (!s.customerId) throw new SenderError('impact cards are for takeover sessions');
    ctx.db.impactCard.insert({ id: 0n, sessionId, customerId: s.customerId, campaignId, customersProtected, summary, createdAt: ctx.timestamp });
    logChat(ctx, { customerId: s.customerId, sessionId, sender: 'system', kind: 'event', text: `Impact card: ${summary}`,
      detail: { campaign_id: campaignId ?? null, customers_protected: customersProtected } });
    if (s.status === 'active') ctx.db.session.id.update({ ...s, status: 'completed', endedAt: ctx.timestamp });
  }
);

export const addInsight = spacetimedb.reducer(
  { id: t.string(), campaignId: t.string(), kind: t.string(), text: t.string(), citedIndicatorIds: t.array(t.u64()), confidence: t.f64() },
  (ctx, { id, campaignId, kind, text, citedIndicatorIds, confidence }) => {
    requireAdmin(ctx);
    for (const ind of citedIndicatorIds) {
      if (!ctx.db.indicator.id.find(ind)) throw new SenderError(`insight cites unknown indicator ${ind}`);
    }
    ctx.db.insight.insert({ id, campaignId, kind, text, citedIndicatorIds, confidence, createdAt: ctx.timestamp });
  }
);

export const recordEvent = spacetimedb.reducer(
  { runId: t.string(), offsetMs: t.u64(), reducer: t.string(), argsJson: t.string() },
  (ctx, { runId, offsetMs, reducer, argsJson }) => {
    requireAdmin(ctx);
    ctx.db.recordedEvent.insert({ id: 0n, runId, offsetMs, reducer, argsJson });
  }
);

// Clear all runtime rows (sessions, messages, campaigns, ...) between demo runs.
// Keeps personas, customers, canaries, recorded runs, taxonomy and datasets.
export const resetRuntime = spacetimedb.reducer(ctx => {
  requireAdmin(ctx);
  // Save every customer's conversation first, so nothing on the dashboard is lost.
  const customerIds = new Set<string>();
  for (const m of ctx.db.inboundMessage.iter()) customerIds.add(m.customerId);
  for (const ss of ctx.db.session.iter()) if (ss.customerId) customerIds.add(ss.customerId);
  for (const cid of customerIds) archiveCustomer(ctx, cid, roomForCustomer(ctx, cid), 'reset_runtime');
  for (const r of [...ctx.db.inboundMessage.iter()]) ctx.db.inboundMessage.id.delete(r.id);
  for (const r of [...ctx.db.session.iter()]) ctx.db.session.id.delete(r.id);
  for (const r of [...ctx.db.turn.iter()]) ctx.db.turn.id.delete(r.id);
  for (const r of [...ctx.db.handlerPlan.iter()]) ctx.db.handlerPlan.id.delete(r.id);
  for (const r of [...ctx.db.indicator.iter()]) ctx.db.indicator.id.delete(r.id);
  for (const r of [...ctx.db.campaign.iter()]) ctx.db.campaign.id.delete(r.id);
  for (const r of [...ctx.db.insight.iter()]) ctx.db.insight.id.delete(r.id);
  for (const r of [...ctx.db.tripwire.iter()]) ctx.db.tripwire.id.delete(r.id);
  for (const r of [...ctx.db.probeResult.iter()]) ctx.db.probeResult.id.delete(r.id);
  for (const r of [...ctx.db.customerAlert.iter()]) ctx.db.customerAlert.id.delete(r.id);
  for (const r of [...ctx.db.impactCard.iter()]) ctx.db.impactCard.id.delete(r.id);
  for (const r of [...ctx.db.scammerMessage.iter()]) ctx.db.scammerMessage.id.delete(r.id);
  for (const r of [...ctx.db.customerMessage.iter()]) ctx.db.customerMessage.id.delete(r.id);
  for (const r of [...ctx.db.agentStep.iter()]) ctx.db.agentStep.id.delete(r.id);
});

// ---------------------------------------------------------------------------
// Live demo reducers
// ---------------------------------------------------------------------------

const MAX_SCAMMER_TEXT = 480;
const MIN_SCAMMER_GAP_MICROS = 750_000n; // light rate limit per room

export const openDemoRoom = spacetimedb.reducer(
  { code: t.string(), customerId: t.string(), scammerNumber: t.string() },
  (ctx, { code, customerId, scammerNumber }) => {
    requireAdmin(ctx);
    if (!ctx.db.customer.id.find(customerId)) throw new SenderError(`unknown customer ${customerId}`);
    const existing = ctx.db.demoRoom.code.find(code);
    const row = { code, customerId, scammerNumber, status: 'open', createdAt: ctx.timestamp };
    if (existing) ctx.db.demoRoom.code.update(row);
    else ctx.db.demoRoom.insert(row);
  }
);

export const closeDemoRoom = spacetimedb.reducer({ code: t.string() }, (ctx, { code }) => {
  requireAdmin(ctx);
  const room = ctx.db.demoRoom.code.find(code);
  if (room) ctx.db.demoRoom.code.update({ ...room, status: 'closed' });
});

// Open to anyone with the room code: the scammer phone isn't an admin. The
// engine treats the text as untrusted input like any scam message.
export const scammerSend = spacetimedb.reducer(
  { roomCode: t.string(), text: t.string() },
  (ctx, { roomCode, text }) => {
    const room = ctx.db.demoRoom.code.find(roomCode);
    if (!room || room.status !== 'open') throw new SenderError('unknown or closed room');
    const body = text.trim();
    if (!body) throw new SenderError('empty message');
    if (body.length > MAX_SCAMMER_TEXT) throw new SenderError(`message longer than ${MAX_SCAMMER_TEXT} characters`);
    let last = 0n;
    for (const m of ctx.db.scammerMessage.roomCode.filter(roomCode)) {
      if (m.sentAt.microsSinceUnixEpoch > last) last = m.sentAt.microsSinceUnixEpoch;
    }
    if (ctx.timestamp.microsSinceUnixEpoch - last < MIN_SCAMMER_GAP_MICROS) {
      throw new SenderError('slow down');
    }
    ctx.db.scammerMessage.insert({ id: 0n, roomCode, text: body, status: 'queued', error: undefined, sentAt: ctx.timestamp });
  }
);

// A demo phone page opened (or reconnected). Open like scammer_send: it only records that someone is
// looking at the room, once per connection.
export const phoneOpened = spacetimedb.reducer({ roomCode: t.string() }, (ctx, { roomCode }) => {
  const conn = ctx.connectionId;
  if (!conn) throw new SenderError('phone_opened needs a live connection');
  if (!ctx.db.demoRoom.code.find(roomCode)) throw new SenderError('unknown room');
  for (const v of ctx.db.roomViewer.roomCode.filter(roomCode)) {
    if (v.connection.isEqual(conn)) return;
  }
  ctx.db.roomViewer.insert({ id: 0n, roomCode, connection: conn, joinedAt: ctx.timestamp });
});

// The customer texts the scammer back. Open like scammer_send. Refused while Talon is
// handling the conversation, so the customer and Talon never talk over each other.
export const customerSend = spacetimedb.reducer(
  { roomCode: t.string(), text: t.string() },
  (ctx, { roomCode, text }) => {
    const room = ctx.db.demoRoom.code.find(roomCode);
    if (!room || room.status !== 'open') throw new SenderError('unknown or closed room');
    const body = text.trim();
    if (!body) throw new SenderError('empty message');
    if (body.length > MAX_SCAMMER_TEXT) throw new SenderError(`message longer than ${MAX_SCAMMER_TEXT} characters`);
    for (const s of ctx.db.session.iter()) {
      if (s.customerId === room.customerId && s.status === 'active') {
        throw new SenderError('Talon is handling this conversation. Tap Stop to take it back.');
      }
    }
    let last = 0n;
    for (const m of ctx.db.customerMessage.roomCode.filter(roomCode)) {
      if (m.sentAt.microsSinceUnixEpoch > last) last = m.sentAt.microsSinceUnixEpoch;
    }
    if (ctx.timestamp.microsSinceUnixEpoch - last < MIN_SCAMMER_GAP_MICROS) throw new SenderError('slow down');
    ctx.db.customerMessage.insert({ id: 0n, roomCode, text: body, sentAt: ctx.timestamp });
    logChat(ctx, { customerId: room.customerId, roomCode, sender: 'customer', kind: 'message', text: body });
  }
);

export const setScammerMessageStatus = spacetimedb.reducer(
  { id: t.u64(), status: t.string(), error: t.option(t.string()) },
  (ctx, { id, status, error }) => {
    requireAdmin(ctx);
    const m = ctx.db.scammerMessage.id.find(id);
    if (!m) throw new SenderError(`unknown scammer message ${id}`);
    ctx.db.scammerMessage.id.update({ ...m, status, error });
  }
);

export const addAgentStep = spacetimedb.reducer(
  { sessionId: t.string(), turnId: t.option(t.string()), agent: t.string(), kind: t.string(), contentJson: t.string(), latencyMs: t.u32() },
  (ctx, { sessionId, turnId, agent, kind, contentJson, latencyMs }) => {
    requireAdmin(ctx);
    ctx.db.agentStep.insert({ id: 0n, sessionId, turnId, agent, kind, contentJson, latencyMs, createdAt: ctx.timestamp });
  }
);

// Customer taps Delete or Report on a warned message. Open like request_takeover.
export const dismissMessage = spacetimedb.reducer(
  { messageId: t.string(), action: t.string() },
  (ctx, { messageId, action }) => {
    const msg = ctx.db.inboundMessage.id.find(messageId);
    if (!msg) throw new SenderError(`unknown message ${messageId}`);
    if (action !== 'deleted' && action !== 'reported') throw new SenderError('action must be deleted or reported');
    if (msg.sessionId) throw new SenderError('Talon is already handling this message');
    ctx.db.inboundMessage.id.update({ ...msg, status: action });
    logChat(ctx, { customerId: msg.customerId, sender: 'system', kind: 'event',
      text: `Customer tapped ${action === 'deleted' ? 'Delete' : 'Report'}`, detail: { message_id: messageId } });
    // A reported number is marked Reported in the scammer catalog (the brand and intel from the text itself
    // were recorded when Talon warned about it). Status only moves forward, so a later block still wins.
    if (action === 'reported') markReported(ctx, msg.sender, msg.customerId, msg.category, messageId);
  }
);

// Clear one room's conversation so judges can try another scenario: the customer's messages, Talon's
// sessions with everything hanging off them (turns, plans, intel, trace, cards, tripwires), campaigns
// those sessions belonged to, and both phones' outboxes. Rooms, customers, taxonomy and other rooms stay.
function wipeRoom(ctx: Ctx, code: string) {
  const room = ctx.db.demoRoom.code.find(code);
  if (!room) return;
  const customerId = room.customerId;
  archiveCustomer(ctx, customerId, code, 'reset_room');
  const sessionIds = new Set<string>();
  const campaignIds = new Set<string>();
  for (const s of [...ctx.db.session.iter()]) {
    if (s.customerId !== customerId) continue;
    sessionIds.add(s.id);
    if (s.campaignId) campaignIds.add(s.campaignId);
  }
  for (const m of [...ctx.db.inboundMessage.customerId.filter(customerId)]) {
    if (m.campaignId) campaignIds.add(m.campaignId);
    for (const st of [...ctx.db.agentStep.sessionId.filter(m.id)]) ctx.db.agentStep.id.delete(st.id);
    ctx.db.inboundMessage.id.delete(m.id);
  }
  for (const sid of sessionIds) {
    for (const r of [...ctx.db.turn.sessionId.filter(sid)]) ctx.db.turn.id.delete(r.id);
    for (const r of [...ctx.db.handlerPlan.sessionId.filter(sid)]) ctx.db.handlerPlan.id.delete(r.id);
    for (const r of [...ctx.db.indicator.sessionId.filter(sid)]) ctx.db.indicator.id.delete(r.id);
    for (const r of [...ctx.db.agentStep.sessionId.filter(sid)]) ctx.db.agentStep.id.delete(r.id);
    ctx.db.session.id.delete(sid);
  }
  for (const r of [...ctx.db.impactCard.customerId.filter(customerId)]) ctx.db.impactCard.id.delete(r.id);
  for (const r of [...ctx.db.customerAlert.customerId.filter(customerId)]) ctx.db.customerAlert.id.delete(r.id);
  for (const r of [...ctx.db.tripwire.iter()]) if (sessionIds.has(r.sessionId)) ctx.db.tripwire.id.delete(r.id);
  for (const r of [...ctx.db.probeResult.iter()]) if (sessionIds.has(r.sessionId)) ctx.db.probeResult.id.delete(r.id);
  for (const cid of campaignIds) {
    for (const r of [...ctx.db.insight.campaignId.filter(cid)]) ctx.db.insight.id.delete(r.id);
    ctx.db.campaign.id.delete(cid);
  }
  for (const r of [...ctx.db.scammerMessage.roomCode.filter(code)]) ctx.db.scammerMessage.id.delete(r.id);
  for (const r of [...ctx.db.customerMessage.roomCode.filter(code)]) ctx.db.customerMessage.id.delete(r.id);
  const prev = ctx.db.roomReset.code.find(code);
  if (prev) ctx.db.roomReset.code.update({ code, count: prev.count + 1 });
  else ctx.db.roomReset.insert({ code, count: 1 });
}

// The dashboard's "Reset session" button. Open like the other room actions (it only needs the room
// code) and clears the room and its second-customer room (CODE-2) together.
export const resetRoom = spacetimedb.reducer({ code: t.string() }, (ctx, { code }) => {
  const room = ctx.db.demoRoom.code.find(code);
  if (!room || room.status !== 'open') throw new SenderError('unknown or closed room');
  wipeRoom(ctx, code);
  wipeRoom(ctx, `${code}-2`);
});

// Delete chat log rows: one room's (room_code), or all of them (empty room_code). Admin only; nothing
// else ever deletes the log.
export const clearChatLog = spacetimedb.reducer({ roomCode: t.string() }, (ctx, { roomCode }) => {
  requireAdmin(ctx);
  const rows = roomCode ? [...ctx.db.chatLog.roomCode.filter(roomCode)] : [...ctx.db.chatLog.iter()];
  for (const r of rows) ctx.db.chatLog.id.delete(r.id);
});

// Delete session archive rows: one room's (room_code), or all of them (empty room_code). Admin only.
export const clearSessionArchive = spacetimedb.reducer({ roomCode: t.string() }, (ctx, { roomCode }) => {
  requireAdmin(ctx);
  const rows = roomCode ? [...ctx.db.sessionArchive.roomCode.filter(roomCode)] : [...ctx.db.sessionArchive.iter()];
  for (const r of rows) ctx.db.sessionArchive.id.delete(r.id);
});

// ---------------------------------------------------------------------------
// Scammer catalog
// ---------------------------------------------------------------------------

function union(a: string[], b: string[]): string[] {
  return [...new Set([...a, ...b.filter(Boolean)])];
}

// reported: the customer tapped Report on the text instead of handing it to Talon.
const STATUS_RANK: Record<string, number> = { active: 0, reported: 1, blocked: 2, shut_down: 3 };

function markReported(ctx: Ctx, number: string, customerId: string, category: string | undefined, messageId: string) {
  const row = ctx.db.scamCatalog.number.find(number);
  const rank = (st: string) => STATUS_RANK[st] ?? 0;
  if (row) {
    ctx.db.scamCatalog.number.update({
      ...row,
      lastSeen: ctx.timestamp,
      categories: union(row.categories, category ? [category] : []),
      customers: union(row.customers, [customerId]),
      status: rank('reported') > rank(row.status) ? 'reported' : row.status,
    });
  } else {
    ctx.db.scamCatalog.insert({
      number, firstSeen: ctx.timestamp, lastSeen: ctx.timestamp, attempts: 1,
      categories: category ? [category] : [], brands: [], customers: [customerId], sessions: [], intel: [],
      status: 'reported', lastMessageId: messageId,
    });
  }
}

// Record a scam attempt or new intel for a scammer number. Merges into the existing row: lists are
// unioned, attempts count distinct messages, and status only moves forward (active -> blocked -> shut_down).
export const recordScammer = spacetimedb.reducer(
  {
    number: t.string(), messageId: t.option(t.string()), sessionId: t.option(t.string()),
    customerId: t.option(t.string()), category: t.option(t.string()), brands: t.array(t.string()),
    intel: t.array(t.string()), status: t.option(t.string()),
  },
  (ctx, { number, messageId, sessionId, customerId, category, brands, intel, status }) => {
    requireAdmin(ctx);
    const row = ctx.db.scamCatalog.number.find(number);
    const newAttempt = Boolean(messageId) && messageId !== row?.lastMessageId;
    const nextStatus = (cur: string) => (status && (STATUS_RANK[status] ?? 0) > (STATUS_RANK[cur] ?? 0) ? status : cur);
    if (row) {
      ctx.db.scamCatalog.number.update({
        ...row,
        lastSeen: ctx.timestamp,
        attempts: row.attempts + (newAttempt ? 1 : 0),
        categories: union(row.categories, category ? [category] : []),
        brands: union(row.brands, brands),
        customers: union(row.customers, customerId ? [customerId] : []),
        sessions: union(row.sessions, sessionId ? [sessionId] : []),
        intel: union(row.intel, intel),
        status: nextStatus(row.status),
        lastMessageId: messageId ?? row.lastMessageId,
      });
    } else {
      ctx.db.scamCatalog.insert({
        number, firstSeen: ctx.timestamp, lastSeen: ctx.timestamp, attempts: newAttempt ? 1 : 0,
        categories: category ? [category] : [], brands: union([], brands), customers: customerId ? [customerId] : [],
        sessions: sessionId ? [sessionId] : [], intel: union([], intel), status: nextStatus('active'),
        lastMessageId: messageId,
      });
    }
  }
);

// Import scammer catalog rows with their own first/last-seen times (e.g. history from earlier sessions or
// another environment). Upserts by number. Admin only; live sessions keep using record_scammer.
const CatalogInput = t.object('CatalogInput', {
  number: t.string(),
  firstSeen: t.timestamp(),
  lastSeen: t.timestamp(),
  attempts: t.u32(),
  categories: t.array(t.string()),
  brands: t.array(t.string()),
  customers: t.array(t.string()),
  sessions: t.array(t.string()),
  intel: t.array(t.string()),
  status: t.string(),
  lastMessageId: t.option(t.string()),
});

export const importScamCatalog = spacetimedb.reducer({ entries: t.array(CatalogInput) }, (ctx, { entries }) => {
  requireAdmin(ctx);
  for (const e of entries) {
    if (!(e.status in STATUS_RANK)) throw new SenderError(`unknown catalog status ${e.status}`);
    if (ctx.db.scamCatalog.number.find(e.number)) ctx.db.scamCatalog.number.update(e);
    else ctx.db.scamCatalog.insert(e);
  }
});
