# Lafia Chat AI — UNICEF FemTech Ventures fit assessment

Source: <https://www.unicef.org/innovation/FemTechCall>
Reviewed: 9 November 2026
**Application deadline: 11 November 2026**

The full application pack, draft answers, budget and demo script are in
[`UNICEF_FEMTECH_APPLICATION.md`](UNICEF_FEMTECH_APPLICATION.md).

## What the call offers

- Up to **US$100,000** equity-free funding.
- **12 months** of technical mentorship.
- Access to UNICEF's global network, including government relationships.
- A place in the second FemTech Ventures cohort.
- Strong encouragement for **women-led startups and founders under 35**.

## Hard eligibility checks

| Requirement | Lafia status | Action before submitting |
| --- | --- | --- |
| Registered in a UNICEF programme country | `[TO CONFIRM]` — Nigeria is a programme country; confirm legal entity and CAC. | Provide registration details. |
| Functional prototype | **Yes** — local build with responsive UI, WHO runtime retrieval, citations, privacy controls and tests. | Deploy on HTTPS and record a demo. |
| Committed to open-source licensing and principles | **Yes** — public repository, MIT code, CC BY 4.0 docs/design, NOTICE for WHO. Secret history rewritten. | Rotate provider keys and purge old cached commit SHAs. |
| Uses frontier technology | **Yes** — generative AI + RAG + data science. | Explain architecture and model hosting. |
| Focus on girls' and women's health | **Yes** — maternal/newborn, contraception, menstrual health, adolescent and mental-health topics; women-first onboarding. | Keep the application focused on women and girls, not general health. |
| Safety-by-design | **Strong prototype** — required consent, no account, chats off by default, local-only saving, delete, Quick exit, local-only location, disclaimers. | Add DPIA, clinical governance and verified facility data before a pilot. |

## Fit against the three pillars

### Pillar 1 — Healthcare access for women and girls
**Fit: medium-high.** WHO maternal/newborn, pregnancy danger-sign,
contraception and newborn content; Find care and CHW call-back concepts.

**Gap:** it is an information and navigation tool, not a diagnostic, supply-planning
or point-of-care device. Do not overclaim this pillar.

### Pillar 2 — Informed, safe and accessible reproductive health
**Fit: strongest.** The call asks for *“AI-powered accessible platforms delivering
personalized reproductive health information and counselling in underserved
languages, especially for low-literacy and low-bandwidth environments.”*

Lafia now has:

- six-language UI: English, Kiswahili, Luganda, Acholi, Ateso, Lusoga;
- language-aware model prompting;
- voice input, and Listen output when the browser has a matching voice;
- cited WHO and document sources;
- a consent-first, no-account, private-by-default flow;
- Quick exit, delete-my-chats and local-only saving.

**Remaining gaps:** human review of low-resource translations, PWA/offline mode,
SMS/WhatsApp productisation, and measured comprehension in the field.

### Pillar 3 — Mental wellbeing, safety and protection
**Fit: medium.** Mental-health and adolescent-health topics and a private access
path. There is no screening, GBV referral or safeguarding workflow yet.

## Readiness snapshot

| Dimension | Score | Note |
| --- | --- | --- |
| Technology / prototype | 8/10 | Working, tested and documented. |
| Women's and girls' health focus | 8/10 | Women-first copy, topics and flow. |
| Low-resource / low-bandwidth readiness | 5/10 | Responsive browser UI; no PWA/offline or SMS yet. |
| Privacy, consent and safety-by-design | 8/10 | Strong prototype; DPIA and governance remain. |
| Open source and documentation | 9/10 | Clean public repo, licences, docs, tests and CI; key rotation pending. |
| Impact measurement | 2/10 | No baseline or field data yet. |

**Current overall: roughly 6.5/10 — a credible, well-documented prototype.**
With human-reviewed translations, a public repo, HTTPS deployment, verified
facilities and a small pilot, it can reach **8/10**.

## Highest-impact work before submitting

1. Confirm legal entity, country, CAC and women-led/under-35 status.
2. Rotate the exposed provider keys; the old repository has been deleted (`docs/SECRETS_AUDIT.md`).
3. Deploy on HTTPS; the repository is already public.
4. Replace placeholder facilities and the emergency number.
5. Human-review Acholi, Ateso and Lusoga strings and key health terms.
6. Record the 2–3 minute demo in `UNICEF_FEMTECH_APPLICATION.md`.
7. Name a clinical adviser and safeguarding contact.
8. Finalise the proposed budget and 12-month milestones.

## Information still needed from the team

- Country of registration and CAC number.
- Whether the company is women-led or has a founder under 35.
- Initial pilot geography, languages and CHW partners.
- Confirmation of the MIT / CC BY 4.0 split.
- Model hosting choice and data-processing terms.
- Clinical adviser and safeguarding contact.
