"""The OAuth 2.1 authorization server.

This is the one place in the project where getting a check wrong hands someone
else's account to a stranger, so the tests are adversarial rather than
illustrative. Two controls carry almost all the weight and are pinned hardest:
the redirect URI, which decides where a code is delivered, and the PKCE
verifier, which decides who may redeem it.
"""

from __future__ import annotations

import base64
import hashlib

import pytest
from helpers import T0  # noqa: F401  (adds src/ to sys.path)

from career_agent import oauth as oa

BASE = "https://career.example.test"


def challenge_for(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


VERIFIER = "x" * 64
CHALLENGE = challenge_for(VERIFIER)


def client(**over):
    base = {"client_id": "mcp_abc", "client_name": "Some MCP Client",
            "redirect_uris": ["http://127.0.0.1:33418/callback"]}
    base.update(over)
    return base


def authorize_params(**over):
    base = {"client_id": "mcp_abc", "redirect_uri": "http://127.0.0.1:33418/callback",
            "response_type": "code", "code_challenge": CHALLENGE, "code_challenge_method": "S256",
            "state": "opaque-state"}
    base.update(over)
    return base


# --------------------------------------------------------------------------- redirect URIs


class TestRedirectUri:
    @pytest.mark.parametrize("uri", [
        "https://claude.ai/api/mcp/auth_callback",
        "http://127.0.0.1:33418/callback",
        "http://localhost:8080/oauth/cb",
        "http://[::1]:9000/cb",
    ])
    def test_allowed(self, uri):
        assert oa.validate_redirect_uri(uri) == uri

    @pytest.mark.parametrize("uri,why", [
        ("http://evil.test/cb", "plain http off loopback"),
        ("http://localhost.evil.test/cb", "a host that merely starts with localhost"),
        ("http://127.0.0.1.evil.test/cb", "a host that merely starts with the loopback address"),
        ("javascript:alert(1)", "a script scheme"),
        ("data:text/html,<script>", "a data URI"),
        ("file:///etc/passwd", "a file URI"),
        ("https://ok.test/cb#fragment", "a fragment"),
        ("", "empty"),
        ("not-a-uri", "no scheme"),
    ])
    def test_rejected(self, uri, why):
        with pytest.raises(oa.OAuthError):
            oa.validate_redirect_uri(uri)

    def test_appending_preserves_an_existing_query(self):
        got = oa.redirect_with("https://ok.test/cb?keep=1", {"code": "abc", "state": "s"})
        assert got.startswith("https://ok.test/cb?keep=1&")
        assert "code=abc" in got and "state=s" in got


# --------------------------------------------------------------------------- registration


class TestRegistration:
    def test_issues_a_public_client(self):
        got = oa.register_client({"redirect_uris": ["https://claude.ai/api/mcp/auth_callback"],
                                  "client_name": "Claude"}, 1_789_000_000)
        assert got["client_id"].startswith("mcp_")
        assert got["token_endpoint_auth_method"] == "none"
        assert "client_secret" not in got

    def test_client_ids_are_unguessable_and_unique(self):
        ids = {oa.register_client({"redirect_uris": ["https://a.test/cb"]}, 0)["client_id"] for _ in range(50)}
        assert len(ids) == 50
        assert all(len(i) > 20 for i in ids)

    def test_a_bad_redirect_uri_is_refused_at_registration(self):
        with pytest.raises(oa.OAuthError):
            oa.register_client({"redirect_uris": ["http://evil.test/cb"]}, 0)

    def test_confidential_clients_are_refused(self):
        """A secret shipped inside a desktop client is not a secret; PKCE instead."""
        with pytest.raises(oa.OAuthError):
            oa.register_client({"redirect_uris": ["https://a.test/cb"],
                                "token_endpoint_auth_method": "client_secret_post"}, 0)

    @pytest.mark.parametrize("body", [{}, {"redirect_uris": []}, {"redirect_uris": "https://a.test/cb"}])
    def test_missing_redirect_uris(self, body):
        with pytest.raises(oa.OAuthError):
            oa.register_client(body, 0)

    def test_implicit_grant_is_refused(self):
        with pytest.raises(oa.OAuthError):
            oa.register_client({"redirect_uris": ["https://a.test/cb"], "grant_types": ["implicit"]}, 0)


# --------------------------------------------------------------------------- authorize


class TestAuthorize:
    def test_a_valid_request_is_parked(self):
        got = oa.validate_authorize(authorize_params(), client())
        assert got["client_id"] == "mcp_abc"
        assert got["code_challenge"] == CHALLENGE
        assert got["state"] == "opaque-state"

    def test_unknown_client(self):
        with pytest.raises(oa.OAuthError) as exc:
            oa.validate_authorize(authorize_params(), None)
        assert exc.value.code == "invalid_client"

    def test_an_unregistered_redirect_uri_is_refused(self):
        """The attack this stops: a code delivered somewhere the client never named."""
        with pytest.raises(oa.OAuthError) as exc:
            oa.validate_authorize(authorize_params(redirect_uri="https://evil.test/cb"), client())
        assert exc.value.code == "invalid_redirect_uri"
        assert not isinstance(exc.value, oa.RedirectableError), "an unregistered URI must never be redirected to"

    def test_a_bad_client_is_never_redirected_to(self):
        """Reporting these by redirect is how an open redirect becomes a token thief."""
        with pytest.raises(oa.OAuthError) as exc:
            oa.validate_authorize(authorize_params(), None)
        assert not isinstance(exc.value, oa.RedirectableError)

    def test_omitted_redirect_uri_uses_the_only_registered_one(self):
        params = authorize_params()
        del params["redirect_uri"]
        assert oa.validate_authorize(params, client())["redirect_uri"] == "http://127.0.0.1:33418/callback"

    def test_omitted_redirect_uri_is_ambiguous_with_several_registered(self):
        params = authorize_params()
        del params["redirect_uri"]
        with pytest.raises(oa.OAuthError):
            oa.validate_authorize(params, client(redirect_uris=["https://a.test/cb", "https://b.test/cb"]))

    @pytest.mark.parametrize("over,code", [
        ({"response_type": "token"}, "unsupported_response_type"),
        ({"code_challenge_method": "plain"}, "invalid_request"),
        ({"code_challenge_method": None}, "invalid_request"),
        ({"code_challenge": "too-short"}, "invalid_request"),
        ({"code_challenge": None}, "invalid_request"),
    ])
    def test_client_mistakes_are_reported_to_the_client(self, over, code):
        with pytest.raises(oa.RedirectableError) as exc:
            oa.validate_authorize(authorize_params(**over), client())
        assert exc.value.code == code
        assert exc.value.location().startswith("http://127.0.0.1:33418/callback?")
        assert "state=opaque-state" in exc.value.location()

    def test_pkce_is_not_optional(self):
        """Without it a stolen code is redeemable by whoever stole it."""
        params = authorize_params()
        del params["code_challenge"]
        del params["code_challenge_method"]
        with pytest.raises(oa.RedirectableError):
            oa.validate_authorize(params, client())


# --------------------------------------------------------------------------- PKCE


class TestPkce:
    def test_the_matching_verifier_passes(self):
        assert oa.pkce_matches(VERIFIER, CHALLENGE)

    @pytest.mark.parametrize("verifier", ["y" * 64, "", "short", VERIFIER[:-1], None, 12345])
    def test_anything_else_fails(self, verifier):
        assert not oa.pkce_matches(verifier, CHALLENGE)

    def test_the_challenge_is_not_the_verifier(self):
        """Replaying the challenge as the verifier must not work."""
        assert not oa.pkce_matches(CHALLENGE, CHALLENGE)

    def test_an_empty_challenge_matches_nothing(self):
        assert not oa.pkce_matches(VERIFIER, "")


# --------------------------------------------------------------------------- metadata


class TestMetadata:
    def test_protected_resource_points_at_the_mcp_endpoint(self):
        got = oa.protected_resource_metadata(BASE + "/")
        assert got["resource"] == f"{BASE}/api/mcp"
        assert got["authorization_servers"] == [BASE]

    def test_authorization_server_advertises_only_what_is_supported(self):
        got = oa.authorization_server_metadata(BASE)
        assert got["code_challenge_methods_supported"] == ["S256"]
        assert got["token_endpoint_auth_methods_supported"] == ["none"]
        assert got["response_types_supported"] == ["code"]
        assert set(got["grant_types_supported"]) == {"authorization_code", "refresh_token"}
        for key in ("authorization_endpoint", "token_endpoint", "registration_endpoint"):
            assert got[key].startswith(BASE + "/")

    def test_the_bearer_challenge_points_at_discovery(self):
        assert "/.well-known/oauth-protected-resource" in oa.bearer_challenge(BASE)


class TestConsentCopy:
    def test_it_names_the_client_the_host_and_the_limit(self):
        got = oa.describe_consent("Claude", "https://claude.ai/api/mcp/auth_callback")
        assert got["client_name"] == "Claude"
        assert got["redirect_host"] == "claude.ai"
        assert "approve or submit" in got["withheld"]
        # The refresh token handed over is the person's own session; say so.
        assert "same reach as your own signed-in session" in got["caution"]


class TestSecretsAreUnguessable:
    def test_codes(self):
        codes = {oa.new_code() for _ in range(200)}
        assert len(codes) == 200
        assert all(len(c) >= 40 for c in codes)

    def test_request_ids(self):
        ids = {oa.new_request_id() for _ in range(200)}
        assert len(ids) == 200
        assert all(i.startswith("oar_") for i in ids)
