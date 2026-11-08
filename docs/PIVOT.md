# Talon pivot proposal: "Let Talon handle it"

Nov 7, 2026 · **Adopted** (Nov 7, 2026). PRD.md and ARCHITECTURE.md now follow this model.

## Summary

**Every scam text is an invitation. Talon accepts it.**

When a customer receives a scam, they tap **"Let Talon handle it."** Talon's agent takes over that conversation with the customer's consent. It extracts the scammer's payment method, callback numbers and links, burns the campaign network-wide, warns every other customer the campaign is hitting, and shows the original customer the impact they had.

The engine stays the same (triage, handler, persona, safety guard, extraction, campaigns, Nemotron). What changes is **where conversations come from** and **who the customer is in the story**: from target to the person who caught the scammer.

## Why pivot

The weak spot in every honeypot (O2's Daisy, Apate.ai, T-Mobile's new honeypot program, our own canaries) is the same: **you have to attract scammers to decoy numbers.**

T-Mobile customers already receive billions of scam texts a year. Each one is a scammer actively starting a conversation, and today all of them get blocked and thrown away. The pivot turns each one into a possible takeover, so scale comes for free.

Canaries don't go away. They become the second source: "Talon also runs decoy numbers, but customers are its biggest source."

## How it scores

| What judges look for | Canary Network (about 8/10) | "Let Talon handle it" (aiming for 10/10) |
| --- | --- | --- |
| Creativity | Honeypots already exist | Victims start the takeover themselves. Nobody does this. |
| Impact | Depends on scammers finding decoy numbers | Every scam text received becomes a possible takeover |
| Usability | Customers mostly never see it | One tap, and a reward the customer can feel |
| Security and privacy | Fake decoy identities | Only starts with an explicit tap. The agent never uses the customer's real details. The scammer already had the number. |
| Detection accuracy | Measured on the gold set | Same, plus each customer tap is a free, high-quality label |
| Education | Not much | The customer sees the scammer's whole playbook play out on someone who can't be hurt |
| Nemotron "beyond a chatbot" | Decoy agent | Multi-agent takeover with tools, campaign memory and a scored self-play arena |

The human story is the difference. Judges remember "a grandmother tapped a button and took down a scam ring" far longer than "we have AI decoys."

## Customer flow

1. A scam text arrives. Talon shows: *"Likely toll scam, 92% confidence. Fake E-ZPass. Real tolls never ask for payment by text."* with **[Delete] [Report] [Let Talon handle it]**.
2. The customer taps **Let Talon handle it**. Talon's persona replies from then on: slow, confused, cooperative. The customer can stop it at any time with one tap.
3. Talon's handler plans each turn ("We have their link. Need: payment method. Tactic: say the card was declined."), and the persona writes the reply. Every reply passes the safety guard.
4. Extracted details link the conversation to a campaign. The campaign burns, and other customers receiving it are warned or blocked.
5. The customer gets an **impact card**: *"The scammer who texted you was running a toll scam that hit 3,412 T-Mobile customers. You helped shut it down. Here's what they were after."*

## Demo (3 minutes, judges take part)

1. **A judge plays the scammer.** They call our Twilio number, which plays the "customer's phone," or text from a scammer console on a tablet, using a scam card with fictional details.
2. **The customer's phone (on the big screen) lights up** with the warning and the three buttons.
3. **The presenter taps "Let Talon handle it."** The judge keeps going, and replies now come from Talon's persona. The dashboard shows the agent's plan live.
4. **The judge gives the wallet from the card.** It appears in the extraction panel, a tripwire is issued, and the campaign burns.
5. **A second customer phone** receives the same scam and it's blocked on arrival: *"Talon shut this campaign down 40 seconds ago, thanks to a customer in Dallas."*
6. **The first customer gets the impact card.**
7. **The metrics panel:** beats the baseline on the independent gold set, 0 leaks in 75 attack attempts, X% of details extracted.

Every judging criterion appears on screen, and a judge was part of it.

## What changes in the build

| Change | Effort |
| --- | --- |
| Customer phone screen: 3 buttons and a "Talon took over" state | 1–2 h |
| "Takeover session" replaces "canary": a conversation that starts from a real inbound scam, with a generic persona that never uses the customer's real details | ~1 h (mostly renaming) |
| Impact card ("you helped stop a campaign that hit N customers") | 1 h |
| Second customer phone showing the auto-block | 30 min |
| Voice: the presenter taps "Let Talon answer" on an incoming scam call; Twilio ConversationRelay answers as the persona | ~3 h |
| Self-play arena: a scammer agent vs Talon, scored by a Nemotron judge (yield, leaks, turns). Hits the Nemotron track's "simulation and eval" directly | 2 h |

## Risks and answers

- **Live SMS is risky.** US carriers block texts from unregistered business numbers (A2P 10DLC registration takes days). Do the text side through a scammer console web page, and use a real phone call for the live voice moment. Calls don't need that registration.
- **"Isn't replying as the customer impersonation?"** It's the customer's own line, with their explicit consent, and the persona invents every detail. Say this in the pitch before a judge asks.
- **False positives:** Talon never takes over on its own. Only a customer tap starts it. That also covers the "honest confidence" requirement.
- **Abuse limits:** cap turns per takeover, never send outbound links, files or code, and stop at any time with one tap.

## Pitch line

> **"Scam protection has always meant hanging up. Talon lets every customer fight back with one tap, and every scam they hand us protects the next person."**

## Decision needed

- [x] Do we adopt the pivot? Yes.
- [x] PRD and ARCHITECTURE updated (takeover session, customer buttons, impact card); the SpacetimeDB module has the matching tables. PR #4 was closed.
