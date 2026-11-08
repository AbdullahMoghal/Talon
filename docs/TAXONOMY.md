# Talon — Scam Taxonomy

Nov 7, 2026

## Summary

T-Mobile is not releasing a dataset, taxonomy or baseline for the Safe Signal track, so this taxonomy is ours. It has 15 scam categories plus a legitimate class with 9 subtypes. The machine-readable version in [data/taxonomy.json](../data/taxonomy.json) (v0.2.0) is the source of truth; this page explains it.

**Talon is text-only.** Every category is a text-message scam, and in our data the scam stays in text: a reply, a link, a payment handle, an email or a chat app. No message asks the victim to phone a number, because Talon can't take over a call.

Each category drives four things in Talon:

1. **Triage label:** what the classifier predicts.
2. **Decoy tactic:** how Talon's persona keeps the scammer texting and gets indicators out of them.
3. **Indicators to expect:** what extraction looks for.
4. **Customer next steps:** what the customer phone tells a real customer to do.

## Where the categories come from

| Source | What it tells us |
| --- | --- |
| [FTC Data Spotlight: top text scams of 2024](https://www.ftc.gov/news-events/data-visualizations/data-spotlight/2025/04/top-text-scams-2024) | The five most reported text scams, in order: fake package delivery problems, fake job and "task" offers, fake fraud alerts, unpaid toll notices, and "wrong number" texts that turn into romance or investment scams. Reported text-scam losses reached $470 million in 2024. **The weights below follow this ranking.** |
| T-Mobile scam help page | Forward spam to 7726, Scam Block (#662#), and change your T-Mobile ID password if you opened a link. |
| Public reporting on T-Mobile-themed texts | Fake reward points expiring, fake outage compensation, fake "suspicious activity" alerts, and port-out scams. These give `carrier_impersonation` more weight than general data would. |
| T-Mobile 2023 Scam and Robocall Report | Retail and delivery impersonation peak around the holidays; tax season, back to school and open enrollment are peak seasons; TX, CA, FL, NY and NC are hit hardest. Used for seasons and places only: its category shares are for **calls** (Medicare and health insurance were over 40%), so they don't set our text weights. |

The weights are our estimates from these sources, not measured shares. We say this openly in the pitch.

## Scam categories

Weight is the category's share of the scam messages we generate (see [DATA_SPEC.md](DATA_SPEC.md)).

| ID | Category | Weight | Main harm | Typical lure |
| --- | --- | --- | --- | --- |
| `package_delivery` | Package delivery | 0.15 | Money, credentials | "Package on hold. Pay $1.99 redelivery fee" |
| `bank_fraud_alert` | Fake bank fraud alert | 0.13 | Credentials, money | "Suspicious charge of $849. Reply NO if this wasn't you" |
| `job_task` | Job and task scams | 0.12 | Money, personal info | "Earn $300/day with simple online tasks" |
| `toll_fee` | Unpaid toll or fine | 0.11 | Money, credentials | "Unpaid toll balance. Pay today to avoid a late fee" |
| `wrong_number_romance` | Wrong number and romance | 0.09 | Money | "Hi Jessica, are we still on for dinner?" |
| `carrier_impersonation` | Carrier impersonation and SIM swap | 0.07 | Credentials, account takeover | "Your T-Mobile reward points expire today" |
| `account_security` | Tech support and account lockout | 0.05 | Credentials, device access | "Your account was locked after a sign-in from a new device" |
| `retail_order` | Retail order or refund | 0.05 | Credentials, money, device access | "Your order of an iPhone 17 has shipped. Not you? Text CANCEL" |
| `investment_crypto` | Investment and crypto | 0.05 | Money | "Join our VIP group: 30% weekly returns" |
| `family_emergency` | Family emergency | 0.04 | Money | "Hi Mom, I dropped my phone, this is my new number" |
| `government_impersonation` | Government impersonation | 0.04 | Personal info, money | "IRS: your refund is pending verification" |
| `prize_lottery` | Prize, lottery and giveaway | 0.03 | Money, personal info | "You've won a $500 gift card. Claim before midnight" |
| `health_insurance` | Medicare and health insurance | 0.03 | Personal info, money | "Your new Medicare card requires verification" |
| `debt_loan` | Debt relief and loans | 0.02 | Money, personal info | "You're pre-approved for student loan forgiveness" |
| `charity_disaster` | Fake charity and disaster relief | 0.02 | Money | "Help hurricane victims now. Donate via Cash App" |

We left out vehicle warranty scams: they were mostly robocalls, and they nearly disappeared in 2023.

Full details per category (brands, hooks, asks, indicators, targets, seasonality) are in the JSON.

## Legitimate subtypes

These are the "not a scam" class. Most are **hard negatives**: real messages that look like a scam category, so the classifier can't just learn "mentions a bank = scam".

| ID | What it is | Looks like |
| --- | --- | --- |
| `otp_code` | One-time sign-in code | `carrier_impersonation`, `bank_fraud_alert` |
| `delivery_update` | Real delivery update | `package_delivery` |
| `bank_alert` | Real bank alert (reply YES or NO, no link) | `bank_fraud_alert` |
| `appointment_reminder` | Appointment reminder | `health_insurance` |
| `carrier_notice` | Real carrier notice from a short code | `carrier_impersonation` |
| `healthcare_notice` | Pharmacy or insurer reminder | `health_insurance` |
| `retail_marketing` | Retail promo the customer opted into | `retail_order`, `prize_lottery` |
| `personal` | Personal chat, including real "new number" texts | `family_emergency`, `wrong_number_romance` |
| `government_notice` | Real agency notice with no payment link | `government_impersonation`, `toll_fee` |

## Indicator types

Extraction pulls these out of each scammer turn. These match the Indicator types in the architecture's data model. `payment_handle` covers Zelle, Cash App, Venmo and similar.

| Type | Example (fictional) |
| --- | --- |
| `url` | `usps-redelivery-help.example/track` |
| `phone` | `(214) 555-0147` (a number the scammer wants texted or paid) |
| `email` | `support@refund-desk.example` |
| `wallet` | A crypto address in the right format that can't receive funds |
| `payment_handle` | `$HelpDesk2291` |
| `account` | A fake bank account and routing number |
| `giftcard_ask` | "Buy three $200 gift cards and send the codes" |
| `remote_access_id` | A remote-support session ID |
| `brand` | The organization impersonated, such as "USPS" |

## Decoy tactics

Talon's handler picks from these tactics based on the category. Each tactic is meant to make the scammer reveal another indicator.

| Tactic | What Talon's persona does |
| --- | --- |
| `play_confused` | Misunderstands on purpose so the scammer repeats and restates details |
| `ask_contact_details` | Asks for another way to reach them by text: a number, an email or a chat handle |
| `ask_link_again` | Says the link didn't open and asks for it again or for another site |
| `ask_who_to_pay` | Agrees to pay, then asks exactly where and to whom |
| `payment_trouble` | Stalls with payment trouble so the scammer offers another method |
| `ask_company_details` | Asks for company name, department, agent ID or case number |
| `accept_next_step` | Goes along and asks what to do next |
| `issue_tripwire` | Hands over a mock trackable gift card code or wallet (FR-14) |

## Customer next steps

Every warning shows the three shared steps, then the category's own step. This covers the challenge's "clear next steps".

Shared steps:

1. Don't reply or tap any link.
2. Forward the text to 7726 (SPAM) to report it.
3. Contact the company using its official app or the number on your card or statement, not the one in the message.

Example category step, `carrier_impersonation`: "T-Mobile won't ask you to confirm sensitive info in an unsolicited text. Check your account in the T-Life app. Never share a verification code or account PIN. If you tapped the link, change your T-Mobile ID password."

## Changing the taxonomy

- Edit [data/taxonomy.json](../data/taxonomy.json) first, then update this page.
- Bump `version` in the JSON whenever categories change, and regenerate any affected data.
- Weights must add up to 1.0.
