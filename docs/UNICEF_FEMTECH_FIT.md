# Lafia Chat AI — UNICEF FemTech Ventures fit assessment

Source: <https://www.unicef.org/innovation/FemTechCall>
Reviewed: 9 November 2026
**Application deadline: 11 November 2026**

The full application pack, application answers, budget and demo script are in
[`UNICEF_FEMTECH_APPLICATION.md`](UNICEF_FEMTECH_APPLICATION.md).

## What the call offers

- Up to **US$100,000** equity-free funding.
- **12 months** of technical mentorship.
- Access to UNICEF's global network, including government relationships.
- A place in the second FemTech Ventures cohort.
- Strong encouragement for **women-led startups and founders under 35**.

## Hard eligibility checks

| Requirement | Lafia status | Next milestone |
| --- | --- | --- |
| Registered in a UNICEF programme country | **Yes** — Nigeria is a UNICEF programme country; legal details are supplied in the application form. | Pilot partner and site selection. |
| Functional prototype | **Yes** — working build with responsive UI, runtime WHO retrieval, citations, privacy controls, tests, CI and CodeQL. | HTTPS demo deployment. |
| Committed to open-source licensing and principles | **Yes** — public repository, MIT code, CC BY 4.0 documentation/design and WHO attribution. | Contributor onboarding and localisation guide. |
| Uses frontier technology | **Yes** — generative AI, RAG and data science. | In-country/self-hosted model option. |
| Focus on girls' and women's health | **Yes** — maternal/newborn, contraception, menstrual health, adolescent and mental-health topics; women-first onboarding. | Clinical and community review of content. |
| Safety-by-design | **Strong prototype** — required consent, no account, chats off by default, local-only saving, delete, Quick exit, local-only location and clear disclaimers. | DPIA, clinical governance and verified facility data in the pilot. |

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
| Open source and documentation | 9/10 | Clean public repo, licences, docs, tests, CI and CodeQL. |
| Impact measurement | 2/10 | No baseline or field data yet. |

**Current overall: roughly 6.5/10 — a credible, well-documented prototype.**
With human-reviewed translations, a public repo, HTTPS deployment, verified
facilities and a small pilot, it can reach **8/10**.

## Focus for the next 90 days

1. Human-review Acholi, Ateso and Lusoga strings and key health terms.
2. Replace placeholder facilities and the emergency number with verified local services.
3. Deploy the demo on HTTPS and complete the 2–3 minute walkthrough.
4. Confirm the pilot geography, CHW partners and clinical adviser.
5. Complete a DPIA and safeguarding/incident process with the pilot partner.
6. Finalise the budget and 12-month milestones with UNICEF.

## Pilot design inputs

- Initial pilot geography and languages.
- CHW and facility partners.
- Clinical adviser and safeguarding contact.
- Model hosting choice and data-processing terms.
- Baseline/endline evaluation partners.
