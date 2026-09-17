"""SQS notification-queue consumer."""

from __future__ import annotations

import json
from typing import Any

from ..notify import Notifier
from ..util import get_logger, log, sha256
from .common import services

logger = get_logger("notifier")


def handler(event: dict, context: Any) -> dict:
    failures = []
    n = Notifier(services())
    for rec in event.get("Records", []):
        try:
            msg = json.loads(rec["body"])
            dedupe = sha256(msg)[:40]
            res = n.deliver(msg, dedupe)
            log(logger, "notify.done", kind=msg.get("kind"), channels=res)
        except Exception as exc:
            log(logger, "notify.error", error=str(exc)[:300])
            failures.append({"itemIdentifier": rec["messageId"]})
    return {"batchItemFailures": failures}
