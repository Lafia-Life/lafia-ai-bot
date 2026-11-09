import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
I18N = ROOT / "static/i18n"
LANGUAGES = {"en", "sw", "lg", "ach", "teo", "xog"}

REQUIRED_KEYS = {
    "app.title",
    "consent.title",
    "consent.languageLabel",
    "consent.notDiagnosis",
    "consent.continue",
    "chat.inputPlaceholder",
    "chat.send",
    "chat.listen",
    "chat.quickExit",
    "chat.findCare",
    "chat.saveChats",
    "chat.deleteChats",
    "chat.disclaimer",
    "privacy.title",
    "care.title",
    "care.useLocation",
    "care.emergency",
}


def load(code):
    return json.loads((I18N / f"{code}.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("code", sorted(LANGUAGES))
def test_language_file_is_valid_and_complete(code):
    data = load(code)
    assert data["_meta"]["code"] == code
    missing = REQUIRED_KEYS - set(data)
    assert not missing, f"{code} is missing {sorted(missing)}"
    assert all(isinstance(value, str) and value.strip() for key, value in data.items() if not key.startswith("_"))


def test_english_is_the_reference_language():
    english = load("en")
    for code in LANGUAGES - {"en"}:
        other = load(code)
        assert set(other) == set(english)


def test_all_language_files_are_documented_for_human_review():
    for code in LANGUAGES - {"en"}:
        data = load(code)
        assert "review" in data["_meta"]
        assert "human review" in data["_meta"]["review"].lower()
