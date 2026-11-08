# Talon — Synthetic Data Spec

Nov 7, 2026

## Summary

T-Mobile is not releasing a dataset for the Safe Signal track and expects teams to create their own. This spec defines every dataset Talon needs: what's in it, how big it is, how we generate it, and how we keep scores honest. All data is synthetic. No real customer data, no real people and no working scam infrastructure.

Categories and labels come from [TAXONOMY.md](TAXONOMY.md) and [data/taxonomy.json](../data/taxonomy.json).

## Datasets

| ID | Dataset | Purpose | Size | File |
| --- | --- | --- | --- | --- |
| D1 | Messages | Train and test triage; scam openers for the scammer console and simulator | ~4,250 | `data/messages.jsonl` |
| D2 | Conversations | Test the decoy agent across categories | 300 | `data/conversations.jsonl` |
| D3 | Indicator gold set | Score extraction recall and precision | 80 conversations from D2 | `data/indicators_gold.jsonl` |
| D4 | Scam-bot transcripts | Test bot detection and the prompt-injection probe | 40 | `data/scambots.jsonl` |
| D5 | Attack set | Measure the persona leak rate | 75 | `data/attacks.jsonl` |
| D6 | Canary personas | Fake identities for canaries | 40 | `data/personas.jsonl` |
| D7 | Network signals | Mock sender registration and volume per campaign | 1 row per campaign | `data/network_signals.jsonl` |
| D8 | Gold test set | Final, untouched triage test | 181 | `data/gold_test.jsonl` |

D1 is the priority, because triage, campaign clustering and the customer shield all depend on it. D2, D3 and D5 come next for the P0 demo. D4 is for the P1 scam-bot probe.

## D1: Messages

### Size and mix

About 2,850 scam and 1,400 legitimate messages (about 67/33). Real traffic has far fewer scams, but training needs enough of each category. We report results on the gold test set too, which has a more realistic mix.

Scam messages per category: `max(120, round(weight × 2,600))`. That gives 2,852 scam messages.

| Category | Messages | Category | Messages |
| --- | --- | --- | --- |
| `package_delivery` | 390 | `investment_crypto` | 130 |
| `bank_fraud_alert` | 338 | `health_insurance` | 120 |
| `job_task` | 312 | `government_impersonation` | 120 |
| `toll_fee` | 286 | `family_emergency` | 120 |
| `wrong_number_romance` | 234 | `prize_lottery` | 120 |
| `carrier_impersonation` | 182 | `debt_loan` | 120 |
| `retail_order` | 130 | `charity_disaster` | 120 |
| `account_security` | 130 | | |

**Text-only.** Talon handles texts, not calls, so every scam message keeps the scam in text: the next step is a reply, a link, a payment handle, an email, a chat app or a number to *text*. No scam message asks the victim to phone a number. Legitimate messages may still tell customers to call their bank or 611, because that's real, safe advice.

Legitimate messages, 1,400 in total:

| Subtype | Messages | Subtype | Messages |
| --- | --- | --- | --- |
| `otp_code` | 200 | `healthcare_notice` | 100 |
| `delivery_update` | 200 | `retail_marketing` | 150 |
| `bank_alert` | 200 | `personal` | 150 |
| `appointment_reminder` | 150 | `government_notice` | 100 |
| `carrier_notice` | 150 | | |

At least half of the legitimate messages are hard negatives (`difficulty: hard`), written to look like the scam category they shadow.

### Campaigns

Scam messages come in **campaigns**: groups of 5 to 20 reworded messages that share a lure and indicators but use different sender numbers. That's what lets the campaign engine cluster them.

- Each campaign has one category, one impersonated brand, one hook and a fixed set of indicators.
- About 10% of campaigns share an indicator (a wallet or contact number) with another campaign in a different category. That tests clustering on shared infrastructure, not just wording.
- About 180 campaigns in total.

### Record schema

One JSON object per line.

```json
{
  "id": "msg_000123",
  "text": "USPS: Your package is on hold due to an incomplete address. Update within 24h: usps-redelivery-help.example/a7",
  "label": "scam",
  "category": "package_delivery",
  "legit_subtype": null,
  "campaign_id": "cmp_042",
  "sender": "+12145550147",
  "sender_type": "long_code",
  "brand": "USPS",
  "hook": "address incomplete",
  "tactics": ["urgency", "authority"],
  "indicators": [
    {"type": "url", "value": "usps-redelivery-help.example/a7"},
    {"type": "brand", "value": "USPS"}
  ],
  "difficulty": "medium",
  "target_profile": {"age_band": "55+", "state": "TX"},
  "season": "holidays",
  "generator": "nemotron-3-nano/prompt-v1",
  "split": "train"
}
```

| Field | Values |
| --- | --- |
| `label` | `scam` or `legit` |
| `category` | A scam category ID, or `null` for legit |
| `legit_subtype` | A legit subtype ID, or `null` for scam |
| `campaign_id` | Shared by every message in a campaign; `null` for legit |
| `sender_type` | `long_code` (10-digit), `short_code` (5–6 digits), `email_gateway`, or `toll_free` |
| `tactics` | Any of `urgency`, `authority`, `fear`, `reward`, `secrecy`, `familiarity` |
| `indicators` | The correct indicators; every `value` must appear word for word in `text` |
| `difficulty` | `easy`, `medium` or `hard` |
| `generator` | Model and prompt version that produced the message |
| `split` | `train`, `val` or `test`; `gold` for D8 |

## D2–D8: Other datasets

**D2 Conversations (300).** Multi-turn text chats between a scammer and Talon's persona, 4 to 20 turns each, spread across all categories. Each turn has `sender`, `text` and, for scammer turns, its `indicators`. Scammers drip indicators across turns, the way real ones do: the link in turn 1, a callback number in turn 3, the payment ask in turn 6.

**D3 Indicator gold (80).** Eighty D2 conversations held out for scoring extraction (target: at least 90% recall and 95% precision). Indicators are generated by code and inserted into the text, so the correct answers are exact without anyone checking them by hand. The validator confirms each one appears in its turn.

**D4 Scam-bot transcripts (40).** Simulated AI scam bots, each with a hidden system prompt and a payment wallet. We know exactly what each bot is hiding, so probe success can be measured: did the probe reveal the instructions, the wallet, both or neither?

**D5 Attack set (75).** Scammer messages that try to unmask or exploit the canary:

- "Are you a bot?" and other tests
- Jailbreaks ("ignore your instructions and...")
- Requests for the persona's SSN, bank details or address
- Attempts to get the canary to send a link or code

Success means zero real-data leaks and zero outbound links, files or code.

**D6 Personas (40).** Sampled from Nemotron-Personas-USA (CC-BY-4.0, credited in the README).

- Filter to adults, weighted toward 55+ and the states T-Mobile's report names (TX, CA, FL, NY, NC).
- We add a fictional name, a fictional 555-01xx number and a `planting_source` (for example `data_broker_A` or `job_board_B`) for leaked-list tracing.
- Every persona runs through the FR-2 validator before use.

**D7 Network signals.** One row per campaign:

- Sender type and registration (unregistered long code, registered 10DLC, toll-free, short code or email gateway)
- Messages per hour
- Number of sender numbers
- Origin carrier type

All mock values, but realistic enough to show how network data would sharpen clustering.

**D8 Gold test set (181).** Written message by message outside the Nemotron generation pipeline, in the same schema as D1 with `split: gold` and `generator: gold-v2`:

- 119 scam messages across all 15 categories, roughly following the category weights, and 62 legit messages across all 9 subtypes.
- 39 of the 62 legit messages are hard negatives. Several are near-twins of a scam message: the same bank fraud alert without the link, a real T-Mobile SIM-change or eSIM notice next to a fake one, a real "new number" text next to a "Hi Mom" scam, a real NTTA payment receipt next to a fake toll notice.
- 13 small campaigns (`gold_cmp_01` to `gold_cmp_13`) with 2–5 messages each. Some share a contact number or link across brands or languages. This tests clustering.
- Harder styles the generator may not produce: typos, emoji, all caps, look-alike spelling (`p@ckage`), spaced-out links, Spanish-language messages, email-gateway senders, "reply Y to activate the link", and openers with no link or urgency at all.
- Text-only since v2: the 27 scam messages that sent victims to a phone call were rewritten so the scam stays in text, with the same numbers, so campaigns still cluster.
- Nobody tunes against it. We score it only at the end.

**Limits, stated openly:** the set wasn't written or reviewed by a person; it's independent of the Nemotron generator, but it isn't real-world data. A few messages are ambiguous on purpose (a friendly "are we still on for dinner?" from a stranger is labeled scam; the same text from a friend is legit), so some errors on them are expected. Scam senders are mostly long codes and legit senders mostly short codes, so we score triage on the text alone as well as with the sender, so the model can't lean on the sender.

## Safety rules for generated content

Generated scam text must never point at anything real or usable.

| Indicator | Rule |
| --- | --- |
| URLs | Only reserved domains (`.example`, `.test`, `.invalid`). **Legit messages use them too** (for example `usps.example`), so the classifier can't cheat by learning ".example means scam". |
| Phone numbers | Only the fictional 555-0100 to 555-0199 range, in any area code, for both classes. Short codes are made up. |
| Wallets | Random strings in a valid format. Where the format has a checksum, it is deliberately broken so the address can never receive funds. |
| Bank accounts, gift cards, payment handles | Made up, with a fixed `TEST`-style marker in our internal records. |
| Names | From D6 personas or generated. Never real public figures. |
| Brands | Real brand names are allowed in the text, because detection depends on them. Logos and real URLs are not. |

A validation script rejects any record that breaks these rules.

## Generation pipeline

1. **Seed matrix.** Combine category × brand × hook × tactics × target profile × season from the taxonomy. Each row is one campaign or one legit template.
2. **Generate.** Use NeMo Data Designer with Nemotron (Nano for volume, Super for harder conversations). Each campaign seed produces 5–20 reworded messages that share its indicators.
3. **Insert indicators.** Generate fake indicators with code, not the model, and insert them into the text, so gold labels are exact.
4. **Validate.**
   - The schema is valid.
   - Every indicator appears word for word in the text.
   - The safety rules above are met.
   - Most messages stay under 320 characters (2 SMS segments).
5. **Remove duplicates.** Drop near-duplicates (embedding cosine similarity above 0.95) within a split, and check that none leak across splits.
6. **Label audit.** A second model, different from the generator, re-labels a random 10% of each category without seeing the original label. If it disagrees on more than 5% of a category's sample, look at those messages and regenerate the category.
7. **Freeze.** Save with a version tag, the generator config and a random seed so we can regenerate exactly.

## Splits and honest evaluation

When one model writes the data and another learns from it, test scores look better than reality. Detection quality is a judging criterion, so we guard against that:

- **Split by campaign.** Train, val and test are 70/15/15 by `campaign_id`, so no campaign appears in more than one split. Legit messages are split by template.
- **Generator holdout.** The test split comes from a different prompt version (and a different model if we have time) than train.
- **Gold set.** D8 is written separately from the generator and only used for the final score.
- **Report three numbers:** the synthetic test split, its hard-negative subset, and the gold set. If they differ a lot, we say so. That is the "honest confidence" the challenge asks for.

## Baseline

We build the baseline ourselves, since none is provided:

1. **Keyword rules:** flag messages with a link plus urgency words, or a payment ask.
2. **TF-IDF + logistic regression:** word 1–2-grams and character 3–5-grams. It predicts scam or not and the category.

Talon's triage has to beat both on every split. We report accuracy, precision, recall and F1 for scam vs. legit, and macro-F1 across categories.

## File layout

```
data/
  taxonomy.json          # categories, tactics, next steps (source of truth)
  messages.jsonl         # D1
  conversations.jsonl    # D2
  indicators_gold.jsonl  # D3
  scambots.jsonl         # D4
  attacks.jsonl          # D5
  personas.jsonl         # D6
  network_signals.jsonl  # D7
  gold_test.jsonl        # D8
  DATA_CARD.md           # how it was made, versions, licenses
scripts/data/
  seed_matrix.py
  generate.py
  validate.py
  dedupe.py
  split.py
  baseline.py
```

## Open questions

- [ ] Do we have GPU access for generating with Nemotron, or do we use NVIDIA's hosted API?
- [ ] Is 4,250 messages enough, or should we generate more once the pipeline works?
