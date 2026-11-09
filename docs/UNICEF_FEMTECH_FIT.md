# Lafia Chat AI — UNICEF FemTech Ventures fit assessment

Source: <https://www.unicef.org/innovation/FemTechCall>
Reviewed: 9 November 2026
**Application deadline: 11 November 2026 — about 2 days away.**

## What the call offers

- Up to **US$100,000** equity-free funding.
- **12 months** of technical mentorship.
- Access to UNICEF's global network, including government relationships.
- A place in the second FemTech Ventures cohort.
- Strong encouragement for **women-led startups and founders under 35**.

## Hard eligibility checks

| Requirement | Lafia status | Action needed |
| --- | --- | --- |
| Registered in a UNICEF programme country | Likely yes if the company is registered in Nigeria. | Confirm CAC registration and country of incorporation. |
| Functional prototype | **Yes** — working chat app with document upload, WHO knowledge base, streaming answers and citations. | Record a 2-minute demo and deploy on HTTPS. |
| Committed to open-source licensing and principles | **Yes — MIT `LICENSE` added.** | Publish the repository publicly and add contribution/security docs. |
| Uses frontier technology (AI/ML/data science) | **Yes** — retrieval-augmented generation over uploaded documents plus a WHO knowledge base. | Explain the architecture and the model/hosting choices. |
| Focus on girls' and women's health | Partly — maternal/newborn, adolescent and sexual health, and mental health topics are included. | Reposition the product explicitly around women's and girls' health rather than general health. |
| Safety-by-design (privacy, consent, user risk) | **Strong prototype.** Required consent, private-by-default chats, device-only saving, delete-my-chats, Quick exit, local-only location, placeholder facilities and clear disclaimers. Supabase auth scaffold is not mounted. | Add per-user isolation if accounts are introduced; complete the Phase 1 items in `AUTH_AND_PRIVACY.md` before real-user deployment. |

## Fit against the three pillars

### Pillar 1 — Healthcare access for women and girls
**Fit: medium-high.** Lafia already carries WHO guidance on antenatal care, danger signs in pregnancy, postnatal care, immunization and newborn health. It can support continuity of care and CHW workflows.

**Gap:** it is an information assistant, not a point-of-care diagnostic or supply-planning tool. Do not overclaim this pillar.

### Pillar 2 — Informed, safe and accessible reproductive health
**Fit: strongest.** The call explicitly asks for:

> "AI-powered accessible platforms delivering personalized reproductive health information and counselling in underserved languages, especially for low-literacy and low-bandwidth environments."

Lafia is close to this: cited answers, a curated WHO corpus, a browser chat UI, and existing SMS/WhatsApp integration paths in the codebase. This is the best positioning.

**Gaps:** English-only, text-only, no local-language or voice output, no offline/low-bandwidth mode, no consent/privacy controls.

### Pillar 3 — Mental wellbeing, safety and protection
**Fit: medium.** WHO mental-health and adolescent-health topics are included, but there is no screening, safeguarding or GBV referral workflow.

## Overall readiness score

| Dimension | Score |
| --- | --- |
| Technology / prototype | 8/10 |
| Women's and girls' health focus | 6/10 |
| Low-resource and low-bandwidth readiness | 4/10 |
| Privacy, consent and safety-by-design | 5/10 |
| Open source and documentation | 7/10 |
| Impact measurement | 2/10 |

**Current overall: roughly 6/10 — a credible prototype with open-source and auth foundations, not yet a competitive FemTech application.**

With a focused 2-week sprint on privacy, local languages and positioning, this can realistically reach **7.5–8/10**.

## Recommended application positioning

> **Lafia Chat AI is a privacy-first, multilingual sexual and reproductive health companion for adolescent girls and women in low-bandwidth Nigerian communities. It turns trusted WHO guidance and locally approved materials into cited, conversational answers in local languages, and connects users to human care through WhatsApp and SMS.**

Do not lead with "general health chatbot". Lead with:

- adolescent girls and women;
- trusted, cited SRH and maternal-health information;
- Hausa, Yoruba, Igbo, Nigerian Pidgin and English;
- low-literacy and low-bandwidth design;
- privacy and consent by default;
- a bridge to CHWs and facilities, not a replacement for them.

## Highest-impact work before submitting

1. **Publish the repository** with the MIT `LICENSE` and `CONTRIBUTING.md` (licence already added).
2. **Finish auth**: add phone OTP, per-user document isolation and retention controls (Supabase scaffold is in place).
3. **Add one Nigerian language** end-to-end (Hausa or Nigerian Pidgin) and voice input/output for low literacy.
4. **Add a PWA/offline shell and SMS/WhatsApp fallback** for low bandwidth.
5. **Add red-flag triage and a human referral path** with local emergency numbers.
6. **Add basic impact metrics**: questions answered, sources cited, referrals triggered, language split, user satisfaction.
7. **Write a one-page clinical governance note**: who reviews content, how WHO/local guidance is approved, how incidents are handled.
8. **Deploy on HTTPS** with a real domain and record a demo video.

## Information still needed from the team

- Country of company registration and CAC number.
- Whether the company is women-led or has a founder under 35 (strongly encouraged).
- Which local languages and geographies to target first.
- Confirm the MIT / CC BY 4.0 split in `LICENSING.md` is acceptable to the company.
- Whether the model can be hosted in-country or must use a third-party API.
