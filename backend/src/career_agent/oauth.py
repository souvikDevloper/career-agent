"""OAuth 2.1 authorization server for the MCP connector.

Why this exists: an MCP client needs a way to get a token without a person
pasting one, and without that token expiring in an hour. The Connectors page's
copy-a-token trick works for a demo and is miserable for anything else.

What this is not: a second identity system. Cognito remains the only place a
password is checked, and the token handed to the client is the **Cognito ID
token** - the same one the browser uses. That matters because API Gateway's JWT
authorizer validates it before any of this code runs, so the MCP endpoint keeps
exactly the authorization story it already had. This module only decides *who
may be handed one*, never who someone is.

The flow, once: client registers (RFC 7591), sends the user to /oauth/authorize
with a PKCE challenge, the person signs in and consents in the app, the app
mints a single-use code, the client exchanges code + verifier for tokens.
Afterwards the client refreshes against Cognito through /oauth/token.

Known limitation, stated rather than hidden: the refresh token handed to the
client is the person's own Cognito refresh token, because minting a separate one
would need their password again. A connected client therefore has the reach of
their browser session until it expires or they sign out everywhere. The consent
screen says so in those words.
"""

from __future__ import annotations

import base64
import hashlib
import re
import secrets
from typing import Any
from urllib.parse import urlencode, urlparse, urlunparse

CODE_TTL_SECONDS = 60          # a code is redeemed immediately or not at all
REQUEST_TTL_SECONDS = 600      # a person has ten minutes to sign in and consent
CLIENT_TTL_SECONDS = 90 * 86400

SCOPE = "career-agent"
MAX_REDIRECT_URIS = 10


class OAuthError(Exception):
    """An error the spec says to report in a specific shape."""

    def __init__(self, code: str, description: str, status: int = 400):
        super().__init__(description)
        self.code = code
        self.description = description
        self.status = status


# ---------------------------------------------------------------------------
# redirect URIs
# ---------------------------------------------------------------------------

def validate_redirect_uri(raw: str) -> str:
    """Accept only what OAuth 2.1 allows a public client to be sent back to.

    This is the control that stops an authorization code being delivered to
    somebody else, so it is exact and it is not clever: https anywhere, plain
    http only on the loopback interface, never a fragment, never a wildcard.
    """
    if not isinstance(raw, str) or not raw or len(raw) > 2000:
        raise OAuthError("invalid_redirect_uri", "A redirect URI is required.")
    parsed = urlparse(raw)
    if parsed.fragment:
        raise OAuthError("invalid_redirect_uri", "A redirect URI may not contain a fragment.")
    if parsed.scheme == "https":
        if not parsed.hostname:
            raise OAuthError("invalid_redirect_uri", "That redirect URI has no host.")
        return raw
    if parsed.scheme == "http":
        # Loopback only, and by address: "localhost.example.com" is not loopback.
        if parsed.hostname in ("localhost", "127.0.0.1", "::1"):
            return raw
        raise OAuthError("invalid_redirect_uri", "Plain http is only allowed on the loopback interface.")
    raise OAuthError("invalid_redirect_uri", "A redirect URI must use https, or http on loopback.")


def redirect_with(redirect_uri: str, params: dict[str, str]) -> str:
    """Append parameters to a redirect URI, preserving any query it already has."""
    parsed = urlparse(redirect_uri)
    query = parsed.query + "&" + urlencode(params) if parsed.query else urlencode(params)
    return urlunparse(parsed._replace(query=query))


# ---------------------------------------------------------------------------
# client registration
# ---------------------------------------------------------------------------

def register_client(body: dict, now: float) -> dict:
    """RFC 7591 dynamic registration, public clients only.

    Registration is open because MCP clients cannot be enrolled by hand, so a
    client id proves nothing on its own. Every security decision downstream
    rests on the redirect URI and the PKCE verifier instead.
    """
    uris = body.get("redirect_uris")
    if not isinstance(uris, list) or not uris:
        raise OAuthError("invalid_redirect_uri", "redirect_uris is required.")
    if len(uris) > MAX_REDIRECT_URIS:
        raise OAuthError("invalid_client_metadata", f"At most {MAX_REDIRECT_URIS} redirect URIs.")
    validated = [validate_redirect_uri(u) for u in uris]

    method = body.get("token_endpoint_auth_method", "none")
    if method != "none":
        raise OAuthError("invalid_client_metadata", "Only public clients are supported; use PKCE.")
    grants = body.get("grant_types") or ["authorization_code", "refresh_token"]
    unsupported = set(grants) - {"authorization_code", "refresh_token"}
    if unsupported:
        raise OAuthError("invalid_client_metadata", f"Unsupported grant types: {', '.join(sorted(unsupported))}")

    client_id = "mcp_" + secrets.token_urlsafe(18)
    name = str(body.get("client_name") or "An MCP client")[:120]
    return {
        "client_id": client_id,
        "client_name": name,
        "redirect_uris": validated,
        "grant_types": sorted(set(grants)),
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",
        "client_id_issued_at": int(now),
        "scope": SCOPE,
    }


# ---------------------------------------------------------------------------
# authorization request
# ---------------------------------------------------------------------------

def validate_authorize(params: dict, client: dict | None) -> dict:
    """Check an /oauth/authorize request before a person is ever shown a screen.

    Errors split in two, and the split is the point. A bad client_id or
    redirect_uri cannot be reported *to* the redirect URI - that is how an open
    redirect becomes a token thief - so those raise. Everything else is the
    client's mistake and is reported back to it.
    """
    client_id = params.get("client_id") or ""
    if not client:
        raise OAuthError("invalid_client", "Unknown client. Register before authorizing.", 400)

    redirect_uri = params.get("redirect_uri") or ""
    if not redirect_uri:
        if len(client["redirect_uris"]) != 1:
            raise OAuthError("invalid_request", "redirect_uri is required for this client.", 400)
        redirect_uri = client["redirect_uris"][0]
    if redirect_uri not in client["redirect_uris"]:
        raise OAuthError("invalid_redirect_uri", "That redirect URI is not registered for this client.", 400)

    state = params.get("state") or ""
    reportable: list[tuple[str, str]] = []
    if params.get("response_type") != "code":
        reportable.append(("unsupported_response_type", "Only the authorization code flow is supported."))
    if params.get("code_challenge_method") != "S256":
        reportable.append(("invalid_request", "PKCE with S256 is required."))
    challenge = params.get("code_challenge") or ""
    if not re.fullmatch(r"[A-Za-z0-9._~-]{43,128}", challenge):
        reportable.append(("invalid_request", "A valid S256 code_challenge is required."))
    if reportable:
        code, description = reportable[0]
        raise RedirectableError(code, description, redirect_uri, state)

    return {
        "client_id": client_id,
        "client_name": client.get("client_name", "An MCP client"),
        "redirect_uri": redirect_uri,
        "state": state,
        "code_challenge": challenge,
        "scope": params.get("scope") or SCOPE,
        "resource": params.get("resource") or "",
    }


class RedirectableError(OAuthError):
    """An error the client is entitled to see, delivered to its redirect URI."""

    def __init__(self, code: str, description: str, redirect_uri: str, state: str):
        super().__init__(code, description)
        self.redirect_uri = redirect_uri
        self.state = state

    def location(self) -> str:
        params = {"error": self.code, "error_description": self.description}
        if self.state:
            params["state"] = self.state
        return redirect_with(self.redirect_uri, params)


# ---------------------------------------------------------------------------
# PKCE
# ---------------------------------------------------------------------------

def pkce_matches(verifier: str, challenge: str) -> bool:
    """S256 only. Compared in constant time; a verifier is as good as a password."""
    if not isinstance(verifier, str) or not re.fullmatch(r"[A-Za-z0-9._~-]{43,128}", verifier or ""):
        return False
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    expected = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return secrets.compare_digest(expected, challenge or "")


# ---------------------------------------------------------------------------
# metadata documents
# ---------------------------------------------------------------------------

def protected_resource_metadata(base: str) -> dict:
    """RFC 9728. Tells a client which authorization server guards this resource."""
    base = base.rstrip("/")
    return {
        "resource": f"{base}/api/mcp",
        "authorization_servers": [base],
        "scopes_supported": [SCOPE],
        "bearer_methods_supported": ["header"],
        "resource_name": "Career Agent",
        "resource_documentation": f"{base}/app/connectors",
    }


def authorization_server_metadata(base: str) -> dict:
    """RFC 8414. Public clients, PKCE required, registration open."""
    base = base.rstrip("/")
    return {
        "issuer": base,
        "authorization_endpoint": f"{base}/oauth/authorize",
        "token_endpoint": f"{base}/oauth/token",
        "registration_endpoint": f"{base}/oauth/register",
        "scopes_supported": [SCOPE],
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": ["none"],
        "service_documentation": f"{base}/app/connectors",
    }


def new_code() -> str:
    return secrets.token_urlsafe(32)


def new_request_id() -> str:
    return "oar_" + secrets.token_urlsafe(16)


def bearer_challenge(base: str) -> str:
    """The WWW-Authenticate header that points an unauthenticated client at discovery."""
    base = base.rstrip("/")
    return f'Bearer realm="career-agent", resource_metadata="{base}/.well-known/oauth-protected-resource"'


def describe_consent(client_name: str, redirect_uri: str) -> dict[str, Any]:
    """What the person is actually agreeing to, in the words they should read."""
    host = urlparse(redirect_uri).hostname or redirect_uri
    return {
        "client_name": client_name,
        "redirect_host": host,
        "grants": [
            "Search openings and read your matches, applications and profile summary",
            "Create watches and prepare application packets for you to review",
        ],
        "withheld": "It cannot approve or submit an application. You do that here.",
        "caution": ("Connecting gives this client the same reach as your own signed-in session, "
                    "for up to 7 days or until you sign out everywhere."),
    }
