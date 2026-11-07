//! Talon's SpacetimeDB module: every table from docs/ARCHITECTURE.md plus the
//! reducers that are the only write path. Readers (dashboard, workers) subscribe.
//!
//! Conventions, to keep reducer arguments easy to send as JSON over HTTP:
//! - Reducer arguments never use Option. 0 means "no id", "" means "none".
//! - Times come from `ctx.timestamp`, never from the caller.
//! - Reducers can't return values, so callers that need an id right away
//!   (conversation, turn, campaign) choose it themselves; see services/talon/ids.py.

use spacetimedb::{reducer, table, ReducerContext, Table, Timestamp};

// ---------- Tables ----------

#[table(name = canary, public)]
pub struct Canary {
    #[primary_key]
    #[auto_inc]
    pub id: u64,
    #[unique]
    pub number: String,
    pub persona_id: u64,
    pub planting_source: String,
    pub status: String,
    pub created_at: Timestamp,
}

#[table(name = persona, public)]
pub struct Persona {
    #[primary_key]
    #[auto_inc]
    pub id: u64,
    pub name: String,
    pub age: u32,
    pub location: String,
    pub backstory: String,
    pub quirks: String,
    pub memory_json: String,
}

#[table(name = conversation, public)]
pub struct Conversation {
    /// Chosen by the caller.
    #[primary_key]
    pub id: u64,
    pub canary_id: u64,
    /// 0 until the campaign worker assigns one.
    pub campaign_id: u64,
    /// "sms" or "voice".
    pub channel: String,
    /// Recorded run this conversation belongs to; "" for live traffic.
    pub run_id: String,
    pub started_at: Timestamp,
    pub turn_count: u32,
    pub is_bot_suspected: bool,
}

#[table(name = turn, public)]
pub struct Turn {
    /// Chosen by the caller, so indicators can cite it.
    #[primary_key]
    pub id: u64,
    #[index(btree)]
    pub conversation_id: u64,
    /// "scammer" or "canary".
    pub sender: String,
    /// Transcript only for voice; audio is never stored.
    pub text: String,
    pub triage_label: String,
    pub confidence: f32,
    pub safety_passed: bool,
    pub ts: Timestamp,
}

#[table(name = indicator, public)]
pub struct Indicator {
    #[primary_key]
    #[auto_inc]
    pub id: u64,
    #[index(btree)]
    pub conversation_id: u64,
    /// One of taxonomy.json `indicator_types`.
    pub kind: String,
    pub value: String,
    pub confidence: f32,
    pub source_turn_id: u64,
    pub created_at: Timestamp,
}

#[table(name = campaign, public)]
pub struct Campaign {
    /// Chosen by the campaign worker.
    #[primary_key]
    pub id: u64,
    pub taxonomy_category: String,
    pub first_seen: Timestamp,
    pub burned_at: Option<Timestamp>,
    pub time_to_burn_s: Option<u64>,
    /// "active" or "burned".
    pub status: String,
}

#[table(name = insight, public)]
pub struct Insight {
    #[primary_key]
    #[auto_inc]
    pub id: u64,
    #[index(btree)]
    pub campaign_id: u64,
    /// "summary", "new_pattern" or "customer_warning".
    pub kind: String,
    pub text: String,
    pub cited_indicator_ids: Vec<u64>,
    pub confidence: f32,
    pub created_at: Timestamp,
}

#[table(name = tripwire, public)]
pub struct Tripwire {
    #[primary_key]
    #[auto_inc]
    pub id: u64,
    pub campaign_id: u64,
    /// "giftcard", "wallet" or "account".
    pub kind: String,
    #[unique]
    pub token: String,
    pub issued_at: Timestamp,
    pub hit_at: Option<Timestamp>,
    pub hit_details: String,
}

#[table(name = probe_result, public)]
pub struct ProbeResult {
    #[primary_key]
    #[auto_inc]
    pub id: u64,
    pub conversation_id: u64,
    pub revealed_prompt: String,
    pub revealed_payment: String,
    pub success: bool,
    pub created_at: Timestamp,
}

#[table(name = customer_alert, public)]
pub struct CustomerAlert {
    #[primary_key]
    #[auto_inc]
    pub id: u64,
    pub campaign_id: u64,
    /// Hashed; the customer view never stores raw identifiers.
    pub customer_ref: String,
    pub message_hash: String,
    pub shown_at: Timestamp,
}

#[table(name = recorded_event, public)]
pub struct RecordedEvent {
    #[primary_key]
    #[auto_inc]
    pub id: u64,
    #[index(btree)]
    pub run_id: String,
    pub offset_ms: u64,
    pub reducer: String,
    pub args_json: String,
}

// ---------- Registry ----------

#[reducer]
pub fn add_persona(
    ctx: &ReducerContext,
    name: String,
    age: u32,
    location: String,
    backstory: String,
    quirks: String,
) -> Result<(), String> {
    if age < 18 {
        return Err("personas must be adults".into());
    }
    ctx.db.persona().insert(Persona {
        id: 0,
        name,
        age,
        location,
        backstory,
        quirks,
        memory_json: "{}".into(),
    });
    Ok(())
}

#[reducer]
pub fn register_canary(
    ctx: &ReducerContext,
    number: String,
    persona_id: u64,
    planting_source: String,
) -> Result<(), String> {
    if ctx.db.persona().id().find(persona_id).is_none() {
        return Err(format!("unknown persona {persona_id}"));
    }
    ctx.db.canary().insert(Canary {
        id: 0,
        number,
        persona_id,
        planting_source,
        status: "active".into(),
        created_at: ctx.timestamp,
    });
    Ok(())
}

// ---------- Pipeline ----------

#[reducer]
pub fn start_conversation(
    ctx: &ReducerContext,
    id: u64,
    canary_id: u64,
    channel: String,
    run_id: String,
) -> Result<(), String> {
    if channel != "sms" && channel != "voice" {
        return Err(format!("unknown channel {channel}"));
    }
    if id == 0 || ctx.db.conversation().id().find(id).is_some() {
        return Err(format!("conversation id {id} is 0 or already used"));
    }
    ctx.db.conversation().insert(Conversation {
        id,
        canary_id,
        campaign_id: 0,
        channel,
        run_id,
        started_at: ctx.timestamp,
        turn_count: 0,
        is_bot_suspected: false,
    });
    Ok(())
}

#[reducer]
pub fn add_turn(
    ctx: &ReducerContext,
    id: u64,
    conversation_id: u64,
    sender: String,
    text: String,
    triage_label: String,
    confidence: f32,
    safety_passed: bool,
) -> Result<(), String> {
    let Some(mut conv) = ctx.db.conversation().id().find(conversation_id) else {
        return Err(format!("unknown conversation {conversation_id}"));
    };
    if sender != "scammer" && sender != "canary" {
        return Err(format!("unknown sender {sender}"));
    }
    if sender == "canary" && !safety_passed {
        return Err("canary replies must pass the safety guard before they are stored".into());
    }
    if id == 0 || ctx.db.turn().id().find(id).is_some() {
        return Err(format!("turn id {id} is 0 or already used"));
    }
    ctx.db.turn().insert(Turn {
        id,
        conversation_id,
        sender,
        text,
        triage_label,
        confidence,
        safety_passed,
        ts: ctx.timestamp,
    });
    conv.turn_count += 1;
    ctx.db.conversation().id().update(conv);
    Ok(())
}

#[reducer]
pub fn flag_bot_suspected(ctx: &ReducerContext, conversation_id: u64) -> Result<(), String> {
    let Some(mut conv) = ctx.db.conversation().id().find(conversation_id) else {
        return Err(format!("unknown conversation {conversation_id}"));
    };
    conv.is_bot_suspected = true;
    ctx.db.conversation().id().update(conv);
    Ok(())
}

#[reducer]
pub fn add_indicator(
    ctx: &ReducerContext,
    conversation_id: u64,
    kind: String,
    value: String,
    confidence: f32,
    source_turn_id: u64,
) -> Result<(), String> {
    if ctx.db.conversation().id().find(conversation_id).is_none() {
        return Err(format!("unknown conversation {conversation_id}"));
    }
    ctx.db.indicator().insert(Indicator {
        id: 0,
        conversation_id,
        kind,
        value,
        confidence,
        source_turn_id,
        created_at: ctx.timestamp,
    });
    Ok(())
}

#[reducer]
pub fn add_probe_result(
    ctx: &ReducerContext,
    conversation_id: u64,
    revealed_prompt: String,
    revealed_payment: String,
    success: bool,
) {
    ctx.db.probe_result().insert(ProbeResult {
        id: 0,
        conversation_id,
        revealed_prompt,
        revealed_payment,
        success,
        created_at: ctx.timestamp,
    });
}

// ---------- Campaign worker ----------

/// Creates the campaign if `campaign_id` is new, then attaches the conversation
/// to it (pass 0 as `conversation_id` to only create).
#[reducer]
pub fn upsert_campaign(
    ctx: &ReducerContext,
    campaign_id: u64,
    taxonomy_category: String,
    conversation_id: u64,
) -> Result<(), String> {
    if campaign_id == 0 {
        return Err("campaign id must not be 0".into());
    }
    if ctx.db.campaign().id().find(campaign_id).is_none() {
        ctx.db.campaign().insert(Campaign {
            id: campaign_id,
            taxonomy_category,
            first_seen: ctx.timestamp,
            burned_at: None,
            time_to_burn_s: None,
            status: "active".into(),
        });
    }
    if conversation_id != 0 {
        let Some(mut conv) = ctx.db.conversation().id().find(conversation_id) else {
            return Err(format!("unknown conversation {conversation_id}"));
        };
        conv.campaign_id = campaign_id;
        ctx.db.conversation().id().update(conv);
    }
    Ok(())
}

#[reducer]
pub fn burn_campaign(ctx: &ReducerContext, campaign_id: u64) -> Result<(), String> {
    let Some(mut c) = ctx.db.campaign().id().find(campaign_id) else {
        return Err(format!("unknown campaign {campaign_id}"));
    };
    if c.burned_at.is_some() {
        return Ok(());
    }
    let elapsed_us = ctx
        .timestamp
        .to_micros_since_unix_epoch()
        .saturating_sub(c.first_seen.to_micros_since_unix_epoch());
    c.burned_at = Some(ctx.timestamp);
    c.time_to_burn_s = Some((elapsed_us / 1_000_000) as u64);
    c.status = "burned".into();
    ctx.db.campaign().id().update(c);
    Ok(())
}

#[reducer]
pub fn issue_tripwire(ctx: &ReducerContext, campaign_id: u64, kind: String, token: String) {
    ctx.db.tripwire().insert(Tripwire {
        id: 0,
        campaign_id,
        kind,
        token,
        issued_at: ctx.timestamp,
        hit_at: None,
        hit_details: String::new(),
    });
}

#[reducer]
pub fn hit_tripwire(ctx: &ReducerContext, token: String, hit_details: String) -> Result<(), String> {
    let Some(mut t) = ctx.db.tripwire().token().find(&token) else {
        return Err(format!("unknown tripwire token {token}"));
    };
    t.hit_at = Some(ctx.timestamp);
    t.hit_details = hit_details;
    ctx.db.tripwire().token().update(t);
    Ok(())
}

#[reducer]
pub fn add_customer_alert(
    ctx: &ReducerContext,
    campaign_id: u64,
    customer_ref: String,
    message_hash: String,
) {
    ctx.db.customer_alert().insert(CustomerAlert {
        id: 0,
        campaign_id,
        customer_ref,
        message_hash,
        shown_at: ctx.timestamp,
    });
}

// ---------- Insight worker ----------

#[reducer]
pub fn add_insight(
    ctx: &ReducerContext,
    campaign_id: u64,
    kind: String,
    text: String,
    cited_indicator_ids: Vec<u64>,
    confidence: f32,
) -> Result<(), String> {
    if !["summary", "new_pattern", "customer_warning"].contains(&kind.as_str()) {
        return Err(format!("unknown insight kind {kind}"));
    }
    for id in &cited_indicator_ids {
        if ctx.db.indicator().id().find(*id).is_none() {
            return Err(format!("insight cites unknown indicator {id}"));
        }
    }
    ctx.db.insight().insert(Insight {
        id: 0,
        campaign_id,
        kind,
        text,
        cited_indicator_ids,
        confidence,
        created_at: ctx.timestamp,
    });
    Ok(())
}

// ---------- Recorder ----------

#[reducer]
pub fn record_event(ctx: &ReducerContext, run_id: String, offset_ms: u64, reducer: String, args_json: String) {
    ctx.db.recorded_event().insert(RecordedEvent {
        id: 0,
        run_id,
        offset_ms,
        reducer,
        args_json,
    });
}
