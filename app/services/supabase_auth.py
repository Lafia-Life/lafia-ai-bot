"""Thin server-side Supabase Auth client.

Uses the Supabase Auth REST API through httpx so the app does not need the
heavy Supabase Python SDK. Access and refresh tokens are kept in HttpOnly
cookies; the browser never receives them directly.

Auth is optional until SUPABASE_URL and SUPABASE_ANON_KEY are replaced with
real project credentials. The rest of Lafia keeps working in guest mode.
"""

from __future__ import annotations

from typing import Any, Optional

import httpx

from app.config import get_settings

REQUEST_TIMEOUT = 15.0


class SupabaseAuthError(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _clean(value: Optional[str]) -> str:
    return (value or "").strip()


def is_configured() -> bool:
    """Return True only when real-looking Supabase credentials are present."""
    settings = get_settings()
    url = _clean(settings.supabase_url).lower()
    key = _clean(settings.supabase_anon_key).lower()
    if not url or not key:
        return False
    if "your-project" in url or "placeholder" in url or "example.supabase.co" in url:
        return False
    if "your-" in key or "placeholder" in key or key in {"anon-key", "public-anon-key"}:
        return False
    return url.startswith("https://") or url.startswith("http://localhost")


def _base_url() -> str:
    return _clean(get_settings().supabase_url).rstrip("/")


def _headers(access_token: Optional[str] = None) -> dict:
    settings = get_settings()
    token = _clean(access_token) or _clean(settings.supabase_anon_key)
    return {
        "apikey": _clean(settings.supabase_anon_key),
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


def _raise_for_response(response: httpx.Response) -> None:
    if response.is_success:
        return
    message = f"Supabase request failed ({response.status_code})."
    try:
        payload = response.json()
        message = (
            payload.get("msg")
            or payload.get("error_description")
            or payload.get("error")
            or payload.get("message")
            or message
        )
    except Exception:  # noqa: BLE001
        pass
    status = response.status_code if 400 <= response.status_code < 500 else 502
    if status == 401:
        message = "Your session has expired. Please sign in again."
    raise SupabaseAuthError(str(message), status)


def sanitize_user(user: Optional[dict]) -> Optional[dict]:
    if not user:
        return None
    metadata = user.get("user_metadata") or {}
    return {
        "id": user.get("id"),
        "email": user.get("email"),
        "phone": user.get("phone"),
        "full_name": metadata.get("full_name") or metadata.get("name"),
        "created_at": user.get("created_at"),
    }


def sanitize_session(session: Optional[dict]) -> dict:
    session = session or {}
    return {
        "access_token": session.get("access_token"),
        "refresh_token": session.get("refresh_token"),
        "expires_in": session.get("expires_in"),
        "expires_at": session.get("expires_at"),
        "token_type": session.get("token_type"),
    }


async def sign_up(email: str, password: str, full_name: Optional[str] = None) -> dict:
    if not is_configured():
        raise SupabaseAuthError(
            "Supabase auth is not configured yet. Add SUPABASE_URL and SUPABASE_ANON_KEY to .env.",
            503,
        )
    payload = {
        "email": email,
        "password": password,
        "data": {"full_name": (full_name or "").strip()},
    }
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        response = await client.post(
            f"{_base_url()}/auth/v1/signup",
            headers=_headers(),
            json=payload,
        )
    _raise_for_response(response)
    data = response.json()
    return {
        "user": sanitize_user(data.get("user")),
        "session": sanitize_session(data.get("session")),
        "needs_confirmation": not bool(data.get("session")),
    }


async def sign_in(email: str, password: str) -> dict:
    if not is_configured():
        raise SupabaseAuthError(
            "Supabase auth is not configured yet. Add SUPABASE_URL and SUPABASE_ANON_KEY to .env.",
            503,
        )
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        response = await client.post(
            f"{_base_url()}/auth/v1/token?grant_type=password",
            headers=_headers(),
            json={"email": email, "password": password},
        )
    _raise_for_response(response)
    data = response.json()
    return {
        "user": sanitize_user(data.get("user")),
        "session": sanitize_session(data),
    }


async def refresh_session(refresh_token: str) -> dict:
    if not is_configured():
        raise SupabaseAuthError("Supabase auth is not configured yet.", 503)
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        response = await client.post(
            f"{_base_url()}/auth/v1/token?grant_type=refresh_token",
            headers=_headers(),
            json={"refresh_token": refresh_token},
        )
    _raise_for_response(response)
    data = response.json()
    return {
        "user": sanitize_user(data.get("user")),
        "session": sanitize_session(data),
    }


async def get_user(access_token: str) -> Optional[dict]:
    if not access_token or not is_configured():
        return None
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        response = await client.get(
            f"{_base_url()}/auth/v1/user",
            headers=_headers(access_token),
        )
    if response.status_code == 401:
        return None
    _raise_for_response(response)
    return sanitize_user(response.json())


async def sign_out(access_token: Optional[str]) -> None:
    if not access_token or not is_configured():
        return
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            await client.post(
                f"{_base_url()}/auth/v1/logout",
                headers=_headers(access_token),
            )
    except httpx.HTTPError:
        # Local cookie removal is still sufficient.
        return


def public_config() -> dict[str, Any]:
    settings = get_settings()
    configured = is_configured()
    return {
        "provider": "supabase",
        "enabled": configured,
        "required": bool(settings.auth_required),
        "message": (
            "Supabase auth is ready."
            if configured
            else "Auth placeholder active. Add SUPABASE_URL and SUPABASE_ANON_KEY to .env to enable sign in."
        ),
    }
