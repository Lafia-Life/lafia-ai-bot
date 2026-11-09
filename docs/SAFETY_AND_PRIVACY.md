# Safety and privacy

Lafia Chat AI is a prototype for women and girls. It provides general health
information, not a diagnosis, prescription or emergency service.

## Data flow

```
Browser (phone or desktop)
  ├─ language + consent preference ── localStorage (non-health settings)
  ├─ chat messages ─────────────────── memory only by default
  │                                   localStorage only if "Save my chats" is ON
  ├─ geolocation ───────────────────── memory only; haversine distances computed in JS
  ├─ facilities ───────────────────── fetched once from /data/facilities.json
  ├─ speech synthesis ─────────────── browser API, no network call by Lafia
  └─ POST /api/chat ─────────────────► FastAPI
                                        ├─ retrieval from local Chroma
                                        ├─ inline prompt to configured LLM provider
                                        └─ streamed answer; nothing persisted
```

The server does not persist conversations. The previous in-memory answer cache
was removed so repeated questions are not retained server-side.

## What is stored

| Item | Where | By default | Notes |
| --- | --- | --- | --- |
| Language choice | Browser localStorage | Yes | Non-health preference. |
| Consent record | Browser localStorage | Yes | `accepted`, version and timestamp. |
| Save-chats preference | Browser localStorage | Yes | Boolean. |
| Chat messages | Browser localStorage | **No** | Only when the user turns saving on. |
| Chat messages | Server | **No** | Streamed and discarded. |
| Location | Browser memory | **No** | Never sent, never persisted. |
| Uploaded documents | Server storage | N/A | Currently shared; see known limits. |
| WHO text | Server cache (`storage/who_cache`) | Runtime | Gitignored; not committed. |

## Privacy promises → verification

| Promise | Implementation | Automated test | Manual check |
| --- | --- | --- | --- |
| No account, name or phone required | Chat and care screens work without auth; auth UI is not mounted | `test_health_and_bootstrap_need_no_account` | Open in a private window and use the full flow. |
| Chats are not saved by default | Save switch defaults off; `localStorage` not written while off | `test_no_server_side_answer_cache`; code review of `saveChatsIfEnabled` | DevTools → Application → Local Storage: no chat entry after a conversation. |
| Saved chats stay on this device | Only `localStorage` is used; no server write | Code review; no chat persistence endpoint | Turn saving on, chat, inspect Network: no chat payload to server. |
| Delete my chats removes them | Removes `lafia.chats.v1` and clears memory | Manual only | Save a chat, delete it, refresh, confirm it is gone. |
| Quick exit clears and cannot be reached with Back | Clears memory, removes saved chats, calls `location.replace` | Manual only | Press Escape twice; confirm neutral site; press Back. |
| Language sent to model | `ChatRequest.language`; prompt says “Reply in …” | `test_language_is_passed_to_prompt` | Switch to Kiswahili and ask a question. |
| Listen uses browser speech and hides when unavailable | `speechSynthesis`; button hidden if no matching voice | Manual only | Choose a language with no installed voice; Listen disappears. |
| Location is never sent or stored | `navigator.geolocation` + client-side haversine only | Code review of `useLocation`/`renderFacilities` | DevTools → Network: no coordinates in requests. |
| Find-care data is placeholder | `data/facilities.json` marked `placeholder: true` | `test_facilities_are_served_and_placeholders` | Review the file before launch. |
| No diagnosis; urgent care for danger signs | System prompt and UI disclaimer | Manual conversation review | Ask about chest pain, heavy bleeding, difficulty breathing. |
| WHO text is not committed | Runtime fetch; metadata only in code | `test_who_topics_contain_metadata_only` | Search the repo for long WHO passages. |

## Known limits

1. **Uploaded documents are shared.** The current document index is not scoped
   per user. Do not upload personal medical records to a shared deployment.
2. **The LLM provider sees the question and retrieved context.** Use a provider
   with suitable terms, or an in-country/self-hosted OpenAI-compatible model.
3. **Browser storage is not encrypted at rest.** On a shared device, anyone with
   access to the browser profile could read saved chats. Saving is opt-in and
   deletable, but not a secure vault.
4. **Translations are machine-drafted.** Acholi, Ateso and Lusoga need human
   review; see `docs/TRANSLATING.md`.
5. **Facilities, hours and numbers are placeholders.** They must be replaced
   with verified local services.
6. **WHO pages can change or be unavailable.** Runtime fetching may fail; the
   app falls back to a local runtime cache or uploaded documents.
7. **No rate limiting or abuse detection yet.** Add before a public pilot.
8. **No clinical governance.** A local clinical adviser should review content,
   referral language and red-flag behaviour before launch.
9. **Supabase auth is optional and not mounted in the UI.** The default flow is
   account-free. If auth is enabled later, add per-user data isolation first.

## Emergency behaviour

The UI tells users that Lafia is not a diagnosis and directs them to a health
worker for danger signs. The emergency button uses a **placeholder** number
(`112`) from `data/facilities.json`. Verify the correct local number before
launch. Do not promise emergency response capability.

## Reporting a privacy issue

Follow `SECURITY.md`. Do not open a public issue containing personal health data.

## Verification run (9 November 2026)

Automated browser checks against the local build:

- Fresh consent → `localStorage` contained only `lafia.consent.v1`; no chat key.
- With saving **off**, a completed answer did not create `lafia.chats.v1`.
- With saving **on**, one exchange stored 2 messages in this browser only.
- “Delete my chats” removed `lafia.chats.v1` and all visible messages.
- Quick exit navigated to `https://www.google.com/` via `location.replace`; the
  chat key remained absent.
- Geolocation override near the placeholder facilities produced distances of
  0.0, 1.6 and 2.9 km with **zero** network requests containing coordinates.
- `pytest` and `ruff` pass locally and in CI configuration.
