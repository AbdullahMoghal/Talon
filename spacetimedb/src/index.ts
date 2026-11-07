import { schema, table, t, SenderError } from 'spacetimedb/server';

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

const spacetimedb = schema({
  admin,
  taxonomyMeta,
  scamCategory,
  legitSubtype,
  decoyTactic,
  datasetMessage,
  datasetIndicator,
});
export default spacetimedb;

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

export const onDisconnect = spacetimedb.clientDisconnected(_ctx => {});

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
