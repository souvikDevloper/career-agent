"""HTTP API (API Gateway HTTP API, payload v2). Commands are validated, recorded and answered quickly;
long work is dispatched through the transactional outbox."""

from __future__ import annotations

import base64
import json
import re
import secrets
import time
import urllib.error
import urllib.request
from typing import Any, Callable

from pydantic import BaseModel, Field, ValidationError

from .. import connectors, discovery, voice
from ..config import settings as cfg
from ..demo import DEMO_FACTS, DEMO_PREFERENCES, DEMO_RESUME_TEXT, DEMO_SAVED_ANSWERS, PUBLISHABLE_TEMPLATES, minimal_pdf
from ..resume import ResumeError, resume_doc_id
from ..store import C, Delete, Put, Update
from ..util import get_logger, log, new_id
from ..workflow import Principal, WorkflowError
from .common import SECURITY_HEADERS, body_json, correlation, error, portal_signature, principal, respond, services, verify_signature

logger = get_logger("api")

# ---------------------------------------------------------------------------
# request models
# ---------------------------------------------------------------------------


class CommandIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    client_request_id: str = Field(min_length=8, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")
    source: str = Field(default="chat", pattern=r"^(chat|voice)$")


class SettingsIn(BaseModel):
    mode: str | None = Field(default=None, pattern=r"^(review|auto_above_80|auto_eligible)$")
    daily_cap: int | None = Field(default=None, ge=0, le=25)
    cooldown_seconds: int | None = Field(default=None, ge=30, le=3600)
    timezone: str | None = Field(default=None, max_length=60)
    notify_email: str | None = Field(default=None, max_length=200)
    voice_enabled: bool | None = None
    preferences: dict | None = None


class MandateIn(BaseModel):
    enabled: bool
    mode: str | None = Field(default=None, pattern=r"^(auto_above_80|auto_eligible)$")
    hours: int = Field(default=72, ge=1, le=720)


class UploadIn(BaseModel):
    filename: str = Field(min_length=1, max_length=200)
    size: int = Field(gt=0, le=5 * 1024 * 1024)


class ApproveIn(BaseModel):
    packet_hash: str = Field(min_length=64, max_length=64)


class BrowserSessionIn(BaseModel):
    packet_hash: str = Field(min_length=64, max_length=64)


class BrowserCompleteIn(BaseModel):
    outcome: str = Field(pattern=r"^(submitted|needs_user|known_failure|unknown)$")
    reference: str | None = Field(default=None, max_length=300)
    provider: str | None = Field(default=None, max_length=120)
    url: str | None = Field(default=None, max_length=2000)
    reason: str | None = Field(default=None, max_length=500)


class WatchIn(BaseModel):
    keywords: str = Field(min_length=1, max_length=200)


class SearchIn(BaseModel):
    keywords: str = Field(default="", max_length=200)
    client_request_id: str = Field(min_length=8, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")


class FeedbackIn(BaseModel):
    question: str = Field(min_length=3, max_length=600)
    answer: str = Field(min_length=1, max_length=4000)
    client_request_id: str = Field(min_length=8, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")


# ---------------------------------------------------------------------------
# router
# ---------------------------------------------------------------------------

Route = tuple[str, re.Pattern, Callable[..., dict], bool]
ROUTES: list[Route] = []


def route(method: str, pattern: str, auth: bool = True):
    def deco(fn):
        ROUTES.append((method, re.compile("^" + pattern + "$"), fn, auth))
        return fn

    return deco


def handler(event: dict, context: Any) -> dict:
    cid = correlation(event)
    method = event.get("requestContext", {}).get("http", {}).get("method", "GET")
    path = event.get("rawPath", "")
    started = time.time()
    try:
        for m, rx, fn, auth in ROUTES:
            match = rx.match(path)
            if m != method or not match:
                continue
            p = principal(event)
            if auth and p is None:
                return error(401, "unauthorized", "Sign in required", cid)
            res = fn(event=event, p=p, cid=cid, **match.groupdict())
            log(logger, "http.request", method=method, route=rx.pattern, status=res["statusCode"],
                ms=int((time.time() - started) * 1000), correlation_id=cid, user=(p.user_id if p else None))
            return res
        return error(404, "not_found", "No such route", cid)
    except ValidationError as exc:
        return error(400, "invalid_request", "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors()[:5]), cid)
    except (ValueError, json.JSONDecodeError) as exc:
        return error(400, "invalid_request", str(exc)[:200], cid)
    except WorkflowError as exc:
        return error(exc.status, exc.code, str(exc), cid)
    except ResumeError as exc:
        return error(422, "resume_error", str(exc), cid)
    except Exception as exc:  # pragma: no cover - logged, never leaked
        log(logger, "http.error", error=type(exc).__name__, detail=str(exc)[:500], correlation_id=cid, path=path)
        return error(500, "internal", "Something went wrong. Reference: " + cid, cid)


def _svc():
    return services()


# ---------------------------------------------------------------------------
# public
# ---------------------------------------------------------------------------


@route("GET", r"/api/public/health", auth=False)
def health(event, p, cid):
    return respond(200, {"ok": True, "service": "career-agent", "version": "1.0.0", "stage": cfg().stage})


@route("GET", r"/api/public/status", auth=False)
def public_status(event, p, cid):
    return respond(200, {"sources": discovery.source_status(_svc().wf), "connectors": connectors.CONNECTORS,
                         "model": cfg().model_id, "region": cfg().region})


@route("POST", r"/api/public/demo-session", auth=False)
def demo_session(event, p, cid):
    """Isolated example workspace: a short-lived Cognito user in the 'judge' group with fictional data."""
    import boto3

    svc = _svc()
    hour = time.strftime("%Y%m%d%H", time.gmtime())
    try:
        svc.store.update(Update("DEMO#RATE", hour, add={"count": 1}, set={"ttl": int(time.time()) + 7200},
                                condition=_rate_condition(cfg().demo_sessions_per_hour)))
    except Exception as exc:
        if type(exc).__name__ == "ConditionFailed":
            return error(429, "busy", "Too many example workspaces were started this hour. Please try again shortly.", cid)
        raise
    idp = boto3.client("cognito-idp")
    username = f"judge-{secrets.token_hex(6)}@example.com"  # the pool uses email as the username attribute
    password = "Aa1!" + secrets.token_urlsafe(24)
    pool = cfg().user_pool_id
    idp.admin_create_user(UserPoolId=pool, Username=username, MessageAction="SUPPRESS",
                          UserAttributes=[{"Name": "email", "Value": username}, {"Name": "email_verified", "Value": "true"}])
    idp.admin_set_user_password(UserPoolId=pool, Username=username, Password=password, Permanent=True)
    idp.admin_add_user_to_group(UserPoolId=pool, Username=username, GroupName="judge")
    auth = idp.admin_initiate_auth(UserPoolId=pool, ClientId=cfg().user_pool_client_id, AuthFlow="ADMIN_USER_PASSWORD_AUTH",
                                   AuthParameters={"USERNAME": username, "PASSWORD": password})["AuthenticationResult"]
    sub = next(a["Value"] for a in idp.admin_get_user(UserPoolId=pool, Username=username)["UserAttributes"] if a["Name"] == "sub")
    seed_example_workspace(sub, username)
    return respond(201, {"id_token": auth["IdToken"], "access_token": auth["AccessToken"], "expires_in": auth["ExpiresIn"],
                         "refresh_token": auth.get("RefreshToken"), "username": username, "example_workspace": True})


def _rate_condition(limit: int):
    from ..store import Or

    return Or(C("count", "not_exists"), C("count", "lt", limit))


def seed_example_workspace(uid: str, username: str) -> None:
    import boto3

    svc = _svc()
    key = f"resumes/{uid}/example-aarav-mehta.pdf"
    boto3.client("s3").put_object(Bucket=cfg().bucket, Key=key, Body=minimal_pdf(DEMO_RESUME_TEXT), ContentType="application/pdf",
                                  ServerSideEncryption="AES256")
    now = int(time.time())
    svc.store.put({"pk": f"USER#{uid}", "sk": "ACCOUNT", "is_judge": True, "username": username, "created_at": svc.wf.clock.iso(),
                   "gsi1pk": "JUDGE#accounts", "gsi1sk": svc.wf.clock.iso(), "ttl": now + 3 * 86400})
    svc.store.put({"pk": f"USER#{uid}", "sk": "SETTINGS", "preferences": DEMO_PREFERENCES, "mode": "review", "daily_cap": 5,
                   "cooldown_seconds": 30, "timezone": "Asia/Kolkata"})
    profile = svc.profiles.save_version(uid, DEMO_FACTS, key, DEMO_RESUME_TEXT, "example_workspace", saved_answers=DEMO_SAVED_ANSWERS)
    svc.store.transact([svc.wf.event_put(uid, "workspace.example_started", {"profile_version": profile["version"],
                                                                            "note": "Fictional applicant; test employer only"})])
    # Seed a watch and kick off one search. Without this the workspace opens with a
    # profile but no matches, which reads as a broken app rather than an empty one.
    svc.store.put({"pk": f"USER#{uid}", "sk": f"WATCH#{new_id('w_')}", "entity": "watch", "keywords": "intern",
                   "interval_minutes": 5, "enabled": True, "gsi1pk": "WATCH#enabled",
                   "gsi1sk": f"USER#{uid}", "created_at": svc.wf.clock.iso(), "ttl": now + 3 * 86400})
    svc.wf.start_operation(uid, "search", {"keywords": "intern"}, f"seed:{uid}", None)


@route("POST", r"/api/inbound/portal", auth=False)
def inbound_portal(event, p, cid):
    raw = event.get("body") or ""
    if event.get("isBase64Encoded"):
        import base64

        raw = base64.b64decode(raw).decode()
    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    if not verify_signature(raw, headers.get("x-portal-signature")):
        return error(403, "forbidden", "bad signature", cid)
    msg = json.loads(raw)
    svc = _svc()
    ref = svc.store.get(f"RECEIPT#{msg.get('reference')}", "RECEIPT")
    if not ref:
        return respond(202, {"accepted": True, "matched": False})
    svc.store.transact([svc.wf.outbox_put("work", {"kind": "inbound_message", "message": {**msg, "user_id": ref["user_id"]}},
                                          f"work:inbound:{msg['message_id']}")])
    return respond(202, {"accepted": True})


@route("POST", r"/api/telegram/webhook", auth=False)
def telegram_webhook(event, p, cid):
    from ..notify import telegram_call

    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    import hmac

    if not hmac.compare_digest(headers.get("x-telegram-bot-api-secret-token", ""), portal_signature("telegram-webhook")[:64]):
        return error(403, "forbidden", "bad secret", cid)
    upd = body_json(event)
    svc = _svc()
    if "message" in upd:
        chat = upd["message"]["chat"]["id"]
        text = (upd["message"].get("text") or "").strip()
        m = re.fullmatch(r"/start\s+([A-Z0-9]{6,12})", text)
        if m:
            link = svc.store.get(f"TGLINK#{m.group(1)}", "LINK")
            if link and float(link["expires_at"]) > time.time() and not link.get("used"):
                svc.store.transact([
                    Update(f"TGLINK#{m.group(1)}", "LINK", set={"used": True}, condition=C("used", "not_exists")),
                    Update(f"USER#{link['user_id']}", "SETTINGS", set={"telegram_chat_id": chat}),
                    svc.wf.event_put(link["user_id"], "connector.telegram_linked", {}),
                ])
                telegram_call("sendMessage", {"chat_id": chat, "text": "Linked to Career Agent. You'll get updates and approval requests here."})
            else:
                telegram_call("sendMessage", {"chat_id": chat, "text": "That link code is invalid or expired. Generate a new one in Settings."})
        return respond(200, {"ok": True})
    if "callback_query" in upd:
        cq = upd["callback_query"]
        data = cq.get("data", "")
        chat = cq.get("message", {}).get("chat", {}).get("id")
        answer = "This approval link is no longer valid."
        if data.startswith("ap:"):
            tok = svc.store.get(f"ACTIONTOKEN#{data[3:]}", "TOKEN")
            if tok and str(tok["chat_id"]) == str(chat) and float(tok["expires_at"]) > time.time():
                try:
                    app = svc.wf.approve(Principal(tok["user_id"], svc.is_judge(tok["user_id"])), tok["app_id"], tok["packet_hash"], "telegram")
                    answer = f"Approved. Status: {app['action_state']}"
                except WorkflowError as exc:
                    answer = str(exc)[:180]
        telegram_call("answerCallbackQuery", {"callback_query_id": cq["id"], "text": answer})
        return respond(200, {"ok": True})
    return respond(200, {"ok": True})


# ---------------------------------------------------------------------------
# account & settings
# ---------------------------------------------------------------------------


@route("GET", r"/api/me")
def me(event, p, cid):
    svc = _svc()
    account = svc.store.get(f"USER#{p.user_id}", "ACCOUNT")
    if not account and not p.is_judge:
        try:
            svc.store.put({"pk": f"USER#{p.user_id}", "sk": "ACCOUNT", "is_judge": False, "email": p.email,
                           "created_at": svc.wf.clock.iso()}, C("pk", "not_exists"))
        except Exception as exc:
            if type(exc).__name__ != "ConditionFailed":
                raise
    profile = svc.profiles.current(p.user_id)
    settings = svc.wf.settings(p.user_id)
    conn = {k: dict(v) for k, v in connectors.CONNECTORS.items()}
    if settings.get("telegram_chat_id"):
        conn["telegram"]["status"] = "verified_live"
    if settings.get("notify_email_verified"):
        conn["email-ses"]["status"] = "verified_live"
    if p.is_judge:
        conn["email-ses"]["note"] = "Example workspaces deliver email only to the project's own verified demo inbox."
    inbox = svc.store.query(f"USER#{p.user_id}", "INBOX#", limit=30, newest_first=True)
    return respond(200, {
        "user_id": p.user_id, "is_judge": p.is_judge, "email": p.email if not p.is_judge else None,
        "example_workspace": p.is_judge, "settings": _settings_public(settings, svc),
        "profile": _profile_public(profile), "connectors": conn, "usage": svc.wf.usage(p.user_id),
        "limits": {"model_calls": cfg().judge_daily_model_calls if p.is_judge else cfg().user_daily_model_calls,
                   "voice_seconds": cfg().judge_voice_seconds if p.is_judge else cfg().user_voice_seconds},
        "inbox": [_strip(i) for i in inbox], "sources": discovery.source_status(svc.wf),
        "watches": [_strip(w) for w in svc.store.query(f"USER#{p.user_id}", "WATCH#", limit=50)],
    })


def _settings_public(s: dict, svc) -> dict:
    out = {k: s.get(k) for k in ("mode", "daily_cap", "cooldown_seconds", "timezone", "notify_email", "notify_email_verified",
                                 "voice_enabled", "preferences", "mandate")}
    out["telegram_linked"] = bool(s.get("telegram_chat_id"))
    return out


def _profile_public(profile: dict | None) -> dict | None:
    if not profile:
        return None
    return {"version": profile["version"], "facts": profile["facts"], "created_at": profile["created_at"],
            "source": profile["source"], "saved_answers": profile.get("saved_answers", {}), "has_resume": bool(profile.get("resume_key"))}


def _strip(item: dict) -> dict:
    return {k: v for k, v in item.items() if k not in ("pk", "sk", "gsi1pk", "gsi1sk", "ttl")}


@route("PUT", r"/api/settings")
def put_settings(event, p, cid):
    data = SettingsIn(**body_json(event)).model_dump(exclude_none=True)
    svc = _svc()
    if data.get("notify_email"):
        if p.is_judge:
            raise WorkflowError("forbidden", "Example workspaces can't send email to arbitrary addresses.", 403)
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", data["notify_email"]):
            raise ValueError("invalid email")
    s = svc.wf.update_settings(p.user_id, data)
    ledger = svc.store.get(f"USER#{p.user_id}", svc.wf.ledger_key(p.user_id, s)) or {}
    return respond(200, {"settings": _settings_public(s, svc), "today": _strip(ledger) if ledger else {}})


@route("POST", r"/api/mandate")
def mandate(event, p, cid):
    data = MandateIn(**body_json(event))
    s = _svc().wf.set_mandate(p, data.enabled, data.mode, data.hours)
    return respond(200, {"settings": _settings_public(s, _svc())})


@route("POST", r"/api/email/verify")
def email_verify(event, p, cid):
    import boto3

    if p.is_judge:
        raise WorkflowError("forbidden", "Not available in example workspaces.", 403)
    s = _svc().wf.settings(p.user_id)
    email = s.get("notify_email")
    if not email:
        raise ValueError("set notify_email first")
    ses = boto3.client("ses", region_name=cfg().region)
    status = ses.get_identity_verification_attributes(Identities=[email])["VerificationAttributes"].get(email, {}).get("VerificationStatus")
    if status == "Success":
        _svc().store.update(Update(f"USER#{p.user_id}", "SETTINGS", set={"notify_email_verified": True}))
        return respond(200, {"verified": True})
    ses.verify_email_identity(EmailAddress=email)
    return respond(202, {"verified": False, "message": "AWS sent a verification email. Click the link, then press Verify again."})


@route("POST", r"/api/telegram/link-code")
def telegram_link(event, p, cid):
    from ..notify import telegram_token

    if not telegram_token():
        raise WorkflowError("needs_setup", "The Telegram bot is not configured on this deployment.", 409)
    code = secrets.token_hex(4).upper()
    _svc().store.put({"pk": f"TGLINK#{code}", "sk": "LINK", "user_id": p.user_id, "expires_at": time.time() + 900,
                      "ttl": int(time.time()) + 3600})
    bot = __import__("os").environ.get("TELEGRAM_BOT_USERNAME", "")
    return respond(200, {"code": code, "command": f"/start {code}", "bot": bot, "deep_link": f"https://t.me/{bot}?start={code}" if bot else None})


@route("DELETE", r"/api/account")
def delete_account(event, p, cid):
    n = _svc().delete_account_data(p.user_id)
    return respond(200, {"deleted_items": n, "note": "Queued work referencing deleted records will be discarded."})


# ---------------------------------------------------------------------------
# resume & profile
# ---------------------------------------------------------------------------


@route("POST", r"/api/resume/upload-url")
def upload_url(event, p, cid):
    import boto3

    data = UploadIn(**body_json(event))
    ext = data.filename.lower().rsplit(".", 1)[-1]
    if ext not in ("pdf", "docx"):
        raise ResumeError("Only PDF or DOCX resumes are supported.")
    rid = resume_doc_id()
    key = f"resumes/{p.user_id}/{rid}.{ext}"
    post = boto3.client("s3").generate_presigned_post(
        Bucket=cfg().bucket, Key=key, ExpiresIn=300,
        Fields={"x-amz-server-side-encryption": "AES256"},
        Conditions=[["content-length-range", 100, 5 * 1024 * 1024], {"x-amz-server-side-encryption": "AES256"}])
    _svc().store.put({"pk": f"USER#{p.user_id}", "sk": f"RESUME#{rid}", "entity": "resume", "resume_id": rid, "s3_key": key,
                      "filename": data.filename[:200], "status": "awaiting_upload", "created_at": _svc().wf.clock.iso()})
    return respond(201, {"resume_id": rid, "upload": post})


@route("POST", r"/api/resume/(?P<rid>res_[a-z0-9]+)/process")
def process_resume(event, p, cid, rid):
    body = body_json(event)
    op, created = _svc().wf.start_operation(p.user_id, "resume", {"resume_id": rid}, body.get("client_request_id") or f"resume-{rid}", cid)
    return respond(202 if created else 200, {"operation": _strip(op)})


@route("GET", r"/api/profile")
def get_profile(event, p, cid):
    return respond(200, {"profile": _profile_public(_svc().profiles.current(p.user_id))})


@route("PATCH", r"/api/profile")
def patch_profile(event, p, cid):
    body = body_json(event)
    prof = _svc().profiles.correct(p.user_id, body)
    return respond(200, {"profile": _profile_public(prof)})


@route("PUT", r"/api/profile/answers")
def put_answers(event, p, cid):
    body = body_json(event)
    answers = body.get("answers") or {}
    if not isinstance(answers, dict) or len(answers) > 40:
        raise ValueError("answers must be an object")
    prof = _svc().profiles.save_answers(p.user_id, answers)
    app_id = body.get("reprepare_app_id")
    if app_id:
        _svc().request_prepare(p.user_id, app_id=app_id)
    return respond(200, {"profile": _profile_public(prof)})


@route("GET", r"/api/resume/file")
def resume_file(event, p, cid):
    prof = _svc().profiles.current(p.user_id)
    if not prof or not prof.get("resume_key"):
        raise WorkflowError("not_found", "no resume", 404)
    url = _svc().s3.generate_presigned_url("get_object", Params={"Bucket": cfg().bucket, "Key": prof["resume_key"]}, ExpiresIn=120)
    return respond(200, {"url": url})


@route("POST", r"/api/resume/improve")
def resume_improve(event, p, cid):
    body = body_json(event)
    op, created = _svc().wf.start_operation(p.user_id, "resume_improve", {"job_key": body.get("job_key")},
                                            body.get("client_request_id") or new_id("ri"), cid)
    return respond(202, {"operation": _strip(op)})


# ---------------------------------------------------------------------------
# agent commands & operations
# ---------------------------------------------------------------------------


@route("POST", r"/api/commands")
def command(event, p, cid):
    data = CommandIn(**body_json(event))
    svc = _svc()
    ts = svc.wf.clock.iso()
    op, created = svc.wf.start_operation(p.user_id, "chat", {"text": data.text, "source": data.source}, data.client_request_id, cid)
    if created:
        svc.store.put({"pk": f"USER#{p.user_id}", "sk": f"CHAT#{ts}#{op['op_id']}#u", "entity": "chat", "role": "user",
                       "text": data.text, "source": data.source, "op_id": op["op_id"], "at": ts, "ttl": int(time.time()) + 14 * 86400})
    return respond(202 if created else 200, {"operation": _strip(op)})


@route("GET", r"/api/operations/(?P<op_id>op_[a-z0-9]+)")
def get_operation(event, p, cid, op_id):
    op = _svc().store.get(f"USER#{p.user_id}", f"OP#{op_id}")
    if not op:
        raise WorkflowError("not_found", "operation not found", 404)
    return respond(200, {"operation": _strip(op)})


@route("GET", r"/api/chat")
def chat_history(event, p, cid):
    """The conversation, oldest first.

    The window is a query parameter because sixty was a guess that the client
    then cut to forty, so scrolling up simply ran out of conversation - there was
    nothing above, which reads as broken scrolling rather than a missing page.
    """
    raw = (event.get("queryStringParameters") or {}).get("limit")
    try:
        limit = max(10, min(400, int(raw)))
    except (TypeError, ValueError):
        limit = 60
    rows = _svc().store.query(f"USER#{p.user_id}", "CHAT#", limit=limit, newest_first=True)
    return respond(200, {"messages": [_strip(r) for r in reversed(rows)], "complete": len(rows) < limit})


@route("DELETE", r"/api/chat")
def clear_chat(event, p, cid):
    """Start a fresh conversation.

    The worker replays the last thirteen turns, so a failure the agent hit an
    hour ago stays in front of it and it keeps answering from that belief - it
    reported "a technical error" for searches that had already been fixed,
    without calling the tool at all. Clearing is the user's own history and
    nothing else: applications, matches and profile are untouched.
    """
    store = _svc().store
    rows = store.query(f"USER#{p.user_id}", "CHAT#", limit=500, newest_first=True)
    for row in rows:
        store.delete(row["pk"], row["sk"])
    return respond(200, {"cleared": len(rows)})


@route("POST", r"/api/search")
def search(event, p, cid):
    data = SearchIn(**body_json(event))
    op, created = _svc().wf.start_operation(p.user_id, "search", {"keywords": data.keywords}, data.client_request_id, cid)
    return respond(202 if created else 200, {"operation": _strip(op)})


# ---------------------------------------------------------------------------
# jobs, watches, monitor
# ---------------------------------------------------------------------------


@route("GET", r"/api/jobs/matches")
def matches(event, p, cid):
    svc = _svc()
    return respond(200, {"matches": [svc.match_card(m) for m in svc.matcher.list(p.user_id)],
                         "sources": discovery.source_status(svc.wf)})


@route("POST", r"/api/watches")
def create_watch(event, p, cid):
    data = WatchIn(**body_json(event))
    return respond(201, {"watch": _strip(_svc().create_watch(p.user_id, data.keywords))})


@route("DELETE", r"/api/watches/(?P<wid>w_[a-z0-9]+)")
def delete_watch(event, p, cid, wid):
    _svc().delete_watch(p.user_id, wid)
    return respond(204, {})


@route("POST", r"/api/monitor/check")
def check_now(event, p, cid):
    """Runs the real discovery pipeline immediately (same code path as the 5-minute schedule)."""
    svc = _svc()
    minute = time.strftime("%Y%m%d%H%M", time.gmtime())
    svc.store.transact([svc.wf.outbox_put("work", {"kind": "monitor_now", "user_id": p.user_id}, f"work:monitor:{p.user_id}:{minute}")])
    return respond(202, {"queued": True, "note": "Checking all sources now. New matches will appear in a few seconds."})


@route("GET", r"/api/demo/templates")
def demo_templates(event, p, cid):
    return respond(200, {"templates": [{"slug": t["slug"], "title": t["title"], "location": t["location"]} for t in PUBLISHABLE_TEMPLATES]})


@route("POST", r"/api/demo/publish-job")
def publish_job(event, p, cid):
    body = body_json(event)
    payload = json.dumps({"template": body.get("template"), "published_by": p.user_id[:8]})
    status, data = _portal_admin("/portal/api/admin/jobs", payload)
    svc = _svc()
    if status == 201:
        svc.store.transact([svc.wf.event_put(p.user_id, "demo.job_published", {"title": data["job"]["title"], "job_id": data["job"]["id"],
                                                                                "published_at": data["job"]["published_at"]})])
    return respond(status, data)


@route("POST", r"/api/demo/employer-reply")
def employer_reply(event, p, cid):
    body = body_json(event)
    app = _svc().wf.get_app(p.user_id, str(body.get("app_id")))
    if app.get("target_environment") != "test" or not app.get("receipt"):
        raise WorkflowError("invalid", "Employer replies can only be simulated for submitted test-employer applications.", 400)
    kind = body.get("kind")
    if kind not in ("assessment", "interview", "rejection"):
        raise ValueError("kind must be assessment, interview or rejection")
    status, data = _portal_admin("/portal/api/admin/reply", json.dumps({"reference": app["receipt"]["reference"], "kind": kind}))
    return respond(status, data)


def _portal_admin(path: str, payload: str) -> tuple[int, dict]:
    req = urllib.request.Request(f"{cfg().api_base_url.rstrip('/')}{path}", data=payload.encode(), method="POST",
                                 headers={"Content-Type": "application/json", "X-Portal-Signature": portal_signature(payload)})
    try:
        with urllib.request.urlopen(req, timeout=20) as res:  # noqa: S310 - our own API
            return res.status, json.loads(res.read())
    except urllib.error.HTTPError as exc:
        return exc.code, {"error": exc.read().decode()[:300]}


# ---------------------------------------------------------------------------
# applications
# ---------------------------------------------------------------------------


@route("GET", r"/api/applications")
def list_apps(event, p, cid):
    svc = _svc()
    s = svc.wf.settings(p.user_id)
    ledger = svc.store.get(f"USER#{p.user_id}", svc.wf.ledger_key(p.user_id, s)) or {}
    apps = sorted(svc.wf.list_apps(p.user_id), key=lambda a: a.get("updated_at", ""), reverse=True)
    return respond(200, {"applications": [_strip(a) for a in apps], "today": _strip(ledger), "daily_cap": s["daily_cap"]})


@route("GET", r"/api/applications/(?P<app_id>app_[a-z0-9]+)")
def app_detail(event, p, cid, app_id):
    return respond(200, _svc().application_detail(p.user_id, app_id))


@route("POST", r"/api/applications")
def app_from_job(event, p, cid):
    body = body_json(event)
    job_key = str(body.get("job_key", ""))[:200]
    app = _svc().request_prepare(p.user_id, job_key=job_key)
    return respond(202, {"application": _strip(app)})


@route("POST", r"/api/applications/(?P<app_id>app_[a-z0-9]+)/prepare")
def app_prepare(event, p, cid, app_id):
    app = _svc().request_prepare(p.user_id, app_id=app_id)
    return respond(202, {"application": _strip(app)})


@route("POST", r"/api/applications/(?P<app_id>app_[a-z0-9]+)/approve")
def app_approve(event, p, cid, app_id):
    data = ApproveIn(**body_json(event))
    app = _svc().wf.approve(p, app_id, data.packet_hash, "dashboard")
    return respond(200, {"application": _strip(app)})


@route("POST", r"/api/applications/(?P<app_id>app_[a-z0-9]+)/browser-session")
def browser_session_create(event, p, cid, app_id):
    """Mint a short-lived capability for the installed browser companion.

    The capability contains no account password/cookie. It only grants access to
    this exact approved packet for ten minutes, and is bound to its packet hash.
    """
    data = BrowserSessionIn(**body_json(event))
    svc = _svc()
    app = svc.wf.get_app(p.user_id, app_id)
    packet = svc.wf.latest_packet(p.user_id, app_id)
    if not packet or packet["hash"] != data.packet_hash or app.get("packet_hash") != data.packet_hash:
        raise WorkflowError("stale_packet", "refresh: the application packet changed")
    if app["action_state"] != "NeedsUserPresence":
        raise WorkflowError("invalid_state", f"application is {app['action_state']}, not ready for the browser companion")
    decision = svc.wf.decide_submission(p, app, svc.wf.settings(p.user_id), packet=packet)
    if not decision.allowed:
        raise WorkflowError("approval_required", "approve the current packet before opening the browser companion", 409)

    token = secrets.token_urlsafe(32)
    token_hash = __import__("hashlib").sha256(token.encode()).hexdigest()
    expires = int(time.time()) + 600
    svc.store.put({
        "pk": f"BROWSERSESSION#{token_hash}", "sk": "SESSION", "entity": "browser_session",
        "user_id": p.user_id, "app_id": app_id, "packet_hash": data.packet_hash,
        "is_judge": bool(p.is_judge), "created_at": svc.wf.clock.iso(), "ttl": expires,
    }, C("pk", "not_exists"))
    target = ((packet.get("body") or {}).get("target") or {}).get("url") or app.get("url")
    return respond(201, {"token": token, "target_url": target, "expires_in": 600})


def _browser_capability(token: str):
    svc = _svc()
    token_hash = __import__("hashlib").sha256(token.encode()).hexdigest()
    row = svc.store.get(f"BROWSERSESSION#{token_hash}", "SESSION")
    if not row or int(row.get("ttl", 0)) <= int(time.time()):
        raise WorkflowError("expired", "browser companion session expired; start again from Career Agent", 410)
    return svc, row


@route("GET", r"/api/public/browser-session/(?P<token>[A-Za-z0-9_-]{20,})", auth=False)
def browser_session_get(event, p, cid, token):
    svc, row = _browser_capability(token)
    app = svc.wf.get_app(row["user_id"], row["app_id"])
    packet = svc.wf.latest_packet(row["user_id"], row["app_id"])
    if not packet or packet["hash"] != row["packet_hash"]:
        raise WorkflowError("stale_packet", "application packet changed; start a new browser session", 409)
    body = packet.get("body") or {}
    resume_url = None
    if body.get("resume_key") and cfg().bucket:
        resume_url = svc.s3.generate_presigned_url(
            "get_object", Params={"Bucket": cfg().bucket, "Key": body["resume_key"]}, ExpiresIn=600)
    return respond(200, {
        "app_id": row["app_id"], "packet_hash": row["packet_hash"],
        "company": app.get("company"), "title": app.get("title"),
        "target": body.get("target") or {}, "answers": body.get("answers") or {},
        "fields": packet.get("fields") or [], "resume_url": resume_url,
    })


@route("PUT", r"/api/public/browser-session/(?P<token>[A-Za-z0-9_-]{20,})/answers", auth=False)
def browser_session_answers(event, p, cid, token):
    """Persist non-sensitive answers the user supplied in the live form.

    The browser companion filters protected/sensitive fields before sending.
    The backend still constrains count and size because this capability is public
    and intentionally short lived.
    """
    body = body_json(event)
    answers = body.get("answers") or {}
    if not isinstance(answers, dict) or len(answers) > 30:
        raise ValueError("answers must be an object with at most 30 entries")
    cleaned = {}
    for key, value in answers.items():
        label = str(key).strip()[:120]
        if not label or value in (None, ""):
            continue
        cleaned[label] = str(value)[:1000]
    svc, row = _browser_capability(token)
    if cleaned:
        svc.profiles.save_answers(row["user_id"], cleaned)
    return respond(200, {"saved": len(cleaned)})


@route("POST", r"/api/public/browser-session/(?P<token>[A-Za-z0-9_-]{20,})/start", auth=False)
def browser_session_start(event, p, cid, token):
    svc, row = _browser_capability(token)
    app = svc.wf.local_browser_start(
        Principal(row["user_id"], bool(row.get("is_judge"))), row["app_id"], row["packet_hash"])
    return respond(200, {"application": _strip(app)})


@route("POST", r"/api/public/browser-session/(?P<token>[A-Za-z0-9_-]{20,})/dispatch", auth=False)
def browser_session_dispatch(event, p, cid, token):
    svc, row = _browser_capability(token)
    app = svc.wf.local_browser_dispatch(
        Principal(row["user_id"], bool(row.get("is_judge"))), row["app_id"], row["packet_hash"])
    return respond(200, {"application": _strip(app)})


@route("POST", r"/api/public/browser-session/(?P<token>[A-Za-z0-9_-]{20,})/complete", auth=False)
def browser_session_complete(event, p, cid, token):
    data = BrowserCompleteIn(**body_json(event))
    svc, row = _browser_capability(token)
    receipt = None
    if data.outcome == "submitted":
        receipt = {"reference": data.reference or "", "provider": data.provider or "authenticated-browser",
                   "url": data.url}
    app = svc.wf.local_browser_complete(
        Principal(row["user_id"], bool(row.get("is_judge"))), row["app_id"], row["packet_hash"],
        data.outcome, receipt=receipt, reason=data.reason)
    if data.outcome in ("submitted", "known_failure"):
        token_hash = __import__("hashlib").sha256(token.encode()).hexdigest()
        svc.store.update(Update(f"BROWSERSESSION#{token_hash}", "SESSION", set={"completed_at": svc.wf.clock.iso()}))
    return respond(200, {"application": _strip(app)})


@route("POST", r"/api/applications/(?P<app_id>app_[a-z0-9]+)/reject")
def app_reject(event, p, cid, app_id):
    body = body_json(event)
    return respond(200, {"application": _strip(_svc().wf.reject(p, app_id, str(body.get("reason", ""))))})


@route("POST", r"/api/applications/(?P<app_id>app_[a-z0-9]+)/pause")
def app_pause(event, p, cid, app_id):
    return respond(200, {"application": _strip(_svc().wf.pause(p, app_id))})


@route("POST", r"/api/applications/(?P<app_id>app_[a-z0-9]+)/resume")
def app_resume(event, p, cid, app_id):
    return respond(200, {"application": _strip(_svc().wf.resume(p, app_id))})


@route("POST", r"/api/applications/(?P<app_id>app_[a-z0-9]+)/handoff-complete")
def handoff_complete(event, p, cid, app_id):
    svc = _svc()
    app = svc.wf.get_app(p.user_id, app_id)
    if app["action_state"] not in ("ManualHandoff", "NeedsUserPresence"):
        raise WorkflowError("invalid_state", "Only browser/user handoffs can be marked as submitted by you.")
    svc.store.transact([svc.wf._transition(app, "Submitted", {"recruitment_stage": "applied", "receipt": {"reference": "user-reported",
                                                                                                          "user_reported": True}}),
                        svc.wf.event_put(p.user_id, "submission.user_reported", {"note": "User applied on the employer site"}, app_id)])
    return respond(200, {"application": _strip(svc.wf.get_app(p.user_id, app_id))})


@route("POST", r"/api/applications/(?P<app_id>app_[a-z0-9]+)/interview/questions")
def interview_q(event, p, cid, app_id):
    body = body_json(event)
    op, created = _svc().wf.start_operation(p.user_id, "interview_questions", {"app_id": app_id},
                                            body.get("client_request_id") or new_id("iq"), cid)
    return respond(202, {"operation": _strip(op)})


@route("POST", r"/api/applications/(?P<app_id>app_[a-z0-9]+)/interview/feedback")
def interview_fb(event, p, cid, app_id):
    data = FeedbackIn(**body_json(event))
    op, created = _svc().wf.start_operation(p.user_id, "interview_feedback", {"app_id": app_id, "question": data.question,
                                                                              "answer": data.answer}, data.client_request_id, cid)
    return respond(202, {"operation": _strip(op)})


@route("GET", r"/api/applications/(?P<app_id>app_[a-z0-9]+)/interview")
def interview_get(event, p, cid, app_id):
    item = _svc().store.get(f"USER#{p.user_id}", f"PREP#{app_id}")
    return respond(200, {"prep": _strip(item) if item else None})


# ---------------------------------------------------------------------------
# timeline, tasks, insights
# ---------------------------------------------------------------------------


@route("GET", r"/api/timeline")
def timeline(event, p, cid):
    rows = _svc().store.query(f"USER#{p.user_id}", "EVENT#", limit=150, newest_first=True)
    return respond(200, {"events": [_strip(r) for r in rows]})


@route("GET", r"/api/tasks")
def tasks(event, p, cid):
    rows = _svc().store.query(f"USER#{p.user_id}", "TASK#", limit=200, newest_first=True)
    return respond(200, {"tasks": [_strip(r) for r in rows]})


@route("PATCH", r"/api/tasks/(?P<tid>t_[a-z0-9]+)")
def patch_task(event, p, cid, tid):
    return respond(200, {"task": _strip(_svc().update_task(p.user_id, tid, body_json(event)))})


@route("GET", r"/api/insights")
def insights(event, p, cid):
    return respond(200, _svc().insights(p.user_id))


@route("POST", r"/api/inbox/read")
def inbox_read(event, p, cid):
    svc = _svc()
    for i in svc.store.query(f"USER#{p.user_id}", "INBOX#", limit=50):
        if not i.get("read"):
            svc.store.update(Update(i["pk"], i["sk"], set={"read": True}))
    return respond(200, {"ok": True})


# ---------------------------------------------------------------------------
# voice
# ---------------------------------------------------------------------------


@route("POST", r"/api/voice/session")
def voice_session(event, p, cid):
    body = body_json(event)
    svc = _svc()
    s = cfg()
    per_session = 60
    cap = s.judge_voice_seconds if p.is_judge else s.user_voice_seconds
    if not svc.wf.reserve_usage(p.user_id, "voice_seconds", per_session, cap, 20000):
        raise WorkflowError("quota", "Voice allowance for today is used up. You can keep typing.", 429)
    session = voice.presign_transcribe(body.get("language", "en-IN"))
    session["max_seconds"] = per_session
    return respond(201, session)


@route("POST", r"/api/speak")
def speak(event, p, cid):
    body = body_json(event)
    text = str(body.get("text", ""))[:1500]
    if not text:
        raise ValueError("text required")
    svc = _svc()
    cap = (cfg().judge_voice_seconds if p.is_judge else cfg().user_voice_seconds) * 20
    if not svc.wf.reserve_usage(p.user_id, "speech_chars", len(text), cap, 400000):
        raise WorkflowError("quota", "Speech allowance for today is used up; captions remain available.", 429)
    return respond(200, voice.synthesize(text, body.get("language", "en-IN")))


__all__ = ["handler", "Put"]


# ---------------------------------------------------------------------------
# MCP (Model Context Protocol) - the agent's tools as a connector
# ---------------------------------------------------------------------------


@route("POST", r"/api/mcp")
def mcp_endpoint(event, p, cid):
    """Streamable HTTP transport for the MCP server.

    API Gateway's JWT authorizer has already run, so the caller is a real signed-in
    user and every tool re-derives the owner from that identity. The protocol
    handling itself lives in career_agent.mcp and knows nothing about Lambda.
    """
    from .. import mcp as mcp_proto
    from ..agent import CTX, TOOL_NAMES, ToolContext

    try:
        message = json.loads(event.get("body") or "null")
    except json.JSONDecodeError:
        return respond(200, {"jsonrpc": "2.0", "id": None,
                             "error": {"code": mcp_proto.PARSE_ERROR, "message": "Invalid JSON"}})

    svc = _svc()

    def call_tool(name: str, arguments: dict):
        # Only the search tool needs an operation to stream progress into; writing
        # one for a read is a DynamoDB write nobody reads.
        op_id = ""
        if name == "search_jobs":
            op, _created = svc.wf.start_operation(p.user_id, "mcp", {"tool": name, "arguments": arguments}, cid, cid)
            op_id = op.get("op_id", "")
        ctx = ToolContext(user_id=p.user_id, op_id=op_id, user_text="", channel="mcp", correlation_id=cid,
                          services=svc, is_judge=p.is_judge)
        CTX.current = ctx
        try:
            return TOOL_NAMES[name](**arguments)
        finally:
            CTX.current = None

    reply = mcp_proto.dispatch(message, call_tool)
    log(logger, "mcp.request", method=(message or {}).get("method") if isinstance(message, dict) else None,
        tool=((message or {}).get("params") or {}).get("name") if isinstance(message, dict) else None,
        notification=reply is None, correlation_id=cid, user=p.user_id)
    if reply is None:
        # A notification gets an acknowledgement and no body.
        return {"statusCode": 202, "headers": dict(SECURITY_HEADERS), "body": ""}
    return respond(200, reply, {"MCP-Protocol-Version": mcp_proto.SUPPORTED_VERSIONS[0]})


# ---------------------------------------------------------------------------
# OAuth 2.1 for the MCP connector
#
# Cognito stays the only place a password is checked; these endpoints decide who
# may be handed a Cognito token, never who someone is. See career_agent.oauth.
# ---------------------------------------------------------------------------


def _base_url(event) -> str:
    configured = (cfg().public_base_url or "").rstrip("/")
    if configured:
        return configured
    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    host = headers.get("host") or ""
    return f"https://{host}" if host else ""


def _oauth_error(exc) -> dict:
    from .. import oauth as oa

    if isinstance(exc, oa.RedirectableError):
        return {"statusCode": 302, "headers": {**SECURITY_HEADERS, "Location": exc.location()}, "body": ""}
    return respond(exc.status, {"error": exc.code, "error_description": exc.description})


@route("GET", r"/\.well-known/oauth-protected-resource(/.*)?", auth=False)
def oauth_protected_resource(event, p, cid):
    from .. import oauth as oa

    return respond(200, oa.protected_resource_metadata(_base_url(event)), {"Cache-Control": "public, max-age=3600"})


@route("GET", r"/\.well-known/oauth-authorization-server(/.*)?", auth=False)
def oauth_as_metadata(event, p, cid):
    from .. import oauth as oa

    return respond(200, oa.authorization_server_metadata(_base_url(event)), {"Cache-Control": "public, max-age=3600"})


@route("POST", r"/oauth/register", auth=False)
def oauth_register(event, p, cid):
    from .. import oauth as oa

    try:
        client = oa.register_client(body_json(event), time.time())
    except oa.OAuthError as exc:
        return _oauth_error(exc)
    svc = _svc()
    svc.store.put({"pk": f"OAUTHCLIENT#{client['client_id']}", "sk": "META", "entity": "oauth_client",
                   **client, "ttl": int(time.time()) + oa.CLIENT_TTL_SECONDS})
    log(logger, "oauth.registered", client=client["client_id"], name=client["client_name"], correlation_id=cid)
    return respond(201, client)


@route("GET", r"/oauth/authorize", auth=False)
def oauth_authorize(event, p, cid):
    """Validate, park the request server-side, and hand the person to the app.

    Parking it means the browser carries an opaque id rather than the parameters
    themselves, so nothing a person could edit in the address bar changes where
    the code is ultimately delivered.
    """
    from .. import oauth as oa

    params = event.get("queryStringParameters") or {}
    svc = _svc()
    client = svc.store.get(f"OAUTHCLIENT#{params.get('client_id') or ''}", "META")
    try:
        request = oa.validate_authorize(params, client)
    except oa.OAuthError as exc:
        return _oauth_error(exc)

    rid = oa.new_request_id()
    svc.store.put({"pk": f"OAUTHREQ#{rid}", "sk": "META", "entity": "oauth_request", **request,
                   "created_at": svc.wf.clock.iso(), "ttl": int(time.time()) + oa.REQUEST_TTL_SECONDS})
    log(logger, "oauth.authorize_started", client=request["client_id"], correlation_id=cid)
    return {"statusCode": 302,
            "headers": {**SECURITY_HEADERS, "Location": f"{_base_url(event)}/authorize?request={rid}"},
            "body": ""}


@route("GET", r"/api/public/oauth/request/(?P<rid>oar_[A-Za-z0-9_-]{16,64})", auth=False)
def oauth_request_detail(event, p, cid, rid):
    """What the consent screen shows. Never returns the challenge or anything secret."""
    from .. import oauth as oa

    req = _svc().store.get(f"OAUTHREQ#{rid}", "META")
    if not req:
        raise WorkflowError("not_found", "That authorization request has expired. Start again from your client.", 404)
    return respond(200, oa.describe_consent(req.get("client_name", "An MCP client"), req["redirect_uri"]))


@route("POST", r"/api/oauth/grant")
def oauth_grant(event, p, cid):
    """The person consented. Mint a single-use code bound to their session.

    Reached only with a valid Cognito JWT, so the identity attached to the code
    is the one API Gateway verified - it is never taken from the request body.
    """
    from .. import oauth as oa

    data = body_json(event)
    rid = str(data.get("request") or "")
    svc = _svc()
    req = svc.store.get(f"OAUTHREQ#{rid}", "META")
    if not req:
        raise WorkflowError("not_found", "That authorization request has expired. Start again from your client.", 404)

    if not data.get("approve"):
        svc.store.delete(f"OAUTHREQ#{rid}", "META")
        denied = oa.RedirectableError("access_denied", "The person declined.", req["redirect_uri"], req.get("state", ""))
        return respond(200, {"redirect_to": denied.location()})

    id_token = str(data.get("id_token") or "")
    refresh_token = str(data.get("refresh_token") or "")
    if not id_token:
        raise WorkflowError("invalid_request", "Sign in again and retry the connection.", 400)

    code = oa.new_code()
    svc.store.transact([
        Put({"pk": f"OAUTHCODE#{code}", "sk": "META", "entity": "oauth_code", "user_id": p.user_id,
             "client_id": req["client_id"], "redirect_uri": req["redirect_uri"],
             "code_challenge": req["code_challenge"], "id_token": id_token, "refresh_token": refresh_token,
             "scope": req.get("scope", oa.SCOPE), "ttl": int(time.time()) + oa.CODE_TTL_SECONDS},
            C("pk", "not_exists")),
        Delete(f"OAUTHREQ#{rid}", "META"),
    ])
    params = {"code": code}
    if req.get("state"):
        params["state"] = req["state"]
    log(logger, "oauth.granted", client=req["client_id"], user=p.user_id, correlation_id=cid)
    return respond(200, {"redirect_to": oa.redirect_with(req["redirect_uri"], params)})


@route("POST", r"/oauth/token", auth=False)
def oauth_token(event, p, cid):
    form = _form_body(event)
    grant = form.get("grant_type")
    if grant == "authorization_code":
        return _oauth_code_exchange(form, cid)
    if grant == "refresh_token":
        return _oauth_refresh(form, cid)
    return respond(400, {"error": "unsupported_grant_type",
                         "error_description": "Supported grants: authorization_code, refresh_token."})


def _form_body(event) -> dict:
    """The token endpoint takes form encoding; accept JSON too, since clients differ."""
    import urllib.parse

    raw = event.get("body") or ""
    if event.get("isBase64Encoded"):
        raw = base64.b64decode(raw).decode("utf8", "ignore")
    if raw.lstrip().startswith("{"):
        try:
            data = json.loads(raw)
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {k: v[0] for k, v in urllib.parse.parse_qs(raw, keep_blank_values=True).items()}


def _oauth_code_exchange(form: dict, cid: str) -> dict:
    from .. import oauth as oa

    svc = _svc()
    code = str(form.get("code") or "")
    record = svc.store.get(f"OAUTHCODE#{code}", "META") if code else None
    if not record:
        return respond(400, {"error": "invalid_grant", "error_description": "That code is not valid."})
    # Single use. Deleting under a condition means two simultaneous redemptions
    # cannot both succeed; the loser is treated as a replay.
    try:
        svc.store.delete(f"OAUTHCODE#{code}", "META", C("pk", "exists"))
    except Exception as exc:
        if type(exc).__name__ != "ConditionFailed":
            raise
        return respond(400, {"error": "invalid_grant", "error_description": "That code has already been used."})

    if form.get("client_id") != record["client_id"]:
        return respond(400, {"error": "invalid_grant", "error_description": "That code was issued to another client."})
    if form.get("redirect_uri") and form["redirect_uri"] != record["redirect_uri"]:
        return respond(400, {"error": "invalid_grant", "error_description": "The redirect URI does not match."})
    if not oa.pkce_matches(str(form.get("code_verifier") or ""), record["code_challenge"]):
        return respond(400, {"error": "invalid_grant", "error_description": "The PKCE verifier does not match."})

    log(logger, "oauth.token_issued", client=record["client_id"], user=record["user_id"], correlation_id=cid)
    body = {"access_token": record["id_token"], "token_type": "Bearer", "expires_in": 3600,
            "scope": record.get("scope", oa.SCOPE)}
    if record.get("refresh_token"):
        body["refresh_token"] = record["refresh_token"]
    return respond(200, body)


def _oauth_refresh(form: dict, cid: str) -> dict:
    """Refreshing is Cognito's job; we only pass it through."""
    import boto3

    from .. import oauth as oa

    token = str(form.get("refresh_token") or "")
    if not token:
        return respond(400, {"error": "invalid_request", "error_description": "refresh_token is required."})
    try:
        auth = boto3.client("cognito-idp").initiate_auth(
            ClientId=cfg().user_pool_client_id, AuthFlow="REFRESH_TOKEN_AUTH",
            AuthParameters={"REFRESH_TOKEN": token})["AuthenticationResult"]
    except Exception as exc:
        log(logger, "oauth.refresh_failed", error=type(exc).__name__, correlation_id=cid)
        return respond(400, {"error": "invalid_grant",
                             "error_description": "That refresh token is no longer valid. Reconnect."})
    return respond(200, {"access_token": auth["IdToken"], "token_type": "Bearer",
                         "expires_in": auth.get("ExpiresIn", 3600), "scope": oa.SCOPE})
