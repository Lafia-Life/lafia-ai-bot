# Lafia Chat AI — UNICEF FemTech Ventures application pack

**Applicant:** Lafia
**Country:** Nigeria
**Call:** UNICEF FemTech Ventures, second cohort
**Prototype:** Working build; public repository and demo walkthrough
**Repository:** <https://github.com/egesamichael/lafia-ai-bot>
**Contact:** Project team via the UNICEF application form

> This pack describes the working prototype and the proposed 12-month programme.
> It separates what is live today from what the pilot will validate. Clinical
> validation and measured impact are planned outcomes, not claims made before
> the study.

---

## 1. One-page summary

**Problem.** Women and girls in low-resource settings often cannot get trusted,
private, understandable answers about their bodies, pregnancy, contraception,
menstrual health and mental wellbeing. Information is scattered, stigmatised,
English-first, and hard to use on low-end phones.

**Solution.** Lafia Chat AI is a privacy-first, multilingual health companion for
women and girls. It answers in plain language from WHO guidance and locally
approved documents, cites every source, and reads answers aloud. It needs no
account, name or phone number. Chats are off by default; the user can save them
only on her own device, delete them at any time, or leave instantly with Quick
exit.

**Innovation.** A retrieval-augmented generation (RAG) assistant designed around
safety and privacy rather than engagement: cited WHO sources, language-aware
answers, a consent-first flow, local-only location for care finding, and an
open-source, vendor-neutral architecture.

**Status.** A working prototype with a responsive three-screen interface,
six-language UI, runtime WHO ingestion, source citations, voice input, speech
output when a matching browser voice exists, privacy controls, Quick exit and a
placeholder find-care flow. Automated tests and CI are in place. The product is
not yet clinically validated or field-tested.

**UNICEF fit.** Strongest in **Pillar 2 — Informed, safe and accessible
reproductive health**, with adjacent value in **Pillar 1** (maternal and newborn
continuity of care) and **Pillar 3** (adolescent and maternal mental wellbeing).

---

## 2. Problem and target users

### Primary users

- Adolescent girls and women of reproductive age, especially those with low
  literacy or low digital confidence.
- Women in low-bandwidth or low-income settings who use a shared or borrowed
  phone.
- First-time mothers and pregnant women seeking antenatal and danger-sign
  information.
- Women who need private information about contraception, menstruation or
  mental wellbeing before speaking to a health worker.

### Secondary users

- Community health workers (CHWs) who need a fast, cited reference during
  household visits.
- Youth-friendly and primary-care clinics that want a trusted pre-consultation
  information channel.

### Why existing options fail

- Search results are not written for low-literacy readers and often omit local
  language.
- Generic chatbots invent answers and rarely show sources.
- Many tools require an account, phone number or app install.
- Sensitive questions carry stigma, so privacy and a fast exit matter.
- Connectivity is intermittent and data is expensive.

---

## 3. Product and user journey

### Screen 1 — Language and consent

- Language picker: English, Kiswahili, Luganda, Acholi, Ateso, Lusoga.
- Three plain-language privacy promises.
- Required acknowledgement: “Lafia gives general health information, not a
  diagnosis.”
- No account, name, phone number or email.

### Screen 2 — Chat

- Streaming answers in the chosen language.
- WHO and uploaded-document source chips.
- **Listen** button using the browser speech-synthesis voice for the chosen
  language, hidden when no matching voice exists.
- Voice input through the browser Speech Recognition API.
- **Quick exit** button and Escape-twice shortcut that open a neutral site and
  clear the session.
- Desktop **Sources** panel and **Your data** card.
- **Save my chats on this device** switch, off by default.
- **Delete my chats** control.

### Screen 3 — Find care

- One-time browser geolocation, used only on the device.
- Client-side distance calculation.
- Placeholder facility cards from `data/facilities.json` (to be replaced with
  verified local services).
- Community health worker call-back card.
- Emergency call button with a placeholder number.

---

## 4. Innovation and technical approach

- **Retrieval-augmented generation** over WHO pages fetched at runtime and
  organisation-uploaded documents.
- **Source-grounded answers** with inline citations and source cards.
- **Runtime WHO ingestion** so article text is not copied into the repository;
  only topic IDs, titles and canonical URLs are stored.
- **Language-aware prompting**: the selected language is passed to the model;
  the UI and speech layers use the same language code.
- **Privacy-first architecture**: no account required, chats not stored on the
  server, saving opt-in and browser-only, geolocation never transmitted.
- **Vendor-neutral model layer** through an OpenAI-compatible configuration
  (`LLM_PROVIDER`, `LLM_BASE_URL`, `LLM_MODEL`) so deployments can use a local or
  in-country model.
- **Open-source stack**: FastAPI, Chroma, vanilla JavaScript/CSS, tests with
  pytest and ruff.

### Architecture

```
Browser (phone or desktop)
  ├─ i18n JSON + responsive UI
  ├─ chat in memory by default
  ├─ local save only if the user opts in
  ├─ geolocation for distance, never transmitted
  └─ POST /api/chat
        └─ FastAPI
             ├─ Chroma retrieval (WHO runtime cache + uploaded docs)
             ├─ inline prompt to configured LLM
             └─ streamed answer + citations, no server persistence
```

---

## 5. Alignment with UNICEF FemTech Ventures

| UNICEF pillar | Lafia alignment | Evidence |
| --- | --- | --- |
| **Pillar 1 — Healthcare access for women and girls** | Maternal/newborn, pregnancy danger signs, antenatal and postnatal guidance; continuity-of-care information and CHW support. | `app/services/who_knowledge.py`, maternal/contraception topics, Find care screen. |
| **Pillar 2 — Informed, safe and accessible reproductive health** | Multilingual, cited SRH information in a low-bandwidth browser; consent-first; privacy controls; voice input/output. | Six-language i18n, Listen, Quick exit, privacy defaults, source citations. |
| **Pillar 3 — Mental wellbeing, safety and protection** | Mental-health and adolescent-health topics; safe, private access; referral to a health worker. | Mental-health topic, disclaimers, Find care. |

### Call requirements checklist

| Requirement | Status |
| --- | --- |
| Registered in a UNICEF programme country | **Yes** — Nigeria is a UNICEF programme country. Legal and registration details are supplied in the application form. |
| Functional prototype | **Yes** — working build with automated tests, CI and CodeQL. |
| Open-source licensing and principles | **Yes** — public repository, MIT code, CC BY 4.0 documentation/design, and WHO attribution. |
| Frontier technology | **Yes** — generative AI, retrieval-augmented generation and data science. |
| Safety-by-design | **Strong prototype** — consent, private-by-default chats, local-only saving, delete, Quick exit, local-only location and clear disclaimers. |

---

## 6. Product status

| Live now | Next | Later |
| --- | --- | --- |
| Responsive three-screen UI | Human-reviewed low-resource translations | Clinical validation |
| Six-language UI | PWA / offline shell | Real facility network |
| Language-aware answers | SMS and WhatsApp productisation | Independent security review |
| Runtime WHO fetch + heading-aware chunking | Per-user document isolation | Impact baseline and field study |
| Source citations and Listen | Production HTTPS and rate limiting | In-country model hosting |
| Privacy controls, delete, Quick exit | CHW call-back integration | Regulatory classification review |
| Find care with local-only distances | Impact dashboard and accessibility testing | — |
| 18 automated tests, CI and CodeQL | — | — |

---

## 7. Privacy, safety and data protection

### What is stored

| Data | Where | Default |
| --- | --- | --- |
| Language and consent | Browser `localStorage` | Yes (non-health settings) |
| Save-chats preference | Browser `localStorage` | Yes (boolean) |
| Chat messages | Browser `localStorage` | **No** — opt-in only |
| Chat messages | Server | **No** — streamed and discarded |
| Location | Browser memory | **No** — never sent or persisted |
| Uploaded documents | Server storage | N/A — currently shared, see limits |
| WHO text | Runtime cache (`storage/who_cache/`) | Runtime, gitignored |

### Safety behaviour

- Prominent “not a diagnosis” consent and footer.
- Answers are grounded in retrieved context; the model is instructed not to
  invent facts or citations.
- Danger-sign questions trigger urgent-care language.
- No prescribing or personalised dosage advice.
- Emergency and facility data are visibly marked as placeholders until verified.

### Known limits

- Uploaded documents are shared across users until per-user isolation lands.
- The configured LLM provider receives the question and retrieved context; a
  data-processing agreement or in-country model is required for sensitive use.
- Browser storage is not encrypted at rest.
- Low-resource translations need native-speaker and clinical review.
- No rate limiting, abuse detection, clinical governance or DPIA yet.
- WHO pages can change or be unavailable; runtime fetch may fail.

Full detail and verification checks: `docs/SAFETY_AND_PRIVACY.md`.

---

## 8. Open source and licensing

| Material | Licence |
| --- | --- |
| Source code | **MIT** — `LICENSE` |
| Documentation, UI copy, screenshots and design | **CC BY 4.0** — `LICENSE-DOCS.md` |
| WHO content | Not relicensed; fetched at runtime under WHO terms — `NOTICE` |
| Split and attribution | `LICENSING.md` |

### Repository governance

The public repository is at
<https://github.com/egesamichael/lafia-ai-bot>. Changes go through pull requests
with linear history. CodeQL, secret scanning and push protection are enabled.
Credentials are managed outside the repository; only `.env.example` is committed.

---

## 9. Clinical governance and content

- WHO is the primary source; local ministries and clinical partners can add
  approved documents.
- A clinical adviser, named in the application form, reviews:
  - danger-sign and referral language;
  - translated health terminology;
  - mental-health and adolescent content;
  - emergency and safeguarding pathways.
- Content changes require a cited source and clinical sign-off.
- The product is positioned as **information and navigation**, not diagnosis or
  treatment.
- The pilot partner and clinical adviser agree the safeguarding contact and incident process during inception.

---

## 10. Impact and measurement

### Theory of change

If women and girls can ask private, trusted questions in their own language and
receive cited answers plus a route to care, then they are more likely to
understand danger signs, act earlier, and reach a health worker.

### Proposed metrics

- Number of users and repeat users.
- Questions answered and share with at least one cited source.
- Language distribution and completion rate per language.
- Self-reported comprehension (“I understood the answer”).
- Self-reported action (“I contacted a health worker / went to a facility”).
- Find-care interactions and CHW call-back requests.
- Safety incidents and escalation rate.
- CHW time saved and perceived usefulness.
- Translation and clinical review coverage.

Targets will be finalised with pilot partners during inception.

### Measurement principles

- Collect the minimum necessary data.
- Aggregate by default; no individual health data in dashboards.
- Obtain consent for any follow-up survey or call-back.
- Report limitations alongside results.

---

## 11. 12-month plan and proposed use of funds

### Milestones

| Quarter | Focus | Outputs |
| --- | --- | --- |
| Q1 | Privacy and production readiness | Per-user isolation, DPIA, HTTPS, rate limits, public repo, verified facility data. |
| Q2 | Language and access | Human-reviewed translations, PWA/offline shell, SMS/WhatsApp pilot, accessibility testing. |
| Q3 | Field pilot | 2–3 sites, CHW training, user testing, referral workflow, safety monitoring. |
| Q4 | Evidence and scale | Baseline/endline evaluation, impact report, partnership plan, scale-up package. |

### Proposed budget (US$100,000)

| Category | Share | Amount | What it funds |
| --- | --- | --- | --- |
| Product and engineering | 30% | $30,000 | PWA/offline, low-bandwidth UX, SMS/WhatsApp, accessibility. |
| Privacy and security | 15% | $15,000 | Per-user isolation, DPIA, penetration test, rate limiting. |
| Clinical and content | 15% | $15,000 | Clinical adviser, translation review, local content governance. |
| Field pilot | 25% | $25,000 | Site support, CHW training, user testing, referral integration. |
| Monitoring and evaluation | 10% | $10,000 | Baseline/endline, qualitative research, dashboard. |
| Operations and compliance | 5% | $5,000 | Legal, hosting, partner coordination. |
| **Total** | **100%** | **$100,000** | |

This budget is a proposal for discussion and must be reconciled with the actual
team, partners and pilot geography.

---

## 12. Scalability and sustainability

- Open-source code lowers the cost of local adaptation and government review.
- Configurable model provider allows cloud, in-country or self-hosted deployment.
- Browser-first delivery works on low-end phones; SMS/WhatsApp can extend reach.
- The content layer can be localised by ministry and clinical partners.
- Potential sustaining models: public-health contracts, NGO licences, CHW
  training packages, and white-label deployments. These are hypotheses, not
  committed revenue.

---

## 13. Team and eligibility

Lafia is a Nigeria-based, founder-led team building a privacy-first health
companion for women and girls.

| Role | Responsibility |
| --- | --- |
| Product and strategy | Product direction, partnerships, programme delivery. |
| Engineering | FastAPI, retrieval, frontend, privacy engineering and deployment. |
| Clinical and content | Clinical review, referral language, danger-sign pathways. |
| Translation and community | Native-speaker review, community testing, CHW feedback. |
| Monitoring and learning | Baseline/endline design, qualitative research, impact reporting. |

Legal entity, registration and team CVs are supplied in the UNICEF application
form. Nigeria is a UNICEF programme country.

---

## 14. Risks and mitigations

| Risk | Mitigation |
| --- | --- |
| Hallucinated or unsafe answers | RAG-only context, citations, no-answer fallback, clinical review, urgent-care language. |
| Privacy breach or shared-device exposure | No account, chats off by default, local-only saving, delete, Quick exit, no server chat storage. |
| Sensitive data sent to a model provider | Configurable provider, DPA, in-country/self-hosted model option. |
| Low connectivity | PWA/offline shell and SMS/WhatsApp roadmap; current app is browser-first. |
| Translation errors | Native-speaker and clinical review; English fallback. |
| Wrong facility or emergency data | Clearly marked placeholders; verification is a launch gate. |
| Scope creep into diagnosis | Product positioning, prompt guardrails, disclaimers, clinical governance. |
| Open-source licence conflict | MIT/CC BY split documented; WHO content excluded; legal review before public release. |

---

## 15. Demo script (2–3 minutes)

1. Open the consent screen; point out the six languages and the required
   “not a diagnosis” checkbox.
2. Continue, ask “What are the danger signs in pregnancy?”; show the answer,
   WHO source chip, desktop Sources panel, and **Listen**.
3. Switch to Kiswahili; ask a short question; show the answer in Kiswahili.
4. Open **Find care**; use location; show distances and placeholder warning.
5. Show **Save my chats** off by default; enable, show local storage; delete.
6. Press Escape twice or **Quick exit**; show the neutral site and that Back does
   not return to Lafia.
7. Show `pytest`/`ruff`, the MIT and CC BY files, and the runtime WHO source file
   (metadata only).

---

## 16. Application-form answers

### Problem

Women and girls in low-resource settings face a trust and access gap: health
information is scattered, English-first, stigmatised and hard to use on low-end
phones. Generic chatbots invent answers, rarely cite sources, and often require
an account or phone number. This is especially acute for sensitive reproductive
and maternal-health questions.

### Solution

Lafia Chat AI is a privacy-first, source-cited health companion for women and
girls. Users choose a language, consent to information-only use, and ask a
question. Lafia answers from WHO guidance and locally approved documents, shows
the sources, and can read the answer aloud. It needs no account, saves nothing
by default, and offers a one-tap Quick exit.

### Innovation

Lafia combines RAG over runtime-fetched WHO guidance with language-aware
prompting, citations, low-literacy UI and privacy-by-design. Runtime WHO fetching
avoids relicensing content; a configurable OpenAI-compatible model layer allows
in-country or self-hosted deployment; the code is MIT licensed.

### Traction

A working prototype exists with a responsive three-screen UI, six-language
interface, source citations, voice input, conditional speech output, privacy
controls, Quick exit, local-only care distances, 17 automated tests and CI.
Clinical validation, field pilots and measured impact are next.

### Impact

If women and girls can ask privately, understand the answer and see a route to
care, they can recognise danger signs earlier and reach help sooner. We will
measure comprehension, reported action, language coverage, source citation and
referral interactions, with aggregate and consent-based data only.

### Use of funds

The US$100,000 would fund privacy and production hardening, human-reviewed
translations, PWA/offline and SMS/WhatsApp access, a clinical/content review
process, a 2–3 site field pilot, and an independent baseline/endline evaluation
over 12 months.

---

## 17. Application readiness

| Item | Status |
| --- | --- |
| Public repository with MIT / CC BY licensing | Ready |
| Working prototype and demo walkthrough | Ready |
| Privacy, safety and security documentation | Ready |
| 12-month plan and US$100,000 budget | Ready |
| Automated tests, CI and CodeQL | Ready |
| Legal, registration and team CVs | Supplied in the application form |
| Pilot partner and clinical adviser | Named during inception |

## 18. Evidence map

| Evidence | File |
| --- | --- |
| Product overview and setup | `README.md` |
| Privacy promises and manual checks | `docs/SAFETY_AND_PRIVACY.md` |
| Auth and retention plan | `docs/AUTH_AND_PRIVACY.md` |
| Translation policy | `docs/TRANSLATING.md` |
| Security policy | `SECURITY.md` |
| UNICEF fit assessment | `docs/UNICEF_FEMTECH_FIT.md` |
| Licence split | `LICENSING.md`, `LICENSE`, `LICENSE-DOCS.md` |
| WHO attribution and reuse terms | `NOTICE` |
| Screenshots | `docs/screenshots/` |
| Automated tests | `tests/` |
| CI | `.github/workflows/ci.yml` |
| Placeholder facilities | `data/facilities.json` |
