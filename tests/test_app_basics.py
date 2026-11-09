from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas import ChatRequest
from app.services.retrieval import _build_prompt
from app.services.who_knowledge import WHO_TOPICS

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_health_and_bootstrap_need_no_account(client):
    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["app"] == "Lafia Chat AI"

    bootstrap = client.get("/api/bootstrap")
    assert bootstrap.status_code == 200
    payload = bootstrap.json()
    assert payload["auth"]["provider"] == "supabase"
    assert len(payload["suggestions"]) == 6
    assert payload["who"]["total_topics"] == len(WHO_TOPICS)
    assert "documents" in payload


def test_auth_requires_consent_before_signup(client):
    response = client.post(
        "/api/auth/signup",
        json={"email": "test@example.com", "password": "password123", "consent": False},
    )
    assert response.status_code == 400
    assert "privacy notice" in response.json()["detail"].lower()

    config = client.get("/api/auth/config").json()
    if not config["enabled"]:
        response = client.post(
            "/api/auth/signup",
            json={"email": "test@example.com", "password": "password123", "consent": True},
        )
        assert response.status_code == 503


def test_language_is_passed_to_prompt():
    messages = _build_prompt(
        "Nini dalili za hatari?",
        "context",
        history=None,
        language="sw",
    )
    system = messages[0]["content"]
    assert "Kiswahili" in system
    assert "Reply in Kiswahili" in system

    english = _build_prompt("What are the danger signs?", "context", language="en")
    assert "Reply in" not in english[0]["content"]


def test_chat_request_accepts_language():
    payload = ChatRequest(question="Hello", language="lg")
    assert payload.language == "lg"


def test_no_server_side_answer_cache():
    source = (ROOT / "app/services/retrieval.py").read_text(encoding="utf-8")
    assert "_answer_cache" not in source
    assert "AnswerCache" not in source


def test_facilities_are_served_and_placeholders(client):
    response = client.get("/data/facilities.json")
    assert response.status_code == 200
    data = response.json()
    assert data["_meta"]["placeholder"] is True
    assert data["emergency"]["placeholder"] is True
    assert data["chw"]["placeholder"] is True
    assert data["facilities"]
    for facility in data["facilities"]:
        assert facility["placeholder"] is True
        assert facility["name"].startswith("Placeholder")
        assert facility["phone"] == "+000000000"
        assert facility["hours"] == "Placeholder hours"


def test_who_topics_contain_metadata_only():
    for topic in WHO_TOPICS:
        assert set(topic.keys()) == {"id", "title", "url"}
        assert topic["url"].startswith("https://www.who.int/")
    notice = (ROOT / "NOTICE").read_text(encoding="utf-8")
    assert "World Health Organization" in notice
    assert "who.int/about/policies/publishing/copyright" in notice


def test_provider_is_environment_configurable():
    example = (ROOT / ".env.example").read_text(encoding="utf-8")
    for key in ("LLM_PROVIDER", "LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL", "WHO_SYNC_ON_STARTUP"):
        assert key in example
    assert "sk-" not in example
    assert "atsk_" not in example


def test_gitignore_covers_private_artifacts():
    patterns = (ROOT / ".gitignore").read_text(encoding="utf-8")
    for pattern in ("storage/uploads/", "storage/chroma/", ".env", "*.db", "storage/data/*.json"):
        assert pattern in patterns
