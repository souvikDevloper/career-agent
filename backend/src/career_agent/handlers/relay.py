"""Outbox relay: DynamoDB Streams -> SQS. A scheduled repair re-sends anything the stream missed."""

from __future__ import annotations

import json
import os
from typing import Any

from boto3.dynamodb.types import TypeDeserializer

from ..store import C, Update, from_dynamo
from ..util import get_logger, log
from .common import services

logger = get_logger("relay")
_sqs = None
QUEUES = {"work": "WORK_QUEUE_URL", "submit": "SUBMIT_QUEUE_URL", "notify": "NOTIFY_QUEUE_URL"}


def sqs():
    global _sqs
    if _sqs is None:
        import boto3

        _sqs = boto3.client("sqs")
    return _sqs


def dispatch(item: dict) -> bool:
    if item.get("status") != "pending":
        return False
    url = os.environ[QUEUES[item["queue"]]]
    params: dict[str, Any] = {"QueueUrl": url, "MessageBody": json.dumps(item["message"], default=str)}
    if url.endswith(".fifo"):
        params["MessageGroupId"] = item.get("group") or "default"
        params["MessageDeduplicationId"] = item["pk"].split("#", 1)[1][:128]
    sqs().send_message(**params)
    svc = services()
    try:
        svc.store.update(Update(item["pk"], item["sk"], set={"status": "dispatched", "dispatched_at": svc.wf.clock.iso()},
                                remove=["gsi1pk", "gsi1sk"], add={"attempts": 1}, condition=C("status", "eq", "pending")))
    except Exception as exc:
        if type(exc).__name__ != "ConditionFailed":
            raise
    return True


def handler(event: dict, context: Any) -> dict:
    des = TypeDeserializer()
    failures = []
    for rec in event.get("Records", []):
        try:
            image = rec.get("dynamodb", {}).get("NewImage")
            if not image or rec.get("eventName") not in ("INSERT",):
                continue
            item = from_dynamo({k: des.deserialize(v) for k, v in image.items()})
            if item.get("entity") != "outbox":
                continue
            dispatch(item)
            log(logger, "outbox.dispatched", queue=item["queue"], kind=item["message"].get("kind"))
        except Exception as exc:
            log(logger, "outbox.error", error=str(exc)[:300])
            failures.append({"itemIdentifier": rec["dynamodb"]["SequenceNumber"]})
    return {"batchItemFailures": failures}


def repair() -> int:
    """Re-dispatch outbox items still pending after 60 seconds (missed stream delivery)."""
    svc = services()
    cutoff = svc.wf.clock.iso(svc.wf.clock.now() - 60)
    rows = svc.store.query("OUTBOX#pending", "", index="gsi1", limit=200, sk_lte=cutoff)
    n = 0
    for r in rows:
        if dispatch(r):
            n += 1
    if n:
        log(logger, "outbox.repaired", count=n)
    return n
