"""Regression tests for cutting new user work away from the legacy backlog."""

import json

from career_agent.handlers import queue_router


class FakeSQS:
    def __init__(self):
        self.sent = []

    def send_message(self, **kwargs):
        self.sent.append(kwargs)
        return {"MessageId": "forwarded"}


def test_legacy_watch_message_goes_to_watch_queue(monkeypatch):
    fake = FakeSQS()
    monkeypatch.setenv("WATCH_QUEUE_URL", "https://sqs.us-east-1.amazonaws.com/123/astra-watch")
    monkeypatch.setenv("INTERACTIVE_QUEUE_URL", "https://sqs.us-east-1.amazonaws.com/123/interactive")
    monkeypatch.setattr(queue_router, "_sqs", fake)

    msg = {"kind": "check_watch", "user_id": "u1", "watch_id": "w_1"}
    result = queue_router.handler(
        {"Records": [{"messageId": "old-1", "body": json.dumps(msg)}]},
        None,
    )

    assert result == {"batchItemFailures": []}
    assert fake.sent == [{
        "QueueUrl": "https://sqs.us-east-1.amazonaws.com/123/astra-watch",
        "MessageBody": json.dumps(msg),
    }]


def test_legacy_interactive_message_goes_to_fresh_interactive_queue(monkeypatch):
    fake = FakeSQS()
    monkeypatch.setenv("WATCH_QUEUE_URL", "https://sqs.us-east-1.amazonaws.com/123/astra-watch")
    monkeypatch.setenv("INTERACTIVE_QUEUE_URL", "https://sqs.us-east-1.amazonaws.com/123/interactive")
    monkeypatch.setattr(queue_router, "_sqs", fake)

    msg = {"kind": "search", "user_id": "u1", "op_id": "op_1", "payload": {"keywords": "backend intern"}}
    result = queue_router.handler(
        {"Records": [{"messageId": "old-2", "body": json.dumps(msg)}]},
        None,
    )

    assert result == {"batchItemFailures": []}
    assert fake.sent == [{
        "QueueUrl": "https://sqs.us-east-1.amazonaws.com/123/interactive",
        "MessageBody": json.dumps(msg),
    }]


def test_router_retries_only_failed_record(monkeypatch):
    class FailingSQS:
        def send_message(self, **kwargs):
            raise RuntimeError("temporary send failure")

    monkeypatch.setenv("INTERACTIVE_QUEUE_URL", "https://sqs.us-east-1.amazonaws.com/123/interactive")
    monkeypatch.setattr(queue_router, "_sqs", FailingSQS())

    result = queue_router.handler(
        {"Records": [{"messageId": "old-3", "body": json.dumps({"kind": "resume"})}]},
        None,
    )

    assert result == {"batchItemFailures": [{"itemIdentifier": "old-3"}]}
