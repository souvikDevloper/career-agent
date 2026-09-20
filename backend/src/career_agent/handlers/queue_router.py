"""One-time compatibility drain for the pre-isolation WorkQueue.

Messages already delivered to the legacy queue cannot be reprioritized in place.
This handler performs only classification + SQS forwarding, so the old backlog can
be drained quickly without executing expensive resume/search/watch work there.
"""

from __future__ import annotations

import json
import os
from typing import Any

from ..util import get_logger, log

logger = get_logger("queue_router")
_sqs = None

WATCH_KINDS = {"check_watch", "match_new_job", "monitor_now"}


def sqs():
    global _sqs
    if _sqs is None:
        import boto3

        _sqs = boto3.client("sqs")
    return _sqs


def destination(msg: dict) -> str:
    env = "WATCH_QUEUE_URL" if msg.get("kind") in WATCH_KINDS else "INTERACTIVE_QUEUE_URL"
    url = os.environ.get(env)
    if not url:
        raise RuntimeError(f"{env} is not configured")
    return url


def handler(event: dict, context: Any) -> dict:
    failures = []
    for record in event.get("Records", []):
        try:
            msg = json.loads(record["body"])
            url = destination(msg)
            sqs().send_message(QueueUrl=url, MessageBody=json.dumps(msg, default=str))
            log(
                logger,
                "legacy_work.forwarded",
                kind=msg.get("kind"),
                target="watch" if msg.get("kind") in WATCH_KINDS else "interactive",
                message_id=record.get("messageId"),
            )
        except Exception as exc:
            log(
                logger,
                "legacy_work.forward_failed",
                error=type(exc).__name__,
                detail=str(exc)[:300],
                message_id=record.get("messageId"),
            )
            failures.append({"itemIdentifier": record["messageId"]})
    return {"batchItemFailures": failures}
