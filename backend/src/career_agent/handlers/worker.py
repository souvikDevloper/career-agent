"""SQS work-queue consumer: agent commands, resume parsing, search, matching, preparation, reconciliation.

Delivery is at-least-once; every handler is idempotent (operations, outbox keys, conditional writes).
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

from .. import agent, discovery
from ..util import get_logger, log
from ..workflow import WorkflowError
from .common import services

logger = get_logger("worker")

WATCH_KINDS = {"check_watch", "match_new_job", "monitor_now"}
_sqs = None


def sqs():
    global _sqs
    if _sqs is None:
        import boto3

        _sqs = boto3.client("sqs")
    return _sqs


def _watch_queue_record(record: dict) -> bool:
    url = os.environ.get("WATCH_QUEUE_URL", "")
    arn = record.get("eventSourceARN") or record.get("eventSourceArn") or ""
    return bool(url and arn and arn.rsplit(":", 1)[-1] == url.rstrip("/").rsplit("/", 1)[-1])


def _forward_legacy_watch(record: dict, msg: dict) -> bool:
    """Move pre-deploy Astra backlog out of WorkQueue without dropping work."""
    if msg.get("kind") not in WATCH_KINDS or _watch_queue_record(record):
        return False
    url = os.environ.get("WATCH_QUEUE_URL")
    if not url:
        return False
    sqs().send_message(QueueUrl=url, MessageBody=json.dumps(msg, default=str))
    log(logger, "work.watch_migrated", kind=msg.get("kind"), message_id=record.get("messageId"))
    return True


def handler(event: dict, context: Any) -> dict:
    failures = []
    for record in event.get("Records", []):
        try:
            msg = json.loads(record["body"])
            if _forward_legacy_watch(record, msg):
                continue
            process(msg)
        except Exception as exc:
            log(logger, "work.failed", error=type(exc).__name__, detail=str(exc)[:400], message_id=record.get("messageId"))
            failures.append({"itemIdentifier": record["messageId"]})
    return {"batchItemFailures": failures}




def _model_unavailable(exc: Exception) -> bool:
    from ..llm import is_unavailable

    return is_unavailable(exc)


def _finish_op_error(uid: str, op_id: str | None, exc: Exception) -> None:
    if not op_id:
        return
    if isinstance(exc, WorkflowError):
        msg = str(exc)
    elif _model_unavailable(exc):
        # Strands calls ConverseStream on its own client, so a blocked model arrives as a
        # raw botocore error rather than llm.ModelUnavailable. Saying "try again" for a
        # model that cannot answer sends people in circles.
        msg = ("The AI model is unavailable right now, so I could not answer. "
               "Searching and scoring still work without it.")
    else:
        msg = "This request could not be completed. Please try again."
    services().wf.op_progress(uid, op_id, status="failed", message=msg, final={"error": msg})


def process(msg: dict) -> None:
    svc = services()
    kind = msg.get("kind")
    uid = msg.get("user_id")
    op_id = msg.get("op_id")
    cid = msg.get("correlation_id")
    log(logger, "work.start", kind=kind, user=uid, op=op_id, correlation_id=cid)
    if op_id:
        op = svc.store.get(f"USER#{uid}", f"OP#{op_id}")
        if not op or op.get("status") in ("succeeded", "failed"):
            return  # duplicate delivery or deleted account
    try:
        if kind == "chat":
            run_chat(svc, uid, op_id, msg["payload"]["text"], msg["payload"].get("source", "chat"), cid)
        elif kind == "resume":
            svc.process_resume(uid, op_id, msg["payload"]["resume_id"], cid)
        elif kind == "search":
            cards = svc.search(uid, op_id, msg["payload"].get("keywords", ""), correlation_id=cid)
            svc.wf.op_progress(uid, op_id, status="succeeded", message=f"Scored {len(cards)} jobs", final={"count": len(cards)})
        elif kind == "resume_improve":
            data = svc.resume_improvements(uid, msg["payload"].get("job_key"), cid)
            svc.wf.op_progress(uid, op_id, status="succeeded", final=data)
        elif kind == "interview_questions":
            data = svc.interview_questions(uid, msg["payload"]["app_id"], cid)
            svc.wf.op_progress(uid, op_id, status="succeeded", final=data)
        elif kind == "interview_feedback":
            p = msg["payload"]
            data = svc.interview_feedback(uid, p["app_id"], p["question"], p["answer"], cid)
            svc.wf.op_progress(uid, op_id, status="succeeded", final=data)
        elif kind == "prepare":
            try:
                svc.prepare(uid, msg["app_id"], cid, prepare_request_id=msg.get("prepare_request_id"))
            except WorkflowError as exc:
                if exc.code in ("invalid_state", "invalid_transition", "not_found"):
                    log(logger, "work.prepare_skipped", reason=str(exc))
                    return
                app = svc.wf.get_app(uid, msg["app_id"])
                if app["action_state"] == "Preparing" and (
                    not msg.get("prepare_request_id") or app.get("prepare_request_id") == msg["prepare_request_id"]
                ):
                    svc.store.transact([
                        svc.wf._transition(app, "KnownFailure", {"last_error": str(exc)[:300]}),
                        svc.wf.event_put(uid, "application.preparation_failed",
                                         {"reason": str(exc)[:300]}, app["app_id"]),
                    ])
                return
            except Exception as exc:
                # Preparation used to fail only in the queue, leaving the UI on
                # "Preparing" forever. Record the failure before allowing SQS to
                # retry so the user sees a recoverable state and can press retry.
                try:
                    app = svc.wf.get_app(uid, msg["app_id"])
                    if app["action_state"] == "Preparing" and (
                        not msg.get("prepare_request_id") or app.get("prepare_request_id") == msg["prepare_request_id"]
                    ):
                        svc.store.transact([
                            svc.wf._transition(app, "KnownFailure",
                                               {"last_error": "Could not prepare this employer form. Retry preparation."}),
                            svc.wf.event_put(uid, "application.preparation_failed",
                                             {"reason": type(exc).__name__}, app["app_id"]),
                        ])
                except Exception as record_exc:
                    log(logger, "work.prepare_failure_record_failed", reason=type(record_exc).__name__)
                raise
        elif kind == "check_watch":
            svc.check_watch(uid, msg["watch_id"])
        elif kind == "match_new_job":
            svc.match_new_job(uid, msg["job_key"], msg.get("watch_id"), watch_revision=msg.get("watch_revision"))
        elif kind == "monitor_now":
            summary = svc.run_monitor(force=True, user_id=uid)
            svc.store.transact([svc.wf.event_put(uid, "monitor.checked", summary)])
        elif kind == "reconcile":
            svc.reconcile(uid, msg["app_id"], msg["attempt_id"])
        elif kind == "inbound_message":
            svc.inbound_message(msg["message"])
        else:
            log(logger, "work.unknown_kind", kind=kind)
    except Exception as exc:
        _finish_op_error(uid, op_id, exc)
        if isinstance(exc, WorkflowError):
            return  # user-facing failure recorded; do not retry
        raise



_AMAZON_SEARCH_VERBS = {"find", "search", "show", "get", "check", "look"}
_AMAZON_JOB_NOUNS = {"job", "jobs", "role", "roles", "opening", "openings", "position", "positions"}
_AMAZON_SECOND_STEPS = {
    "apply", "applying", "application", "applications", "prepare", "preparing",
    "submit", "submitting", "approve", "send",
    "watch", "monitor", "repeat", "every", "notify", "remember", "save",
}


def _known_place(text: str) -> str:
    """Return a place spelling already known by discovery, or an empty string."""
    lower = (text or "").lower()
    known = set(discovery._PLACE_ALIASES)
    for forms in discovery._PLACE_ALIASES.values():
        known.update(forms)
    for region, members in discovery._REGIONS.items():
        known.add(region)
        known.update(members)
    for place in sorted(known, key=lambda p: (len(p.split()), len(p)), reverse=True):
        if re.search(r"\b" + re.escape(place) + r"\b", lower):
            return place
    return ""


def _fallback_amazon_filters(text: str) -> dict[str, str] | None:
    """Compatibility wrapper for callers specifically testing the Amazon path."""
    filters = _fallback_search_filters(text)
    return filters if filters and filters["company"] == "Amazon" else None


def _fallback_search_filters(text: str) -> dict[str, str] | None:
    """Parse a simple, explicit search for one supported employer.

    This is a recovery path, not the normal chat path. Multi-step instructions
    stay with the agent so a request such as "find ... and apply" cannot lose its
    second action. Informational Amazon questions are not searches either.
    """
    tokens = re.findall(r"[a-z0-9+#]+", (text or "").lower())
    if not tokens:
        return None
    employers = {"amazon": "Amazon", "google": "Google", "microsoft": "Microsoft"}
    for source in discovery.all_sources():
        if source.startswith(("greenhouse:", "lever:", "ashby:", "workday:")):
            name = source.split(":", 2)[1].lower()
            employers[name] = name.title()
    named = [name for name in employers if re.search(r"\b" + re.escape(name) + r"\b", text, re.I)]
    if len(named) != 1:
        return None
    company = named[0]

    # The first meaningful word must be an imperative search verb. This rejects
    # questions such as "what does Amazon look for in an SDE 1?"
    conversational = {"please", "can", "could", "would", "you", "hey", "hi", "hello", "bro", "brother"}
    first = next((t for t in tokens if t not in conversational), "")
    if first not in _AMAZON_SEARCH_VERBS:
        return None
    if not any(t in _AMAZON_JOB_NOUNS | {"swe", "sde", "engineer", "internship", "intern"} for t in tokens):
        return None
    if any(t in _AMAZON_SECOND_STEPS for t in tokens):
        return None

    location = _known_place(text)
    location_tokens = set(re.findall(r"[a-z0-9]+", location))
    role_tokens = [
        token for token in tokens
        if token not in company.split()
        and token not in discovery.STOP
        and token not in _AMAZON_JOB_NOUNS
        and token not in location_tokens
        and token not in conversational | _AMAZON_SEARCH_VERBS | {"up"}
    ]
    return {"company": employers[company], "role": " ".join(role_tokens), "location": location}


def _direct_search_reply(cards: list[dict], filters: dict[str, str], stats: dict) -> str:
    role = filters.get("role") or "jobs"
    location = filters.get("location")
    target = f"{filters.get('company') or 'Requested'} {role}" + (f" in {location}" if location else "")
    if not cards:
        context = agent.ToolContext("", "", "", "chat", "", None,
                                    actions=[{"type": "search", "count": 0}],
                                    search_result={"results": [], "searched": {**stats, "filters": filters}})
        return agent._ground_search_reply(context, "")

    preview = []
    for card in cards[:3]:
        job = card.get("job") or {}
        where = job.get("location") or "location not listed"
        preview.append(f"{job.get('title') or 'Untitled role'} — {where} ({card.get('score', 0)}/100)")
    more = f" +{len(cards) - 3} more." if len(cards) > 3 else ""
    freshness = "Cached results: " if stats.get("freshness") in ("cached", "stale_fallback") else ""
    return freshness + f"Found {len(cards)} matches for {target}. " + "; ".join(preview) + more


def _finish_direct_search(svc, uid: str, op_id: str, filters: dict[str, str], cid: str | None) -> None:
    stats: dict = {}
    svc.wf.op_progress(uid, op_id, status="running", message=f"Searching {filters.get('company', 'employer')} directly")
    cards = svc.search(uid, op_id, correlation_id=cid, stats=stats, filters=filters)
    reply = _direct_search_reply(cards, filters, stats)
    actions = [{"type": "search", "count": len(cards), "filters": filters}]
    ts = svc.wf.clock.iso()
    svc.store.put({"pk": f"USER#{uid}", "sk": f"CHAT#{ts}#{op_id}#a", "entity": "chat", "role": "assistant",
                   "text": reply, "op_id": op_id, "at": ts, "actions": actions, "runtime": "direct-search-fallback"})
    svc.wf.op_progress(uid, op_id, status="succeeded",
                       final={"reply": reply, "actions": actions, "runtime": "direct-search-fallback"})


def run_chat(svc, uid: str, op_id: str, text: str, source: str, cid: str | None) -> None:
    from ..util import new_id

    fallback = _fallback_search_filters(text)
    svc.wf.op_progress(uid, op_id, status="running", message="Thinking")
    rows = svc.store.query(f"USER#{uid}", "CHAT#", limit=13, newest_first=True)
    history = []
    for r in reversed(rows):
        if r.get("op_id") == op_id:
            continue
        role = "assistant" if r["role"] == "assistant" else "user"
        if history and history[-1]["role"] == role:
            history[-1]["content"][0]["text"] += "\n" + r["text"]
        else:
            history.append({"role": role, "content": [{"text": r["text"][:1500]}]})
    while history and history[0]["role"] != "user":
        history.pop(0)
    if history and history[-1]["role"] == "user":
        history.pop()
    ctx = agent.ToolContext(user_id=uid, op_id=op_id, user_text=text, channel=source, correlation_id=cid or new_id(),
                            services=svc, is_judge=svc.is_judge(uid))
    try:
        svc._reserve_model(uid)
        reply, runtime = agent.run(ctx, history)
    except Exception as exc:
        # A simple employer search can still succeed when the chat model is down or
        # its allowance is exhausted. Only recover when no action has happened;
        # otherwise retrying the intent could duplicate a side effect.
        if fallback and not ctx.actions:
            log(logger, "chat.search_fallback", company=fallback["company"], error=type(exc).__name__,
                detail=str(exc)[:160], correlation_id=cid)
            _finish_direct_search(svc, uid, op_id, fallback, cid)
            return
        raise

    # A model can also end the turn without calling search_jobs. For this one
    # narrow, explicit search command, an action-free answer is not completion:
    # run the deterministic search instead. Multi-step requests never qualify.
    if fallback and not ctx.actions:
        log(logger, "chat.search_fallback", company=fallback["company"], reason="no_search_action", correlation_id=cid)
        _finish_direct_search(svc, uid, op_id, fallback, cid)
        return

    ts = svc.wf.clock.iso()
    svc.store.put({"pk": f"USER#{uid}", "sk": f"CHAT#{ts}#{op_id}#a", "entity": "chat", "role": "assistant", "text": reply,
                   "op_id": op_id, "at": ts, "actions": ctx.actions, "runtime": runtime})
    svc.wf.op_progress(uid, op_id, status="succeeded", final={"reply": reply, "actions": ctx.actions, "runtime": runtime})
