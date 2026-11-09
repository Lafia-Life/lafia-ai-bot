# Translating Lafia

All UI text lives in `static/i18n/`. Each language has one JSON file:

| Code | Language |
| --- | --- |
| `en` | English |
| `sw` | Kiswahili |
| `lg` | Luganda |
| `ach` | Acholi |
| `teo` | Ateso |
| `xog` | Lusoga |

The interface falls back to English for any missing key, so a translation can be
shipped incrementally.

## Add a language

1. Copy `static/i18n/en.json` to `static/i18n/<code>.json`.
2. Set `_meta.language`, `_meta.code`, and a `_meta.review` note.
3. Translate the values. Keep keys exactly the same.
4. Keep placeholders such as `{distance}` unchanged.
5. Add the language to `LANGUAGES` in `static/js/chat.js`.
6. Add the code and label to the picker translations (`language.<code>`).
7. Run `pytest -q`.
8. Test the consent screen, one chat answer, the privacy sheet and Find care at
   phone width.

## Low-resource languages need human review

Acholi, Ateso and Lusoga strings in this repository are **machine-drafted**.
They are included so contributors can review and improve them, not as validated
clinical communication. Before launch in a community:

- have a native speaker review every string, especially consent and danger-sign
  language;
- have a clinical adviser review any translated health terminology;
- test comprehension with low-literacy users;
- check that the model's answer quality is acceptable in that language, not just
  the interface labels.

## Voice

The Listen button appears only when the browser reports a speech-synthesis voice
matching the chosen language. Many browsers do not ship voices for Acholi,
Ateso or Lusoga. That is expected; do not fake availability. Document which
languages have voice support in your deployment.

## Text-to-speech and recognition codes

`static/js/chat.js` maps each language to a browser speech code. Update these if
your target devices use different locale tags.

## Medical terminology

Do not translate a medical term by guessing. Prefer a reviewed local term, or
keep the English term in parentheses. The model is instructed to do the same,
but model output is not a substitute for a glossary review.
