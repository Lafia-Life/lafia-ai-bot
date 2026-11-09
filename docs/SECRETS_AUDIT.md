# Secrets audit

Audit date: 9 November 2026
Scope: current working tree and local git history of this repository.

No secret values are reproduced in this document.

## Clean replacement repository

On 9 November 2026 the rewritten history was pushed to a new public repository:

- **New repository:** <https://github.com/Lafia-Life/lafia-ai-bot>
- **Default branch:** `master`
- **Branches:** `master` and `add_voice_feature`
- **Secret scanning / push protection / Dependabot:** enabled
- **Current refs:** 0 matches for the audited secret patterns

The old `egesamichael/chatlearning` repository was **deleted on 9 November
2026**. Its old repo URL, old commit URLs and secret-scanning alert now return
HTTP 404. The clean replacement is the only repository.

## Remediation performed on 9 November 2026

- Backed up the pre-rewrite repository to a local bundle outside the repo.
- Rewrote all local refs with `git filter-repo --replace-text`:
  - DeepSeek key literals → `REDACTED_LLM_KEY`
  - Africa's Talking key literals → `REDACTED_AFRICAS_TALKING_KEY`
  - `+256…` / `256…` phone-like literals → `+000000000`
- Force-pushed the rewritten `master` and `add_voice_feature` branches.
- Verified that all current local and remote refs contain **0** matches for the
  audited secret patterns.
- Enabled GitHub **secret scanning**, **secret scanning push protection** and
  **Dependabot security updates**.
- GitHub secret scanning currently reports an open alert for the DeepSeek key.
  It must stay open until the key is actually revoked.

### Still required outside this repository

1. Revoke and replace the DeepSeek key in the provider dashboard.
2. Revoke and replace the Africa's Talking key in its dashboard.
3. Update the local `.env` with the new values.
4. Mark the GitHub secret-scanning alert as resolved **after** revocation.
5. **Old commit SHAs remain cached by GitHub.** After the force-push, the old
   commit page and the old raw `.env.example` URL still returned HTTP 200. Ask
   GitHub Support to purge unreachable commits, or delete and recreate the
   repository if a completely clean public object history is required. This is
   not something a normal force-push can remove.
6. Triage the open Dependabot alerts before production use (see `SECURITY.md`).

## Findings

### 1. Africa's Talking API key — **high**

A hardcoded `atsk_…` key was present in `test_africastalking_direct.py` in the
working tree and in history.

- Fixed in the working tree: the script now reads
  `AFRICAS_TALKING_API_KEY` from the environment and exits if unset.
- Removed from all current refs on 9 November 2026. Pre-rewrite commit SHAs
  may remain reachable through GitHub's object cache.
- **Action:** revoke the key in the Africa's Talking dashboard and create a new
  one. Do not rely on the history rewrite alone.

### 2. DeepSeek API key in `.env.example` — **high**

An early commit (`005becb`) committed a real-looking `sk-…` key in
`.env.example`. The current `.env.example` is blank, but the key remains in git
history.

- Removed from all current refs on 9 November 2026. GitHub still shows an
  open secret-scanning alert for it.
- **Action:** revoke/rotate the DeepSeek key and then resolve the alert. If the
  key was reused anywhere else, rotate it there too.

### 3. Local `.env` — **medium**

The current `.env` contains a provider key. It is gitignored and was not found
in git history, so it should not be in the public commit. It was still present
on disk in this workspace.

- **Action:** rotate it if it was ever shared outside the machine, and never
  commit `.env`.

### 4. Real-looking phone numbers in test scripts — **medium / possible PII**

`test_sms.py` and `test_africastalking_direct.py` contained real-looking phone
numbers. They are replaced with `+000000000` in the working tree, but history
still contains the originals.

- Replaced with `+000000000` in the rewritten history.
- **Action:** treat the original numbers as personal data; old commit SHAs may
  still be cached by GitHub until purged.

### 5. Tracked local data and OS files — **low**

`storage/data/users.json`, `courses.json`, `enrollments.json` and several
`.DS_Store` files were tracked. `users.json` is empty now, but the schema can
hold personal data.

- The files are now untracked and covered by `.gitignore`.

## Checks performed

- Working tree scan for `sk-…`, `atsk_…`, JWTs, Google API keys, GitHub tokens,
  Twilio SIDs and private keys.
- History scan for `atsk_` and `sk-` across all commits.
- Confirmed `.env` was never committed.
- Excluded PDFs, images, video, `.venv`, Chroma and upload caches from the scan.

No Twilio, Google, GitHub or private-key material was found.

## Before making the repository public

The repository is already public. The remaining steps are:

1. Rotate the Africa's Talking and DeepSeek keys listed above.
2. Keep `.env` local; commit only `.env.example`.
3. Confirm CI remains green and secret scanning finds nothing in new pushes.
4. Use only `Lafia-Life/lafia-ai-bot` for the UNICEF application.

## Ongoing prevention

- CI should run `gitleaks` or GitHub secret scanning.
- Never put keys in docs, screenshots or issue templates.
- Use short-lived credentials and rotate on any suspected exposure.
- Test scripts must read credentials from environment variables only.
