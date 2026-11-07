import type { Feed } from "./types";

// Mock rows so the UI can be built before the pipeline writes real ones.
// All indicators follow DATA_SPEC.md safety rules (.example domains, 555-01xx numbers).
export const mockFeed: Feed = {
  source: "mock",
  conversations: [
    { id: 1001, canary_id: 4471, campaign_id: 1, channel: "sms", run_id: "", turn_count: 4, is_bot_suspected: false },
    { id: 1002, canary_id: 2208, campaign_id: 1, channel: "sms", run_id: "", turn_count: 2, is_bot_suspected: false },
    { id: 1003, canary_id: 3150, campaign_id: 0, channel: "voice", run_id: "demo-voice-1", turn_count: 3, is_bot_suspected: true },
  ],
  turns: [
    { id: 1, conversation_id: 1001, sender: "scammer", text: "NTTA: You have an unpaid toll of $4.15. Pay within 24h to avoid a $50 late fee: ntta-tollpay.example/p", triage_label: "toll_fee", confidence: 0.93, safety_passed: true },
    { id: 2, conversation_id: 1001, sender: "canary", text: "oh no I didn't know I had a toll. the link won't open on my phone, is there another way?", triage_label: "", confidence: 0, safety_passed: true },
    { id: 3, conversation_id: 1001, sender: "scammer", text: "You can call our billing desk at 1-469-555-0137 or try tollpay-help.example", triage_label: "toll_fee", confidence: 0.95, safety_passed: true },
    { id: 4, conversation_id: 1001, sender: "canary", text: "ok who do I make the payment out to?", triage_label: "", confidence: 0, safety_passed: true },
    { id: 5, conversation_id: 1002, sender: "scammer", text: "Final notice: unpaid toll balance. Avoid penalties: ntta-tollpay.example/q", triage_label: "toll_fee", confidence: 0.91, safety_passed: true },
    { id: 6, conversation_id: 1003, sender: "scammer", text: "This is the fraud department. We stopped a charge of $1,240. Please confirm your account to reverse it.", triage_label: "bank_fraud_alert", confidence: 0.88, safety_passed: true },
  ],
  indicators: [
    { id: 1, conversation_id: 1001, kind: "url", value: "ntta-tollpay.example/p", confidence: 0.97, source_turn_id: 1 },
    { id: 2, conversation_id: 1001, kind: "brand", value: "NTTA", confidence: 0.99, source_turn_id: 1 },
    { id: 3, conversation_id: 1001, kind: "phone", value: "1-469-555-0137", confidence: 0.96, source_turn_id: 3 },
    { id: 4, conversation_id: 1001, kind: "url", value: "tollpay-help.example", confidence: 0.94, source_turn_id: 3 },
    { id: 5, conversation_id: 1002, kind: "url", value: "ntta-tollpay.example/q", confidence: 0.97, source_turn_id: 5 },
  ],
};
