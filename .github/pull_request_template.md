## Summary

<!-- What does this change and why? -->

## Type

- [ ] UI / accessibility
- [ ] Privacy or safety
- [ ] Translation / i18n
- [ ] WHO content or retrieval
- [ ] Docs / tooling
- [ ] Bug fix

## Privacy checklist

- [ ] No name, phone number or account is required for the default flow
- [ ] Chats remain unsaved unless the user enables save-on-device
- [ ] No chat content, location or health data is sent to a new third party
- [ ] Quick exit still clears in-memory state and uses `location.replace`
- [ ] Delete-my-chats still removes stored data completely

## Verification

- [ ] `ruff check app tests`
- [ ] `pytest -q`
- [ ] Checked at 390px phone width
- [ ] Checked at 1280px desktop width
- [ ] Keyboard tested (Escape twice, focus states)
- [ ] No secrets or real health data in the diff

## Screenshots

<!-- Redact names, numbers and health details. -->
