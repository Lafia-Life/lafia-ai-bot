# Lafia Chat AI — Authentication and Privacy Plan

## Current state (honest baseline)

| Area | Today | Risk |
| --- | --- | --- |
| Accounts | **No account required in the UI.** A Supabase Auth scaffold exists in the backend but is not mounted. | OTP, per-user isolation and auth UI are future work. |
| Chat history | **Not saved by default.** Saved only in the browser when the user enables "Save my chats"; "Delete my chats" removes it. | Shared-device risk if saving is enabled. |
| Uploaded documents | Stored on the server and searchable by every user. | One user's document can appear in another user's answers. |
| LLM calls | Sent to the configured provider (DeepSeek/OpenAI). | Prompt text leaves the server. Not suitable for sensitive data without a DPA. |
| Transport | HTTP on `0.0.0.0:8000` in local/dev. | Must be HTTPS in production. |
| Logs | Access logs contain paths, not message bodies. | Verify no prompt/answer logging in production. |

**Conclusion:** the current build is a functional prototype with an auth foundation. It is **not yet ready** for real patients' sensitive reproductive-health data until per-user isolation, OTP and retention controls are finished.

Implementation lives in `app/services/supabase_auth.py` and the `/api/auth/*` routes. Tokens are held in HttpOnly cookies, never in browser JavaScript. The current three-screen UI deliberately exposes no sign-up form, so no name, phone number or email is requested.

## Recommended auth architecture

Use **passwordless phone/email OTP** as the primary login. It is low-friction, works on low-end phones, and avoids password reuse.

```
User -> phone/email OTP -> signed HttpOnly session cookie
                              |
                              +-- user_id
                              +-- consent_version
                              +-- role (user | chw | admin)
```

- Session cookies: `HttpOnly`, `Secure`, `SameSite=Lax`, 30-day rotation, server-side session table.
- Add CSRF protection on state-changing routes.
- Rate-limit OTP requests and chat requests per user/IP.
- Store only a hash of OTPs and sessions.
- Optional later: Google/Apple sign-in and passkeys.

## Data isolation model

Every user-owned row gets a `user_id`:

- `documents.user_id`
- `conversations.user_id`
- `messages.conversation_id`
- `consents.user_id`

Retrieval must always filter `where={"user_id": current_user.id}` plus a separate `shared=true` corpus for WHO guidance. Never retrieve across users.

Chroma metadata should include `user_id`; the query wrapper must enforce the filter server-side, not in the prompt.

## Consent and safeguarding

Before the first message, show a short consent screen:

1. What Lafia is and is not (information, not diagnosis).
2. What data is stored, where, and for how long.
3. Whether the model provider processes the text.
4. How to delete data and withdraw consent.
5. Emergency guidance and local emergency numbers.

Add:

- Age gate / adolescent-appropriate mode.
- Red-flag detection with a clear "go to a health facility now" response.
- Human escalation path (CHW callback or facility referral).
- Content review by a local clinical adviser.
- A named safeguarding contact.

## Retention and user rights

- Default chat retention: **0 days on the server** (browser only) until users opt in to saved history.
- If saved: configurable retention (e.g. 30/90 days), auto-delete job, export and delete endpoints.
- "Delete my account" removes documents, vectors, sessions, and consent records within 30 days.
- Keep a minimal, content-free audit trail (login, delete, consent changes).

## Encryption and hosting

- HTTPS/TLS everywhere; HSTS.
- Encrypt uploaded files and the vector database at rest (disk encryption or application-level envelope encryption).
- Separate production and analytics databases.
- Prefer in-country or regionally hosted infrastructure.
- Offer an on-prem/open-weight model option (e.g. Ollama) for deployments that cannot send health text to a third party.

## Regulatory alignment

- Nigeria Data Protection Act 2023 / NDPR.
- UNICEF data protection and safeguarding principles.
- GDPR-style rights if any EU users are served.
- Complete a DPIA before real-user deployment.
- Publish a plain-language privacy notice and retention policy.

## Suggested delivery phases

**Phase 1 — 1 to 2 weeks (before any real-user pilot)**
- OTP auth, sessions, consent screen, per-user document isolation.
- HTTPS deployment, rate limits, delete-my-data.
- Disable provider logging / sign a DPA.

**Phase 2 — 4 to 6 weeks**
- Encrypted storage, retention jobs, audit log, safeguarding and escalation flows.
- Age-appropriate content paths and clinical review.

**Phase 3 — 8 to 12 weeks**
- CHW roles and dashboards, passkeys/OAuth, on-prem model option, independent security review.
