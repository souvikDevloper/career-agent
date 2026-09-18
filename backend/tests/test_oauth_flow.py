"""The OAuth flow end to end, through the real dispatcher.

The unit tests pin each control; this pins the wiring between them - that a code
really is single-use, really is bound to its client and its PKCE challenge, and
that the identity attached to it comes from the JWT rather than the request body.
"""

from __future__ import annotations

import base64
import hashlib
import json
import urllib.parse

import pytest
from helpers import make  # noqa: F401  (adds src/ to sys.path)

from career_agent.handlers import api

VERIFIER = "v" * 64
CHALLENGE = base64.urlsafe_b64encode(hashlib.sha256(VERIFIER.encode()).digest()).rstrip(b"=").decode()
REDIRECT = "http://127.0.0.1:33418/callback"
USER = "11111111-2222-3333-4444-555555555555"
OTHER_USER = "99999999-8888-7777-6666-555555555555"


class FakeServices:
    def __init__(self):
        self.wf, self.store, self.clock = make()


@pytest.fixture
def svc(monkeypatch):
    fake = FakeServices()
    monkeypatch.setattr(api, "_svc", lambda: fake)
    return fake


def event(method, path, *, body=None, query=None, sub=None, form=None):
    ev = {
        "rawPath": path,
        "requestContext": {"http": {"method": method}, "requestId": "req-1"},
        "headers": {"host": "career.example.test"},
        "queryStringParameters": query or {},
        "body": "",
    }
    if sub:
        ev["requestContext"]["authorizer"] = {"jwt": {"claims": {"sub": sub, "email": "a@example.test"}}}
    if body is not None:
        ev["body"] = json.dumps(body)
    if form is not None:
        ev["body"] = urllib.parse.urlencode(form)
    return ev


def body_of(res):
    return json.loads(res["body"])


def register(client_name="Claude", uris=(REDIRECT,)):
    res = api.handler(event("POST", "/oauth/register",
                            body={"redirect_uris": list(uris), "client_name": client_name}), None)
    assert res["statusCode"] == 201, res["body"]
    return body_of(res)["client_id"]


def authorize(client_id, **over):
    query = {"client_id": client_id, "redirect_uri": REDIRECT, "response_type": "code",
             "code_challenge": CHALLENGE, "code_challenge_method": "S256", "state": "st-1"}
    query.update(over)
    return api.handler(event("GET", "/oauth/authorize", query=query), None)


def request_id_from(res):
    location = res["headers"]["Location"]
    return urllib.parse.parse_qs(urllib.parse.urlparse(location).query)["request"][0]


def grant(rid, sub=USER, approve=True):
    return api.handler(event("POST", "/api/oauth/grant", sub=sub, body={
        "request": rid, "approve": approve, "id_token": f"id-token-for-{sub}", "refresh_token": "refresh-abc"}), None)


def code_from(res):
    location = body_of(res)["redirect_to"]
    return urllib.parse.parse_qs(urllib.parse.urlparse(location).query)["code"][0]


def exchange(code, client_id, verifier=VERIFIER, **over):
    form = {"grant_type": "authorization_code", "code": code, "client_id": client_id,
            "redirect_uri": REDIRECT, "code_verifier": verifier}
    form.update(over)
    return api.handler(event("POST", "/oauth/token", form=form), None)


class TestDiscovery:
    def test_protected_resource_metadata(self, svc):
        got = body_of(api.handler(event("GET", "/.well-known/oauth-protected-resource"), None))
        assert got["resource"].endswith("/api/mcp")
        assert got["authorization_servers"]

    def test_metadata_is_reachable_with_the_resource_path_appended(self, svc):
        """RFC 9728 clients probe /.well-known/oauth-protected-resource/api/mcp."""
        res = api.handler(event("GET", "/.well-known/oauth-protected-resource/api/mcp"), None)
        assert res["statusCode"] == 200

    def test_authorization_server_metadata(self, svc):
        got = body_of(api.handler(event("GET", "/.well-known/oauth-authorization-server"), None))
        assert got["code_challenge_methods_supported"] == ["S256"]
        assert got["registration_endpoint"].endswith("/oauth/register")

    def test_discovery_needs_no_token(self, svc):
        for path in ("/.well-known/oauth-protected-resource", "/.well-known/oauth-authorization-server"):
            assert api.handler(event("GET", path), None)["statusCode"] == 200


class TestHappyPath:
    def test_register_authorize_consent_exchange(self, svc):
        client_id = register()

        started = authorize(client_id)
        assert started["statusCode"] == 302
        assert "/authorize?request=oar_" in started["headers"]["Location"]

        rid = request_id_from(started)
        detail = body_of(api.handler(event("GET", f"/api/public/oauth/request/{rid}"), None))
        assert detail["client_name"] == "Claude"
        assert detail["redirect_host"] == "127.0.0.1"

        granted = grant(rid)
        assert granted["statusCode"] == 200
        location = body_of(granted)["redirect_to"]
        assert location.startswith(REDIRECT + "?")
        assert "state=st-1" in location

        tokens = body_of(exchange(code_from(granted), client_id))
        assert tokens["access_token"] == f"id-token-for-{USER}"
        assert tokens["token_type"] == "Bearer"
        assert tokens["refresh_token"] == "refresh-abc"

    def test_declining_sends_access_denied_and_no_code(self, svc):
        client_id = register()
        rid = request_id_from(authorize(client_id))
        location = body_of(grant(rid, approve=False))["redirect_to"]
        assert "error=access_denied" in location
        assert "code=" not in location


class TestCodeIsSingleUse:
    def test_a_replayed_code_is_refused(self, svc):
        client_id = register()
        code = code_from(grant(request_id_from(authorize(client_id))))
        assert exchange(code, client_id)["statusCode"] == 200
        second = exchange(code, client_id)
        assert second["statusCode"] == 400
        assert body_of(second)["error"] == "invalid_grant"

    def test_a_consumed_request_cannot_mint_a_second_code(self, svc):
        client_id = register()
        rid = request_id_from(authorize(client_id))
        assert grant(rid)["statusCode"] == 200
        assert grant(rid)["statusCode"] == 404


class TestCodeBinding:
    def test_the_wrong_verifier_is_refused(self, svc):
        """Someone who intercepted the code but not the verifier gets nothing."""
        client_id = register()
        code = code_from(grant(request_id_from(authorize(client_id))))
        res = exchange(code, client_id, verifier="w" * 64)
        assert res["statusCode"] == 400
        assert body_of(res)["error"] == "invalid_grant"

    def test_a_missing_verifier_is_refused(self, svc):
        client_id = register()
        code = code_from(grant(request_id_from(authorize(client_id))))
        assert exchange(code, client_id, code_verifier="")["statusCode"] == 400

    def test_another_client_cannot_redeem_it(self, svc):
        mine = register("Mine")
        theirs = register("Theirs")
        code = code_from(grant(request_id_from(authorize(mine))))
        res = exchange(code, theirs)
        assert res["statusCode"] == 400
        assert body_of(res)["error"] == "invalid_grant"

    def test_a_mismatched_redirect_uri_is_refused(self, svc):
        client_id = register()
        code = code_from(grant(request_id_from(authorize(client_id))))
        assert exchange(code, client_id, redirect_uri="http://127.0.0.1:1/other")["statusCode"] == 400


class TestIdentity:
    def test_the_token_belongs_to_whoever_consented(self, svc):
        client_id = register()
        code = code_from(grant(request_id_from(authorize(client_id)), sub=OTHER_USER))
        assert body_of(exchange(code, client_id))["access_token"] == f"id-token-for-{OTHER_USER}"

    def test_consent_requires_a_signed_in_person(self, svc):
        """Without a JWT there is nobody to attach the code to."""
        client_id = register()
        rid = request_id_from(authorize(client_id))
        res = api.handler(event("POST", "/api/oauth/grant", body={"request": rid, "approve": True}), None)
        assert res["statusCode"] == 401


class TestRejections:
    def test_an_unregistered_redirect_uri_is_not_redirected_to(self, svc):
        client_id = register()
        res = authorize(client_id, redirect_uri="https://evil.test/cb")
        assert res["statusCode"] == 400, "an unregistered URI must never receive a redirect"
        assert body_of(res)["error"] == "invalid_redirect_uri"

    def test_an_unknown_client_is_not_redirected_to(self, svc):
        res = authorize("mcp_does_not_exist")
        assert res["statusCode"] == 400
        assert body_of(res)["error"] == "invalid_client"

    def test_a_client_mistake_is_redirected_back_to_the_client(self, svc):
        client_id = register()
        res = authorize(client_id, code_challenge_method="plain")
        assert res["statusCode"] == 302
        assert "error=invalid_request" in res["headers"]["Location"]
        assert res["headers"]["Location"].startswith(REDIRECT)

    def test_an_unsupported_grant_type(self, svc):
        res = api.handler(event("POST", "/oauth/token", form={"grant_type": "password",
                                                              "username": "a", "password": "b"}), None)
        assert res["statusCode"] == 400
        assert body_of(res)["error"] == "unsupported_grant_type"

    def test_an_unknown_code(self, svc):
        assert exchange("not-a-real-code", register())["statusCode"] == 400

    def test_an_expired_request_id(self, svc):
        assert api.handler(event("GET", "/api/public/oauth/request/oar_aaaaaaaaaaaaaaaaaaaa"), None)["statusCode"] == 404


class TestTokenEndpointAcceptsBothEncodings:
    def test_json_body(self, svc):
        client_id = register()
        code = code_from(grant(request_id_from(authorize(client_id))))
        res = api.handler(event("POST", "/oauth/token", body={
            "grant_type": "authorization_code", "code": code, "client_id": client_id,
            "redirect_uri": REDIRECT, "code_verifier": VERIFIER}), None)
        assert res["statusCode"] == 200
