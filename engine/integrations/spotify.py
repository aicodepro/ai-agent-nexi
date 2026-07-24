"""Spotify Web API integration using Authorization Code with PKCE."""
from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import time
import webbrowser
from dataclasses import asdict, dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

import requests


AUTHORIZE_URL = "https://accounts.spotify.com/authorize"
TOKEN_URL = "https://accounts.spotify.com/api/token"
API_BASE = "https://api.spotify.com/v1"
REDIRECT_URI = "http://127.0.0.1:43821/callback"
CREDENTIAL_TARGET = "Nexi/SpotifyOAuth"
SCOPES = (
    "user-read-playback-state",
    "user-modify-playback-state",
    "user-read-currently-playing",
    "playlist-read-private",
)


class SpotifyError(RuntimeError):
    pass


@dataclass
class SpotifyToken:
    access_token: str
    refresh_token: str
    expires_at: float
    scope: str = ""
    token_type: str = "Bearer"

    @property
    def expired(self) -> bool:
        return time.time() >= self.expires_at - 30.0


class WindowsCredentialTokenStore:
    """Stores OAuth tokens in Windows Credential Manager, never a project file."""

    def load(self) -> SpotifyToken | None:
        try:
            import win32cred

            credential = win32cred.CredRead(CREDENTIAL_TARGET, win32cred.CRED_TYPE_GENERIC)
            blob = credential.get("CredentialBlob", b"")
            if isinstance(blob, bytes):
                blob = blob.decode("utf-16-le" if b"\x00" in blob else "utf-8")
            data = json.loads(str(blob))
            return SpotifyToken(**data)
        except Exception:
            return None

    def save(self, token: SpotifyToken) -> None:
        try:
            import win32cred

            win32cred.CredWrite({
                "Type": win32cred.CRED_TYPE_GENERIC,
                "TargetName": CREDENTIAL_TARGET,
                "UserName": "spotify-oauth",
                "CredentialBlob": json.dumps(asdict(token)),
                "Persist": win32cred.CRED_PERSIST_LOCAL_MACHINE,
                "Comment": "Nexi Spotify PKCE token",
            }, 0)
        except Exception as exc:
            raise SpotifyError("Windows Credential Manager is unavailable; Spotify tokens were not stored.") from exc

    def clear(self) -> None:
        try:
            import win32cred

            win32cred.CredDelete(CREDENTIAL_TARGET, win32cred.CRED_TYPE_GENERIC)
        except Exception:
            pass


class MemoryTokenStore:
    """Test-only in-memory token store."""

    def __init__(self, token: SpotifyToken | None = None) -> None:
        self.token = token

    def load(self) -> SpotifyToken | None:
        return self.token

    def save(self, token: SpotifyToken) -> None:
        self.token = token

    def clear(self) -> None:
        self.token = None


def generate_code_verifier(length: int = 96) -> str:
    length = max(43, min(128, int(length)))
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def code_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


class SpotifyOAuth:
    def __init__(self, client_id: str = "", *, token_store=None, session=requests) -> None:
        self.client_id = client_id or os.getenv("SPOTIFY_CLIENT_ID", "").strip()
        self.token_store = token_store or WindowsCredentialTokenStore()
        self.session = session

    def authorization_url(self) -> tuple[str, str, str]:
        if not self.client_id:
            raise SpotifyError("Set SPOTIFY_CLIENT_ID before connecting Spotify.")
        verifier = generate_code_verifier()
        state = secrets.token_urlsafe(32)
        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "scope": " ".join(SCOPES),
            "code_challenge_method": "S256",
            "code_challenge": code_challenge(verifier),
            "redirect_uri": REDIRECT_URI,
            "state": state,
        }
        return f"{AUTHORIZE_URL}?{urlencode(params)}", verifier, state

    def authorize(self, *, timeout_seconds: float = 120.0, open_browser: bool = True) -> SpotifyToken:
        url, verifier, expected_state = self.authorization_url()

        class CallbackHandler(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                parsed = urlparse(self.path)
                self.server.callback = parse_qs(parsed.query) if parsed.path == "/callback" else {}
                ok = bool(self.server.callback.get("code"))
                body = (
                    "Spotify connected. You can return to Nexi."
                    if ok else
                    "Spotify authorization did not complete. Return to Nexi for details."
                ).encode("utf-8")
                self.send_response(200 if ok else 400)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, _format, *_args):
                return

        server = HTTPServer(("127.0.0.1", 43821), CallbackHandler)
        server.timeout = max(1.0, float(timeout_seconds))
        server.callback = {}
        try:
            if open_browser and not webbrowser.open(url):
                raise SpotifyError("The Spotify authorization page could not be opened.")
            server.handle_request()
        finally:
            server.server_close()
        callback = server.callback
        if callback.get("error"):
            raise SpotifyError(f"Spotify authorization was denied: {callback['error'][0]}")
        state = (callback.get("state") or [""])[0]
        if not secrets.compare_digest(state, expected_state):
            raise SpotifyError("Spotify authorization state did not match.")
        code = (callback.get("code") or [""])[0]
        if not code:
            raise SpotifyError("Spotify authorization timed out or returned no code.")
        return self.exchange_code(code, verifier)

    def exchange_code(self, authorization_code: str, verifier: str) -> SpotifyToken:
        response = self.session.post(TOKEN_URL, data={
            "client_id": self.client_id,
            "grant_type": "authorization_code",
            "code": authorization_code,
            "redirect_uri": REDIRECT_URI,
            "code_verifier": verifier,
        }, headers={"Content-Type": "application/x-www-form-urlencoded"}, timeout=15)
        response.raise_for_status()
        token = self._token_from_response(response.json())
        self.token_store.save(token)
        return token

    def refresh(self, token: SpotifyToken) -> SpotifyToken:
        response = self.session.post(TOKEN_URL, data={
            "client_id": self.client_id,
            "grant_type": "refresh_token",
            "refresh_token": token.refresh_token,
        }, headers={"Content-Type": "application/x-www-form-urlencoded"}, timeout=15)
        response.raise_for_status()
        refreshed = self._token_from_response(response.json(), old_refresh_token=token.refresh_token)
        self.token_store.save(refreshed)
        return refreshed

    def access_token(self) -> str:
        token = self.token_store.load()
        if token is None:
            raise SpotifyError("Spotify is not connected. Say 'connect Spotify' first.")
        if token.expired:
            token = self.refresh(token)
        return token.access_token

    @staticmethod
    def _token_from_response(data: dict[str, Any], old_refresh_token: str = "") -> SpotifyToken:
        access_token = str(data.get("access_token") or "")
        refresh_token = str(data.get("refresh_token") or old_refresh_token)
        if not access_token or not refresh_token:
            raise SpotifyError("Spotify returned an incomplete OAuth token response.")
        return SpotifyToken(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=time.time() + max(60, int(data.get("expires_in") or 3600)),
            scope=str(data.get("scope") or ""),
            token_type=str(data.get("token_type") or "Bearer"),
        )


class SpotifyClient:
    def __init__(self, oauth: SpotifyOAuth | None = None, *, session=requests) -> None:
        self.oauth = oauth or SpotifyOAuth(session=session)
        self.session = session

    def _request(self, method: str, path: str, *, params=None, body=None, retry_auth: bool = True) -> dict[str, Any]:
        token = self.oauth.access_token()
        response = self.session.request(
            method,
            f"{API_BASE}{path}",
            params=params,
            json=body,
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        if response.status_code == 401 and retry_auth:
            stored = self.oauth.token_store.load()
            if stored is not None:
                self.oauth.refresh(stored)
                return self._request(method, path, params=params, body=body, retry_auth=False)
        if response.status_code in {204, 202}:
            return {}
        if response.status_code >= 400:
            raise SpotifyError(f"Spotify API request failed with status {response.status_code}.")
        return response.json() if response.content else {}

    def devices(self) -> list[dict[str, Any]]:
        return list(self._request("GET", "/me/player/devices").get("devices") or [])

    def resolve_device(self, requested: str = "") -> dict[str, Any] | None:
        devices = [item for item in self.devices() if item.get("id") and not item.get("is_restricted")]
        if requested:
            needle = requested.strip().lower()
            for device in devices:
                if needle in str(device.get("name") or "").lower() or needle == str(device.get("type") or "").lower():
                    return device
        return next((item for item in devices if item.get("is_active")), devices[0] if devices else None)

    def transfer(self, device_id: str, *, play: bool = False) -> None:
        self._request("PUT", "/me/player", body={"device_ids": [device_id], "play": bool(play)})

    def search(self, query: str, kind: str = "track", *, limit: int = 5) -> list[dict[str, Any]]:
        safe_kind = kind if kind in {"track", "artist", "album", "playlist"} else "track"
        data = self._request("GET", "/search", params={"q": query, "type": safe_kind, "limit": limit})
        return list(data.get(f"{safe_kind}s", {}).get("items") or [])

    def play(self, query: str, *, kind: str = "track", device_name: str = "") -> dict[str, Any]:
        items = self.search(query, kind)
        if not items:
            return _failure("I couldn't find that on Spotify.")
        item = items[0]
        uri = str(item.get("uri") or "")
        item_id = str(item.get("id") or "")
        if not uri:
            return _failure("Spotify found a result without a playable URI.")
        device = self.resolve_device(device_name)
        if device is None:
            return _failure("No controllable Spotify Connect device is available. Open Spotify on a device first.")
        device_id = str(device["id"])
        if not device.get("is_active"):
            self.transfer(device_id)
        body = {"uris": [uri]} if kind == "track" else {"context_uri": uri}
        self._request("PUT", "/me/player/play", params={"device_id": device_id}, body=body)
        verified = self._verify_playback(item_id=item_id if kind == "track" else "", context_uri=uri if kind != "track" else "")
        name = str(item.get("name") or query)
        return _success(f"Playing {name} on Spotify.", verified=verified, item=item, device=device)

    def control(self, action: str, *, device_name: str = "") -> dict[str, Any]:
        device = self.resolve_device(device_name)
        if device is None:
            return _failure("No controllable Spotify Connect device is available.")
        device_id = str(device["id"])
        before = self.currently_playing()
        if action == "pause":
            self._request("PUT", "/me/player/pause", params={"device_id": device_id})
            verified = self._verify_state(False)
        elif action == "resume":
            self._request("PUT", "/me/player/play", params={"device_id": device_id})
            verified = self._verify_state(True)
        elif action in {"next", "previous"}:
            self._request("POST", f"/me/player/{action}", params={"device_id": device_id})
            previous_id = str((before.get("item") or {}).get("id") or "")
            verified = self._verify_changed(previous_id)
        else:
            return _failure("That Spotify control is not supported.")
        return _success(f"Spotify {action} completed.", verified=verified, device=device)

    def currently_playing(self) -> dict[str, Any]:
        return self._request("GET", "/me/player/currently-playing")

    def _verify_playback(self, *, item_id: str = "", context_uri: str = "") -> bool:
        for _ in range(3):
            state = self.currently_playing()
            current_id = str((state.get("item") or {}).get("id") or "")
            current_context = str((state.get("context") or {}).get("uri") or "")
            if state.get("is_playing") is True and ((item_id and current_id == item_id) or (context_uri and current_context == context_uri)):
                return True
            time.sleep(0.35)
        return False

    def _verify_state(self, expected: bool) -> bool:
        for _ in range(3):
            if self.currently_playing().get("is_playing") is expected:
                return True
            time.sleep(0.35)
        return False

    def _verify_changed(self, previous_id: str) -> bool:
        for _ in range(3):
            current = self.currently_playing()
            current_id = str((current.get("item") or {}).get("id") or "")
            if current_id and current_id != previous_id:
                return True
            time.sleep(0.35)
        return False


def _success(message: str, *, verified: bool, **metadata) -> dict[str, Any]:
    return {
        "handled": True,
        "ok": bool(verified),
        "success": bool(verified),
        "verified": bool(verified),
        "tool": "spotify",
        "message": message if verified else "Spotify accepted the request, but Nexi could not verify playback.",
        **metadata,
    }


def _failure(message: str) -> dict[str, Any]:
    return {"handled": True, "ok": False, "success": False, "verified": False, "tool": "spotify", "message": message}


_CLIENT: SpotifyClient | None = None


def get_spotify_client() -> SpotifyClient:
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = SpotifyClient()
    return _CLIENT


def spotify_connect(_slots: dict | None = None) -> dict[str, Any]:
    try:
        get_spotify_client().oauth.authorize()
        return {"success": True, "verified": True, "tool": "spotify_connect", "message": "Spotify connected securely."}
    except Exception as exc:
        return _failure(str(exc))


def spotify_play(slots: dict | None = None) -> dict[str, Any]:
    values = slots or {}
    query = str(values.get("query") or "").strip()
    if not query:
        return {**_failure("What should I play on Spotify?"), "expects_user_reply": True, "missing_slot": "query"}
    try:
        return get_spotify_client().play(
            query,
            kind=str(values.get("kind") or "track"),
            device_name=str(values.get("device") or ""),
        )
    except Exception as exc:
        return _failure(str(exc))


def spotify_control(action: str, slots: dict | None = None) -> dict[str, Any]:
    try:
        return get_spotify_client().control(action, device_name=str((slots or {}).get("device") or ""))
    except Exception as exc:
        return _failure(str(exc))


def spotify_now_playing(_slots: dict | None = None) -> dict[str, Any]:
    try:
        state = get_spotify_client().currently_playing()
        item = state.get("item") or {}
        if not item:
            return _failure("Spotify is not currently playing anything.")
        artists = ", ".join(str(a.get("name") or "") for a in item.get("artists") or [] if a.get("name"))
        message = f"Spotify is playing {item.get('name', 'an unknown track')}"
        if artists:
            message += f" by {artists}"
        return {"success": True, "verified": True, "tool": "spotify_now_playing", "message": message + ".", "state": state}
    except Exception as exc:
        return _failure(str(exc))


def spotify_devices(_slots: dict | None = None) -> dict[str, Any]:
    try:
        devices = get_spotify_client().devices()
        if not devices:
            return _failure("No Spotify Connect devices are available.")
        names = ", ".join(str(item.get("name") or item.get("type") or "device") for item in devices)
        return {"success": True, "verified": True, "tool": "spotify_devices", "message": f"Available Spotify devices: {names}.", "devices": devices}
    except Exception as exc:
        return _failure(str(exc))
