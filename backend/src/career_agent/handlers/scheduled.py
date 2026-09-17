"""EventBridge Scheduler targets: source monitor (5 min), outbox repair, reminders, judge-session cleanup."""

from __future__ import annotations

import time
from typing import Any

from ..config import settings as cfg
from ..util import get_logger, log
from .common import services
from .relay import repair

logger = get_logger("scheduled")


def handler(event: dict, context: Any) -> dict:
    task = (event or {}).get("task", "monitor")
    svc = services()
    out: dict[str, Any] = {"task": task}
    if task == "monitor":
        out["monitor"] = svc.run_monitor()
        out["reminders"] = svc.due_reminders()
        out["repaired"] = repair()
    elif task == "cleanup":
        out["judges_removed"] = cleanup_judges(svc)
    log(logger, "scheduled.done", **{k: v for k, v in out.items() if k != "monitor"})
    return out


def cleanup_judges(svc) -> int:
    import boto3

    idp = boto3.client("cognito-idp")
    cutoff = svc.wf.clock.iso(time.time() - 24 * 3600)
    rows = svc.store.query("JUDGE#accounts", "", index="gsi1", limit=200, sk_lte=cutoff)
    removed = 0
    for r in rows:
        uid = r["pk"].split("#", 1)[1]
        try:
            idp.admin_delete_user(UserPoolId=cfg().user_pool_id, Username=r["username"])
        except idp.exceptions.UserNotFoundException:
            pass
        svc.delete_account_data(uid)
        removed += 1
    return removed
