# Secrets audit

Audit date: 9 November 2026
Scope: current working tree and local git history of this repository.

No secret values are reproduced in this document.

## Findings

### 1. Africa's Talking API key — **high**

A hardcoded `atsk_…` key was present in `test_africastalking_direct.py` in the
working tree and in history.

- Fixed in the working tree: the script now reads
  `AFRICAS_TALKING_API_KEY` from the environment and exits if unset.
- Still present in history: commits `c7d5101`, `64cc8b8` and `cb628bd`
  contain the file with the key.
- **Action:** revoke the key in the Africa's Talking dashboard and create a new
  one. Do not rely on removing it from the latest commit.

### 2. DeepSeek API key in `.env.example` — **high**

An early commit (`005becb`) committed a real-looking `sk-…` key in
`.env.example`. The current `.env.example` is blank, but the key remains in git
history.

- **Action:** revoke/rotate that DeepSeek key.
- If the key was reused anywhere else, rotate it there too.

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

- **Action:** treat as personal data. Purge history before publishing or confirm
  the numbers are non-personal test numbers.

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

1. Rotate the Africa's Talking and DeepSeek keys listed above.
2. Purge the secrets and phone numbers from history. For example, with
   `git filter-repo` and a private replacements file:

   ```bash
   # replacements.txt is local and must never be committed
   git filter-repo --replace-text replacements.txt
   ```

   This rewrites every commit hash. Coordinate with all clones and force-push
   only after the rewrite is verified.
3. Re-run this audit on the rewritten history.
4. Enable GitHub secret scanning and push protection.
5. Keep `.env` local; commit only `.env.example`.

## Ongoing prevention

- CI should run `gitleaks` or GitHub secret scanning.
- Never put keys in docs, screenshots or issue templates.
- Use short-lived credentials and rotate on any suspected exposure.
- Test scripts must read credentials from environment variables only.
