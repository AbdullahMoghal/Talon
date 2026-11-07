# Talon — Scam Taxonomy

Nov 7, 2026

## Summary

T-Mobile is not releasing a dataset, taxonomy or baseline for the Safe Signal track, so this taxonomy is ours. It has 15 scam categories plus a legitimate class with 9 subtypes. The machine-readable version in [data/taxonomy.json](../data/taxonomy.json) is the source of truth; this page explains it.

Each category drives four things in Talon:

1. **Triage label:** what the classifier predicts.
2. **Decoy tactic:** how the canary keeps the scammer talking and gets indicators out of them.
3. **Indicators to expect:** what extraction looks for.
4. **Customer next steps:** what the customer shield tells a real customer to do.

## Where the categories come from

The categories are grounded in public T-Mobile data, so judges from T-Mobile should recognize them.

| Source | What it tells us |
| --- | --- |
| T-Mobile 2023 Scam and Robocall Report | Healthcare scams (Medicare, health insurance) are over 40% of scam attempts and financial scams almost 20%, both targeting adults 55+. Retail (Amazon, Walmart) and delivery (UPS, FedEx, USPS) impersonation peak around the holidays. Tax season, back to school and open enrollment are peak seasons. TX, CA, FL, NY and NC are hit hardest. Vehicle warranty scams nearly disappeared in 2023. |
| T-Mobile 2021 Scam Shield Report | Impersonation of Social Security (10%), wireless carriers (9%), car insurance (6%) and package delivery (4%). |
| T-Mobile scam help page | Forward spam to 7726, Scam Block (#662#), and change your T-Mobile ID password if you opened a link. |
| Public reporting on T-Mobile-themed texts | Fake reward points expiring, fake outage compensation, fake "suspicious activity" alerts, and port-out scams. |

T-Mobile's shares are for **calls**, and texts skew more toward delivery, bank and toll lures. The weights below blend the two and are our estimates, not measured shares. We say this openly in the pitch.

We left out vehicle warranty scams, because T-Mobile's data shows they nearly disappeared.

## Scam categories

Weight is the category's share of the scam messages we generate (see [DATA_SPEC.md](DATA_SPEC.md)).

| ID | Category | Weight | Main harm | Typical lure |
| --- | --- | --- | --- | --- |
| `health_insurance` | Medicare and health insurance | 0.15 | Personal info, money | "Your new Medicare card requires verification" |
| `bank_fraud_alert` | Fake bank fraud alert | 0.11 | Credentials, money | "Suspicious charge of $849. Reply or call now" |
| `package_delivery` | Package delivery | 0.08 | Money, credentials | "Package on hold. Pay $1.99 redelivery fee" |
| `carrier_impersonation` | Carrier impersonation and SIM swap | 0.08 | Credentials, account takeover | "Your T-Mobile reward points expire today" |
| `government_impersonation` | Government impersonation | 0.07 | Personal info, money | "IRS: your refund is pending verification" |
| `toll_fee` | Unpaid toll or fine | 0.06 | Money, credentials | "Unpaid toll balance. Pay today to avoid a late fee" |
| `retail_order` | Retail order or refund | 0.06 | Credentials, money, device access | "Your order of an iPhone 17 has shipped. Not you? Call..." |
| `account_security` | Tech support and account lockout | 0.06 | Credentials, device access | "Your account was locked after a sign-in from a new device" |
| `job_task` | Job and task scams | 0.06 | Money, personal info | "Earn $300/day with simple online tasks" |
| `investment_crypto` | Investment and crypto | 0.06 | Money | "Join our VIP group: 30% weekly returns" |
| `wrong_number_romance` | Wrong number and romance | 0.05 | Money | "Hi Jessica, are we still on for dinner?" |
| `family_emergency` | Family emergency | 0.05 | Money | "Hi Mom, I dropped my phone, this is my new number" |
| `prize_lottery` | Prize, lottery and giveaway | 0.05 | Money, personal info | "You've won a $500 gift card. Claim before midnight" |
| `debt_loan` | Debt relief and loans | 0.03 | Money, personal info | "You're pre-approved for student loan forgiveness" |
| `charity_disaster` | Fake charity and disaster relief | 0.03 | Money | "Help hurricane victims now. Donate via Cash App" |

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
| `phone` | `(214) 555-0147` |
| `email` | `support@refund-desk.example` |
| `wallet` | A crypto address in the right format that can't receive funds |
| `payment_handle` | `$HelpDesk2291` |
| `account` | A fake bank account and routing number |
| `giftcard_ask` | "Buy three $200 gift cards and send the codes" |
| `remote_access_id` | A remote-support session ID |
| `brand` | The organization impersonated, such as "USPS" |

## Decoy tactics

The decoy agent picks from these tactics based on the category. Each tactic is meant to make the scammer reveal another indicator.

| Tactic | What the canary does |
| --- | --- |
| `play_confused` | Misunderstands on purpose so the scammer repeats and restates details |
| `ask_callback_number` | Asks for a number to call back |
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
