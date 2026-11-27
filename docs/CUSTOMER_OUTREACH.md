# Customer outreach that people are glad to get

What Manifest follows when it finds a founder's first customers and writes to them: the evidence behind each rule, where code enforces it (`backend/app/services/ideas/outreach.py`), and where the agent skill and prompts carry it (`agent-plugin/skills/manifest-customers/SKILL.md`, the voice prompt in `backend/app/services/voice/live/bot.py`). The flow itself is ADR 0018 (research to drafts) and ADR 0026 (drafts to Messages, sent on a yes).

The aim of a first message is to **learn how one real person handles a problem today**, not to sell. Most of the cold-email data below is published by email vendors and is not peer-reviewed; treat the numbers as direction, not law. Opinions are marked.

## Choosing who to write to

| Rule | Evidence | Where |
|---|---|---|
| Write to people who lived the problem recently. Ask about their life and past behaviour, not your idea. | The Mom Test ([summary](https://mtlynch.io/book-reports/the-mom-test/)) | skill |
| Each batch tests a stated assumption about a segment. | Steve Blank, [customer development](https://en.wikipedia.org/wiki/Customer_development) | research segments |
| Recruit by hand, one person at a time, early on. | Paul Graham, [Do things that don't scale](https://paulgraham.com/ds.html) | flow |
| Strongest need signals: their own public words about the problem, time or money already spent (a job listing, a workaround), a recent trigger. Being in the industry is not evidence. | Mom Test "what are they doing about it now" (opinion: derived) | skill; score gives 0 for need without a sourced item |
| One specific, work-related fact per person. About five minutes of research is enough. | [Gong](https://www.gong.io/resources/labs/does-cold-email-even-work-any-more-heres-what-the-data-says/) (opinion: the time cap) | skill |
| Nothing personal or intrusive. 53% of B2B buyers said personalization did more harm than good. | Gartner, via [Autobound](https://www.autobound.ai/blog/how-writing-style-impacts-sales-email-performance) (secondhand) | skill, prompt |
| Prefer the person closest to the pain. C-level executives are about 30% less likely to reply. | [Gong](https://www.gong.io/blog/do-execs-really-reply-to-cold-email-here-s-what-the-data-says) | skill |
| An address is used only if it's really found. That means a public page showing it (Manifest reads the page), a provider that verified it, or the founder's word. Never a guessed pattern. | trust rule | code: `_verify_contacts`, `set_recipient` |

## The first message

| Rule | Evidence | Where |
|---|---|---|
| 40–90 words (hard limits 25–150). | [Hunter, 34M emails](https://hunter.io/blog/cold-email-word-count): 20–39 words had the best reply rate. Gong: under 100 words, 3–4 sentences. | code: `check` |
| Plain words, short sentences. | Lavender: reading grade 3–5 got 67% more replies (secondhand) | prompt |
| Subject of 2–6 plain words. Never "Re:"/"Fwd:", a question, a number or a pitch. | Reply.io and Hunter (snippets), Gong. CAN-SPAM forbids deceptive subjects. | code: Re/Fwd refused, long subjects noted |
| The first line is the true, specific reason for writing. No "I hope this finds you well". | opinion, from the personalization data | code: stock openers refused |
| Say who's writing, that it's early and that it's not a pitch. Never pose as a student or a writer, and never claim past contact. | Gong: pitching in a cold email cuts replies by up to 57%. CAN-SPAM requires honest identification. | code: invented familiarity refused; prompt |
| One question, low friction. An interest ask beats asking for a meeting. | [Gong, 304k emails](https://www.gong.io/resources/labs/this-surprising-cold-email-cta-will-help-you-book-a-lot-more-meetings/) | prompt; several questions noted |
| Plain text, no images or tracking, at most one link. | Woodpecker: plain text got about 42% more clicks (secondhand) | sent as plain text; extra links noted |
| An easy way to say no, and the sender's name. | CAN-SPAM opt-out; courtesy | code: `finish` adds both if missing |
| No hype or urgency words. | Gong on buzzwords; the word list itself is opinion | code: refused list |

## Follow-ups

- One or two follow-ups, never more than three, at least 2–3 days apart. Manifest waits 5 days. A first follow-up lifts replies from about 9% to 13% ([Woodpecker](https://woodpecker.co/blog/follow-up/follow-up-statistics/)), and later ones add little ([benchmark](https://woodpecker.co/cold-email-benchmark/)).
- Each one is shorter, adds something new and offers to stop. Never "just bumping this".
- Stop at once on any "no", and exclude that person.

## Replies

- Aim for a commitment or a next step: their time, an introduction, or money. A conversation with no next step taught nothing (Mom Test).
- Relay faithfully. Keep their words separate from your interpretation. Compliments, generic claims and feature requests are not evidence. Say "they said X", never "they want X", unless they committed to it. Manifest stores the reply verbatim as an `external_claim`, with the email as its source, and strips the quoted original.
- Common answers:
  - "Tell me more": two sentences on what you're exploring, then ask how they handle it today.
  - Pricing: honest that it isn't set. Ask what it costs them now.
  - "Not now": ask whether you can check back at a date they choose.
  - "Not interested": a one-line thanks and no more messages.
  - A referral: ask for the intro, and ask who else you should talk to.

## Law (not legal advice)

- **US (CAN-SPAM)** covers B2B too. It requires an accurate From line, an honest subject, a postal address and an opt-out for commercial email. A message whose main purpose is research may not be commercial, but the line is unsettled, so the message always identifies the sender and offers an opt-out. If a founder's message promotes a product, they should add a postal address. ([FTC guide](https://www.ftc.gov/business-guidance/resources/can-spam-act-compliance-guide-business))
- **UK (PECR / UK GDPR):** companies can be emailed without prior consent, but sole traders count as individuals. Always identify yourself and honour objections. ([ICO](https://ico.org.uk/for-organisations/direct-marketing-and-privacy-and-electronic-communications/guide-to-pecr/electronic-and-telephone-marketing/electronic-mail-marketing/))
- **EU:** national rules apply, and some countries (such as Germany) need consent. Opinion: don't cold-email EU individuals without local advice.
- **India:** the DPDP Act treats a named person's email as personal data. Take advice before scaling.
- **Google/Yahoo bulk-sender rules** apply above 5,000 a day. They don't apply to a handful of 1:1 emails, but messages go from the founder's own authenticated mailbox anyway.

Manifest sends one message per person from the founder's own mailbox or Open Media account, only after the founder approves that exact message. It never sends in bulk.
