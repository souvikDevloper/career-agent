"""Submission gate, invoked synchronously (Lambda Invoke) by the browser worker.

The browser worker holds no business rules and no DynamoDB permissions: all
authorization, quota reservation, lease/fencing and outcome recording happen here.
"""

from __future__ import annotations

from typing import Any

from ..config import settings as cfg
from ..sources.portal import parse_form
from ..util import get_logger, log
from ..workflow import Principal, WorkflowError
from .common import services

logger = get_logger("gate")


def handler(event: dict, context: Any) -> dict:
    svc = services()
    op = event.get("op")
    uid = event["user_id"]
    app_id = event["app_id"]
    attempt_id = event["attempt_id"]
    try:
        if op == "begin":
            res = svc.wf.gate_begin(Principal(uid, svc.is_judge(uid)), app_id, attempt_id, event["packet_hash"])
            if res["action"] == "proceed":
                packet = res["packet"]
                body = packet["body"]
                resume_url = None
                if body.get("resume_key"):
                    resume_url = svc.s3.generate_presigned_url("get_object", Params={"Bucket": cfg().bucket, "Key": body["resume_key"]},
                                                               ExpiresIn=300)
                return {"action": "proceed", "fencing": res["attempt"]["fencing"], "target": body["target"],
                        "answers": body["answers"], "resume_url": resume_url, "fields": packet.get("fields", []),
                        "evidence_prefix": f"evidence/{uid}/{app_id}/{attempt_id}"}
            if res["action"] == "reconcile":
                svc.reconcile(uid, app_id, (res.get("attempt") or {}).get("attempt_id", attempt_id))
            return {k: v for k, v in res.items() if k in ("action", "reason", "decision", "retry_later")}
        if op == "dispatch":
            signature = parse_form(event.get("form_html", ""))["signature"]
            return svc.wf.gate_dispatch(uid, app_id, attempt_id, int(event["fencing"]), signature)
        if op == "complete":
            return svc.wf.gate_complete(uid, app_id, attempt_id, event["outcome"], receipt=event.get("receipt"),
                                        reason=event.get("reason"), evidence_key=event.get("evidence_key"))
        return {"action": "error", "reason": "unknown op"}
    except WorkflowError as exc:
        log(logger, "gate.workflow_error", op=op, code=exc.code, detail=str(exc))
        return {"action": "error", "reason": str(exc), "code": exc.code}
