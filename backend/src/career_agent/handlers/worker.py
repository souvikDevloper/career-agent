"""SQS work-queue consumer: agent commands, resume parsing, search, matching, preparation, reconciliation.

Delivery is at-least-once; every handler is idempotent (operations, outbox keys, conditional writes).
"""

from __future__ import annotations

import json
from typing import Any

from .. import agent
from ..util import get_logger, log
from ..workflow import WorkflowError
from .common import services

logger = get_logger("worker")


def handler(event: dict, context: Any) -> dict:
    failures = []
    for record in event.get("Records", []):
        try:
            process(json.loads(record["body"]))
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
                svc.prepare(uid, msg["app_id"], cid)
            except WorkflowError as exc:
                if exc.code in ("invalid_state", "invalid_transition", "not_found"):
                    log(logger, "work.prepare_skipped", reason=str(exc))
                    return
                raise
        elif kind == "match_new_job":
            svc.match_new_job(uid, msg["job_key"], msg.get("watch_id"))
        elif kind == "monitor_now":
            summary = svc.run_monitor(force=True)
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


def run_chat(svc, uid: str, op_id: str, text: str, source: str, cid: str | None) -> None:
    from ..util import new_id

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
    svc._reserve_model(uid)
    ctx = agent.ToolContext(user_id=uid, op_id=op_id, user_text=text, channel=source, correlation_id=cid or new_id(),
                            services=svc, is_judge=svc.is_judge(uid))
    reply, runtime = agent.run(ctx, history)
    ts = svc.wf.clock.iso()
    svc.store.put({"pk": f"USER#{uid}", "sk": f"CHAT#{ts}#{op_id}#a", "entity": "chat", "role": "assistant", "text": reply,
                   "op_id": op_id, "at": ts, "actions": ctx.actions, "runtime": runtime})
    svc.wf.op_progress(uid, op_id, status="succeeded", final={"reply": reply, "actions": ctx.actions, "runtime": runtime})
