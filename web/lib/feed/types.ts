// Mirrors the SpacetimeDB tables in spacetime/src/lib.rs (only what the dashboard reads).

export type Conversation = {
  id: number;
  canary_id: number;
  campaign_id: number;
  channel: "sms" | "voice";
  run_id: string;
  turn_count: number;
  is_bot_suspected: boolean;
};

export type Turn = {
  id: number;
  conversation_id: number;
  sender: "scammer" | "canary";
  text: string;
  triage_label: string;
  confidence: number;
  safety_passed: boolean;
};

export type Indicator = {
  id: number;
  conversation_id: number;
  kind: string;
  value: string;
  confidence: number;
  source_turn_id: number;
};

export type Feed = {
  source: "live" | "mock";
  /** Set when the live source failed and the dashboard fell back to mock rows. */
  error?: string;
  conversations: Conversation[];
  turns: Turn[];
  indicators: Indicator[];
};
