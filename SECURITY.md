# Security policy

Lafia handles sensitive health questions. Please report security issues
privately.

## Reporting

Contact the repository owner through GitHub or the security contact published in
the repository profile. Do not open a public issue containing a secret, personal
health information or an exploitable detail.

Include:

- affected endpoint or component;
- steps to reproduce;
- impact (data exposure, auth bypass, prompt injection, etc.);
- any suggested fix.

We aim to acknowledge reports within 72 hours.

## Current posture

- The default UI requires **no account, name or phone number**.
- Chat messages are not persisted on the server. The previous in-memory answer
  cache was removed.
- Chat history is stored in the browser only when the user enables "Save my
  chats"; "Delete my chats" removes it.
- Quick exit clears in-memory chat state and uses `location.replace`.
- Location is used once in the browser for distance calculation and is never
  sent or stored.
- WHO text is fetched at runtime; no WHO article text is committed.
- Secrets are expected in environment variables only. `.env` is gitignored.

## Known gaps

- Uploaded documents are still shared across users; per-user isolation is not
  implemented.
- The configured LLM provider receives the question and retrieved context. Use a
  suitable data-processing agreement or an in-country/self-hosted model.
- No rate limiting, abuse detection or CSRF hardening on the auth endpoints yet.
- Supabase auth is scaffolded but not mounted in the UI.
- Browser localStorage is not encrypted and may be readable on a shared device.
- Facility data is placeholder and must be verified before launch.

See `docs/SAFETY_AND_PRIVACY.md` and `docs/SECRETS_AUDIT.md`.

## Before a public deployment

1. Rotate the credentials listed in `docs/SECRETS_AUDIT.md` and purge history.
2. Add HTTPS and set `AUTH_COOKIE_SECURE=true` if auth is enabled.
3. Add server-side rate limiting and per-user document isolation.
4. Complete a data protection impact assessment.
5. Add clinical governance and a named safeguarding contact.
