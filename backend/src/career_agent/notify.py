"""Notifications: dashboard events always; SES email and Telegram when set up. Deduplicated per event/channel."""

from __future__ import annotations

import json
import os
import secrets
import urllib.parse
import urllib.request
from typing import Any

from .config import settings as cfg
from .store import C, Put, Update
from .util import get_logger, log

logger = get_logger("notify")


def telegram_token() -> str | None:
    name = cfg().telegram_secret_arn
    if not name:
        return None
    cached = os.environ.get("_TG_TOKEN_CACHE")
    if cached is not None:
        return cached or None
    import boto3

    try:
        value = boto3.client("ssm").get_parameter(Name=name, WithDecryption=True)["Parameter"]["Value"].strip()
    except Exception:
        value = ""
    if value in ("none", "unset", "-"):
        value = ""
    os.environ["_TG_TOKEN_CACHE"] = value
    return value or None


def telegram_call(method: str, payload: dict) -> dict:
    token = telegram_token()
    if not token:
        raise RuntimeError("telegram not configured")
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/{method}", data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=10) as res:  # noqa: S310
        return json.loads(res.read())


def compose(msg: dict, app: dict | None) -> tuple[str, str, bool]:
    """Returns (subject, text, wants_approval_button)."""
    kind = msg["kind"]
    name = f"{(app or {}).get('title', 'a role')} at {(app or {}).get('company', '')}".strip()
    env = " [TEST ENVIRONMENT]" if (app or {}).get("target_environment") == "test" else ""
    if kind == "approval_requested":
        return f"Approve application: {name}", f"Your application for {name}{env} is ready. Review the exact answers, then approve.", True
    if kind == "information_needed":
        qs = "; ".join(msg.get("questions", [])[:4])
        return f"We need an answer: {name}", f"{name}{env} has required questions we won't guess: {qs}", False
    if kind == "submitted":
        return f"Submitted: {name}", f"Submitted {name}{env}. Receipt reference: {msg.get('reference')}.", False
    if kind == "failed":
        return f"Submission failed: {name}", f"{name}{env} was not submitted: {msg.get('reason')}.", False
    if kind == "needs_review":
        return f"Check needed: {name}", f"We couldn't confirm whether {name}{env} went through. We will not retry until you check.", False
    if kind == "new_match":
        return f"New match {msg.get('score')}/100: {name}", f"New opening {name}{env} scored {msg.get('score')}/100 on our fit rubric.", False
    if kind == "employer_message":
        due = f" Deadline: {msg['deadline']}." if msg.get("deadline") else ""
        return f"Employer update: {name}", f"New {str(msg.get('type', 'message')).replace('_', ' ')} for {name}{env}.{due}", False
    if kind == "reminder":
        return f"Reminder: {msg.get('title')}", f"Reminder: {msg.get('title')} for {name} is due {msg.get('due')}.", False
    return "Career Agent update", f"Update for {name}.", False


class Notifier:
    def __init__(self, services) -> None:
        self.svc = services
        self.store = services.store
        self.wf = services.wf

    def _claim(self, uid: str, key: str, channel: str) -> bool:
        try:
            self.store.put({"pk": f"USER#{uid}", "sk": f"NOTIF#{channel}#{key}", "entity": "notification", "channel": channel,
                            "state": "sending", "at": self.wf.clock.iso(), "ttl": int(self.wf.clock.now()) + 30 * 86400},
                           C("pk", "not_exists"))
            return True
        except Exception as exc:
            if type(exc).__name__ == "ConditionFailed":
                return False
            raise

    def _mark(self, uid: str, key: str, channel: str, state: str, detail: str = "") -> None:
        self.store.update(Update(f"USER#{uid}", f"NOTIF#{channel}#{key}", set={"state": state, "detail": detail[:300]}))

    def action_token(self, uid: str, app: dict, chat_id: Any) -> str:
        token = secrets.token_urlsafe(18)
        self.store.put({"pk": f"ACTIONTOKEN#{token}", "sk": "TOKEN", "user_id": uid, "app_id": app["app_id"],
                        "packet_hash": app["packet_hash"], "chat_id": str(chat_id), "expires_at": self.wf.clock.now() + 24 * 3600,
                        "ttl": int(self.wf.clock.now()) + 2 * 86400})
        return token

    def deliver(self, msg: dict, dedupe: str) -> dict:
        uid = msg["user_id"]
        app = None
        if msg.get("app_id"):
            try:
                app = self.wf.get_app(uid, msg["app_id"])
            except Exception:
                app = None
        subject, text, approval = compose(msg, app)
        settings = self.wf.settings(uid)
        link = f"{cfg().public_base_url.rstrip('/')}/app/applications/{msg.get('app_id')}" if msg.get("app_id") else cfg().public_base_url
        results: dict[str, str] = {}
        is_judge = self.svc.is_judge(uid)

        # Dashboard inbox (always)
        if self._claim(uid, dedupe, "dashboard"):
            self.store.put({"pk": f"USER#{uid}", "sk": f"INBOX#{self.wf.clock.iso()}#{dedupe[:40]}", "entity": "inbox", "kind": msg["kind"],
                            "subject": subject, "text": text, "app_id": msg.get("app_id"), "read": False, "at": self.wf.clock.iso(),
                            "ttl": int(self.wf.clock.now()) + 30 * 86400})
            self._mark(uid, dedupe, "dashboard", "delivered")
            results["dashboard"] = "delivered"

        # Email via SES (verified recipients only; judge sessions only to pre-verified demo inbox)
        to = settings.get("notify_email") if settings.get("notify_email_verified") else None
        if is_judge:
            to = os.environ.get("DEMO_INBOX") or None
        if to and cfg().ses_sender and self._claim(uid, dedupe, "email"):
            try:
                import boto3

                html = (f"<div style='font-family:Inter,Arial,sans-serif;max-width:520px'><h2 style='color:#0f172a'>{_esc(subject)}</h2>"
                        f"<p style='color:#334155;font-size:15px'>{_esc(text)}</p>"
                        f"<p><a href='{link}' style='background:#4f46e5;color:#fff;padding:10px 16px;border-radius:8px;text-decoration:none'>"
                        f"{'Review and approve' if approval else 'Open Career Agent'}</a></p>"
                        "<p style='color:#94a3b8;font-size:12px'>Opening this link never approves anything by itself. You confirm inside the app.</p></div>")
                boto3.client("ses", region_name=cfg().region).send_email(
                    Source=cfg().ses_sender, Destination={"ToAddresses": [to]},
                    Message={"Subject": {"Data": subject[:120]}, "Body": {"Text": {"Data": f"{text}\n\n{link}"}, "Html": {"Data": html}}})
                self._mark(uid, dedupe, "email", "delivered")
                results["email"] = "delivered"
            except Exception as exc:
                self._mark(uid, dedupe, "email", "failed", str(exc))
                results["email"] = "failed"
                log(logger, "notify.email_failed", error=str(exc)[:200])

        chat_id = settings.get("telegram_chat_id")
        if chat_id and telegram_token() and self._claim(uid, dedupe, "telegram"):
            try:
                payload: dict[str, Any] = {"chat_id": chat_id, "text": f"{subject}\n\n{text}"}
                buttons = [[{"text": "Open review", "url": link}]] if link.startswith("https://") else []
                if approval and app and app.get("packet_hash"):
                    token = self.action_token(uid, app, chat_id)
                    buttons.insert(0, [{"text": "Approve this exact packet", "callback_data": f"ap:{token}"}])
                if buttons:
                    payload["reply_markup"] = {"inline_keyboard": buttons}
                telegram_call("sendMessage", payload)
                self._mark(uid, dedupe, "telegram", "delivered")
                results["telegram"] = "delivered"
            except Exception as exc:
                self._mark(uid, dedupe, "telegram", "failed", str(exc))
                results["telegram"] = "failed"
        self.store.transact([self.wf.event_put(uid, "notification.delivered", {"kind": msg["kind"], "channels": results}, msg.get("app_id"))])
        return results


def _esc(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


__all__ = ["Notifier", "telegram_call", "telegram_token", "Put", "urllib"]
