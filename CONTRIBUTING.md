# Contributing to Lafia Chat AI

Thank you for helping build a safer, more useful health companion for women and
girls. This project is MIT licensed; docs and design are CC BY 4.0. See
`LICENSING.md`.

## Ground rules

- Be respectful and inclusive. Read `CODE_OF_CONDUCT.md`.
- Never commit real patient data, names, phone numbers, API keys or production
  credentials.
- Health content changes must cite a WHO or nationally approved source.
- Do not add features that diagnose, prescribe or promise a cure.
- Keep the default flow account-free and usable on low-end phones.
- Preserve the privacy promises in `docs/SAFETY_AND_PRIVACY.md`. If a change
  alters data collection or storage, update the docs and tests.

## Development

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Tests are offline and use `EMBEDDING_BACKEND=hash`:

```bash
ruff check app tests
pytest -q
```

## UI and i18n

- All interface strings live in `static/i18n/*.json`, never in HTML or JS.
- Add every new key to `en.json` first.
- Preserve placeholders such as `{distance}`.
- Low-resource translations need human review; see `docs/TRANSLATING.md`.
- Check phone (390px) and desktop (1280px) layouts.
- Every interactive target must be at least 44px; icon-only buttons need an
  accessible name.
- Avoid colours outside the tokens in `static/css/chat.css`.

## Privacy review

Before opening a PR that changes chat storage, location, voice or auth:

1. State what is stored, where and for how long.
2. Confirm Quick exit still clears memory and uses `location.replace`.
3. Confirm chats stay unsaved unless the user enables saving.
4. Add or update a manual check in `docs/SAFETY_AND_PRIVACY.md`.

## Pull requests

1. Describe the user need and the change.
2. Include screenshots for UI changes, with personal data redacted.
3. Run lint and tests.
4. Update the relevant docs.
5. Keep commits small and focused.

## WHO content

Do not paste WHO article text into the repository. The app fetches WHO pages at
runtime and caches them under `storage/who_cache/` (gitignored). See `NOTICE`.
